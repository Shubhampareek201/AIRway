class PaymentStatus {
  static const pending = 'pending';
  static const paid = 'paid';
  static const failed = 'failed';
  static const refunded = 'refunded';

  static String display(String status) {
    switch (status) {
      case pending:
        return 'Pending';
      case paid:
        return 'Paid';
      case failed:
        return 'Failed';
      case refunded:
        return 'Refunded';
      default:
        return status;
    }
  }
}

class PaymentResult {
  final int bookingId;
  final double amount;
  final String status;
  final String? razorpayOrderId;
  final String? razorpayPaymentId;
  final DateTime? paidAt;
  final DateTime? createdAt;
  final Map<String, dynamic>? metadata;
  final bool isLateWebhook;

  PaymentResult({
    required this.bookingId,
    required this.amount,
    required this.status,
    this.razorpayOrderId,
    this.razorpayPaymentId,
    this.paidAt,
    this.createdAt,
    this.metadata,
    this.isLateWebhook = false,
  });

  factory PaymentResult.fromMap(Map<String, dynamic> map) {
    final data = map['data'] as Map<String, dynamic>?;
    return PaymentResult(
      bookingId: map['booking_id'],
      amount: double.tryParse(map['amount'].toString()) ?? 0.0,
      status: map['status'] ?? PaymentStatus.pending,
      razorpayOrderId: map['razorpay_order_id'],
      razorpayPaymentId: map['razorpay_payment_id'],
      paidAt: map['paid_at'] != null ? DateTime.parse(map['paid_at']) : null,
      createdAt: map['created_at'] != null ? DateTime.parse(map['created_at']) : null,
      metadata: data,
      isLateWebhook: data != null && data['late_webhook'] == true,
    );
  }
}