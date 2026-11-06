import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:airway/features/booking/data/booking_api.dart';

class CustomerCartScreen extends StatefulWidget {
  const CustomerCartScreen({super.key});
  @override
  State<CustomerCartScreen> createState() => _CustomerCartScreenState();
}

class _CustomerCartScreenState extends State<CustomerCartScreen> {
  static const violet = Color(0xFF7861A8);
  static const ink = Color(0xFF292331);
  static const sub = Color(0xFF81788A);
  static const bg = Color(0xFFF7F3EC);
  static const pale = Color(0xFFEDE7F5);
  static const line = Color(0xFFE8E0ED);

  Map<String, dynamic>? cart;
  bool loading = true;
  bool busy = false;
  String? error;
  final Map<int, DateTime> dates = {};
  final Map<int, TimeOfDay> times = {};
  final Map<int, TimeOfDay> dropTimes = {};

  @override
  void initState() {
    super.initState();
    loadCart();
  }

  List<Map<String, dynamic>> get items => (cart?['items'] as List? ?? [])
      .whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList();

  double number(dynamic value) => double.tryParse(value?.toString() ?? '') ?? 0;

  Future<void> loadCart() async {
    setState(() { loading = true; error = null; });
    try {
      final value = await BookingApi.getCart();
      final tomorrow = DateTime.now().add(const Duration(days: 1));
      for (final row in (value['items'] as List? ?? []).whereType<Map>()) {
        final id = row['id'] as int;
        dates.putIfAbsent(id, () => DateTime(tomorrow.year, tomorrow.month, tomorrow.day));
        times.putIfAbsent(id, () => const TimeOfDay(hour: 10, minute: 0));
        dropTimes.putIfAbsent(id, () => const TimeOfDay(hour: 14, minute: 0));
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
      if (mounted) setState(() { cart = value; busy = false; });
    } catch (e) {
      if (mounted) setState(() { busy = false; error = e.toString(); });
    }
  }

  Future<void> pickDate(int id) async {
    final now = DateTime.now();
    final initial = dates[id] ?? now.add(const Duration(days: 1));
    final value = await showDatePicker(
      context: context,
      initialDate: initial.isBefore(DateTime(now.year, now.month, now.day)) ? now : initial,
      firstDate: DateTime(now.year, now.month, now.day),
      lastDate: now.add(const Duration(days: 90)),
    );
    if (value != null) setState(() => dates[id] = value);
  }

  Future<void> pickTime(int id) async {
    final value = await showTimePicker(context: context, initialTime: times[id] ?? const TimeOfDay(hour: 10, minute: 0));
    if (value != null) setState(() => times[id] = value);
  }

  Future<void> checkout() async {
    if (items.isEmpty) return;
    if (cart?['address'] == null) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Please select a service address first.')));
      return;
    }
    setState(() => busy = true);
    try {
      final schedules = items.map((item) {
        final id = item['id'] as int;
        final date = dates[id] ?? DateTime.now().add(const Duration(days: 1));
        final time = times[id] ?? const TimeOfDay(hour: 10, minute: 0);
        final row = <String, dynamic>{
          'cart_item_id': id,
          'scheduled_at': DateTime(date.year, date.month, date.day, time.hour, time.minute).toIso8601String(),
        };
        if (item['booking_mode'] == 'pickup_drop') {
          final drop = dropTimes[id] ?? const TimeOfDay(hour: 14, minute: 0);
          if (drop.hour * 60 + drop.minute <= time.hour * 60 + time.minute) {
            throw Exception('Drop time must be later than pickup time for ' + (item['service_title']?.toString() ?? 'this service') + '.');
          }
          row['drop_scheduled_at'] = DateTime(date.year, date.month, date.day, drop.hour, drop.minute).toIso8601String();
        }
        return row;
      }).toList();
      final result = await BookingApi.checkoutCart(items: schedules);
      if (!mounted) return;
      setState(() => busy = false);
      await showDialog<void>(
        context: context,
        barrierDismissible: false,
        builder: (ctx) => AlertDialog(
          icon: const Icon(Icons.check_circle_rounded, color: violet, size: 48),
          title: const Text('Order placed'),
          content: Text(
            'Your order #' + result['order_id'].toString() +
            ' has been created. Service professionals will be assigned. Payment becomes available after all services are assigned.',
            textAlign: TextAlign.center,
          ),
          actions: [FilledButton(onPressed: () => Navigator.pop(ctx), child: const Text('Continue'))],
        ),
      );
      if (mounted) Navigator.pop(context);
    } catch (e) {
      if (mounted) {
        setState(() => busy = false);
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Checkout failed: ' + e.toString())));
      }
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    backgroundColor: bg,
    appBar: AppBar(
      title: const Text('Your Cart'),
      backgroundColor: bg,
      actions: [IconButton(onPressed: loading ? null : loadCart, icon: const Icon(Icons.refresh_rounded))],
    ),
    body: loading
      ? const Center(child: CircularProgressIndicator(color: violet))
      : error != null
        ? emptyState('Could not load your cart', error!, Icons.error_outline, loadCart)
        : items.isEmpty
          ? emptyState('Your cart is empty', 'Add a service to get started.', Icons.shopping_bag_outlined, () => Navigator.pop(context))
          : cartBody(),
  );

  Widget cartBody() {
    final subtotal = number(cart?['subtotal']);
    return Column(children: [
      Expanded(child: ListView(
        padding: const EdgeInsets.all(18),
        children: [
          addressCard(),
          const SizedBox(height: 16),
          Text(items.length.toString() + ' services in your cart', style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w900, color: ink)),
          const SizedBox(height: 12),
          for (final item in items) ...[itemCard(item), const SizedBox(height: 12)],
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(color: pale, borderRadius: BorderRadius.circular(18)),
            child: Column(children: [
              priceRow('Subtotal', '₹' + subtotal.toStringAsFixed(0)),
              priceRow('Taxes', 'Calculated at checkout'),
              const Divider(height: 20),
              priceRow('Payment', 'After service assignment'),
            ]),
          ),
        ],
      )),
      Container(
        padding: const EdgeInsets.fromLTRB(18, 12, 18, 18),
        decoration: const BoxDecoration(color: Colors.white, border: Border(top: BorderSide(color: line))),
        child: SafeArea(top: false, child: Row(children: [
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
            const Text('Cart subtotal', style: TextStyle(color: sub, fontSize: 12)),
            Text('₹' + subtotal.toStringAsFixed(0), style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w900, color: ink)),
          ])),
          Expanded(child: FilledButton(
            onPressed: busy ? null : checkout,
            child: busy ? const SizedBox(height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white)) : const Text('Place Order'),
          )),
        ])),
      ),
    ]);
  }

  Widget addressCard() => Container(
    padding: const EdgeInsets.all(15),
    decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(18), border: Border.all(color: line)),
    child: Row(children: [
      const CircleAvatar(backgroundColor: pale, child: Icon(Icons.location_on_outlined, color: violet)),
      const SizedBox(width: 12),
      Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text('Service address', style: TextStyle(fontWeight: FontWeight.w800, color: ink)),
        Text(cart?['address'] == null ? 'No address selected' : 'Saved address #' + cart!['address'].toString(), style: const TextStyle(color: sub, fontSize: 12)),
      ])),
      const Icon(Icons.check_circle, color: violet),
    ]),
  );

  Widget itemCard(Map<String, dynamic> item) {
    final id = item['id'] as int;
    final date = dates[id] ?? DateTime.now().add(const Duration(days: 1));
    final time = times[id] ?? const TimeOfDay(hour: 10, minute: 0);
    final snapshot = Map<String, dynamic>.from(item['pricing_snapshot'] ?? {});
    final addons = (snapshot['addons'] as List? ?? []);
    return Container(
      padding: const EdgeInsets.all(15),
      decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(18), border: Border.all(color: line)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Container(width: 44, height: 44, decoration: BoxDecoration(color: pale, borderRadius: BorderRadius.circular(12)), child: const Icon(Icons.home_repair_service_outlined, color: violet)),
          const SizedBox(width: 10),
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(item['service_title']?.toString() ?? 'Service', style: const TextStyle(fontWeight: FontWeight.w800, color: ink)),
            if ((item['variant_title'] ?? '').toString().isNotEmpty) Text(item['variant_title'].toString(), style: const TextStyle(fontSize: 12, color: sub)),
            Text('Qty ' + item['quantity'].toString() + ' • ₹' + number(item['line_total']).toStringAsFixed(0), style: const TextStyle(fontWeight: FontWeight.w800, color: violet, fontSize: 12)),
          ])),
          IconButton(onPressed: busy ? null : () => removeItem(id), icon: const Icon(Icons.delete_outline, color: Colors.redAccent)),
        ]),
        if (addons.isNotEmpty) ...[
          const Divider(height: 20),
          const Text('Add-ons', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 12, color: sub)),
          for (final addon in addons) Text('• ' + addon['title'].toString() + ' × ' + addon['quantity'].toString(), style: const TextStyle(fontSize: 12, color: ink)),
        ],
        const Divider(height: 20),
        const Text('Choose service date and time', style: TextStyle(fontWeight: FontWeight.w800, color: ink, fontSize: 13)),
        const SizedBox(height: 8),
        Row(children: [
          Expanded(child: OutlinedButton.icon(onPressed: () => pickDate(id), icon: const Icon(Icons.calendar_today_outlined, size: 15), label: Text(DateFormat('dd MMM yyyy').format(date)))),
          const SizedBox(width: 8),
          Expanded(child: OutlinedButton.icon(onPressed: () => pickTime(id), icon: const Icon(Icons.schedule_rounded, size: 15), label: Text(time.format(context)))),
        ]),
        if (item['booking_mode'] == 'pickup_drop') ...[
          const SizedBox(height: 8),
          OutlinedButton.icon(
            onPressed: () async {
              final value = await showTimePicker(context: context, initialTime: dropTimes[id] ?? const TimeOfDay(hour: 14, minute: 0));
              if (value != null) setState(() => dropTimes[id] = value);
            },
            icon: const Icon(Icons.flag_outlined, size: 15),
            label: Text('Drop-off: ' + (dropTimes[id] ?? const TimeOfDay(hour: 14, minute: 0)).format(context)),
          ),
        ],
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
        FilledButton(onPressed: action, child: const Text('Continue')),
      ]),
    ),
  );
}
