import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:airway/features/booking/data/booking_api.dart';

class BookingScheduleResult {
  final DateTime scheduledAt;
  final DateTime? dropScheduledAt;
  final Map<String, dynamic> categoryAnswers;

  const BookingScheduleResult({
    required this.scheduledAt,
    this.dropScheduledAt,
    this.categoryAnswers = const {},
  });
}

/// Two-page date/time picker. Availability always comes from the booking API;
/// the client never treats a locally generated slot as confirmed.
class BookingScheduleScreen extends StatefulWidget {
  final int serviceId;
  final int addressId;
  final int? variantId;
  final int quantity;
  final String bookingMode;
  final Map<String, dynamic> categoryAnswers;
  final int? cartItemId;
  final DateTime? initialDate;
  final TimeOfDay? initialTime;
  final TimeOfDay? initialDropTime;

  const BookingScheduleScreen({
    super.key,
    required this.serviceId,
    required this.addressId,
    this.variantId,
    this.quantity = 1,
    this.bookingMode = 'scheduled',
    this.categoryAnswers = const {},
    this.cartItemId,
    this.initialDate,
    this.initialTime,
    this.initialDropTime,
  });

  @override
  State<BookingScheduleScreen> createState() => _BookingScheduleScreenState();
}

class _BookingScheduleScreenState extends State<BookingScheduleScreen> {
  static const _green = Color(0xFF075B43);
  static const _ink = Color(0xFF1E2923);
  static const _muted = Color(0xFF748078);
  static const _line = Color(0xFFEAE6DE);
  static const _pale = Color(0xFFEAF1EA);

  late DateTime _selectedDate;
  TimeOfDay? _selectedTime;
  TimeOfDay _dropTime = const TimeOfDay(hour: 17, minute: 0);
  List<TimeOfDay> _availableSlots = [];
  bool _checking = false;
  String? _slotError;
  bool _femalePreferenceUnavailable = false;
  bool _updatingPreference = false;
  late Map<String, dynamic> _categoryAnswers;
  int _page = 0;

  bool get _isPickupDrop => widget.bookingMode == 'pickup_drop';

  @override
  void initState() {
    super.initState();
    final tomorrow = DateTime.now().add(const Duration(days: 1));
    final initial = widget.initialDate ?? tomorrow;
    _selectedDate = DateTime(initial.year, initial.month, initial.day);
    _selectedTime = widget.initialTime;
    _dropTime = widget.initialDropTime ?? const TimeOfDay(hour: 17, minute: 0);
    _categoryAnswers = Map<String, dynamic>.from(widget.categoryAnswers);
  }

  DateTime _at(TimeOfDay time) => DateTime(
        _selectedDate.year,
        _selectedDate.month,
        _selectedDate.day,
        time.hour,
        time.minute,
      );

  Future<void> _continueToTime() async {
    setState(() {
      _page = 1;
      _selectedTime = null;
      _slotError = null;
    });
    await _loadSlots();
  }

  Future<void> _loadSlots() async {
    setState(() {
      _checking = true;
      _slotError = null;
      _femalePreferenceUnavailable = false;
      _availableSlots = [];
    });

    final candidates = <TimeOfDay>[];
    for (var hour = 9; hour <= 18; hour++) {
      final slot = TimeOfDay(hour: hour, minute: 0);
      final startsAt = _at(slot);
      if (!startsAt.isAfter(DateTime.now())) continue;
      if (_isPickupDrop && !_at(_dropTime).isAfter(startsAt)) continue;
      candidates.add(slot);
    }

    try {
      final results = await Future.wait(candidates.map((slot) {
        return BookingApi.checkSlotAvailability(
          serviceId: widget.serviceId,
          scheduledAt: _at(slot),
          dropScheduledAt: _isPickupDrop ? _at(_dropTime) : null,
          variantId: widget.variantId,
          addressId: widget.addressId,
          quantity: widget.quantity,
          bookingMode: widget.bookingMode,
          categoryAnswers: _categoryAnswers,
        );
      }));
      if (!mounted) return;
      final available = <TimeOfDay>[
        for (var i = 0; i < candidates.length; i++)
          if (results[i]['available'] == true) candidates[i],
      ];
      setState(() {
        _availableSlots = available;
        _checking = false;
        if (available.isEmpty) {
          Map<String, dynamic>? preferenceFailure;
          for (final result in results) {
            if (result['reason'] == 'female_professional_unavailable') {
              preferenceFailure = result;
              break;
            }
          }
          _femalePreferenceUnavailable = preferenceFailure != null;
          _slotError = preferenceFailure?['message']?.toString() ??
              'No available slots for this date. Choose another date.';
        } else if (_selectedTime != null &&
            !available.any((slot) =>
                slot.hour == _selectedTime!.hour &&
                slot.minute == _selectedTime!.minute)) {
          _selectedTime = null;
        }
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _checking = false;
        _slotError = 'Could not check availability. Please retry. $e';
      });
    }
  }

  Future<void> _changeToNoPreference() async {
    if (widget.cartItemId == null || _updatingPreference) return;
    setState(() => _updatingPreference = true);
    try {
      final answers = Map<String, dynamic>.from(_categoryAnswers)
        ..['professional_preference'] = 'any';
      await BookingApi.updateCartItem(
        itemId: widget.cartItemId!,
        data: {'category_answers': answers},
      );
      if (!mounted) return;
      _categoryAnswers = answers;
      setState(() {
        _femalePreferenceUnavailable = false;
        _slotError = null;
        _selectedTime = null;
        _updatingPreference = false;
      });
      await _loadSlots();
    } catch (e) {
      if (!mounted) return;
      setState(() => _updatingPreference = false);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Could not update preference: $e')),
      );
    }
  }

  Future<void> _changeDropTime() async {
    final value = await showTimePicker(
      context: context,
      initialTime: _dropTime,
    );
    if (value == null || !mounted) return;
    setState(() {
      _dropTime = value;
      _selectedTime = null;
    });
    await _loadSlots();
  }

  void _confirm() {
    final time = _selectedTime;
    if (time == null) return;
    final start = _at(time);
    final drop = _isPickupDrop ? _at(_dropTime) : null;
    if (!start.isAfter(DateTime.now())) {
      setState(() => _slotError = 'Please choose a future time.');
      return;
    }
    if (drop != null && !drop.isAfter(start)) {
      setState(() => _slotError = 'Drop-off time must be after pickup time.');
      return;
    }
    Navigator.of(context).pop(
      BookingScheduleResult(
        scheduledAt: start,
        dropScheduledAt: drop,
        categoryAnswers: Map<String, dynamic>.from(_categoryAnswers),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final dateLabel = DateFormat('EEEE, d MMMM yyyy').format(_selectedDate);
    return Scaffold(
      backgroundColor: Colors.white,
      appBar: AppBar(
        backgroundColor: Colors.white,
        title: Text(_page == 0 ? 'Select Date' : 'Select Time Slot'),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_rounded),
          onPressed: () {
            if (_page == 1) {
              setState(() {
                _page = 0;
                _slotError = null;
              });
            } else {
              Navigator.of(context).pop();
            }
          },
        ),
      ),
      body: SafeArea(
        child: Column(
          children: [
            Expanded(
              child: ListView(
                padding: const EdgeInsets.fromLTRB(20, 18, 20, 24),
                children: [
                  Text(
                    _page == 0
                        ? 'When would you like us to come?'
                        : 'What time works for you?',
                    style: const TextStyle(
                      fontSize: 24,
                      fontWeight: FontWeight.w900,
                      color: _ink,
                    ),
                  ),
                  const SizedBox(height: 7),
                  Text(
                    _page == 0
                        ? 'Choose a date for your service.'
                        : 'Only slots confirmed as available by AIRway are shown.',
                    style: const TextStyle(color: _muted, height: 1.4),
                  ),
                  const SizedBox(height: 22),
                  if (_page == 0) ...[
                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(18),
                        border: Border.all(color: _line),
                      ),
                      child: CalendarDatePicker(
                        initialDate: _selectedDate,
                        firstDate: DateTime(
                          DateTime.now().year,
                          DateTime.now().month,
                          DateTime.now().day,
                        ),
                        lastDate: DateTime.now().add(const Duration(days: 90)),
                        onDateChanged: (date) => setState(() {
                          _selectedDate = DateTime(date.year, date.month, date.day);
                        }),
                      ),
                    ),
                    const SizedBox(height: 16),
                    _summaryTile(Icons.calendar_month_rounded, dateLabel),
                  ] else ...[
                    _summaryTile(Icons.calendar_month_rounded, dateLabel),
                    if (_isPickupDrop) ...[
                      const SizedBox(height: 12),
                      OutlinedButton.icon(
                        onPressed: _checking ? null : _changeDropTime,
                        icon: const Icon(Icons.flag_outlined),
                        label: Text('Drop-off time: ${_dropTime.format(context)}'),
                      ),
                    ],
                    const SizedBox(height: 22),
                    const Text(
                      'Available Time Slots',
                      style: TextStyle(
                        color: _ink,
                        fontSize: 15,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                    const SizedBox(height: 12),
                    if (_checking)
                      const Padding(
                        padding: EdgeInsets.all(28),
                        child: Center(
                          child: CircularProgressIndicator(color: _green),
                        ),
                      )
                    else if (_availableSlots.isEmpty)
                      Container(
                        padding: const EdgeInsets.all(16),
                        decoration: BoxDecoration(
                          color: const Color(0xFFFFF5E9),
                          borderRadius: BorderRadius.circular(14),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              _slotError ?? 'No available slots. Please choose another date.',
                              style: const TextStyle(color: Color(0xFF80551D)),
                            ),
                            if (_femalePreferenceUnavailable) ...[
                              const SizedBox(height: 12),
                              const Text(
                                'You can also allow any eligible Beauty professional and check availability again.',
                                style: TextStyle(color: Color(0xFF80551D), fontSize: 12),
                              ),
                              const SizedBox(height: 8),
                              OutlinedButton(
                                onPressed: _updatingPreference ? null : _changeToNoPreference,
                                child: Text(_updatingPreference
                                    ? 'Updating…'
                                    : 'Change to No preference'),
                              ),
                            ],
                          ],
                        ),
                      )
                    else
                      GridView.builder(
                        shrinkWrap: true,
                        physics: const NeverScrollableScrollPhysics(),
                        itemCount: _availableSlots.length,
                        gridDelegate:
                            const SliverGridDelegateWithFixedCrossAxisCount(
                          crossAxisCount: 3,
                          mainAxisSpacing: 10,
                          crossAxisSpacing: 10,
                          childAspectRatio: 1.9,
                        ),
                        itemBuilder: (context, index) {
                          final slot = _availableSlots[index];
                          final selected = _selectedTime?.hour == slot.hour &&
                              _selectedTime?.minute == slot.minute;
                          return InkWell(
                            borderRadius: BorderRadius.circular(12),
                            onTap: () => setState(() {
                              _selectedTime = slot;
                              _slotError = null;
                            }),
                            child: Container(
                              alignment: Alignment.center,
                              decoration: BoxDecoration(
                                color: selected ? _green : Colors.white,
                                borderRadius: BorderRadius.circular(12),
                                border: Border.all(
                                  color: selected ? _green : _line,
                                  width: selected ? 2 : 1,
                                ),
                              ),
                              child: Text(
                                slot.format(context),
                                style: TextStyle(
                                  color: selected ? Colors.white : _ink,
                                  fontWeight: FontWeight.w700,
                                  fontSize: 12,
                                ),
                              ),
                            ),
                          );
                        },
                      ),
                    if (_slotError != null && _availableSlots.isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.only(top: 12),
                        child: Text(
                          _slotError!,
                          style: const TextStyle(color: Colors.redAccent),
                        ),
                      ),
                    if (!_checking && _availableSlots.isEmpty)
                      TextButton.icon(
                        onPressed: () => setState(() {
                          _page = 0;
                          _slotError = null;
                        }),
                        icon: const Icon(Icons.edit_calendar_outlined),
                        label: const Text('Choose another date'),
                      ),
                  ],
                ],
              ),
            ),
            Container(
              padding: const EdgeInsets.fromLTRB(20, 12, 20, 18),
              decoration: const BoxDecoration(
                color: Colors.white,
                border: Border(top: BorderSide(color: _line)),
              ),
              child: SizedBox(
                width: double.infinity,
                height: 52,
                child: FilledButton(
                  style: FilledButton.styleFrom(
                    backgroundColor: _green,
                    disabledBackgroundColor: _green.withValues(alpha: .35),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(28),
                    ),
                  ),
                  onPressed: _page == 0
                      ? _continueToTime
                      : (_checking || _selectedTime == null ? null : _confirm),
                  child: Text(_page == 0 ? 'Continue' : 'Confirm Time'),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _summaryTile(IconData icon, String text) => Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: _pale,
          borderRadius: BorderRadius.circular(13),
        ),
        child: Row(
          children: [
            Icon(icon, color: _green),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                text,
                style: const TextStyle(
                  color: _ink,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
          ],
        ),
      );
}
