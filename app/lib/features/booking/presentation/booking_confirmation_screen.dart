import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:share_plus/share_plus.dart';
import 'package:cross_file/cross_file.dart';
import 'dart:typed_data';
import 'dart:convert';
import 'package:airway/core/localization/airway_text.dart';
import 'package:razorpay_flutter/razorpay_flutter.dart';
import 'package:airway/features/booking/data/booking_api.dart';
import 'package:airway/features/booking/data/booking_models.dart';
import 'package:airway/features/booking/presentation/booking_list_screen.dart';
import 'package:airway/features/payment/presentation/payment_result_screen.dart';

class _Ui {
  static const violet = Color(0xFF6F4EF6);
  static const ink = Color(0xFF201A33);
  static const sub = Color(0xFF78718B);
  static const bg = Color(0xFFF8F7FD);
  static const green = Color(0xFF20B779);
  static const line = Color(0xFFEAE5F5);
}

class BookingConfirmationScreen extends StatefulWidget {
  final int bookingId;

  const BookingConfirmationScreen({
    super.key,
    required this.bookingId,
  });

  @override
  State<BookingConfirmationScreen> createState() => _BookingConfirmationScreenState();
}

class _BookingConfirmationScreenState extends State<BookingConfirmationScreen> {
  Booking? _booking;
  bool _loading = true;
  String? _error;
  Map<String, dynamic>? _paymentOrder;
  late Razorpay _razorpay;

  @override
  void initState() {
    super.initState();
    _razorpay = Razorpay();
    _razorpay.on(Razorpay.EVENT_PAYMENT_SUCCESS, _handlePaymentSuccess);
    _razorpay.on(Razorpay.EVENT_PAYMENT_ERROR, _handlePaymentError);
    _razorpay.on(Razorpay.EVENT_EXTERNAL_WALLET, _handleExternalWallet);
    _loadBooking();
  }

  @override
  void dispose() {
    _razorpay.clear();
    super.dispose();
  }

  void _handlePaymentSuccess(PaymentSuccessResponse response) {
    // Send response to backend for verification
    _verifyPayment(response);
  }

  void _handlePaymentError(PaymentFailureResponse response) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(AirwayText.tr('Payment failed: ${response.message}', 'भुगतान विफल: ${response.message}'))));
  }

  void _handleExternalWallet(ExternalWalletResponse response) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(AirwayText.tr('External wallet: ${response.walletName}', 'बाहरी वॉलेट: ${response.walletName}'))));
  }

  Future<void> _verifyPayment(PaymentSuccessResponse response) async {
    if (!mounted) return;
    try {
      final result = await BookingApi.request(
        '/api/v1/payments/verify/',
        method: 'POST',
        data: {
          'razorpay_order_id': response.orderId,
          'razorpay_payment_id': response.paymentId,
          'razorpay_signature': response.signature,
        },
      );

      if (!mounted) return;

      // Navigate to payment result screen with verification result
      Navigator.of(context).push(
        MaterialPageRoute(
          builder: (_) => PaymentResultScreen(
            bookingId: widget.bookingId,
            razorpayOrderId: response.orderId,
            razorpayPaymentId: response.paymentId,
            razorpaySignature: response.signature,
            paymentAmount: double.tryParse(
              _paymentOrder?['stage_amount']?.toString() ?? '',
            ),
            verificationResult: result,
          ),
        ),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(AirwayText.tr('Payment verification failed: $e', 'भुगतान सत्यापन विफल: $e'))),
      );
    }
  }

  Future<void> _payNow() async {
    try {
      final order = await BookingApi.createRazorpayOrder(widget.bookingId);
      if (!mounted) return;
      setState(() => _paymentOrder = order);
      if (order['already_paid'] == true || order['fully_paid_by_wallet'] == true) {
        Navigator.of(context).push(MaterialPageRoute(
          builder: (_) => PaymentResultScreen(
            bookingId: widget.bookingId,
            paymentAmount: double.tryParse(order['stage_amount']?.toString() ?? ''),
            verificationResult: {
              ...order,
              'amount': order['stage_amount'] ?? order['amount'] ?? 0,
              'status': order['payment_status'] ?? 'paid',
            },
          ),
        ));
        return;
      }
      final keyId = order['key_id']?.toString() ?? '';
      final orderId = order['order_id']?.toString() ?? '';
      final amountPaise = int.tryParse(order['amount']?.toString() ?? '') ?? 0;
      if (keyId.isEmpty || orderId.isEmpty || amountPaise <= 0) {
        throw Exception('The server did not return a valid advance payment order.');
      }
      final options = {
        'key': keyId,
        'amount': amountPaise,
        'name': 'AIRway Booking',
        'order_id': orderId,
        'prefill': {'contact': '9876543210'}, // Should be customer phone
      };
      _razorpay.open(options);
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(AirwayText.tr('Error initiating payment: $e', 'भुगतान शुरू करने में त्रुटि: $e'))));
    }
  }

  Future<void> _loadBooking() async {
    setState(() {
      _loading = true;
      _error = null;
    });

    try {
      final booking = await BookingApi.getBooking(widget.bookingId);
      if (!mounted) return;
      setState(() {
        _booking = booking;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString();
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: _Ui.bg,
      appBar: AppBar(
        title: Text(AirwayText.tr('Booking Confirmed', 'बुकिंग की पुष्टि हो गई')),
        backgroundColor: _Ui.bg,
        automaticallyImplyLeading: false,
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: _Ui.violet))
          : _error != null
              ? _errorWidget(_error!)
              : _booking == null
                  ? _errorWidget('Booking not found.')
                  : _buildBody(),
    );
  }

  Widget _buildBody() {
    final booking = _booking!;

    return SingleChildScrollView(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _successHeader(),
          const SizedBox(height: 24),
          _bookingDetailsCard(booking),
          const SizedBox(height: 12),
          _calendarActionCard(booking),
          const SizedBox(height: 16),
          _pricingCard(booking),
          const SizedBox(height: 16),
          _addressCard(booking),
          const SizedBox(height: 16),
          _workerAssignmentCard(booking),
          const SizedBox(height: 24),
          _actionButtons(),
          const SizedBox(height: 20),
        ],
      ),
    );
  }

  Widget _successHeader() => Container(
        width: double.infinity,
        padding: const EdgeInsets.all(24),
        decoration: BoxDecoration(
          gradient: const LinearGradient(
            colors: [_Ui.violet, Color(0xFF8138B8)],
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
          ),
          borderRadius: BorderRadius.circular(24),
          boxShadow: [
            BoxShadow(
              color: _Ui.violet.withAlpha(45),
              blurRadius: 18,
              offset: const Offset(0, 7),
            ),
          ],
        ),
        child: Column(
          children: [
            Container(
              width: 80,
              height: 80,
              decoration: BoxDecoration(
                color: Colors.white.withAlpha(35),
                shape: BoxShape.circle,
              ),
              child: const Icon(
                Icons.check_circle_rounded,
                color: Colors.white,
                size: 40,
              ),
            ),
            const SizedBox(height: 16),
            const Text(
              'Booking Confirmed!',
              style: TextStyle(
                fontSize: 28,
                fontWeight: FontWeight.w900,
                color: Colors.white,
              ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 8),
            Text(
              'Your service has been scheduled successfully.',
              style: TextStyle(
                fontSize: 15,
                color: Colors.white.withAlpha(220),
              ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 12),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
              decoration: BoxDecoration(
                color: Colors.white.withAlpha(30),
                borderRadius: BorderRadius.circular(20),
              ),
              child: Text(
                'Booking ID: #${_booking!.id}',
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 13,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
          ],
        ),
      );

  Widget _bookingDetailsCard(Booking booking) => _card(
        'Booking Details',
        [
          _detailRow('Service', booking.serviceTitle),
          if (booking.variantTitle != null)
            _detailRow('Package', booking.variantTitle!),
          _detailRow('Date & Time', _formatDateTime(booking.scheduledAt)),
          if (booking.dropScheduledAt != null)
            _detailRow('Drop Time', _formatDateTime(booking.dropScheduledAt!)),
          _detailRow('Status', BookingStatus.display(booking.status)),
          _detailRow('Booking Mode', booking.bookingMode),
        ],
      );

  Widget _pricingCard(Booking booking) {
    final snapshot = booking.pricingSnapshot;
    double amount(String key) =>
        double.tryParse(snapshot[key]?.toString() ?? '') ?? 0;
    final subtotal = amount('subtotal');
    final discount = amount('campaign_discount_amount');
    final tax = amount('tax');
    final taxRate = snapshot['tax_rate']?.toString() ?? '18';
    final total = booking.totalAmount;
    final isInspection = booking.bookingMode == 'inspection';
    final previewAdvance = double.tryParse(
          snapshot['advance_amount']?.toString() ?? '',
        ) ?? (isInspection ? total : (total * 0.30 * 100).roundToDouble() / 100);
    final serverStageAmount = double.tryParse(
      _paymentOrder?['stage_amount']?.toString() ?? '',
    );
    final advance = serverStageAmount ?? previewAdvance;
    final balance = (total - advance).clamp(0.0, total).toDouble();

    return _card(
      'Pricing & Payment',
      [
        _detailRow('Service subtotal', '₹${subtotal.toStringAsFixed(2)}'),
        if (discount > 0)
          _detailRow('Campaign savings', '-₹${discount.toStringAsFixed(2)}'),
        if (tax > 0)
          _detailRow('Taxes (${taxRate}%)', '+₹${tax.toStringAsFixed(2)}'),
        _detailRow('Total after offer', '₹${total.toStringAsFixed(2)}', isTotal: true),
        const Divider(height: 20),
        _detailRow(
          serverStageAmount == null ? 'Advance due (30% estimate)' : 'Advance due now',
          '₹${advance.toStringAsFixed(2)}',
        ),
        _detailRow('Remaining balance (70%)', '₹${balance.toStringAsFixed(2)}'),
        if (serverStageAmount == null)
          const Padding(
            padding: EdgeInsets.only(top: 6),
            child: Text(
              'Final advance is confirmed by AIRway when payment is created.',
              style: TextStyle(color: _Ui.sub, fontSize: 12),
            ),
          ),
      ],
    );
  }

  Widget _addressCard(Booking booking) => _card(
        'Service Address',
        [
          _detailRow('Address', booking.pricingSnapshot['address_label'] ?? 'Service Address'),
        ],
        child: Padding(
          padding: const EdgeInsets.only(top: 8),
          child: Text(
            booking.pricingSnapshot['address_full'] ?? 'Address details will be available after assignment',
            style: const TextStyle(color: _Ui.sub, fontSize: 13, height: 1.4),
          ),
        ),
      );

  Widget _workerAssignmentCard(Booking booking) {
    if (booking.assignment == null) {
      return _card(
        'Worker Assignment',
        [
          _detailRow('Status', 'Finding a partner...'),
          _detailRow('Expected', 'A verified partner will be assigned shortly'),
        ],
        trailing: Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
          decoration: BoxDecoration(
            color: Colors.orange.shade50,
            borderRadius: BorderRadius.circular(20),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.access_time_rounded, size: 14, color: Colors.orange[700]),
              const SizedBox(width: 6),
              Text(
                'Pending Assignment',
                style: TextStyle(
                  color: Colors.orange[700],
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ),
        ),
      );
    }

    final assignment = booking.assignment!;
    return _card(
      'Assigned Partner',
      [
        _detailRow('Name', assignment.workerName),
        _detailRow('Phone', assignment.workerPhone),
        if (assignment.workerRating != null)
          _detailRow('Rating', '${assignment.workerRating!.toStringAsFixed(1)} ⭐'),
      ],
      trailing: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        decoration: BoxDecoration(
          color: _Ui.green.withAlpha(20),
          borderRadius: BorderRadius.circular(20),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.check_circle_rounded, size: 14, color: _Ui.green),
            const SizedBox(width: 6),
            Text(
              'Assigned',
              style: TextStyle(
                color: _Ui.green,
                fontSize: 12,
                fontWeight: FontWeight.w700,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _card(
    String title,
    List<Widget> rows, {
    Widget? trailing,
    Widget? child,
  }) =>
      Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: _Ui.line),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Text(
                  title,
                  style: const TextStyle(
                    fontSize: 17,
                    fontWeight: FontWeight.w800,
                    color: _Ui.ink,
                  ),
                ),
                const Spacer(),
                if (trailing != null) trailing,
              ],
            ),
            const SizedBox(height: 12),
            ...rows,
            if (child != null) child,
          ],
        ),
      );

  Widget _detailRow(String label, String value, {bool isTotal = false}) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 4),
        child: Row(
          children: [
            Expanded(
              child: Text(
                label,
                style: TextStyle(
                  fontSize: isTotal ? 16 : 14,
                  fontWeight: isTotal ? FontWeight.w700 : FontWeight.w500,
                  color: isTotal ? _Ui.ink : _Ui.sub,
                ),
              ),
            ),
            Text(
              value,
              style: TextStyle(
                fontSize: isTotal ? 18 : 14,
                fontWeight: isTotal ? FontWeight.w800 : FontWeight.w600,
                color: isTotal ? _Ui.violet : _Ui.ink,
              ),
            ),
          ],
        ),
      );


  Widget _calendarActionCard(Booking booking) => Card(
    color: Colors.white,
    child: ListTile(
      leading: const Icon(Icons.calendar_month_rounded, color: _Ui.ink, size: 30),
      title: const Text('Save to calendar', style: TextStyle(fontWeight: FontWeight.w800)),
      subtitle: const Text('Get a reminder before your service'),
      trailing: OutlinedButton(onPressed: () => _showCalendarOptions(booking), child: const Text('Add')),
    ),
  );

  Future<void> _showCalendarOptions(Booking booking) async {
    await showModalBottomSheet<void>(
      context: context, showDragHandle: true,
      builder: (sheet) => SafeArea(child: Column(mainAxisSize: MainAxisSize.min, children: [
        const ListTile(title: Text('Add booking to', style: TextStyle(fontWeight: FontWeight.w800))),
        ListTile(leading: const Icon(Icons.calendar_today), title: const Text('Google Calendar'),
          onTap: () { Navigator.pop(sheet); _openCalendar(booking, true); }),
        ListTile(leading: const Icon(Icons.calendar_month), title: const Text('Outlook Calendar'),
          onTap: () { Navigator.pop(sheet); _openCalendar(booking, false); }),
        ListTile(leading: const Icon(Icons.event), title: const Text('Apple Calendar / Other'),
          subtitle: const Text('Share calendar event file'),
          onTap: () { Navigator.pop(sheet); _shareCalendar(booking); }),
      ])),
    );
  }

  DateTime _calendarEnd(Booking booking) {
    final drop = booking.dropScheduledAt;
    return drop != null && drop.isAfter(booking.scheduledAt)
        ? drop : booking.scheduledAt.add(const Duration(hours: 1));
  }

  String _calendarUtc(DateTime value) {
    final d = value.toUtc();
    return '${d.year.toString().padLeft(4, '0')}${d.month.toString().padLeft(2, '0')}${d.day.toString().padLeft(2, '0')}T${d.hour.toString().padLeft(2, '0')}${d.minute.toString().padLeft(2, '0')}${d.second.toString().padLeft(2, '0')}Z';
  }

  String _calendarAddress(Booking booking) =>
      booking.pricingSnapshot['address_full']?.toString() ??
      booking.pricingSnapshot['address_label']?.toString() ?? '';

  String _calendarDetails(Booking booking) =>
      'AIRway booking #${booking.id}\\nService: ${booking.serviceTitle}';

  Future<void> _openCalendar(Booking booking, bool google) async {
    final start = booking.scheduledAt, end = _calendarEnd(booking);
    final title = 'AIRway • ${booking.serviceTitle}';
    final location = _calendarAddress(booking);
    final uri = google
      ? Uri.https('calendar.google.com', '/calendar/render', {
          'action': 'TEMPLATE', 'text': title,
          'dates': '${_calendarUtc(start)}/${_calendarUtc(end)}',
          'details': _calendarDetails(booking), if (location.isNotEmpty) 'location': location,
        })
      : Uri.https('outlook.live.com', '/calendar/0/deeplink/compose', {
          'subject': title, 'startdt': start.toUtc().toIso8601String(),
          'enddt': end.toUtc().toIso8601String(), 'body': _calendarDetails(booking),
          if (location.isNotEmpty) 'location': location,
        });
    try {
      final opened = await launchUrl(uri, mode: LaunchMode.externalApplication);
      if (!opened && mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Could not open calendar.')));
    } catch (error) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Calendar error: $error')));
    }
  }

  Future<void> _shareCalendar(Booking booking) async {
    String esc(String s) => s.replaceAll(r'\\', r'\\\\').replaceAll(',', r'\\,').replaceAll(';', r'\\;').replaceAll('\n', r'\\n');
    final start = booking.scheduledAt, end = _calendarEnd(booking);
    final address = _calendarAddress(booking);
    final lines = [
      'BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//AIRway//Booking//EN',
      'BEGIN:VEVENT', 'UID:airway-${booking.id}@airway',
      'DTSTAMP:${_calendarUtc(DateTime.now())}', 'DTSTART:${_calendarUtc(start)}',
      'DTEND:${_calendarUtc(end)}', 'SUMMARY:${esc('AIRway • ${booking.serviceTitle}')}',
      'DESCRIPTION:${esc(_calendarDetails(booking))}',
      if (address.isNotEmpty) 'LOCATION:${esc(address)}',
      'END:VEVENT', 'END:VCALENDAR',
    ];
    final data = Uint8List.fromList(utf8.encode('${lines.join('\r\n')}\r\n'));
    try {
      await SharePlus.instance.share(ShareParams(
        files: [XFile.fromData(data, mimeType: 'text/calendar', name: 'AIRway-booking-${booking.id}.ics')],
        fileNameOverrides: ['AIRway-booking-${booking.id}.ics'],
      ));
    } catch (error) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Could not share calendar event: $error')));
    }
  }

  Widget _actionButtons() {
    final isAssigned = _booking!.status == BookingStatus.assigned;
    final isPaid = _booking!.status == BookingStatus.inProgress || _booking!.status == BookingStatus.completed;

    // Show payment button only for ASSIGNED bookings (worker accepted)
    // Payment is not needed for PENDING/CONFIRMED (pre-assignment) or after completion
    final canPay = isAssigned && !isPaid;

    return Column(
      children: [
        if (canPay)
          Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                onPressed: _payNow,
                icon: const Icon(Icons.credit_card_rounded),
                label: Text(AirwayText.tr('Pay Now with Razorpay', 'Razorpay से अभी भुगतान करें')),
                style: FilledButton.styleFrom(
                  padding: const EdgeInsets.symmetric(vertical: 16),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                ),
              ),
            ),
          ),
        // Show payment status for assigned bookings
        if (isAssigned && !canPay)
          Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: Container(
              width: double.infinity,
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: _Ui.green.withAlpha(20),
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: _Ui.green),
              ),
              child: Row(
                children: [
                  Icon(Icons.check_circle_rounded, color: _Ui.green, size: 20),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      'Payment completed',
                      style: TextStyle(
                        color: _Ui.green,
                        fontSize: 15,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        SizedBox(
          width: double.infinity,
          child: FilledButton.icon(
            onPressed: () {
              Navigator.pushAndRemoveUntil(
                context,
                MaterialPageRoute(builder: (_) => const BookingListScreen()),
                (route) => false,
              );
            },
            icon: const Icon(Icons.list_alt_rounded),
            label: Text(AirwayText.tr('View My Bookings', 'मेरी बुकिंग देखें')),
            style: FilledButton.styleFrom(
              padding: const EdgeInsets.symmetric(vertical: 16),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
            ),
          ),
        ),
        const SizedBox(height: 12),
        SizedBox(
          width: double.infinity,
          child: OutlinedButton.icon(
            onPressed: () {
              Navigator.pop(context);
            },
            icon: const Icon(Icons.home_rounded),
            label: Text(AirwayText.tr('Back to Home', 'होम पर जाएँ')),
            style: OutlinedButton.styleFrom(
              padding: const EdgeInsets.symmetric(vertical: 16),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
              foregroundColor: _Ui.violet,
              side: BorderSide(color: _Ui.violet),
            ),
          ),
        ),
      ],
    );
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
                onPressed: _loadBooking,
                child: Text(AirwayText.tr('Retry', 'फिर कोशिश करें')),
              ),
            ],
          ),
        ),
      );

  String _formatDateTime(DateTime date) {
    final months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    return '${date.day} ${months[date.month - 1]} at ${date.hour}:${date.minute.toString().padLeft(2, '0')}';
  }
}