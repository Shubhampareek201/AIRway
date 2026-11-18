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
  static const bg = Colors.white;
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

  String _bookingCategory(String status) {
    final value = status.toLowerCase();
    if (_isHistoryStatus(value)) return 'history';
    if (value == BookingStatus.inProgress) return 'in_progress';
    return 'upcoming';
  }

  bool _matchesSelectedCategory(String category) =>
      selectedFilter == 'all' || selectedFilter == category;

  List<Booking> get filteredBookings => bookings
      .where((booking) =>
          booking.orderId == null &&
          _matchesSelectedCategory(_bookingCategory(booking.status)))
      .toList()
    ..sort((a, b) => b.scheduledAt.compareTo(a.scheduledAt));

  String _orderCategory(Map<String, dynamic> order) {
    final statuses = (order['items'] as List? ?? [])
        .whereType<Map>()
        .map((item) => item['status']?.toString().toLowerCase() ?? '')
        .where((status) => status.isNotEmpty)
        .toList();
    if (statuses.isEmpty) {
      return _bookingCategory(order['status']?.toString() ?? '');
    }
    if (statuses.any((status) => status == BookingStatus.inProgress)) {
      return 'in_progress';
    }
    if (statuses.every(_isHistoryStatus)) return 'history';
    return 'upcoming';
  }

  List<Map<String, dynamic>> get filteredOrders => orders
      .where((order) => _matchesSelectedCategory(_orderCategory(order)))
      .toList()
    ..sort((a, b) => _orderDate(b).compareTo(_orderDate(a)));

  DateTime _orderDate(Map<String, dynamic> order) {
    final scheduled = (order['items'] as List? ?? [])
        .whereType<Map>()
        .map((item) => DateTime.tryParse(item['scheduled_at']?.toString() ?? ''))
        .whereType<DateTime>()
        .toList()
      ..sort();
    if (scheduled.isNotEmpty) return scheduled.first;
    return DateTime.tryParse(order['created_at']?.toString() ?? '') ??
        DateTime.fromMillisecondsSinceEpoch(0);
  }

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
                  _summaryStrip(),
                  if (filteredOrders.isEmpty && filteredBookings.isEmpty)
                    _emptyState(
                      selectedFilter == 'history'
                        ? AirwayText.tr('No booking history', 'बुकिंग इतिहास नहीं है')
                        : selectedFilter == 'in_progress'
                          ? AirwayText.tr('No services in progress', 'अभी कोई सेवा जारी नहीं है')
                          : selectedFilter == 'upcoming'
                            ? AirwayText.tr('Nothing upcoming yet', 'अभी कोई आगामी बुकिंग नहीं है')
                            : AirwayText.tr('No bookings yet', 'अभी कोई बुकिंग नहीं है'),
                      AirwayText.tr('Your upcoming, active and completed services will appear here.', 'आपकी आने वाली, चालू और पूरी हो चुकी सेवाएँ यहाँ दिखाई देंगी।'),
                      Icons.event_note_rounded, widget.onBookNew ?? _goBack,
                      actionLabel: AirwayText.tr('Book a service', 'सेवा बुक करें'))
                  else ...[
                    _sectionLabel(AirwayText.tr('Your bookings', 'आपकी बुकिंग')),
                    ..._bookingFeed(),
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
      ('all', AirwayText.tr('All', 'सभी')),
      ('upcoming', AirwayText.tr('Upcoming', 'आगामी')),
      ('in_progress', AirwayText.tr('In progress', 'जारी')),
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

  Widget _summaryStrip() {
    final individual = bookings.where((booking) => booking.orderId == null);
    final allCount = orders.length + individual.length;
    final upcomingCount = orders.where((order) => _orderCategory(order) == 'upcoming').length +
        individual.where((booking) => _bookingCategory(booking.status) == 'upcoming').length;
    final activeCount = orders.where((order) => _orderCategory(order) == 'in_progress').length +
        individual.where((booking) => _bookingCategory(booking.status) == 'in_progress').length;
    return Container(
      margin: const EdgeInsets.only(bottom: 14),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 13),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(15),
        border: Border.all(color: line),
      ),
      child: Row(children: [
        _summaryMetric('TOTAL', allCount.toString()),
        const Spacer(),
        _summaryMetric('UPCOMING', upcomingCount.toString()),
        const Spacer(),
        _summaryMetric('IN PROGRESS', activeCount.toString()),
      ]),
    );
  }

  Widget _summaryMetric(String label, String value) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text(value, style: const TextStyle(
        color: ink, fontSize: 18, fontWeight: FontWeight.w900,
      )),
      const SizedBox(height: 2),
      Text(label, style: const TextStyle(
        color: sub, fontSize: 8, fontWeight: FontWeight.w800,
        letterSpacing: .6,
      )),
    ],
  );

  Widget _sectionLabel(String title) => Padding(
    padding: const EdgeInsets.fromLTRB(1, 2, 1, 10),
    child: Text(title, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w800, color: ink)));

  List<Widget> _bookingFeed() {
    final entries = <({DateTime date, Widget child})>[];
    for (final order in filteredOrders) {
      entries.add((date: _orderDate(order), child: orderCard(order)));
    }
    for (final booking in filteredBookings) {
      entries.add((date: booking.scheduledAt, child: bookingCard(booking)));
    }
    entries.sort((a, b) => b.date.compareTo(a.date));
    return [
      for (final entry in entries) ...[
        entry.child,
        const SizedBox(height: 12),
      ],
    ];
  }

  Widget orderCard(Map<String, dynamic> order) {
    final id = int.tryParse(order['id']?.toString() ?? '');
    final total = double.tryParse(order['total_amount']?.toString() ?? '') ?? 0;
    final items = (order['items'] as List? ?? [])
        .whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item))
        .toList();
    final statuses = items
        .map((item) => item['status']?.toString().toLowerCase() ?? '')
        .where((status) => status.isNotEmpty)
        .toList();

    String serviceStatus;
    if (statuses.isNotEmpty && statuses.every((status) => status == BookingStatus.completed)) {
      serviceStatus = BookingStatus.completed;
    } else if (statuses.isNotEmpty && statuses.every((status) => status == BookingStatus.cancelled)) {
      serviceStatus = BookingStatus.cancelled;
    } else if (statuses.any((status) => status == BookingStatus.inProgress)) {
      serviceStatus = BookingStatus.inProgress;
    } else if (statuses.any((status) => status == BookingStatus.assigned)) {
      serviceStatus = BookingStatus.assigned;
    } else if (statuses.any((status) => status == BookingStatus.confirmed)) {
      serviceStatus = BookingStatus.confirmed;
    } else {
      serviceStatus = BookingStatus.pending;
    }

    String paymentStatus;
    Color paymentColor;
    if (order['ready_for_balance'] == true) {
      paymentStatus = AirwayText.tr('Balance due', 'शेष भुगतान बाकी');
      paymentColor = const Color(0xFFB7791F);
    } else if (order['ready_for_advance'] == true) {
      paymentStatus = AirwayText.tr('30% advance due', '30% अग्रिम बाकी');
      paymentColor = const Color(0xFFB7791F);
    } else if (order['balance_paid'] == true) {
      paymentStatus = AirwayText.tr('Fully paid', 'पूरा भुगतान');
      paymentColor = const Color(0xFF2E7D52);
    } else if (order['advance_paid'] == true) {
      paymentStatus = AirwayText.tr('Advance paid', 'अग्रिम भुगतान');
      paymentColor = const Color(0xFF2E7D52);
    } else {
      paymentStatus = AirwayText.tr('Payment pending', 'भुगतान लंबित');
      paymentColor = sub;
    }

    final orderDate = _orderDate(order);
    return Material(
      color: Colors.white,
      borderRadius: BorderRadius.circular(17),
      child: InkWell(
        borderRadius: BorderRadius.circular(17),
        onTap: id == null ? null : () => Navigator.push(
          context,
          MaterialPageRoute(builder: (_) => CustomerOrderScreen(orderId: id)),
        ),
        child: Container(
          padding: const EdgeInsets.all(15),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(17),
            border: Border.all(color: line),
            boxShadow: const [
              BoxShadow(color: Color(0x0714211B), blurRadius: 10, offset: Offset(0, 3)),
            ],
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(children: [
                Container(
                  width: 40,
                  height: 40,
                  decoration: const BoxDecoration(color: greenSoft, shape: BoxShape.circle),
                  child: const Icon(Icons.home_repair_service_rounded, color: green, size: 21),
                ),
                const SizedBox(width: 11),
                Expanded(child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(AirwayText.tr('Order #' + (id?.toString() ?? '—'), 'ऑर्डर #' + (id?.toString() ?? '—')),
                      style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w900, color: ink)),
                    if (orderDate.millisecondsSinceEpoch != 0)
                      Text(DateFormat('EEE, dd MMM yyyy • hh:mm a').format(orderDate.toLocal()),
                        style: const TextStyle(fontSize: 10.5, color: sub)),
                  ],
                )),
                const Icon(Icons.chevron_right_rounded, color: sub),
              ]),
              const SizedBox(height: 12),
              Wrap(
                spacing: 7,
                runSpacing: 6,
                children: [
                  _statusPill(localizedStatus(serviceStatus), statusColor(serviceStatus)),
                  _statusPill(paymentStatus, paymentColor),
                ],
              ),
              const SizedBox(height: 11),
              for (final item in items.take(3)) Padding(
                padding: const EdgeInsets.only(bottom: 7),
                child: Row(children: [
                  const Icon(Icons.circle, size: 5, color: green),
                  const SizedBox(width: 8),
                  Expanded(child: Text(
                    item['service_title']?.toString() ?? AirwayText.tr('Service', 'सेवा'),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontSize: 11.5, color: ink, fontWeight: FontWeight.w700),
                  )),
                  const SizedBox(width: 8),
                  Text(
                    localizedStatus(item['status']?.toString() ?? ''),
                    style: TextStyle(fontSize: 10, color: statusColor(item['status']?.toString() ?? ''), fontWeight: FontWeight.w700),
                  ),
                ]),
              ),
              if (items.length > 3)
                Padding(
                  padding: const EdgeInsets.only(bottom: 6),
                  child: Text(
                    AirwayText.tr(
                      '+ ' + (items.length - 3).toString() + ' more services',
                      '+ ' + (items.length - 3).toString() + ' अन्य सेवाएँ',
                    ),
                    style: const TextStyle(fontSize: 10.5, color: sub),
                  ),
                ),
              const Divider(height: 15, color: line),
              Row(children: [
                Expanded(child: Text(
                  AirwayText.tr(
                    items.length.toString() + ' services in this order',
                    'इस ऑर्डर में ' + items.length.toString() + ' सेवाएँ',
                  ),
                  style: const TextStyle(fontSize: 10.5, color: sub),
                )),
                Text('₹' + total.toStringAsFixed(0),
                  style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w900, color: ink)),
              ]),
            ],
          ),
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

  Widget _emptyState(String title, String message, IconData icon, VoidCallback action, {String? actionLabel}) => Padding(
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
        child: Text(actionLabel ?? AirwayText.tr('Try again', 'फिर कोशिश करें'),
          style: const TextStyle(color: green, fontWeight: FontWeight.w700))),
    ]),
  );
}
