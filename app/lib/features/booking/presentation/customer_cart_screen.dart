import 'package:flutter/material.dart';
import 'package:airway/core/theme/airway_colors.dart';
import 'package:airway/core/theme/airway_spacing.dart';
import 'package:airway/core/theme/airway_typography.dart';
import 'package:airway/core/network/auth_api.dart';
import 'package:intl/intl.dart';
import 'package:airway/features/booking/data/booking_api.dart';
import 'package:airway/features/booking/presentation/customer_order_screen.dart';
import 'package:airway/features/booking/presentation/booking_schedule_screen.dart';
import 'package:airway/features/booking/presentation/customer_cart_badge.dart';
import 'package:airway/features/booking/presentation/cart_item_preferences_screen.dart';
import 'package:airway/core/localization/airway_text.dart' as airway_localization;

class CustomerCartScreen extends StatefulWidget {
  const CustomerCartScreen({super.key});
  @override
  State<CustomerCartScreen> createState() => _CustomerCartScreenState();
}

class _CustomerCartScreenState extends State<CustomerCartScreen> {
  static const violet = AirwayColors.primary;
  static const ink = AirwayColors.text;
  static const sub = AirwayColors.textSecondary;
  static const bg = AirwayColors.background;
  static const pale = AirwayColors.primarySoft;
  static const line = AirwayColors.border;

  Map<String, dynamic>? cart;
  bool loading = true;
  bool busy = false;
  String? error;
  final Map<int, DateTime> dates = {};
  final Map<int, TimeOfDay> times = {};
  final Map<int, TimeOfDay> dropTimes = {};
  final Set<int> _slotConfirmed = {};
  final Set<int> _expandedItems = {};
  List<Map<String, dynamic>> addresses = [];

  @override
  void initState() {
    super.initState();
    loadCart();
  }

  List<Map<String, dynamic>> get items => (cart?['items'] as List? ?? [])
      .whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList();

  double number(dynamic value) => double.tryParse(value?.toString() ?? '') ?? 0;

  Map<String, List<Map<String, dynamic>>> get scheduleGroups {
    final groups = <String, List<Map<String, dynamic>>>{};
    for (final item in items) {
      final id = item['id'] as int;
      final date = dates[id];
      final time = times[id];
      if (!_slotConfirmed.contains(id) || date == null || time == null) continue;
      final slot = DateTime(date.year, date.month, date.day, time.hour, time.minute);
      groups.putIfAbsent(slot.toIso8601String(), () => []).add(item);
    }
    return groups;
  }

  void applyScheduleToAll(int sourceId) {
    final date = dates[sourceId];
    final time = times[sourceId];
    if (date == null || time == null || !_slotConfirmed.contains(sourceId)) return;
    final sourceItems = items.where((item) => item['id'] == sourceId).toList();
    final sourceUsesPickupDrop = sourceItems.isNotEmpty && sourceItems.first['booking_mode'] == 'pickup_drop';
    setState(() {
      for (final item in items) {
        final id = item['id'] as int;
        dates[id] = date;
        times[id] = time;
        if (sourceUsesPickupDrop && item['booking_mode'] == 'pickup_drop') {
          dropTimes[id] = dropTimes[sourceId]!;
        }
        _slotConfirmed.add(id);
      }
    });
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(airway_localization.AirwayText.tr('This date and time has been applied to every service. Availability will be checked for each service at checkout.', 'यह तारीख और समय सभी सेवाओं पर लागू कर दिया गया है। चेकआउट पर हर सेवा की उपलब्धता जाँची जाएगी।'))),
    );
  }

  Widget scheduleOverviewCard() {
    final groups = scheduleGroups;
    if (groups.isEmpty) return const SizedBox.shrink();
    final entries = groups.entries.toList()
      ..sort((a, b) => a.key.compareTo(b.key));
    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AirwayColors.surfaceVariant,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: line),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            const Icon(Icons.event_available_rounded, color: violet),
            const SizedBox(width: 9),
            Expanded(child: Text(airway_localization.AirwayText.tr('Your schedule', 'आपका शेड्यूल'), style: TextStyle(color: ink, fontWeight: FontWeight.w900, fontSize: 15))),
            Text(airway_localization.AirwayText.tr('${groups.length} time slots', '${groups.length} समय स्लॉट'), style: const TextStyle(color: violet, fontWeight: FontWeight.w800, fontSize: 12)),
          ]),
          const SizedBox(height: 5),
          Text(airway_localization.AirwayText.tr('${_slotConfirmed.length} of ${items.length} services scheduled', '${items.length} में से ${_slotConfirmed.length} सेवाएँ शेड्यूल हुईं'), style: const TextStyle(color: sub, fontSize: 12)),
          const SizedBox(height: 10),
          for (final entry in entries) ...[
            const Divider(height: 12, color: line),
            Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const Icon(Icons.schedule_rounded, color: violet, size: 18),
              const SizedBox(width: 9),
              Expanded(child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    DateFormat('EEE, dd MMM').format(DateTime.parse(entry.key)) +
                    ' · ' + TimeOfDay.fromDateTime(DateTime.parse(entry.key)).format(context),
                    style: const TextStyle(color: ink, fontWeight: FontWeight.w800, fontSize: 12),
                  ),
                  Text(
                    entry.value.map((item) => item['service_title']?.toString() ?? 'Service').join(' · '),
                    style: const TextStyle(color: sub, fontSize: 11),
                  ),
                ],
              )),
              Text('${entry.value.length}', style: const TextStyle(color: violet, fontWeight: FontWeight.w900)),
            ]),
          ],
        ],
      ),
    );
  }

  Future<void> loadCart() async {
    setState(() { loading = true; error = null; });
    try {
      final value = await BookingApi.getCart();
      CustomerCartState.updateFromCart(value);
      try {
        final rawAddresses = await BookingApi.request('/api/v1/auth/addresses/');
        final rawList = rawAddresses is List ? rawAddresses : (rawAddresses is Map ? rawAddresses['results'] : null);
        if (rawList is List) addresses = rawList.whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList();
      } catch (_) {}
      final tomorrow = DateTime.now().add(const Duration(days: 1));
      for (final row in (value['items'] as List? ?? []).whereType<Map>()) {
        final id = row['id'] as int;
        dates.putIfAbsent(id, () => DateTime(tomorrow.year, tomorrow.month, tomorrow.day));
        times.putIfAbsent(id, () => const TimeOfDay(hour: 10, minute: 0));
        dropTimes.putIfAbsent(id, () => const TimeOfDay(hour: 17, minute: 0));
      }
      if (mounted) setState(() { cart = value; loading = false; });
    } catch (e) {
      if (mounted) setState(() { error = e.toString(); loading = false; });
    }
  }

  Future<void> removeItem(int id) async {
    setState(() => busy = true);
    try {
      final value = await BookingApi.deleteCartItem(id);
      CustomerCartState.updateFromCart(value);
      if (mounted) setState(() {
        cart = value;
        dates.remove(id);
        times.remove(id);
        dropTimes.remove(id);
        _slotConfirmed.remove(id);
        _expandedItems.remove(id);
        busy = false;
      });
    } catch (e) {
      if (mounted) setState(() { busy = false; error = e.toString(); });
    }
  }

  Future<void> editPreferences(Map<String, dynamic> item) async {
    final saved = await Navigator.of(context).push<bool>(
      MaterialPageRoute(
        builder: (_) => CartItemPreferencesScreen(
          cartItemId: item['id'] as int,
          serviceId: int.parse(item['service'].toString()),
          serviceTitle: item['service_title']?.toString() ?? 'Service',
          categoryAnswers: Map<String, dynamic>.from(
            item['category_answers'] as Map? ?? const {},
          ),
          initialAnswers: Map<String, dynamic>.from(
            item['form_answers'] as Map? ?? const {},
          ),
          initialNotes: item['notes']?.toString() ?? '',
          hasIssuePhoto: item['has_issue_photo'] == true,
        ),
      ),
    );
    if (saved == true && mounted) await loadCart();
  }

  Future<void> chooseSchedule(int id) async {
    Map<String, dynamic>? selectedItem;
    for (final row in items) {
      if (row['id'] == id) {
        selectedItem = row;
        break;
      }
    }
    final serviceId = int.tryParse(selectedItem?['service']?.toString() ?? '');
    final addressId = int.tryParse(cart?['address']?.toString() ?? '');
    if (selectedItem == null || serviceId == null || addressId == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(airway_localization.AirwayText.tr('Select a valid service and address first.', 'पहले सही सेवा और पता चुनें।'))),
      );
      return;
    }

    final item = selectedItem;
    final previousDate = dates[id];
    final previousTime = times[id];
    final previousDrop = dropTimes[id];
    final result = await Navigator.of(context).push<BookingScheduleResult>(
      MaterialPageRoute(
        builder: (_) => BookingScheduleScreen(
          serviceId: serviceId,
          addressId: addressId,
          variantId: int.tryParse(item['variant']?.toString() ?? ''),
          quantity: int.tryParse(item['quantity']?.toString() ?? '1') ?? 1,
          bookingMode: item['booking_mode']?.toString() ?? 'scheduled',
          categoryAnswers: Map<String, dynamic>.from(
            item['category_answers'] as Map? ?? const {},
          ),
          cartItemId: id,
          initialDate: previousDate,
          initialTime: previousTime,
          initialDropTime: previousDrop,
        ),
      ),
    );

    if (result == null || !mounted) return;
    setState(() {
      dates[id] = result.scheduledAt;
      times[id] = TimeOfDay.fromDateTime(result.scheduledAt);
      for (final row in (cart?['items'] as List? ?? []).whereType<Map>()) {
        if (row['id'] == id) {
          row['category_answers'] = Map<String, dynamic>.from(result.categoryAnswers);
          break;
        }
      }
      if (result.dropScheduledAt != null) {
        dropTimes[id] = TimeOfDay.fromDateTime(result.dropScheduledAt!);
      }
      _slotConfirmed.add(id);
    });
  }

  Future<void> checkout() async {
    if (items.isEmpty) return;
    if (cart?['address'] == null) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(airway_localization.AirwayText.tr('Please select a service address first.', 'पहले सेवा का पता चुनें।'))));
      return;
    }
    setState(() => busy = true);
    try {
      final schedules = items.map((item) {
        final id = item['id'] as int;
        final date = dates[id] ?? DateTime.now().add(const Duration(days: 1));
        if (!_slotConfirmed.contains(id)) {
          throw Exception('Choose an available time slot for ${item['service_title'] ?? 'this service'}.');
        }
        final time = times[id] ?? const TimeOfDay(hour: 10, minute: 0);
        final scheduledAt = DateTime(
          date.year,
          date.month,
          date.day,
          time.hour,
          time.minute,
        );
        if (!scheduledAt.isAfter(DateTime.now())) {
          throw Exception(
            'Choose a future service time for '
            '${item['service_title']?.toString() ?? 'this service'}.',
          );
        }
        final row = <String, dynamic>{
          'cart_item_id': id,
          // Send an explicit UTC timestamp so the backend does not interpret
          // the device's local wall-clock time as server time.
          'scheduled_at': scheduledAt.toUtc().toIso8601String(),
        };
        if (item['booking_mode'] == 'pickup_drop') {
          final drop = dropTimes[id] ?? const TimeOfDay(hour: 14, minute: 0);
          final dropScheduledAt = DateTime(
            date.year,
            date.month,
            date.day,
            drop.hour,
            drop.minute,
          );
          if (!dropScheduledAt.isAfter(scheduledAt)) {
            throw Exception(
              'Drop time must be later than pickup time for '
              '${item['service_title']?.toString() ?? 'this service'}.',
            );
          }
          row['drop_scheduled_at'] =
              dropScheduledAt.toUtc().toIso8601String();
        }
        return row;
      }).toList();
      final result = await BookingApi.checkoutCart(items: schedules);
      CustomerCartState.itemCount.value = 0;
      if (!mounted) return;
      setState(() => busy = false);
      await showDialog<void>(
        context: context,
        barrierDismissible: false,
        builder: (ctx) => AlertDialog(
          icon: const Icon(Icons.check_circle_rounded, color: violet, size: 48),
          title: Text(airway_localization.AirwayText.tr('Order placed', 'ऑर्डर दे दिया गया')),
          content: Text(
            'Your order #' + result['order_id'].toString() +
            ' has been created. Pay the 30% advance to start worker matching. The remaining 70% is due only after every service is completed and verified with the customer OTP.',
            textAlign: TextAlign.center,
          ),
          actions: [FilledButton(onPressed: () => Navigator.pop(ctx), child: Text(airway_localization.AirwayText.tr('Continue', 'जारी रखें')))],
        ),
      );
      if (mounted) {
        Navigator.pushAndRemoveUntil(
          context,
          MaterialPageRoute(builder: (_) => CustomerOrderScreen(orderId: result['order_id'] as int)),
          (route) => route.isFirst,
        );
      }
    } catch (e) {
      if (mounted) {
        setState(() => busy = false);
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(airway_localization.AirwayText.tr('Checkout failed: $e', 'चेकआउट विफल: $e'))));
      }
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    backgroundColor: bg,
    appBar: AppBar(
      elevation: 0,
      scrolledUnderElevation: 0,
      backgroundColor: bg,
      foregroundColor: ink,
      titleSpacing: 20,
      title: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(airway_localization.AirwayText.tr('My Cart', 'मेरी कार्ट'), style: AirwayText.titleLarge.copyWith(fontSize: 20, fontWeight: FontWeight.w800, color: ink)),
          Text(airway_localization.AirwayText.tr('Review your services', 'अपनी सेवाओं की समीक्षा करें'), style: TextStyle(fontSize: 11, color: sub, fontWeight: FontWeight.w500)),
        ],
      ),
      actions: [
        IconButton(
          tooltip: airway_localization.AirwayText.tr('Refresh cart', 'कार्ट रीफ़्रेश करें'),
          onPressed: loading ? null : loadCart,
          icon: const Icon(Icons.refresh_rounded),
        ),
        const SizedBox(width: 6),
      ],
    ),
    body: loading
      ? const Center(child: CircularProgressIndicator(color: violet))
      : error != null
        ? emptyState('Could not load your cart', error!, Icons.error_outline_rounded, loadCart)
        : items.isEmpty
          ? emptyState('Your cart is empty', 'Find a service you need and add it here.', Icons.shopping_bag_outlined, () => Navigator.pop(context))
          : cartBody(),
  );

  Widget cartBody() {
    final subtotal = number(cart?['subtotal']);
    final scheduledCount = _slotConfirmed.where((id) => items.any((item) => item['id'] == id)).length;
    return Column(children: [
      Expanded(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 22),
          children: [
            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                gradient: AirwayColors.heroGradient,
                borderRadius: BorderRadius.circular(AirwaySpacing.cardRadius),
                boxShadow: [BoxShadow(color: violet.withValues(alpha: .10), blurRadius: 22, offset: const Offset(0, 10))],
              ),
              child: Stack(children: [
                Positioned(right: -12, top: -18, child: Icon(Icons.shopping_bag_rounded, size: 105, color: AirwayColors.primary.withValues(alpha: .08))),
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                    decoration: BoxDecoration(color: AirwayColors.primarySoft, borderRadius: BorderRadius.circular(30)),
                    child: Text(items.length.toString() + (items.length == 1 ? ' SERVICE ADDED' : ' SERVICES ADDED'),
                      style: const TextStyle(color: AirwayColors.primary, fontSize: 10, fontWeight: FontWeight.w900, letterSpacing: 1)),
                  ),
                  const SizedBox(height: 13),
                  Text(airway_localization.AirwayText.tr('Your home,\nyour services.', 'आपका घर,\nआपकी सेवाएँ।'), style: TextStyle(color: AirwayColors.text, fontSize: 25, height: 1.12, fontWeight: FontWeight.w900)),
                  const SizedBox(height: 7),
                  Text(airway_localization.AirwayText.tr('A few quick details and we’ll take it from here.', 'कुछ ज़रूरी जानकारी दें, बाकी हम संभाल लेंगे।'),
                    style: TextStyle(color: AirwayColors.textSecondary, fontSize: 12)),
                  const SizedBox(height: 17),
                  Row(children: [
                    _heroMetric(Icons.calendar_month_rounded, scheduledCount.toString() + '/' + items.length.toString(), 'Scheduled'),
                    const SizedBox(width: 10),
                    _heroMetric(Icons.currency_rupee_rounded, subtotal.toStringAsFixed(0), 'Cart value'),
                  ]),
                ]),
              ]),
            ),
            const SizedBox(height: 18),
            addressCard(),
            const SizedBox(height: 22),
            Row(children: [
              Expanded(child: Text(airway_localization.AirwayText.tr('Your services', 'आपकी सेवाएँ'), style: TextStyle(fontSize: 19, fontWeight: FontWeight.w900, color: ink))),
              Text(items.length.toString() + ' items', style: const TextStyle(color: sub, fontSize: 12, fontWeight: FontWeight.w700)),
            ]),
            const SizedBox(height: 5),
            Text(airway_localization.AirwayText.tr('Tap a service to view details or update your preferences.', 'विवरण देखने या पसंद बदलने के लिए किसी सेवा पर टैप करें।'), style: TextStyle(fontSize: 12, color: sub)),
            const SizedBox(height: 13),
            scheduleOverviewCard(),
            for (final item in items) ...[itemCard(item), const SizedBox(height: 13)],
            Container(
              padding: const EdgeInsets.all(18),
              decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(22), border: Border.all(color: line)),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Row(children: [
                  Icon(Icons.receipt_long_rounded, color: violet, size: 20),
                  SizedBox(width: 9),
                  Text(airway_localization.AirwayText.tr('Price summary', 'कीमत का सारांश'), style: TextStyle(fontSize: 16, fontWeight: FontWeight.w900, color: ink)),
                ]),
                const SizedBox(height: 16),
                priceRow(airway_localization.AirwayText.tr('Service subtotal', 'सेवा उप-योग'), '₹' + subtotal.toStringAsFixed(0)),
                priceRow(airway_localization.AirwayText.tr('Taxes & applicable charges', 'टैक्स और लागू शुल्क'), airway_localization.AirwayText.tr('Calculated at checkout', 'चेकआउट पर गणना होगी')),
                const Padding(padding: EdgeInsets.symmetric(vertical: 10), child: Divider(color: line)),
                Text(airway_localization.AirwayText.tr('Payment is split for your convenience', 'आपकी सुविधा के लिए भुगतान दो हिस्सों में है'), style: TextStyle(fontSize: 12, fontWeight: FontWeight.w800, color: ink)),
                const SizedBox(height: 5),
                Text(airway_localization.AirwayText.tr('30% advance to begin worker matching · 70% after every service is completed and verified.', 'वर्कर मिलान शुरू करने के लिए 30% अग्रिम · सभी सेवाएँ पूरी और वेरिफ़ाई होने पर 70% शेष।'), style: TextStyle(fontSize: 11, height: 1.4, color: sub)),
              ]),
            ),
          ],
        ),
      ),
      Container(
        padding: const EdgeInsets.fromLTRB(18, 13, 18, 14),
        decoration: BoxDecoration(
          color: Colors.white,
          border: const Border(top: BorderSide(color: line)),
          boxShadow: [BoxShadow(color: AirwayColors.ink.withOpacity(.06), blurRadius: 18, offset: const Offset(0, -5))],
        ),
        child: SafeArea(top: false, child: Row(children: [
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
            Text(airway_localization.AirwayText.tr('TOTAL AMOUNT', 'कुल राशि'), style: TextStyle(color: sub, fontSize: 9, fontWeight: FontWeight.w900, letterSpacing: 1)),
            const SizedBox(height: 2),
            Text('₹' + subtotal.toStringAsFixed(0), style: const TextStyle(fontSize: 23, fontWeight: FontWeight.w900, color: ink)),
          ])),
          const SizedBox(width: 12),
          Expanded(flex: 2, child: SizedBox(
            height: 52,
            child: FilledButton(
              style: FilledButton.styleFrom(
                backgroundColor: violet,
                foregroundColor: Colors.white,
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                elevation: 0,
              ),
              onPressed: busy ? null : checkout,
              child: busy
                ? const SizedBox(height: 19, width: 19, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                : Row(mainAxisAlignment: MainAxisAlignment.center, children: [
                    Text(airway_localization.AirwayText.tr('Continue to checkout', 'चेकआउट पर जाएँ'), style: TextStyle(fontWeight: FontWeight.w800, fontSize: 13)),
                    SizedBox(width: 7),
                    Icon(Icons.arrow_forward_rounded, size: 18),
                  ]),
            ),
          )),
        ])),
      ),
    ]);
  }

  Widget _heroMetric(IconData icon, String value, String label) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 9),
    decoration: BoxDecoration(color: Colors.white.withOpacity(.14), borderRadius: BorderRadius.circular(13)),
    child: Row(mainAxisSize: MainAxisSize.min, children: [
      Icon(icon, color: AirwayColors.primary, size: 17),
      const SizedBox(width: 7),
      Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(value, style: const TextStyle(color: AirwayColors.primary, fontWeight: FontWeight.w900, fontSize: 13)),
        Text(label, style: TextStyle(color: AirwayColors.textSecondary, fontSize: 9)),
      ]),
    ]),
  );

  Widget addressCard() {
    final selectedId = cart?['address'] is int ? cart!['address'] as int : int.tryParse(cart?['address']?.toString() ?? '');
    final selected = addresses.where((a) => a['id'] == selectedId).toList();
    final label = selected.isEmpty
      ? (selectedId == null ? 'Choose where your service is needed' : 'Saved address #' + selectedId.toString())
      : (selected.first['label']?.toString() ?? 'Service address') + ' • ' + (selected.first['full_address']?.toString() ?? '');
    return Container(
      padding: const EdgeInsets.all(15),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(AirwaySpacing.cardRadius),
        border: Border.all(color: line),
        boxShadow: [BoxShadow(color: AirwayColors.ink.withOpacity(.035), blurRadius: 12, offset: const Offset(0, 4))],
      ),
      child: Row(children: [
        Container(
          height: 46, width: 46,
          decoration: BoxDecoration(gradient: const LinearGradient(colors: [AirwayColors.primarySoft, AirwayColors.primarySoft]), borderRadius: BorderRadius.circular(15)),
          child: const Icon(Icons.location_on_rounded, color: violet, size: 23),
        ),
        const SizedBox(width: 12),
        Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(airway_localization.AirwayText.tr('SERVICE LOCATION', 'सेवा का पता'), style: TextStyle(color: sub, fontSize: 9, letterSpacing: 1, fontWeight: FontWeight.w900)),
          const SizedBox(height: 4),
          Text(label, maxLines: 2, overflow: TextOverflow.ellipsis, style: const TextStyle(color: ink, fontSize: 12, height: 1.35, fontWeight: FontWeight.w700)),
        ])),
        if (addresses.isNotEmpty)
          PopupMenuButton<int>(
            tooltip: airway_localization.AirwayText.tr('Change address', 'पता बदलें'),
            icon: const Icon(Icons.edit_location_alt_rounded, color: violet),
            onSelected: (id) async {
              setState(() { busy = true; _slotConfirmed.clear(); });
              try {
                final updated = await BookingApi.updateCartAddress(id);
                if (mounted) setState(() { cart = updated; busy = false; });
              } catch (e) {
                if (mounted) {
                  setState(() => busy = false);
                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.toString())));
                }
              }
            },
            itemBuilder: (context) => addresses.map((a) => PopupMenuItem<int>(
              value: a['id'] as int,
              child: SizedBox(width: 230, child: Text((a['label']?.toString() ?? 'Address') + ' — ' + (a['full_address']?.toString() ?? ''), maxLines: 2, overflow: TextOverflow.ellipsis)),
            )).toList(),
          ),
      ]),
    );
  }

  Widget _cartPhotoPreview({
    required int itemId,
    required String? fieldKey,
    required bool issuePhoto,
  }) {
    final path = issuePhoto
        ? '/api/v1/bookings/cart/items/$itemId/issue-photo/'
        : '/api/v1/bookings/cart/items/$itemId/form-photos/${Uri.encodeComponent(fieldKey ?? '')}/';
    return FutureBuilder<Map<String, String>>(
      future: BookingApi.getAuthHeaders(),
      builder: (context, snapshot) {
        Widget child;
        if (!snapshot.hasData) {
          child = const Center(child: SizedBox(
            width: 18, height: 18,
            child: CircularProgressIndicator(strokeWidth: 2, color: violet),
          ));
        } else {
          child = Image.network(
            '${AuthApi.baseUrl}$path',
            headers: snapshot.data,
            fit: BoxFit.contain,
            width: 112,
            height: 112,
            errorBuilder: (_, __, ___) => const Center(
              child: Icon(Icons.broken_image_outlined, color: sub, size: 25),
            ),
          );
        }
        return Container(
          width: 116,
          height: 116,
          padding: const EdgeInsets.all(4),
          decoration: BoxDecoration(
            color: AirwayColors.surfaceVariant,
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: line),
          ),
          clipBehavior: Clip.antiAlias,
          child: child,
        );
      },
    );
  }

  Widget itemCard(Map<String, dynamic> item) {
    final id = item['id'] as int;
    final date = dates[id] ?? DateTime.now().add(const Duration(days: 1));
    final time = times[id] ?? const TimeOfDay(hour: 10, minute: 0);
    final snapshot = Map<String, dynamic>.from(item['pricing_snapshot'] ?? {});
    final addons = snapshot['addons'] as List? ?? [];
    final expanded = _expandedItems.contains(id);
    final scheduled = _slotConfirmed.contains(id);
    final quantity = item['quantity']?.toString() ?? '1';
    final unit = item['service_unit_label']?.toString() ?? '';
    final quantityLabel = unit.isNotEmpty ? '$quantity $unit' : 'Qty $quantity';
    final amountLabel = '₹' + number(item['line_total']).toStringAsFixed(0);
    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(21),
        border: Border.all(color: line),
        boxShadow: [BoxShadow(color: AirwayColors.ink.withOpacity(.035), blurRadius: 13, offset: const Offset(0, 5))],
      ),
      child: Column(children: [
        InkWell(
          borderRadius: BorderRadius.circular(21),
          onTap: () => setState(() { if (expanded) { _expandedItems.remove(id); } else { _expandedItems.add(id); } }),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(14, 15, 10, 13),
            child: Row(children: [
              Container(
                width: 54, height: 54,
                decoration: BoxDecoration(gradient: const LinearGradient(colors: [AirwayColors.primarySoft, AirwayColors.surfaceVariant], begin: Alignment.topLeft, end: Alignment.bottomRight), borderRadius: BorderRadius.circular(17)),
                child: const Icon(Icons.home_repair_service_rounded, color: violet, size: 26),
              ),
              const SizedBox(width: 12),
              Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(item['service_title']?.toString() ?? 'Service', maxLines: 2, overflow: TextOverflow.ellipsis, style: const TextStyle(fontWeight: FontWeight.w900, color: ink, fontSize: 14, height: 1.2)),
                if ((item['variant_title'] ?? '').toString().isNotEmpty)
                  Padding(padding: const EdgeInsets.only(top: 4), child: Text(item['variant_title'].toString(), maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 11, color: sub))),
                const SizedBox(height: 6),
                Text(quantityLabel + '  ·  ' + amountLabel, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w900, color: violet)),
              ])),
              IconButton(
                tooltip: airway_localization.AirwayText.tr('Remove service', 'सेवा हटाएँ'),
                onPressed: busy ? null : () => removeItem(id),
                icon: const Icon(Icons.delete_outline_rounded, color: AirwayColors.error, size: 21),
              ),
              Icon(expanded ? Icons.keyboard_arrow_up_rounded : Icons.keyboard_arrow_down_rounded, color: sub),
            ]),
          ),
        ),
        if (item['has_issue_photo'] == true || item['has_form_photos'] == true)
          Padding(
            padding: const EdgeInsets.fromLTRB(13, 0, 13, 11),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Padding(
                  padding: EdgeInsets.only(top: 5, right: 9),
                  child: Icon(Icons.photo_library_outlined, color: violet, size: 17),
                ),
                Expanded(
                  child: Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      if (item['has_issue_photo'] == true)
                        _cartPhotoPreview(itemId: id, fieldKey: null, issuePhoto: true),
                      for (final key in (item['form_photo_keys'] as List? ?? const []))
                        _cartPhotoPreview(
                          itemId: id,
                          fieldKey: key.toString(),
                          issuePhoto: false,
                        ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        Padding(
          padding: const EdgeInsets.fromLTRB(13, 0, 13, 13),
          child: InkWell(
            borderRadius: BorderRadius.circular(14),
            onTap: busy ? null : () => chooseSchedule(id),
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 11),
              decoration: BoxDecoration(
                color: scheduled ? AirwayColors.primarySoft : AirwayColors.warningSoft,
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: scheduled ? AirwayColors.borderStrong : AirwayColors.borderStrong),
              ),
              child: Row(children: [
                Icon(scheduled ? Icons.event_available_rounded : Icons.add_circle_outline_rounded, color: scheduled ? violet : AirwayColors.warning, size: 19),
                const SizedBox(width: 9),
                Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(scheduled ? DateFormat('EEE, dd MMM').format(date) + ' · ' + time.format(context) : 'Choose date & time',
                    style: TextStyle(color: scheduled ? ink : AirwayColors.warning, fontWeight: FontWeight.w800, fontSize: 12)),
                  Text(scheduled ? 'Tap to change your schedule' : 'Select a convenient service slot',
                    style: TextStyle(color: scheduled ? sub : AirwayColors.textSecondary, fontSize: 10)),
                ])),
                Text(scheduled ? 'CHANGE' : 'SCHEDULE', style: const TextStyle(color: violet, fontSize: 9, fontWeight: FontWeight.w900, letterSpacing: .5)),
                const SizedBox(width: 3),
                const Icon(Icons.chevron_right_rounded, color: violet, size: 18),
              ]),
            ),
          ),
        ),
        AnimatedCrossFade(
          duration: const Duration(milliseconds: 200),
          crossFadeState: expanded ? CrossFadeState.showSecond : CrossFadeState.showFirst,
          firstChild: const SizedBox(width: double.infinity),
          secondChild: Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const Divider(color: line, height: 12),
              if (item['category_answers'] is Map)
                for (final entry in (item['category_answers'] as Map).entries)
                  if (!entry.key.toString().endsWith('_id') && entry.key.toString() != 'vehicle_type' && entry.value != null && entry.value.toString().isNotEmpty)
                    Padding(padding: const EdgeInsets.only(bottom: 5), child: Text(entry.key.toString().replaceAll('_', ' ') + ': ' + entry.value.toString(), style: const TextStyle(fontSize: 11, color: sub))),
              if (number(snapshot['visit_fee']) > 0)
                Padding(padding: const EdgeInsets.only(top: 5), child: Text(airway_localization.AirwayText.tr('Inspection / visit charge: ₹${number(snapshot['visit_fee']).toStringAsFixed(0)} (included once)', 'निरीक्षण / विज़िट शुल्क: ₹${number(snapshot['visit_fee']).toStringAsFixed(0)} (एक बार शामिल)'), style: const TextStyle(fontSize: 11, color: sub, fontWeight: FontWeight.w700))),
              if (item['notes']?.toString().trim().isNotEmpty == true)
                Padding(padding: const EdgeInsets.only(top: 7), child: Text(airway_localization.AirwayText.tr('Issue description: ${item['notes']}', 'समस्या का विवरण: ${item['notes']}'), style: const TextStyle(fontSize: 11, color: sub))),

              if (addons.isNotEmpty) ...[
                const SizedBox(height: 10),
                Text(airway_localization.AirwayText.tr('ADD-ONS', 'अतिरिक्त सेवाएँ'), style: TextStyle(fontWeight: FontWeight.w900, fontSize: 9, color: sub, letterSpacing: .8)),
                for (final addon in addons)
                  Padding(padding: const EdgeInsets.only(top: 4), child: Text('• ' + addon['title'].toString() + ' × ' + addon['quantity'].toString(), style: const TextStyle(fontSize: 11, color: ink))),
              ],
              if (item['booking_mode'] == 'pickup_drop' && scheduled)
                Padding(padding: const EdgeInsets.only(top: 8), child: Text(airway_localization.AirwayText.tr('Drop-off time: ${(dropTimes[id] ?? const TimeOfDay(hour: 17, minute: 0)).format(context)}', 'ड्रॉप-ऑफ़ समय: ${(dropTimes[id] ?? const TimeOfDay(hour: 17, minute: 0)).format(context)}'), style: const TextStyle(color: sub, fontSize: 11))),
              const SizedBox(height: 12),
              SizedBox(width: double.infinity, child: OutlinedButton.icon(
                onPressed: busy ? null : () => editPreferences(item),
                icon: const Icon(Icons.tune_rounded, size: 17),
                label: Text(airway_localization.AirwayText.tr('Edit service preferences', 'सेवा की पसंद बदलें')),
                style: OutlinedButton.styleFrom(foregroundColor: violet, side: const BorderSide(color: AirwayColors.borderStrong), shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12))),
              )),
              if (scheduled && items.length > 1)
                Align(alignment: Alignment.centerLeft, child: TextButton.icon(
                  onPressed: busy ? null : () => applyScheduleToAll(id),
                  icon: const Icon(Icons.copy_all_rounded, size: 16),
                  label: Text(airway_localization.AirwayText.tr('Apply this time to all services', 'यह समय सभी सेवाओं पर लागू करें')),
                  style: TextButton.styleFrom(foregroundColor: violet, visualDensity: VisualDensity.compact),
                )),
            ]),
          ),
        ),
      ]),
    );
  }

  Widget priceRow(String label, String value) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 4),
    child: Row(children: [
      Text(label, style: const TextStyle(color: sub)),
      const Spacer(),
      Text(value, style: const TextStyle(fontWeight: FontWeight.w800, color: ink, fontSize: 12)),
    ]),
  );

  Widget emptyState(String title, String message, IconData icon, VoidCallback action) => Center(
    child: Padding(
      padding: const EdgeInsets.all(28),
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        Icon(icon, size: 58, color: violet),
        const SizedBox(height: 16),
        Text(title, style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w900, color: ink)),
        const SizedBox(height: 8),
        Text(message, textAlign: TextAlign.center, style: const TextStyle(color: sub)),
        const SizedBox(height: 18),
        FilledButton(onPressed: action, child: Text(airway_localization.AirwayText.tr('Continue', 'जारी रखें'))),
      ]),
    ),
  );
}
