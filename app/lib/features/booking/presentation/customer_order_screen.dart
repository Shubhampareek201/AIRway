import 'dart:async';
import 'package:flutter/material.dart';
import 'package:razorpay_flutter/razorpay_flutter.dart';
import 'package:airway/features/booking/data/booking_api.dart';
import 'package:airway/features/booking/presentation/booking_list_screen.dart';
import 'package:airway/features/payment/data/payment_api.dart';

class CustomerOrderScreen extends StatefulWidget {
  final int orderId;
  const CustomerOrderScreen({super.key, required this.orderId});

  @override
  State<CustomerOrderScreen> createState() => _CustomerOrderScreenState();
}

class _CustomerOrderScreenState extends State<CustomerOrderScreen> {
  static const violet = Color(0xFF7861A8);
  static const ink = Color(0xFF292331);
  static const sub = Color(0xFF81788A);
  static const bg = Color(0xFFF7F3EC);
  static const pale = Color(0xFFEDE7F5);
  static const line = Color(0xFFE8E0ED);

  final Razorpay razorpay = Razorpay();
  Map<String, dynamic>? order;
  bool loading = true;
  bool paying = false;
  String? error;
  Timer? refreshTimer;

  @override
  void initState() {
    super.initState();
    razorpay.on(Razorpay.EVENT_PAYMENT_SUCCESS, onPaymentSuccess);
    razorpay.on(Razorpay.EVENT_PAYMENT_ERROR, onPaymentError);
    razorpay.on(Razorpay.EVENT_EXTERNAL_WALLET, onExternalWallet);
    loadOrder();
    refreshTimer = Timer.periodic(const Duration(seconds: 25), (_) {
      if (mounted && !paying) loadOrder(showLoader: false);
    });
  }

  @override
  void dispose() {
    refreshTimer?.cancel();
    razorpay.clear();
    super.dispose();
  }

  Future<void> loadOrder({bool showLoader = true}) async {
    if (showLoader && mounted) setState(() { loading = true; error = null; });
    try {
      final result = await BookingApi.request('/api/v1/bookings/orders/' + widget.orderId.toString() + '/');
      if (mounted) setState(() { order = Map<String, dynamic>.from(result); loading = false; error = null; });
    } catch (e) {
      if (mounted) setState(() { loading = false; error = e.toString(); });
    }
  }

  double amount(dynamic value) => double.tryParse(value?.toString() ?? '') ?? 0;

  Future<void> startPayment() async {
    if (order?['ready_for_payment'] != true || paying) return;
    setState(() => paying = true);
    try {
      final payment = await PaymentApi.createOrderForParent(widget.orderId);
      final key = payment['key_id']?.toString() ?? '';
      if (key.isEmpty) throw Exception('Razorpay key is not configured on the server.');
      razorpay.open({
        'key': key,
        'amount': payment['amount'],
        'currency': payment['currency'] ?? 'INR',
        'name': 'AIRway',
        'description': 'Service order #' + widget.orderId.toString(),
        'order_id': payment['order_id'],
        'theme': {'color': '#7861A8'},
      });
    } catch (e) {
      if (mounted) {
        setState(() => paying = false);
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Could not start payment: ' + e.toString())));
      }
    }
  }

  Future<void> onPaymentSuccess(PaymentSuccessResponse response) async {
    final orderId = response.orderId;
    final paymentId = response.paymentId;
    final signature = response.signature;
    if (orderId == null || paymentId == null || signature == null) {
      if (mounted) setState(() => paying = false);
      return;
    }
    try {
      await PaymentApi.verifyPayment(
        razorpayOrderId: orderId,
        razorpayPaymentId: paymentId,
        razorpaySignature: signature,
      );
      if (!mounted) return;
      setState(() => paying = false);
      await loadOrder();
      if (!mounted) return;
      showDialog<void>(
        context: context,
        builder: (ctx) => AlertDialog(
          icon: const Icon(Icons.verified_rounded, color: violet, size: 48),
          title: const Text('Payment successful'),
          content: const Text('Your AIRway order has been paid and confirmed.'),
          actions: [FilledButton(onPressed: () => Navigator.pop(ctx), child: const Text('Done'))],
        ),
      );
    } catch (e) {
      if (mounted) {
        setState(() => paying = false);
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Payment verification failed: ' + e.toString())));
      }
    }
  }

  void onPaymentError(PaymentFailureResponse response) {
    if (!mounted) return;
    setState(() => paying = false);
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(response.message ?? 'Payment was not completed. You can try again.')),
    );
  }

  void onExternalWallet(ExternalWalletResponse response) {
    if (!mounted) return;
    setState(() => paying = false);
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('External wallet selected: ' + (response.walletName ?? 'Wallet'))),
    );
  }

  String statusLabel(String value) {
    switch (value) {
      case 'pending': return 'Finding professional';
      case 'confirmed': return 'Confirmed';
      case 'assigned': return 'Professional assigned';
      case 'in_progress': return 'In progress';
      case 'completed': return 'Completed';
      case 'cancelled': return 'Cancelled';
      default: return value.replaceAll('_', ' ');
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    backgroundColor: bg,
    appBar: AppBar(
      title: Text('Order #' + widget.orderId.toString()),
      backgroundColor: bg,
      actions: [IconButton(onPressed: loading ? null : () => loadOrder(), icon: const Icon(Icons.refresh_rounded))],
    ),
    body: loading
      ? const Center(child: CircularProgressIndicator(color: violet))
      : error != null
        ? emptyState('Could not load order', error!, Icons.error_outline, () => loadOrder())
        : orderBody(),
  );

  Widget orderBody() {
    final rows = (order?['items'] as List? ?? []).whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList();
    final ready = order?['ready_for_payment'] == true;
    final paid = order?['status'] == 'paid';
    final total = amount(order?['total_amount']);
    return Column(children: [
      Expanded(child: ListView(
        padding: const EdgeInsets.all(18),
        children: [
          Container(
            padding: const EdgeInsets.all(18),
            decoration: BoxDecoration(color: pale, borderRadius: BorderRadius.circular(20)),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(paid ? 'Payment complete' : ready ? 'All professionals assigned' : 'Your order is being arranged',
                  style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w900, color: ink)),
              const SizedBox(height: 6),
              Text(paid ? 'Your services are confirmed.' : ready
                  ? 'All services have an assigned professional. You can now complete payment.'
                  : 'We are assigning professionals for each service. This page refreshes automatically.',
                  style: const TextStyle(color: sub, height: 1.4)),
              const SizedBox(height: 12),
              Text('Order total  ₹' + total.toStringAsFixed(0), style: const TextStyle(fontSize: 21, fontWeight: FontWeight.w900, color: violet)),
            ]),
          ),
          const SizedBox(height: 18),
          const Text('Your services', style: TextStyle(fontSize: 17, fontWeight: FontWeight.w900, color: ink)),
          const SizedBox(height: 10),
          for (final row in rows) serviceRow(row),
        ],
      )),
      Container(
        padding: const EdgeInsets.fromLTRB(18, 12, 18, 18),
        decoration: const BoxDecoration(color: Colors.white, border: Border(top: BorderSide(color: line))),
        child: SafeArea(top: false, child: Column(mainAxisSize: MainAxisSize.min, children: [
          if (ready && !paid)
            SizedBox(width: double.infinity, child: FilledButton(
              onPressed: paying ? null : startPayment,
              child: paying ? const SizedBox(height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white)) : Text('Pay ₹' + total.toStringAsFixed(0)),
            )),
          if (!ready && !paid)
            const Text('Payment will unlock after every service has a professional assigned.', textAlign: TextAlign.center, style: TextStyle(color: sub, fontSize: 12)),
          if (paid)
            const Text('Paid successfully', style: TextStyle(color: Color(0xFF2E7D52), fontWeight: FontWeight.w800)),
          const SizedBox(height: 8),
          SizedBox(width: double.infinity, child: OutlinedButton(
            onPressed: () => Navigator.push(context, MaterialPageRoute(builder: (_) => const BookingListScreen())),
            child: const Text('View My Bookings'),
          )),
        ])),
      ),
    ]);
  }

  Widget serviceRow(Map<String, dynamic> row) {
    final snapshot = Map<String, dynamic>.from(row['service'] ?? {});
    final status = row['booking_status']?.toString() ?? 'pending';
    final worker = row['worker'] is Map ? Map<String, dynamic>.from(row['worker']) : null;
    final scheduled = row['scheduled_at'] == null ? '' : DateFormatForOrder.format(row['scheduled_at'].toString());
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(16), border: Border.all(color: line)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(snapshot['service_title']?.toString() ?? 'Service', style: const TextStyle(fontWeight: FontWeight.w800, color: ink)),
        if (snapshot['variant_title'] != null) Text(snapshot['variant_title'].toString(), style: const TextStyle(color: sub, fontSize: 12)),
        const SizedBox(height: 6),
        Text(statusLabel(status), style: const TextStyle(color: violet, fontWeight: FontWeight.w700, fontSize: 12)),
        if (scheduled.isNotEmpty) Text(scheduled, style: const TextStyle(color: sub, fontSize: 12)),
        if (worker != null) Text('Professional: ' + (worker['name']?.toString() ?? 'Assigned'), style: const TextStyle(color: sub, fontSize: 12)),
        Align(alignment: Alignment.centerRight, child: Text('₹' + amount(row['line_total']).toStringAsFixed(0), style: const TextStyle(fontWeight: FontWeight.w900, color: ink))),
      ]),
    );
  }

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
        FilledButton(onPressed: action, child: const Text('Retry')),
      ]),
    ),
  );
}

class DateFormatForOrder {
  static String format(String value) {
    final parsed = DateTime.tryParse(value);
    if (parsed == null) return value;
    final local = parsed.toLocal();
    final month = local.month.toString().padLeft(2, '0');
    final day = local.day.toString().padLeft(2, '0');
    final hour = (local.hour % 12 == 0 ? 12 : local.hour % 12).toString().padLeft(2, '0');
    final minute = local.minute.toString().padLeft(2, '0');
    return day + '/' + month + '/' + local.year.toString() + ' • ' + hour + ':' + minute + (local.hour >= 12 ? ' PM' : ' AM');
  }
}
