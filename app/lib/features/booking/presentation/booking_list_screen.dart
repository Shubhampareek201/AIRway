import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:airway/features/booking/data/booking_api.dart';
import 'package:airway/features/booking/data/booking_models.dart';
import 'package:airway/features/booking/presentation/customer_order_screen.dart';
import 'package:airway/features/booking/presentation/booking_tracking_screen.dart';
import 'package:airway/core/localization/airway_text.dart';

class BookingListScreen extends StatefulWidget {
  final VoidCallback? onBookNew;
  final VoidCallback? onBack;
  const BookingListScreen({super.key, this.onBookNew, this.onBack});
  @override
  State<BookingListScreen> createState() => _BookingListScreenState();
}

class _BookingListScreenState extends State<BookingListScreen> {
  static const green = Color(0xFF0B5D3B);
  static const greenDark = Color(0xFF064A2E);
  static const greenSoft = Color(0xFFE3F2E9);
  static const ink = Color(0xFF14211B);
  static const sub = Color(0xFF6B7A72);
  static const bg = Color(0xFFF1F4F2);
  static const line = Color(0xFFE8EEEA);

  List<Booking> bookings = [];
  List<Map<String, dynamic>> orders = [];
  bool loading = true;
  String? error;
  int? trackingId;
  String selectedFilter = 'all';

  @override
  void initState() {
    super.initState();
    loadBookings();
  }

  Future<void> loadBookings() async {
    if (mounted) setState(() { loading = true; error = null; });
    try {
      final result = await BookingApi.listBookings();
      List<Map<String, dynamic>> parentOrders = [];
      try {
        parentOrders = await BookingApi.listOrders();
      } catch (_) {
        // Keep individual bookings visible if the parent-order endpoint is unavailable.
      }
      if (mounted) setState(() {
        bookings = result;
        orders = parentOrders;
        loading = false;
      });
    } catch (e) {
      if (mounted) setState(() { error = e.toString(); loading = false; });
    }
  }

  bool _isHistoryStatus(String status) => const {
    BookingStatus.completed, BookingStatus.cancelled, BookingStatus.disputed,
    'refunded', 'failed', 'closed',
  }.contains(status.toLowerCase());

  bool _matchesFilter(String status) {
    if (selectedFilter == 'all') return true;
    final history = _isHistoryStatus(status);
    return selectedFilter == 'history' ? history : !history;
  }

  List<Booking> get filteredBookings => bookings
      .where((b) => _matchesFilter(b.status)).toList()
    ..sort((a, b) => b.scheduledAt.compareTo(a.scheduledAt));

  List<Map<String, dynamic>> get filteredOrders => orders
      .where((o) => _matchesFilter(o['status']?.toString() ?? '')).toList()
    ..sort((a, b) => _orderDate(b).compareTo(_orderDate(a)));

  DateTime _orderDate(Map<String, dynamic> order) =>
      DateTime.tryParse(order['scheduled_at']?.toString() ?? '') ??
      DateTime.tryParse(order['created_at']?.toString() ?? '') ??
      DateTime.fromMillisecondsSinceEpoch(0);

  Color statusColor(String status) {
    switch (status.toLowerCase()) {
      case BookingStatus.completed:
      case 'paid': return const Color(0xFF2E7D52);
      case BookingStatus.cancelled:
      case BookingStatus.disputed:
      case 'failed':
      case 'refunded': return const Color(0xFFB42318);
      case BookingStatus.inProgress: return const Color(0xFFB7791F);
      default: return green;
    }
  }

  String localizedStatus(String status) {
    switch (status) {
      case BookingStatus.completed: return AirwayText.tr('Completed', 'पूर्ण');
      case BookingStatus.cancelled: return AirwayText.tr('Cancelled', 'रद्द');
      case BookingStatus.disputed: return AirwayText.tr('Disputed', 'विवादित');
      case BookingStatus.inProgress: return AirwayText.tr('In progress', 'जारी');
      case BookingStatus.pending: return AirwayText.tr('Pending', 'लंबित');
      case BookingStatus.confirmed: return AirwayText.tr('Confirmed', 'पुष्ट');
      case BookingStatus.assigned: return AirwayText.tr('Assigned', 'असाइन');
      case 'paid': return AirwayText.tr('Paid', 'भुगतान हो गया');
      case 'refunded': return AirwayText.tr('Refunded', 'रिफंड हो गया');
      case 'failed': return AirwayText.tr('Payment failed', 'भुगतान विफल');
      default: return BookingStatus.display(status);
    }
  }

  Future<void> track(Booking booking) async {
    setState(() => trackingId = booking.id);
    try {
      await Navigator.of(context).push<void>(MaterialPageRoute(
        builder: (_) => BookingTrackingScreen(
          bookingId: booking.id,
          serviceTitle: booking.serviceTitle,
          initialStatus: booking.status,
        ),
      ));
    } finally {
      if (mounted) {
        setState(() => trackingId = null);
        await loadBookings();
      }
    }
  }

  void _goBack() {
    if (widget.onBack != null) {
      widget.onBack!.call();
    } else {
      Navigator.of(context).maybePop();
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    backgroundColor: bg,
    appBar: AppBar(
      automaticallyImplyLeading: false,
      centerTitle: true,
      elevation: 0,
      backgroundColor: bg,
      foregroundColor: ink,
      title: Text(AirwayText.tr('My Bookings', 'मेरी बुकिंग'),
        style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700, color: ink)),
      leading: IconButton(
        tooltip: AirwayText.tr('Back', 'वापस'),
        onPressed: _goBack,
        icon: Container(width: 35, height: 35,
          decoration: BoxDecoration(color: Colors.white, shape: BoxShape.circle, border: Border.all(color: line)),
          child: const Icon(Icons.arrow_back_ios_new_rounded, size: 15, color: ink)),
      ),
      actions: [IconButton(
        tooltip: AirwayText.tr('Refresh bookings', 'बुकिंग रीफ़्रेश करें'),
        onPressed: loading ? null : loadBookings,
        icon: const Icon(Icons.refresh_rounded, color: green),
      )],
    ),
    body: Column(children: [
      _filterTabs(),
      Expanded(child: loading
        ? const Center(child: CircularProgressIndicator(color: green))
        : error != null
          ? _emptyState(
              AirwayText.tr('Unable to load bookings', 'बुकिंग लोड नहीं हो सकीं'),
              AirwayText.tr('Please check your connection and try again.', 'कृपया कनेक्शन जाँचें और फिर कोशिश करें।'),
              Icons.cloud_off_rounded, loadBookings)
          : RefreshIndicator(
              color: green,
              onRefresh: loadBookings,
              child: ListView(
                physics: const AlwaysScrollableScrollPhysics(),
                padding: const EdgeInsets.fromLTRB(18, 2, 18, 22),
                children: [
                  _promoBanner(),
                  if (filteredOrders.isEmpty && filteredBookings.isEmpty)
                    _emptyState(
                      selectedFilter == 'history'
                        ? AirwayText.tr('No booking history', 'बुकिंग इतिहास नहीं है')
                        : selectedFilter == 'upcoming'
                          ? AirwayText.tr('Nothing upcoming yet', 'अभी कोई आगामी बुकिंग नहीं है')
                          : AirwayText.tr('No bookings yet', 'अभी कोई बुकिंग नहीं है'),
                      AirwayText.tr('Your upcoming, active and completed services will appear here.', 'आपकी आने वाली, चालू और पूरी हो चुकी सेवाएँ यहाँ दिखाई देंगी।'),
                      Icons.event_note_rounded, widget.onBookNew ?? _goBack)
                  else ...[
                    if (filteredOrders.isNotEmpty) ...[
                      _sectionLabel(AirwayText.tr('Service Orders', 'सेवा ऑर्डर')),
                      for (final order in filteredOrders) ...[orderCard(order), const SizedBox(height: 11)],
                      const SizedBox(height: 7),
                    ],
                    if (filteredBookings.isNotEmpty) ...[
                      _sectionLabel(AirwayText.tr('Individual Services', 'अलग-अलग सेवाएँ')),
                      for (final booking in filteredBookings) ...[bookingCard(booking), const SizedBox(height: 12)],
                    ],
                  ],
                ],
              ),
            )),
      SafeArea(
        top: false,
        minimum: const EdgeInsets.fromLTRB(18, 8, 18, 14),
        child: SizedBox(width: double.infinity, child: FilledButton.icon(
          onPressed: widget.onBookNew ?? _goBack,
          icon: const Icon(Icons.calendar_month_rounded, size: 19),
          label: Text(AirwayText.tr('Book a Service', 'सेवा बुक करें')),
          style: FilledButton.styleFrom(
            backgroundColor: green, foregroundColor: Colors.white,
            padding: const EdgeInsets.symmetric(vertical: 16),
            textStyle: const TextStyle(fontSize: 14, fontWeight: FontWeight.w700),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(30)),
            elevation: 2,
          ),
        )),
      ),
    ]),
  );

  Widget _filterTabs() {
    final tabs = [
      ('all', AirwayText.tr('All Bookings', 'सभी बुकिंग')),
      ('upcoming', AirwayText.tr('Upcoming', 'आगामी')),
      ('history', AirwayText.tr('History', 'इतिहास')),
    ];
    return Container(
      margin: const EdgeInsets.fromLTRB(18, 4, 18, 13),
      padding: const EdgeInsets.all(3),
      decoration: BoxDecoration(color: const Color(0xFFE8ECE9), borderRadius: BorderRadius.circular(12)),
      child: Row(children: [
        for (final tab in tabs)
          Expanded(child: GestureDetector(
            onTap: () => setState(() => selectedFilter = tab.$1),
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 160),
              padding: const EdgeInsets.symmetric(vertical: 10),
              decoration: BoxDecoration(
                color: selectedFilter == tab.$1 ? green : Colors.transparent,
                borderRadius: BorderRadius.circular(10)),
              alignment: Alignment.center,
              child: Text(tab.$2, maxLines: 1, style: TextStyle(
                color: selectedFilter == tab.$1 ? Colors.white : sub,
                fontSize: 11.5,
                fontWeight: selectedFilter == tab.$1 ? FontWeight.w700 : FontWeight.w500)),
            ),
          )),
      ]),
    );
  }

  Widget _promoBanner() => Container(
    margin: const EdgeInsets.only(bottom: 15),
    padding: const EdgeInsets.fromLTRB(15, 15, 12, 13),
    decoration: BoxDecoration(
      gradient: const LinearGradient(colors: [Color(0xFFE3F2E9), Color(0xFFF3FAF5)]),
      borderRadius: BorderRadius.circular(15)),
    child: Row(children: [
      Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(AirwayText.tr('A happier home starts here', 'खुशहाल घर की शुरुआत यहाँ से'),
          style: const TextStyle(fontSize: 16, height: 1.2, fontWeight: FontWeight.w800, color: greenDark)),
        const SizedBox(height: 6),
        Text(AirwayText.tr('Manage your services and book again whenever you need.', 'अपनी सेवाएँ संभालें और ज़रूरत पड़ने पर दोबारा बुक करें।'),
          style: const TextStyle(fontSize: 11.5, height: 1.35, color: sub)),
      ])),
      const SizedBox(width: 8),
      Container(width: 75, height: 68,
        decoration: BoxDecoration(color: Colors.white.withValues(alpha: 0.65), shape: BoxShape.circle),
        child: const Icon(Icons.home_work_rounded, size: 39, color: Color(0xFF39815A))),
    ]),
  );

  Widget _sectionLabel(String title) => Padding(
    padding: const EdgeInsets.fromLTRB(1, 2, 1, 10),
    child: Text(title, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w800, color: ink)));

  Widget orderCard(Map<String, dynamic> order) {
    final id = int.tryParse(order['id']?.toString() ?? '');
    final statusValue = order['status']?.toString() ?? '';
    final ready = order['ready_for_payment'] == true;
    final paid = statusValue == 'paid';
    final total = double.tryParse(order['total_amount']?.toString() ?? '') ?? 0;
    final status = paid
      ? AirwayText.tr('Paid', 'भुगतान हो गया')
      : ready
        ? AirwayText.tr('Ready for payment', 'भुगतान के लिए तैयार')
        : AirwayText.tr('Assigning professionals', 'प्रोफ़ेशनल असाइन किए जा रहे हैं');
    final color = statusColor(statusValue);
    return Material(
      color: Colors.white,
      borderRadius: BorderRadius.circular(16),
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: id == null ? null : () => Navigator.push(context,
          MaterialPageRoute(builder: (_) => CustomerOrderScreen(orderId: id))),
        child: Container(
          padding: const EdgeInsets.all(13),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(16), border: Border.all(color: line),
            boxShadow: const [BoxShadow(color: Color(0x0714211B), blurRadius: 8, offset: Offset(0, 2))]),
          child: Row(children: [
            Container(width: 42, height: 42,
              decoration: const BoxDecoration(color: greenSoft, shape: BoxShape.circle),
              child: const Icon(Icons.home_repair_service_rounded, color: green, size: 21)),
            const SizedBox(width: 12),
            Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [
                Expanded(child: Text(AirwayText.tr('Order #$id', 'ऑर्डर #$id'),
                  style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w800, color: ink))),
                _statusPill(status, color),
              ]),
              const SizedBox(height: 5),
              Text(AirwayText.tr('${order['item_count'] ?? 0} services', '${order['item_count'] ?? 0} सेवाएँ'),
                style: const TextStyle(fontSize: 11.5, color: sub)),
              const SizedBox(height: 5),
              Text('₹${total.toStringAsFixed(0)}',
                style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w800, color: green)),
            ])),
            const SizedBox(width: 4),
            const Icon(Icons.chevron_right_rounded, color: sub),
          ]),
        ),
      ),
    );
  }

  Widget bookingCard(Booking booking) {
    final status = localizedStatus(booking.status);
    final color = statusColor(booking.status);
    final scheduled = booking.scheduledAt.toLocal();
    final date = DateFormat('EEE, dd MMM yyyy').format(scheduled);
    final time = DateFormat('hh:mm a').format(scheduled);
    final worker = booking.assignment;
    return Material(
      color: Colors.white,
      borderRadius: BorderRadius.circular(16),
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: trackingId == booking.id ? null : () => track(booking),
        child: Container(
          padding: const EdgeInsets.all(13),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(16), border: Border.all(color: line),
            boxShadow: const [BoxShadow(color: Color(0x0714211B), blurRadius: 8, offset: Offset(0, 2))]),
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Container(width: 40, height: 40, margin: const EdgeInsets.only(top: 12),
              decoration: const BoxDecoration(color: greenSoft, shape: BoxShape.circle),
              child: const Icon(Icons.home_repair_service_rounded, color: green, size: 20)),
            const SizedBox(width: 12),
            Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [
                _statusPill(status, color),
                const Spacer(),
                Text('#${booking.id}', style: const TextStyle(fontSize: 10.5, color: sub)),
              ]),
              const SizedBox(height: 8),
              Text(booking.serviceTitle, maxLines: 2, overflow: TextOverflow.ellipsis,
                style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w800, color: ink)),
              if (booking.variantTitle?.isNotEmpty == true)
                Padding(padding: const EdgeInsets.only(top: 2),
                  child: Text(booking.variantTitle!, style: const TextStyle(fontSize: 11.5, color: sub))),
              const SizedBox(height: 9),
              Row(children: [
                const Icon(Icons.calendar_today_outlined, size: 14, color: green),
                const SizedBox(width: 7),
                Expanded(child: Text(date, style: const TextStyle(fontSize: 11.5, color: sub))),
              ]),
              const SizedBox(height: 5),
              Row(children: [
                const Icon(Icons.schedule_rounded, size: 14, color: green),
                const SizedBox(width: 7),
                Expanded(child: Text(time, style: const TextStyle(fontSize: 11.5, color: sub))),
                Text('₹${booking.totalAmount.toStringAsFixed(0)}',
                  style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w800, color: ink)),
              ]),
              if (worker != null) ...[
                const SizedBox(height: 9),
                Row(children: [
                  CircleAvatar(radius: 14, backgroundColor: greenSoft,
                    backgroundImage: worker.workerPhoto?.isNotEmpty == true ? NetworkImage(worker.workerPhoto!) : null,
                    child: worker.workerPhoto?.isNotEmpty == true ? null : const Icon(Icons.person_rounded, size: 16, color: green)),
                  const SizedBox(width: 8),
                  Expanded(child: Text(worker.workerName, maxLines: 1, overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontSize: 11.5, fontWeight: FontWeight.w700, color: ink))),
                  const Icon(Icons.chevron_right_rounded, size: 18, color: sub),
                ]),
              ],
              const SizedBox(height: 10),
              Align(alignment: Alignment.centerRight,
                child: Text(AirwayText.tr('View tracking  ›', 'ट्रैकिंग देखें  ›'),
                  style: const TextStyle(fontSize: 11.5, fontWeight: FontWeight.w700, color: green))),
            ])),
          ]),
        ),
      ),
    );
  }

  Widget _statusPill(String text, Color color) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
    decoration: BoxDecoration(color: color.withValues(alpha: 0.11), borderRadius: BorderRadius.circular(8)),
    child: Text(text, maxLines: 1, overflow: TextOverflow.ellipsis,
      style: TextStyle(fontSize: 10, fontWeight: FontWeight.w700, color: color)));

  Widget _emptyState(String title, String message, IconData icon, VoidCallback action) => Padding(
    padding: const EdgeInsets.fromLTRB(16, 36, 16, 24),
    child: Column(mainAxisSize: MainAxisSize.min, children: [
      Container(width: 68, height: 68,
        decoration: const BoxDecoration(color: greenSoft, shape: BoxShape.circle),
        child: Icon(icon, size: 32, color: green)),
      const SizedBox(height: 15),
      Text(title, textAlign: TextAlign.center,
        style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w800, color: ink)),
      const SizedBox(height: 7),
      Text(message, textAlign: TextAlign.center,
        style: const TextStyle(fontSize: 12, height: 1.4, color: sub)),
      const SizedBox(height: 16),
      TextButton(onPressed: action,
        child: Text(AirwayText.tr('Try again', 'फिर कोशिश करें'),
          style: const TextStyle(color: green, fontWeight: FontWeight.w700))),
    ]),
  );
}
