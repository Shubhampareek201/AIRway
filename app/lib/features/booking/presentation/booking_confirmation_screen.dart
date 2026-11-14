import 'package:flutter/material.dart';
import 'package:razorpay_flutter/razorpay_flutter.dart';
import 'package:airway/features/booking/data/booking_api.dart';
import 'package:airway/features/booking/data/booking_models.dart';
import 'package:airway/features/booking/presentation/booking_list_screen.dart';
import 'package:airway/features/payment/presentation/payment_result_screen.dart';

class _Payment {
  static const keyId = 'rzp_test_airway';
}

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
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Payment failed: ${response.message}')));
  }

  void _handleExternalWallet(ExternalWalletResponse response) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('External wallet: ${response.walletName}')));
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
            verificationResult: result,
          ),
        ),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Payment verification failed: $e')),
      );
    }
  }

  Future<void> _payNow() async {
    final order = await BookingApi.createRazorpayOrder(widget.bookingId);
    if (!mounted) return;
    final options = {
      'key': _Payment.keyId,
      'amount': (double.parse(_booking!.totalAmount.toString()) * 100).toInt(),
      'name': 'AIRway Booking',
      'order_id': order['order_id'],
      'prefill': {'contact': '9876543210'}, // Should be customer phone
    };
    try {
      _razorpay.open(options);
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Error initiating payment: $e')));
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
        title: const Text('Booking Confirmed'),
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

  Widget _pricingCard(Booking booking) => _card(
        'Pricing',
        [
          _detailRow('Subtotal', '₹${booking.pricingSnapshot['subtotal']?.toStringAsFixed(0) ?? booking.totalAmount.toStringAsFixed(0)}'),
          if ((booking.pricingSnapshot['discount'] ?? 0) > 0)
            _detailRow('Discount', '-₹${booking.pricingSnapshot['discount']?.toStringAsFixed(0) ?? '0'}'),
          if ((booking.pricingSnapshot['tax'] ?? 0) > 0)
            _detailRow('Tax (18%)', '+₹${booking.pricingSnapshot['tax']?.toStringAsFixed(0) ?? '0'}'),
          _detailRow('Total', '₹${booking.totalAmount.toStringAsFixed(0)}', isTotal: true),
        ],
      );

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
                label: const Text('Pay Now with Razorpay'),
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
            label: const Text('View My Bookings'),
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
            label: const Text('Back to Home'),
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
                child: const Text('Retry'),
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