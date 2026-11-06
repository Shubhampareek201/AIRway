import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:airway/features/booking/data/booking_api.dart';
import 'package:airway/features/booking/data/booking_models.dart';

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
      if (mounted) setState(() { bookings = result; loading = false; });
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
    try {
      final result = await BookingApi.trackBooking(booking.id);
      if (!mounted) return;
      setState(() => trackingId = null);
      final assigned = result['is_assigned'] == true;
      await showModalBottomSheet<void>(
        context: context,
        showDragHandle: true,
        backgroundColor: Colors.white,
        builder: (ctx) => Padding(
          padding: const EdgeInsets.fromLTRB(22, 8, 22, 28),
          child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
            const Text('Service tracking', style: TextStyle(fontSize: 20, fontWeight: FontWeight.w900, color: ink)),
            const SizedBox(height: 14),
            Text('Booking #' + booking.id.toString() + ' • ' + booking.serviceTitle, style: const TextStyle(fontWeight: FontWeight.w700, color: ink)),
            const SizedBox(height: 12),
            if (assigned) ...[
              const Text('Professional assigned', style: TextStyle(color: sub)),
              const SizedBox(height: 6),
              Text(result['worker_name']?.toString() ?? 'Service professional', style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800, color: violet)),
              if (result['worker_phone'] != null) Text(result['worker_phone'].toString(), style: const TextStyle(color: sub)),
              if (result['worker_rating'] != null) Text('Rating: ' + result['worker_rating'].toString(), style: const TextStyle(color: sub)),
              const SizedBox(height: 10),
              Text('Status: ' + BookingStatus.display(result['status']?.toString() ?? booking.status), style: const TextStyle(fontWeight: FontWeight.w700, color: ink)),
            ] else
              const Text('We are finding an available professional for your service. Please check again shortly.', style: TextStyle(color: sub, height: 1.4)),
            const SizedBox(height: 18),
            SizedBox(width: double.infinity, child: FilledButton(onPressed: () => Navigator.pop(ctx), child: const Text('Done'))),
          ]),
        ),
      );
    } catch (e) {
      if (mounted) {
        setState(() => trackingId = null);
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Could not load tracking: ' + e.toString())));
      }
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
        : bookings.isEmpty
          ? empty('No bookings yet', 'Your upcoming and completed services will appear here.', Icons.event_note_rounded, () => Navigator.pop(context))
          : RefreshIndicator(
              color: violet,
              onRefresh: loadBookings,
              child: ListView.separated(
                padding: const EdgeInsets.all(18),
                itemCount: bookings.length,
                separatorBuilder: (_, _) => const SizedBox(height: 12),
                itemBuilder: (context, index) => bookingCard(bookings[index]),
              ),
            ),
  );

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
