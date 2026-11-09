import 'dart:async';
import 'package:flutter/material.dart';
import 'package:razorpay_flutter/razorpay_flutter.dart';
import 'package:airway/features/booking/data/booking_api.dart';
import 'package:airway/features/booking/presentation/booking_list_screen.dart';
import 'package:airway/features/booking/presentation/booking_tracking_screen.dart';
import 'package:airway/features/payment/data/payment_api.dart';

class CustomerOrderScreen extends StatefulWidget {
  final int orderId;
  const CustomerOrderScreen({super.key, required this.orderId});

  @override
  State<CustomerOrderScreen> createState() => _CustomerOrderScreenState();
}

class _CustomerOrderScreenState extends State<CustomerOrderScreen> {
  static const violet = Color(0xFF987451);
  static const ink = Color(0xFF1E2923);
  static const sub = Color(0xFF748078);
  static const bg = Color(0xFFFFFFFF);
  static const pale = Color(0xFFEAF1EA);
  static const line = Color(0xFFEAE6DE);

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
      if (mounted && !paying) {
        loadOrder(showLoader: false);
      }
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
    final readyAdvance = order?['ready_for_advance'] == true;
    final readyBalance = order?['ready_for_balance'] == true;
    if ((!readyAdvance && !readyBalance) || paying) return;
    setState(() => paying = true);
    try {
      final payment = await PaymentApi.createOrderForParent(widget.orderId);
      if (payment['already_paid'] == true) {
        if (!mounted) return;
        setState(() => paying = false);
        await loadOrder();
        return;
      }
      final key = payment['key_id']?.toString() ?? '';
      final gatewayOrderId = payment['order_id']?.toString() ?? '';
      if (key.isEmpty || gatewayOrderId.isEmpty) {
        throw Exception('Payment gateway order could not be initialized.');
      }
      razorpay.open({
        'key': key,
        'amount': payment['amount'],
        'currency': payment['currency'] ?? 'INR',
        'name': 'AIRway',
        'description': (payment['installment'] == 'advance' ? '50% booking advance' : '50% service balance') + ' for order #' + widget.orderId.toString(),
        'order_id': gatewayOrderId,
        'theme': {'color': '#075B43'},
      });
    } catch (e) {
      if (mounted) {
        setState(() => paying = false);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Could not start payment: ' + e.toString())),
        );
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
      final verification = await PaymentApi.verifyPayment(
        razorpayOrderId: orderId,
        razorpayPaymentId: paymentId,
        razorpaySignature: signature,
      );
      if (!mounted) return;
      setState(() => paying = false);
      await loadOrder();
      if (!mounted) return;
      final installment = verification['installment']?.toString();
      final title = installment == 'advance' ? '50% advance received' : 'Balance payment successful';
      final message = installment == 'advance'
          ? 'Your booking advance is confirmed. AIRway will now arrange your professional.'
          : 'Your remaining 50% payment is confirmed. Thank you for using AIRway.';
      showDialog<void>(
        context: context,
        builder: (ctx) => AlertDialog(
          icon: const Icon(Icons.verified_rounded, color: violet, size: 48),
          title: Text(title),
          content: Text(message),
          actions: [FilledButton(onPressed: () => Navigator.pop(ctx), child: const Text('Done'))],
        ),
      );
    } catch (e) {
      if (mounted) {
        setState(() => paying = false);
        await loadOrder(showLoader: false);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Payment is awaiting server verification: ' + e.toString())),
        );
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


  Future<void> trackService(Map<String, dynamic> row) async {
    final bookingId = int.tryParse(row['booking_id']?.toString() ?? '');
    if (bookingId == null) return;
    await Navigator.of(context).push<void>(
      MaterialPageRoute(
        builder: (_) => BookingTrackingScreen(
          bookingId: bookingId,
          serviceTitle: (row['service'] is Map
                  ? row['service']['service_title']
                  : null)?.toString() ??
              'AIRway Service',
          initialStatus: row['booking_status']?.toString() ?? 'pending',
        ),
      ),
    );
    if (mounted) await loadOrder(showLoader: false);
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
    final readyAdvance = order?['ready_for_advance'] == true;
    final readyBalance = order?['ready_for_balance'] == true;
    final paid = order?['status'] == 'paid';
    final total = amount(order?['total_amount']);
    final advanceAmount = amount(order?['advance_amount']);
    final balanceAmount = amount(order?['balance_amount']);
    final payable = readyAdvance ? advanceAmount : balanceAmount;
    final paymentLabel = readyAdvance ? '50% booking advance' : 'Remaining 50% balance';
    final heading = paid ? 'Payment complete' : readyAdvance ? 'Advance payment required' : readyBalance ? 'Service completed' : 'Your order is being arranged';
    final description = paid
        ? 'Both payment installments are settled.'
        : readyAdvance
            ? 'Pay 50% now. AIRway will start professional assignment after the advance is captured.'
            : readyBalance
                ? 'Your services are complete. Pay the remaining 50% to settle the order.'
                : 'Your advance is received. We are arranging the professional and will update this order automatically.';
    return Column(children: [
      Expanded(child: ListView(
        padding: const EdgeInsets.all(18),
        children: [
          Container(
            padding: const EdgeInsets.all(18),
            decoration: BoxDecoration(color: pale, borderRadius: BorderRadius.circular(20)),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(heading, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w900, color: ink)),
              const SizedBox(height: 6),
              Text(description, style: const TextStyle(color: sub, height: 1.4)),
              const SizedBox(height: 12),
              Text('Order total  ₹' + total.toStringAsFixed(2), style: const TextStyle(fontSize: 21, fontWeight: FontWeight.w900, color: violet)),
            ]),
          ),
          const SizedBox(height: 14),
          paymentBreakdown(advanceAmount, balanceAmount, order?['advance_status']?.toString() ?? 'pending', order?['balance_status']?.toString() ?? 'pending'),
          const SizedBox(height: 14),
          orderProgress(rows, paid),
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
          if (readyAdvance || readyBalance)
            SizedBox(width: double.infinity, child: FilledButton(
              onPressed: paying ? null : startPayment,
              child: paying
                  ? const SizedBox(height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                  : Text('Pay ₹' + payable.toStringAsFixed(2) + ' — ' + paymentLabel),
            )),
          if (!readyAdvance && !readyBalance && !paid)
            const Text('Your order status and payment milestones update automatically.', textAlign: TextAlign.center, style: TextStyle(color: sub, fontSize: 12)),
          if (paid)
            const Text('Both installments paid successfully', style: TextStyle(color: Color(0xFF2E7D52), fontWeight: FontWeight.w800)),
          const SizedBox(height: 8),
          SizedBox(width: double.infinity, child: OutlinedButton(
            onPressed: () => Navigator.push(context, MaterialPageRoute(builder: (_) => const BookingListScreen())),
            child: const Text('View My Bookings'),
          )),
        ])),
      ),
    ]);
  }

  Widget paymentBreakdown(double advance, double balance, String advanceStatus, String balanceStatus) {
    Widget row(String label, double value, String status) {
      final settled = status == 'paid';
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 7),
        child: Row(children: [
          Expanded(child: Text(label, style: const TextStyle(color: sub, fontWeight: FontWeight.w600))),
          Text('₹' + value.toStringAsFixed(2), style: const TextStyle(color: ink, fontWeight: FontWeight.w800)),
          const SizedBox(width: 10),
          Text(settled ? 'Paid' : 'Due', style: TextStyle(color: settled ? const Color(0xFF2E7D52) : sub, fontWeight: FontWeight.w700)),
        ]),
      );
    }
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(16), border: Border.all(color: line)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text('Payment breakdown', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w900, color: ink)),
        row('50% booking advance', advance, advanceStatus),
        const Divider(height: 1),
        row('50% after service', balance, balanceStatus),
      ]),
    );
  }

  Widget orderProgress(List<Map<String, dynamic>> rows, bool paid) {
    final assigned = rows.isNotEmpty && rows.every((row) {
      final status = row['booking_status']?.toString();
      return status == 'assigned' || status == 'in_progress' || status == 'completed';
    });
    final completed = rows.isNotEmpty &&
        rows.every((row) => row['booking_status']?.toString() == 'completed');
    final steps = <(String, String, bool)>[
      ('Order placed', 'Your service request is received.', true),
      ('Professionals assigned', assigned ? 'Every service has a professional.' : 'Waiting for worker acceptance.', assigned),
      ('Payment', paid ? 'Payment verified successfully.' : assigned ? 'Payment is now available.' : 'Payment unlocks after assignment.', paid),
      ('Service completed', completed ? 'All services are completed.' : 'Updates appear as work progresses.', completed),
    ];
    return Container(
      padding: const EdgeInsets.all(15),
      decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(16), border: Border.all(color: line)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text('Order progress', style: TextStyle(fontWeight: FontWeight.w900, color: ink)),
        const SizedBox(height: 12),
        for (var i = 0; i < steps.length; i++) ...[
          Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Icon(steps[i].$3 ? Icons.check_circle : Icons.radio_button_unchecked,
                size: 20, color: steps[i].$3 ? const Color(0xFF2E7D52) : sub),
            const SizedBox(width: 10),
            Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(steps[i].$1, style: const TextStyle(fontWeight: FontWeight.w800, color: ink)),
              Text(steps[i].$2, style: const TextStyle(color: sub, fontSize: 12)),
            ])),
          ]),
          if (i != steps.length - 1) const SizedBox(height: 12),
        ],
      ]),
    );
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
        Row(children: [
          Expanded(child: Text(snapshot['service_title']?.toString() ?? 'Service',
              style: const TextStyle(fontWeight: FontWeight.w800, color: ink))),
          Text('₹' + amount(row['line_total']).toStringAsFixed(0),
              style: const TextStyle(fontWeight: FontWeight.w900, color: ink)),
        ]),
        if (snapshot['variant_title'] != null) Text(snapshot['variant_title'].toString(), style: const TextStyle(color: sub, fontSize: 12)),
        const SizedBox(height: 6),
        Text(statusLabel(status), style: const TextStyle(color: violet, fontWeight: FontWeight.w700, fontSize: 12)),
        if (scheduled.isNotEmpty) Text(scheduled, style: const TextStyle(color: sub, fontSize: 12)),
        if (worker != null) Text('Professional: ' + (worker['name']?.toString() ?? 'Assigned'), style: const TextStyle(color: sub, fontSize: 12)),
        const SizedBox(height: 8),
        SizedBox(width: double.infinity, child: OutlinedButton.icon(
          onPressed: () => trackService(row),
          icon: const Icon(Icons.location_searching_rounded, size: 17),
          label: const Text('Track this service'),
        )),
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
