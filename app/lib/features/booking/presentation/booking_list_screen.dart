import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:airway/features/booking/data/booking_api.dart';
import 'package:airway/features/booking/data/booking_models.dart';
import 'package:airway/features/booking/presentation/customer_order_screen.dart';
import 'package:airway/features/booking/presentation/booking_tracking_screen.dart';

class BookingListScreen extends StatefulWidget {
  const BookingListScreen({super.key});
  @override
  State<BookingListScreen> createState() => _BookingListScreenState();
}

class _BookingListScreenState extends State<BookingListScreen> {
  static const violet = Color(0xFF7861A8);
  static const ink = Color(0xFF292331);
  static const sub = Color(0xFF81788A);
  static const bg = Color(0xFFF7F3EC);
  static const pale = Color(0xFFEDE7F5);
  static const line = Color(0xFFE8E0ED);

  List<Booking> bookings = [];
  List<Map<String, dynamic>> orders = [];
  bool loading = true;
  String? error;
  int? trackingId;

  @override
  void initState() {
    super.initState();
    loadBookings();
  }

  Future<void> loadBookings() async {
    setState(() { loading = true; error = null; });
    try {
      final result = await BookingApi.listBookings();
      List<Map<String, dynamic>> parentOrders = [];
      try { parentOrders = await BookingApi.listOrders(); } catch (_) {}
      if (mounted) setState(() { bookings = result; orders = parentOrders; loading = false; });
    } catch (e) {
      if (mounted) setState(() { error = e.toString(); loading = false; });
    }
  }

  Color statusColor(String status) {
    switch (status) {
      case BookingStatus.completed: return const Color(0xFF2E7D52);
      case BookingStatus.cancelled:
      case BookingStatus.disputed: return Colors.redAccent;
      case BookingStatus.inProgress: return const Color(0xFFB7791F);
      default: return violet;
    }
  }

  Future<void> track(Booking booking) async {
    setState(() => trackingId = booking.id);
    await Navigator.of(context).push<void>(
      MaterialPageRoute(
        builder: (_) => BookingTrackingScreen(
          bookingId: booking.id,
          serviceTitle: booking.serviceTitle,
          initialStatus: booking.status,
        ),
      ),
    );
    if (mounted) {
      setState(() => trackingId = null);
      await loadBookings();
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    backgroundColor: bg,
    appBar: AppBar(
      title: const Text('My Bookings'),
      backgroundColor: bg,
      actions: [IconButton(onPressed: loading ? null : loadBookings, icon: const Icon(Icons.refresh_rounded))],
    ),
    body: loading
      ? const Center(child: CircularProgressIndicator(color: violet))
      : error != null
        ? empty('Unable to load bookings', error!, Icons.error_outline, loadBookings)
        : bookings.isEmpty && orders.isEmpty
          ? empty('No bookings yet', 'Your upcoming and completed services will appear here.', Icons.event_note_rounded, () => Navigator.pop(context))
          : RefreshIndicator(
              color: violet,
              onRefresh: loadBookings,
              child: ListView(
                padding: const EdgeInsets.all(18),
                children: [
                  if (orders.isNotEmpty) ...[
                    const Text('Service Orders', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w900, color: ink)),
                    const SizedBox(height: 10),
                    for (final order in orders) ...[orderCard(order), const SizedBox(height: 10)],
                    const SizedBox(height: 12),
                  ],
                  if (bookings.isNotEmpty) ...[
                    const Text('Individual Services', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w900, color: ink)),
                    const SizedBox(height: 10),
                    for (final booking in bookings) ...[bookingCard(booking), const SizedBox(height: 12)],
                  ],
                ],
              ),
            ),
  );

  Widget orderCard(Map<String, dynamic> order) {
    final id = order['id'] as int;
    final ready = order['ready_for_payment'] == true;
    final paid = order['status'] == 'paid';
    final total = double.tryParse(order['total_amount']?.toString() ?? '') ?? 0;
    final status = paid ? 'Paid' : ready ? 'Ready for payment' : 'Assigning professionals';
    return InkWell(
      borderRadius: BorderRadius.circular(18),
      onTap: () => Navigator.push(context, MaterialPageRoute(builder: (_) => CustomerOrderScreen(orderId: id))),
      child: Container(
        padding: const EdgeInsets.all(15),
        decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(18), border: Border.all(color: line)),
        child: Row(children: [
          Container(width: 44, height: 44, decoration: BoxDecoration(color: pale, borderRadius: BorderRadius.circular(12)),
            child: const Icon(Icons.shopping_bag_outlined, color: violet)),
          const SizedBox(width: 12),
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('Order #' + id.toString(), style: const TextStyle(fontWeight: FontWeight.w900, color: ink)),
            Text((order['item_count'] ?? 0).toString() + ' services • ' + status, style: const TextStyle(fontSize: 12, color: sub)),
          ])),
          Text('₹' + total.toStringAsFixed(0), style: const TextStyle(fontWeight: FontWeight.w900, color: violet)),
          const Icon(Icons.chevron_right_rounded, color: sub),
        ]),
      ),
    );
  }

  Widget bookingCard(Booking booking) {
    final status = BookingStatus.display(booking.status);
    final color = statusColor(booking.status);
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(18), border: Border.all(color: line)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Container(width: 46, height: 46, decoration: BoxDecoration(color: pale, borderRadius: BorderRadius.circular(13)),
            child: const Icon(Icons.home_repair_service_outlined, color: violet)),
          const SizedBox(width: 12),
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(booking.serviceTitle, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w900, color: ink)),
            Text('Booking #' + booking.id.toString(), style: const TextStyle(fontSize: 11, color: sub)),
          ])),
          Container(padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
            decoration: BoxDecoration(color: color.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(20)),
            child: Text(status, style: TextStyle(color: color, fontSize: 11, fontWeight: FontWeight.w800))),
        ]),
        const Divider(height: 22),
        Row(children: [
          const Icon(Icons.calendar_today_outlined, size: 15, color: sub),
          const SizedBox(width: 7),
          Expanded(child: Text(DateFormat('dd MMM yyyy, hh:mm a').format(booking.scheduledAt.toLocal()), style: const TextStyle(color: sub, fontSize: 12))),
          Text('₹' + booking.totalAmount.toStringAsFixed(0), style: const TextStyle(fontWeight: FontWeight.w900, color: ink)),
        ]),
        if (booking.assignment != null) ...[
          const SizedBox(height: 8),
          Row(children: [
            const Icon(Icons.person_outline_rounded, size: 16, color: violet),
            const SizedBox(width: 7),
            Text(booking.assignment!.workerName, style: const TextStyle(fontWeight: FontWeight.w700, color: ink, fontSize: 12)),
          ]),
        ],
        const SizedBox(height: 12),
        SizedBox(width: double.infinity, child: OutlinedButton.icon(
          onPressed: trackingId == booking.id ? null : () => track(booking),
          icon: trackingId == booking.id
              ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
              : const Icon(Icons.location_searching_rounded, size: 17),
          label: const Text('Track Service'),
        )),
      ]),
    );
  }

  Widget empty(String title, String message, IconData icon, VoidCallback action) => Center(
    child: Padding(
      padding: const EdgeInsets.all(28),
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        Icon(icon, size: 58, color: violet),
        const SizedBox(height: 16),
        Text(title, style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w900, color: ink)),
        const SizedBox(height: 8),
        Text(message, textAlign: TextAlign.center, style: const TextStyle(color: sub)),
        const SizedBox(height: 18),
        FilledButton(onPressed: action, child: const Text('Retry')),
      ]),
    ),
  );
}
