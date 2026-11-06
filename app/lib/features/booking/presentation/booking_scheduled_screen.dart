import 'package:flutter/material.dart';
import 'package:airway/core/storage/secure_session_storage.dart';
import 'package:airway/features/catalog/data/catalog_api.dart';
import 'package:airway/features/catalog/data/catalog_models.dart';
import 'package:airway/features/booking/data/booking_api.dart';
import 'package:airway/features/booking/presentation/booking_list_screen.dart';

class _Ui {
  static const violet = Color(0xFF7861A8);
  static const ink = Color(0xFF292331);
  static const sub = Color(0xFF81788A);
  static const bg = Color(0xFFF7F3EC);
  static const line = Color(0xFFE8E0ED);
}

class BookingScheduledScreen extends StatefulWidget {
  final int serviceId;
  final String serviceTitle;

  const BookingScheduledScreen({
    super.key,
    required this.serviceId,
    required this.serviceTitle,
  });

  @override
  State<BookingScheduledScreen> createState() => _BookingScheduledScreenState();
}

class _BookingScheduledScreenState extends State<BookingScheduledScreen> {
  Service? _service;
  bool _loading = true;
  String? _error;

  // Availability state
  bool _checkingAvailability = false;
  bool _isAvailable = true;
  String? _availabilityMessage;

  // Selection state
  int? _selectedVariantId;
  List<int> _selectedAddonIds = [];
  final Map<String, dynamic> _formAnswers = {};
  int? _selectedAddressId;
  List<Map<String, dynamic>> _addresses = [];
  Map<String, dynamic>? _selectedScheduleTime;
  Map<String, dynamic>? _selectedDropTime;
  bool _isPickupDrop = false;
  final _formKey = GlobalKey<FormState>();

  // Summary state
  double _subtotal = 0;
  double _estimatedTotal = 0;

  @override
  void initState() {
    super.initState();
    _loadData();
  }

  Future<void> _loadData() async {
    setState(() {
      _loading = true;
      _error = null;
    });

    try {
      final service = await CatalogApi.getService(widget.serviceId);
      final addresses = await _loadAddresses();

      if (!mounted) return;

      setState(() {
        _service = service;
        _addresses = addresses;
        _selectedAddressId = addresses.isNotEmpty ? addresses[0]['id'] : null;
        _isPickupDrop = service.bookingMode == 'pickup_drop';
        _loading = false;

        // Auto-select first variant if exactly one exists
        if (service.variants.length == 1) {
          _selectedVariantId = service.variants[0].id;
        }

        // Set default schedule time
        final now = DateTime.now();
        final tomorrow = now.add(const Duration(days: 1));
        _selectedScheduleTime = {
          'date': tomorrow,
          'hour': now.hour < 20 ? now.hour + 1 : 10,
          'minute': 0,
        };
      });

      _checkSlotAvailability();
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString();
        _loading = false;
      });
    }
  }

  Future<List<Map<String, dynamic>>> _loadAddresses() async {
    final session = await SecureSessionStorage.readSession();
    if (session == null) return [];

    try {
      final result = await BookingApi.request('/api/v1/auth/addresses/');
      final raw = result is List ? result : (result is Map ? result['results'] : null);
      if (raw is! List) return [];
      return raw.map((e) => Map<String, dynamic>.from(e as Map)).toList();
    } catch (_) {
      return [];
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: _Ui.bg,
      appBar: AppBar(
        title: Text(widget.serviceTitle),
        backgroundColor: _Ui.bg,
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: _Ui.violet))
          : _error != null
              ? _errorWidget(_error!)
              : _service == null
                  ? _errorWidget('Service not found.')
                  : _buildBody(),
    );
  }

  Widget _buildBody() {
    final service = _service!;

    return Form(
      key: _formKey,
      child: CustomScrollView(
        slivers: [
          if (service.image?.isNotEmpty ?? false)
            _imageSliver(service.image),
          _sectionHeader('Address'),
          _addressPicker(),
          if (service.variants.length > 1) ...[
            _sectionHeader('Package'),
            _variantPicker(),
          ],
          if (service.addons.isNotEmpty) ...[
            _sectionHeader('Add-ons'),
            _addonPicker(),
          ],
          if (service.formFields.isNotEmpty) ...[
            _sectionHeader('Service Details'),
            _formFields(),
          ],
          _sectionHeader('Schedule'),
          _schedulePicker(),
          if (_isPickupDrop) ...[
            _sectionHeader('Drop Time (Optional)'),
            _dropTimePicker(),
          ],
          _sectionHeader('Booking Summary'),
          _summaryCard(),
          if (_checkingAvailability)
            const SliverToBoxAdapter(
              child: Padding(
                padding: EdgeInsets.all(20),
                child: Center(child: CircularProgressIndicator()),
              ),
            ),
          if (!_checkingAvailability && _availabilityMessage != null)
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 20),
                child: Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: _isAvailable ? Colors.green.shade50 : Colors.red.shade50,
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Row(
                    children: [
                      Icon(
                        _isAvailable ? Icons.check_circle : Icons.error,
                        color: _isAvailable ? Colors.green : Colors.red,
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          _availabilityMessage ?? '',
                          style: TextStyle(
                            color: _isAvailable ? Colors.green[800] : Colors.red[800],
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(20, 8, 20, 16),
              child: SafeArea(
                child: FilledButton(
                  onPressed: (_selectedAddressId != null && _isAvailable) ? _confirmBooking : null,
                  child: const Text('Confirm Booking'),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _imageSliver(String? imageUrl) {
    if (imageUrl == null || imageUrl.isEmpty) {
      return const SliverToBoxAdapter(child: SizedBox(height: 20));
    }
    return SliverToBoxAdapter(
      child: Container(
        height: 160,
        decoration: BoxDecoration(
          image: DecorationImage(
            image: NetworkImage(imageUrl),
            fit: BoxFit.cover,
          ),
        ),
      ),
    );
  }

  Widget _sectionHeader(String title) {
    return SliverToBoxAdapter(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 16, 20, 8),
        child: Text(
          title,
          style: const TextStyle(
            fontSize: 17,
            fontWeight: FontWeight.w800,
            color: _Ui.ink,
          ),
        ),
      ),
    );
  }

  Widget _addressPicker() {
    if (_addresses.isEmpty) {
      return const SliverToBoxAdapter(
        child: Padding(
          padding: EdgeInsets.all(20),
          child: Text(
            'No addresses saved. Please add an address first.',
            style: TextStyle(color: _Ui.sub),
          ),
        ),
      );
    }

    return SliverToBoxAdapter(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 20),
        child: Wrap(
          spacing: 12,
          runSpacing: 12,
          children: _addresses.map((addr) {
            final isSelected = addr['id'] == _selectedAddressId;
            return GestureDetector(
              onTap: () {
                setState(() => _selectedAddressId = addr['id']);
              },
              child: Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(
                    color: isSelected ? _Ui.violet : _Ui.line,
                    width: isSelected ? 2 : 1,
                  ),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Icon(
                          Icons.location_on,
                          size: 16,
                          color: isSelected ? _Ui.violet : _Ui.sub,
                        ),
                        const SizedBox(width: 6),
                        Expanded(
                          child: Text(
                            addr['label'] ?? 'Home',
                            style: TextStyle(
                              fontWeight: FontWeight.w600,
                              color: isSelected ? _Ui.violet : _Ui.ink,
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 4),
                    Text(
                      addr['full_address'] ?? '',
                      style: const TextStyle(
                        fontSize: 12,
                        color: _Ui.sub,
                      ),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                ),
              ),
            );
          }).toList(),
        ),
      ),
    );
  }

  Widget _variantPicker() {
    final service = _service!;
    return SliverToBoxAdapter(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 20),
        child: Wrap(
          spacing: 12,
          runSpacing: 12,
          children: service.variants.map((variant) {
            final isSelected = variant.id == _selectedVariantId;
            return GestureDetector(
              onTap: () {
                setState(() {
                  _selectedVariantId = variant.id;
                });
                _updateSummary();
              },
              child: Container(
                width: MediaQuery.of(context).size.width * 0.48,
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(
                    color: isSelected ? _Ui.violet : _Ui.line,
                    width: isSelected ? 2 : 1,
                  ),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      variant.title,
                      style: const TextStyle(
                        fontSize: 15,
                        fontWeight: FontWeight.w700,
                        color: _Ui.ink,
                      ),
                    ),
                    if (variant.durationMinutes != null)
                      Padding(
                        padding: const EdgeInsets.only(top: 4),
                        child: Text(
                          '${variant.durationMinutes} min',
                          style: const TextStyle(
                            fontSize: 12,
                            color: _Ui.sub,
                          ),
                        ),
                      ),
                    const SizedBox(height: 12),
                    Row(
                      children: [
                        if (variant.mrp > variant.price)
                          Text(
                            '₹${variant.mrp.toStringAsFixed(0)}',
                            style: const TextStyle(
                              fontSize: 12,
                              decoration: TextDecoration.lineThrough,
                              color: _Ui.sub,
                            ),
                          ),
                        const Spacer(),
                        Text(
                          '₹${variant.price.toStringAsFixed(0)}',
                          style: const TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.w800,
                            color: _Ui.violet,
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            );
          }).toList(),
        ),
      ),
    );
  }

  Widget _addonPicker() {
    final service = _service!;
    return SliverToBoxAdapter(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 20),
        child: Column(
          children: service.addons.map((addon) {
            final isSelected = _selectedAddonIds.contains(addon.id);
            return InkWell(
              onTap: () {
                setState(() {
                  if (isSelected) {
                    _selectedAddonIds.remove(addon.id);
                  } else {
                    _selectedAddonIds.add(addon.id);
                  }
                });
                _updateSummary();
              },
              child: Container(
                margin: const EdgeInsets.only(bottom: 8),
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(
                    color: isSelected ? _Ui.violet : _Ui.line,
                  ),
                ),
                child: Row(
                  children: [
                    Container(
                      width: 24,
                      height: 24,
                      decoration: BoxDecoration(
                        color: isSelected ? _Ui.violet : Colors.transparent,
                        border: Border.all(color: _Ui.violet),
                        borderRadius: BorderRadius.circular(6),
                      ),
                      child: isSelected
                          ? const Icon(Icons.check, color: Colors.white, size: 16)
                          : null,
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Text(
                        addon.title,
                        style: const TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.w600,
                          color: _Ui.ink,
                        ),
                      ),
                    ),
                    Text(
                      '₹${addon.price.toStringAsFixed(0)}',
                      style: const TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.w700,
                        color: _Ui.violet,
                      ),
                    ),
                  ],
                ),
              ),
            );
          }).toList(),
        ),
      ),
    );
  }

  Widget _formFields() {
    final fields = _service!.formFields;
    return SliverToBoxAdapter(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 20),
        child: Column(
          children: fields.map((field) {
            final decoration = InputDecoration(
              labelText: field.isRequired ? '${field.label} *' : field.label,
              filled: true,
              fillColor: Colors.white,
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(14),
                borderSide: BorderSide(color: _Ui.line),
              ),
              enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(14),
                borderSide: BorderSide(color: _Ui.line),
              ),
            );
            Widget input;
            switch (field.fieldType) {
              case 'select':
                input = DropdownButtonFormField<String>(
                  value: _formAnswers[field.key]?.toString(),
                  decoration: decoration,
                  items: field.options.map((option) {
                    final value = option.toString();
                    return DropdownMenuItem(value: value, child: Text(value));
                  }).toList(),
                  onChanged: (value) => setState(() => _formAnswers[field.key] = value),
                );
                break;
              case 'photo':
                input = Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(14),
                  decoration: BoxDecoration(
                    color: Colors.white,
                    border: Border.all(color: _Ui.line),
                    borderRadius: BorderRadius.circular(14),
                  ),
                  child: const Text(
                    'Photo upload is not available in this app version.',
                    style: TextStyle(color: _Ui.sub, fontSize: 13),
                  ),
                );
                break;
              default:
                input = TextFormField(
                  initialValue: _formAnswers[field.key]?.toString() ?? '',
                  decoration: decoration,
                  keyboardType: field.fieldType == 'number'
                      ? TextInputType.number
                      : TextInputType.text,
                  maxLines: field.fieldType == 'textarea' ? 3 : 1,
                  onChanged: (value) => _formAnswers[field.key] = value,
                );
            }
            return Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: input,
            );
          }).toList(),
        ),
      ),
    );
  }

  Widget _schedulePicker() {
    final now = DateTime.now();
    final dates = List.generate(7, (index) {
      return now.add(Duration(days: index));
    });

    return SliverToBoxAdapter(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Select Date',
              style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: _Ui.sub),
            ),
            const SizedBox(height: 12),
            SizedBox(
              height: 70,
              child: ListView.builder(
                scrollDirection: Axis.horizontal,
                itemCount: dates.length,
                itemBuilder: (context, index) {
                  final date = dates[index];
                  final isSelected = _selectedScheduleTime?['date']?.day == date.day;
                  return GestureDetector(
                    onTap: () {
                      setState(() {
                        _selectedScheduleTime = {
                          'date': date,
                          'hour': now.hour < 20 ? now.hour + 1 : 10,
                          'minute': 0,
                        };
                      });
                      _checkSlotAvailability();
                    },
                    child: Container(
                      margin: const EdgeInsets.only(right: 8),
                      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                      decoration: BoxDecoration(
                        color: isSelected ? _Ui.violet : Colors.white,
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Text(
                            '${date.day}',
                            style: TextStyle(
                              fontSize: 18,
                              fontWeight: FontWeight.w700,
                              color: isSelected ? Colors.white : _Ui.ink,
                            ),
                          ),
                          Text(
                            ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][date.weekday - 1],
                            style: TextStyle(
                              fontSize: 11,
                              color: isSelected ? Colors.white70 : _Ui.sub,
                            ),
                          ),
                        ],
                      ),
                    ),
                  );
                },
              ),
            ),
            const SizedBox(height: 16),
            const Text(
              'Select Time',
              style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: _Ui.sub),
            ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: ['10:00', '11:00', '12:00', '13:00', '14:00', '15:00', '16:00', '17:00', '18:00', '19:00', '20:00', '21:00'].map((time) {
                final hour = int.parse(time.split(':')[0]);
                final isSelected = _selectedScheduleTime?['hour'] == hour;
                return ChoiceChip(
                  label: Text(time),
                  selected: isSelected,
                  onSelected: (selected) {
                    setState(() {
                      _selectedScheduleTime!['hour'] = hour;
                    });
                    _checkSlotAvailability();
                  },
                );
              }).toList(),
            ),
          ],
        ),
      ),
    );
  }

  Widget _dropTimePicker() {
    return SliverToBoxAdapter(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 20),
        child: Wrap(
          spacing: 8,
          runSpacing: 8,
          children: ['14:00', '16:00', '18:00', '20:00', '22:00'].map((time) {
            final hour = int.parse(time.split(':')[0]);
            final isSelected = _selectedDropTime?['hour'] == hour;
            return ChoiceChip(
              label: Text(time),
              selected: isSelected,
              onSelected: (selected) {
                setState(() {
                  _selectedDropTime = {'hour': hour};
                });
                _checkSlotAvailability();
              },
            );
          }).toList(),
        ),
      ),
    );
  }

  Widget _summaryCard() {
    final service = _service!;
    return SliverToBoxAdapter(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 20),
        child: Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: _Ui.line),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                service.title,
                style: const TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.w700,
                  color: _Ui.ink,
                ),
              ),
              const SizedBox(height: 8),
              Row(
                children: [
                  Icon(Icons.calendar_today, size: 14, color: _Ui.sub),
                  const SizedBox(width: 4),
                  Text(
                    '${_selectedScheduleTime?['date'].toString().split(' ')[0]} at ${_selectedScheduleTime?['hour']}h',
                    style: const TextStyle(fontSize: 13, color: _Ui.sub),
                  ),
                ],
              ),
              if (_selectedVariantId != null) ...[
                const SizedBox(height: 8),
                Row(
                  children: [
                    const Icon(Icons.info_outline, size: 14, color: _Ui.sub),
                    const SizedBox(width: 4),
                    Expanded(
                      child: Text(
                        'Package: ${service.variants.firstWhere((v) => v.id == _selectedVariantId, orElse: () => service.variants.first).title}',
                        style: const TextStyle(fontSize: 13, color: _Ui.sub),
                      ),
                    ),
                  ],
                ),
              ],
              const Divider(height: 16),
              Row(
                children: [
                  const Text('Subtotal', style: TextStyle(color: _Ui.sub)),
                  const Spacer(),
                  Text(
                    '₹${_subtotal.toStringAsFixed(0)}',
                    style: const TextStyle(color: _Ui.sub),
                  ),
                ],
              ),
              const SizedBox(height: 4),
              Row(
                children: [
                  const Text('Est. total (incl. tax)', style: TextStyle(fontWeight: FontWeight.w700, color: _Ui.ink)),
                  const Spacer(),
                  Text(
                    '₹${_estimatedTotal.toStringAsFixed(0)}',
                    style: const TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.w800,
                      color: _Ui.violet,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 4),
              const Text(
                'Final amount confirmed by backend after booking',
                style: TextStyle(fontSize: 11, color: _Ui.sub),
              ),
            ],
          ),
        ),
      ),
    );
  }

  void _updateSummary() {
    final service = _service!;
    final variant = service.variants.firstWhere(
      (v) => v.id == _selectedVariantId,
      orElse: () => service.variants.isEmpty
          ? ServiceVariant(id: 0, title: '', mrp: 0, price: 0, discountPercent: 0, sortOrder: 0, isActive: false)
          : service.variants.first,
    );
    double total = variant.price;

    for (final addonId in _selectedAddonIds) {
      final addon = service.addons.firstWhere(
        (a) => a.id == addonId,
        orElse: () => AddOn(id: 0, title: '', mrp: 0, price: 0, discountPercent: 0, sortOrder: 0, isActive: false),
      );
      total += addon.price;
    }

    _subtotal = total;
    _estimatedTotal = total * 1.18; // Estimate only; backend confirms final amount
    _checkSlotAvailability();
  }

  Future<void> _checkSlotAvailability() async {
    if (_service == null || _selectedScheduleTime == null || _selectedAddressId == null) {
      return;
    }

    setState(() {
      _checkingAvailability = true;
      _availabilityMessage = null;
    });

    try {
      final scheduledAt = DateTime(
        _selectedScheduleTime!['date'].year,
        _selectedScheduleTime!['date'].month,
        _selectedScheduleTime!['date'].day,
        _selectedScheduleTime!['hour'],
        _selectedScheduleTime!['minute'],
      );

      final dropAt = _selectedDropTime != null
          ? DateTime(
              _selectedScheduleTime!['date'].year,
              _selectedScheduleTime!['date'].month,
              _selectedScheduleTime!['date'].day,
              _selectedDropTime!['hour'],
            )
          : null;

      final isAvailable = await BookingApi.checkSlotAvailability(
        serviceId: widget.serviceId,
        scheduledAt: scheduledAt,
        dropScheduledAt: dropAt,
        variantId: _selectedVariantId,
        bookingMode: _service!.bookingMode,
      );

      if (!mounted) return;

      setState(() {
        _isAvailable = isAvailable;
        if (isAvailable) {
          _availabilityMessage = null;
        } else {
          _availabilityMessage = 'Selected slot is not available. Please choose another time.';
        }
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _isAvailable = false;
        _availabilityMessage = 'Unable to check availability. $e';
      });
    }

    if (!mounted) return;
    setState(() {
      _checkingAvailability = false;
    });
  }

  Future<void> _confirmBooking() async {
    if (_selectedAddressId == null) return;
    if (!_isAvailable) return;
    if (_service!.variants.length > 1 && _selectedVariantId == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Please select a package.')),
      );
      return;
    }
    for (final field in _service!.formFields) {
      if (field.isRequired && field.fieldType != 'photo' &&
          (_formAnswers[field.key] == null || _formAnswers[field.key].toString().trim().isEmpty)) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Please complete: ${field.label}')),
        );
        return;
      }
    }

    if (!mounted) return;
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (_) => const Center(child: CircularProgressIndicator()),
    );

    try {
      final scheduledAt = DateTime(
        _selectedScheduleTime!['date'].year,
        _selectedScheduleTime!['date'].month,
        _selectedScheduleTime!['date'].day,
        _selectedScheduleTime!['hour'],
        _selectedScheduleTime!['minute'],
      );

      await BookingApi.createBooking(
        serviceId: widget.serviceId,
        variantId: _selectedVariantId,
        bookingMode: _service!.bookingMode,
        scheduledAt: scheduledAt,
        dropScheduledAt: _selectedDropTime != null
            ? DateTime(
                _selectedScheduleTime!['date'].year,
                _selectedScheduleTime!['date'].month,
                _selectedScheduleTime!['date'].day,
                _selectedDropTime!['hour'],
              )
            : null,
        addressId: _selectedAddressId!,
        addonIds: _selectedAddonIds.isEmpty ? null : _selectedAddonIds,
        formResponses: _formAnswers,
      );

      if (!mounted) return;
      Navigator.pop(context); // Close loading dialog
      Navigator.pushReplacement(
        context,
        MaterialPageRoute(builder: (_) => BookingListScreen()),
      );
    } catch (e) {
      if (!mounted) return;
      Navigator.pop(context); // Close loading dialog
      showDialog(
        context: context,
        builder: (_) => AlertDialog(
          title: const Text('Booking Failed'),
          content: Text(e.toString()),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('OK'),
            ),
          ],
        ),
      );
    }
  }

  Widget _errorWidget(String message) => Center(
        child: Padding(
          padding: const EdgeInsets.all(28),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.error_outline, color: Colors.redAccent, size: 52),
              const SizedBox(height: 14),
              Text(
                message,
                textAlign: TextAlign.center,
                style: const TextStyle(color: _Ui.sub),
              ),
              const SizedBox(height: 20),
              FilledButton(
                onPressed: _loadData,
                child: const Text('Retry'),
              ),
            ],
          ),
        ),
      );
}