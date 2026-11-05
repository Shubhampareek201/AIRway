import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:airway/core/theme/airway_colors.dart';
import 'package:airway/features/payment/data/payment_models.dart';
import 'package:airway/features/payment/data/payment_api.dart';

class PaymentResultScreen extends StatefulWidget {
  final int bookingId;
  final String? razorpayOrderId;
  final String? razorpayPaymentId;
  final String? razorpaySignature;
  final String? initialStatus;
  final Map<String, dynamic>? verificationResult;

  const PaymentResultScreen({
    super.key,
    required this.bookingId,
    this.razorpayOrderId,
    this.razorpayPaymentId,
    this.razorpaySignature,
    this.initialStatus,
    this.verificationResult,
  });

  @override
  State<PaymentResultScreen> createState() => _PaymentResultScreenState();
}

class _PaymentResultScreenState extends State<PaymentResultScreen> {
  bool _loading = true;
  PaymentResult? _paymentResult;
  String? _error;

  @override
  void initState() {
    super.initState();
    _verifyPaymentStatus();
  }

  Future<void> _verifyPaymentStatus() async {
    if (mounted) {
      setState(() {
        _loading = true;
        _error = null;
      });
    }

    try {
      PaymentResult? result;

      // Use pre-verified result if available (to avoid redundant verification)
      if (widget.verificationResult != null) {
        final verification = widget.verificationResult!;
        result = PaymentResult.fromMap({
          'booking_id': widget.bookingId,
          'amount': verification['amount'] ?? 0,
          'status': verification['status'] ?? 'pending',
          'razorpay_order_id': widget.razorpayOrderId,
          'razorpay_payment_id': widget.razorpayPaymentId,
          'paid_at': verification['paid_at'],
          'created_at': DateTime.now().toIso8601String(),
          'data': verification,
          'late_webhook': verification['data']?['late_webhook'] ?? false,
        });
      } else if (widget.razorpayOrderId != null &&
          widget.razorpayPaymentId != null &&
          widget.razorpaySignature != null) {
        // Verify with backend
        final verification = await PaymentApi.verifyPayment(
          razorpayOrderId: widget.razorpayOrderId!,
          razorpayPaymentId: widget.razorpayPaymentId!,
          razorpaySignature: widget.razorpaySignature!,
        );

        result = PaymentResult.fromMap({
          'booking_id': widget.bookingId,
          'amount': verification['amount'] ?? 0,
          'status': verification['status'] ?? 'pending',
          'razorpay_order_id': widget.razorpayOrderId,
          'razorpay_payment_id': widget.razorpayPaymentId,
          'paid_at': verification['paid_at'],
          'created_at': DateTime.now().toIso8601String(),
          'data': verification,
          'late_webhook': verification['data']?['late_webhook'] ?? false,
        });
      } else {
        // Just check the booking status for pending/incomplete payments
        final booking = await PaymentApi.getPaymentStatus(widget.bookingId);

        result = PaymentResult.fromMap({
          'booking_id': widget.bookingId,
          'amount': 0,
          'status': booking['status'] ?? 'pending',
          'razorpay_order_id': booking['razorpay_order_id'],
          'razorpay_payment_id': booking['razorpay_payment_id'],
          'paid_at': booking['paid_at'],
          'created_at': DateTime.now().toIso8601String(),
          'data': {'is_pending_verification': true},
          'late_webhook': false,
        });
      }

      if (mounted) {
        setState(() {
          _paymentResult = result;
          _loading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = 'Could not verify payment status: $e';
          _loading = false;
        });
      }
    }
  }

  Future<void> _refreshStatus() async {
    await _verifyPaymentStatus();
  }

  void _navigateToBooking() {
    // Navigate to booking detail screen
    Navigator.of(context).popUntil((route) => route.isFirst);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: _Ui.bg,
      appBar: AppBar(
        title: const Text('Payment Status'),
        backgroundColor: _Ui.bg,
        elevation: 0,
        foregroundColor: _Ui.ink,
      ),
      body: _loading
          ? _skeleton()
          : _error != null
              ? _errorWidget(_error!)
              : _buildBody(),
    );
  }

  Widget _skeleton() => ListView(
        padding: const EdgeInsets.all(20),
        children: [
          const Center(child: CircularProgressIndicator()),
          const SizedBox(height: 20),
          _PulseBlock(),
        ],
      );

  Widget _buildBody() {
    final result = _paymentResult;

    if (result == null) {
      return _errorWidget('No payment information available.');
    }

    return RefreshIndicator(
      onRefresh: _refreshStatus,
      child: ListView(
        padding: const EdgeInsets.all(20),
        children: [
          _buildStatusCard(result),
          const SizedBox(height: 16),
          _buildPaymentDetails(result),
          const SizedBox(height: 16),
          _buildActions(result),
        ],
      ),
    );
  }

  Widget _buildStatusCard(PaymentResult result) {
    late Color statusColor;
    late String statusText;

    switch (result.status) {
      case PaymentStatus.paid:
        statusColor = Colors.green;
        statusText = 'Payment Successful';
        break;
      case PaymentStatus.failed:
        statusColor = Colors.red;
        statusText = 'Payment Failed';
        break;
      case PaymentStatus.refunded:
        statusColor = Colors.orange;
        statusText = 'Payment Refunded';
        break;
      default:
        statusColor = Colors.orange;
        statusText = 'Payment Pending';
    }

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: _Ui.line),
      ),
      child: Column(
        children: [
          Icon(
            result.status == PaymentStatus.paid ? Icons.check_circle : Icons.schedule,
            size: 56,
            color: statusColor,
          ),
          const SizedBox(height: 16),
          Text(
            statusText,
            style: TextStyle(
              fontSize: 22,
              fontWeight: FontWeight.w800,
              color: statusColor,
            ),
          ),
          if (result.isLateWebhook)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Chip(
                backgroundColor: Colors.orange.shade100,
                label: const Text(
                  'Late webhook received',
                  style: TextStyle(
                    fontSize: 11,
                    color: Colors.orange,
                  ),
                ),
              ),
            ),
          const SizedBox(height: 8),
          Text(
            'Booking #${result.bookingId}',
            style: const TextStyle(
              fontSize: 14,
              color: AirwayColors.textSecondary,
            ),
          ),
          const SizedBox(height: 20),
          _buildStatusTimeline(result),
        ],
      ),
    );
  }

  Widget _buildStatusTimeline(PaymentResult result) {
    final events = [
      {'label': 'Booking created', 'time': result.createdAt},
      if (result.paidAt != null) {'label': 'Payment completed', 'time': result.paidAt},
    ];

    return ListView(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      children: [
        const Text(
          'Timeline',
          style: TextStyle(
            fontSize: 14,
            fontWeight: FontWeight.w600,
          ),
        ),
        const SizedBox(height: 12),
        for (int i = 0; i < events.length; i++) ...[
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              CircleAvatar(
                radius: 16,
                backgroundColor: AirwayColors.primarySoft,
                child: Icon(
                  Icons.circle,
                  size: 8,
                  color: AirwayColors.primary,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      events[i]['label'] as String,
                      style: const TextStyle(
                        fontWeight: FontWeight.w500,
                        fontSize: 13,
                      ),
                    ),
                    Text(
                      DateFormat('MMM dd, yyyy • HH:mm').format(events[i]['time'] as DateTime),
                      style: const TextStyle(
                        fontSize: 12,
                        color: AirwayColors.textSecondary,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          if (i < events.length - 1)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 15),
              child: Divider(color: _Ui.line),
            ),
        ],
      ],
    );
  }

  Widget _buildPaymentDetails(PaymentResult result) {
    return Card(
      color: Colors.white,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Payment Details',
              style: TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 12),
            _detailRow('Status', PaymentStatus.display(result.status)),
            _detailRow('Order ID', result.razorpayOrderId ?? 'N/A'),
            _detailRow('Payment ID', result.razorpayPaymentId ?? 'N/A'),
            if (result.paidAt != null)
              _detailRow('Paid at', DateFormat('MMM dd, yyyy • HH:mm').format(result.paidAt!)),
          ],
        ),
      ),
    );
  }

  Widget _buildActions(PaymentResult result) {
    return Column(
      children: [
        if (result.status == PaymentStatus.paid)
          FilledButton.icon(
            onPressed: _navigateToBooking,
            icon: const Icon(Icons.list_alt_rounded),
            label: const Text('View Booking'),
            style: FilledButton.styleFrom(
              padding: const EdgeInsets.symmetric(vertical: 16),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
            ),
          ),
        if (result.status == PaymentStatus.pending || result.status == PaymentStatus.failed)
          OutlinedButton.icon(
            onPressed: _navigateToBooking,
            icon: const Icon(Icons.refresh_rounded),
            label: const Text('Refresh Status'),
            style: OutlinedButton.styleFrom(
              padding: const EdgeInsets.symmetric(vertical: 16),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
            ),
          ),
        const SizedBox(height: 12),
        OutlinedButton.icon(
          onPressed: () {
            Navigator.pop(context);
          },
          icon: const Icon(Icons.arrow_back_rounded),
          label: const Text('Back'),
          style: OutlinedButton.styleFrom(
            padding: const EdgeInsets.symmetric(vertical: 16),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
            foregroundColor: _Ui.violet,
            side: BorderSide(color: _Ui.violet),
          ),
        ),
      ],
    );
  }

  Widget _detailRow(String label, String value) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 8),
        child: Row(
          children: [
            Expanded(
              child: Text(
                label,
                style: const TextStyle(
                  fontSize: 14,
                  color: AirwayColors.textSecondary,
                ),
              ),
            ),
            Text(
              value,
              style: const TextStyle(
                fontSize: 14,
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ),
      );

  Widget _errorWidget(String message) => Center(
        child: Padding(
          padding: const EdgeInsets.all(28),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.error_outline, color: Colors.redAccent, size: 52),
              const SizedBox(height: 14),
              Text(message,
                  textAlign: TextAlign.center,
                  style: const TextStyle(color: AirwayColors.textSecondary)),
              const SizedBox(height: 20),
              FilledButton(onPressed: _verifyPaymentStatus, child: const Text('Retry')),
            ],
          ),
        ),
      );
}

class _Ui {
  static const violet = Color(0xFF6F4EF6);
  static const ink = Color(0xFF201A33);
  static const bg = Color(0xFFF8F7FD);
  static const line = Color(0xFFEAE5F5);
}

class _PulseBlock extends StatefulWidget {
  const _PulseBlock();
  @override
  State<_PulseBlock> createState() => _$PulseBlockState();
}

class _$PulseBlockState extends State<_PulseBlock> with SingleTickerProviderStateMixin {
  late final AnimationController _animation = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 1100),
  )..repeat(reverse: true);

  @override
  void dispose() {
    _animation.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
        animation: _animation,
        builder: (context, child) => Container(
          height: 200,
          decoration: BoxDecoration(
            color: Color.lerp(const Color(0xFFE9E5F3), const Color(0xFFF6F3FA), _animation.value),
            borderRadius: BorderRadius.circular(22),
          ),
        ),
      );
}