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
  final TextEditingController walletAmountController = TextEditingController(text: '0.00');
  Map<String, dynamic>? order;
  double walletBalance = 0;
  bool walletLoading = true;
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
    loadWalletBalance();
    refreshTimer = Timer.periodic(const Duration(seconds: 25), (_) {
      if (mounted && !paying) {
        loadOrder(showLoader: false);
        loadWalletBalance();
      }
    });
  }

  @override
  void dispose() {
    refreshTimer?.cancel();
    walletAmountController.dispose();
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

  double get selectedWalletAmount {
    final value = double.tryParse(walletAmountController.text.trim());
    return value == null || !value.isFinite ? 0 : value;
  }

  Future<void> loadWalletBalance() async {
    try {
      final result = await BookingApi.request('/api/v1/wallet/balance/');
      if (!mounted) return;
      setState(() {
        walletBalance = amount(result['balance']);
        walletLoading = false;
      });
    } catch (_) {
      if (mounted) setState(() => walletLoading = false);
    }
  }

  Future<void> startPayment() async {
    if (order?['ready_for_payment'] != true || paying) return;
    final total = amount(order?['total_amount']);
    final rawWalletAmount = walletAmountController.text.trim();
    final parsedWalletAmount = rawWalletAmount.isEmpty ? 0.0 : double.tryParse(rawWalletAmount);
    if (parsedWalletAmount == null || !parsedWalletAmount.isFinite) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Enter a valid wallet amount.')),
      );
      return;
    }
    final walletAmount = parsedWalletAmount;
    if (walletAmount < 0 || walletAmount > walletBalance || walletAmount > total) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Enter a wallet amount within your available balance and order total.')),
      );
      return;
    }
    if ((walletAmount * 100).roundToDouble() != walletAmount * 100) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Wallet amount can have at most two decimal places.')),
      );
      return;
    }

    setState(() => paying = true);
    try {
      final payment = await PaymentApi.createOrderForParent(
        widget.orderId,
        walletAmount: walletAmount.toStringAsFixed(2),
      );
      await loadWalletBalance();
      if (payment['fully_paid_by_wallet'] == true || payment['already_paid'] == true) {
        if (!mounted) return;
        setState(() => paying = false);
        await loadOrder();
        if (!mounted) return;
        final paidByWallet = payment['fully_paid_by_wallet'] == true;
        showDialog<void>(
          context: context,
          builder: (ctx) => AlertDialog(
            icon: const Icon(Icons.verified_rounded, color: violet, size: 48),
            title: const Text('Payment successful'),
            content: Text(
              paidByWallet
                  ? 'Your order was paid using your AIRway wallet.'
                  : 'Your AIRway order has already been paid and confirmed.',
            ),
            actions: [FilledButton(onPressed: () => Navigator.pop(ctx), child: const Text('Done'))],
          ),
        );
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
        'description': 'Service order #' + widget.orderId.toString(),
        'order_id': gatewayOrderId,
        'theme': {'color': '#075B43'},
      });
    } catch (e) {
      if (mounted) {
        setState(() => paying = false);
        loadWalletBalance();
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
      final verification = await PaymentApi.verifyPayment(
        razorpayOrderId: orderId,
        razorpayPaymentId: paymentId,
        razorpaySignature: signature,
      );
      if (!mounted) return;
      setState(() => paying = false);
      await loadOrder();
      if (!mounted) return;
      final refunded = verification['status'] == 'refunded';
      showDialog<void>(
        context: context,
        builder: (ctx) => AlertDialog(
          icon: Icon(
            refunded ? Icons.currency_rupee_rounded : Icons.verified_rounded,
            color: refunded ? sub : violet,
            size: 48,
          ),
          title: Text(refunded ? 'Payment refunded' : 'Payment successful'),
          content: Text(
            refunded
                ? 'The late payment was refunded because the wallet funds were no longer available. You can retry checkout.'
                : 'Your AIRway order has been paid and confirmed.',
          ),
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
    loadWalletBalance();
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

  Future<void> cancelServiceLine(Map<String, dynamic> row) async {
    final bookingId = int.tryParse(row['booking_id']?.toString() ?? '');
    if (bookingId == null || row['can_cancel'] != true) return;
    final terms = row['cancellation_terms'] is Map
        ? Map<String, dynamic>.from(row['cancellation_terms'])
        : <String, dynamic>{};
    final refund = amount(terms['refund_amount']);
    final fee = amount(terms['platform_fee']);
    final sameDayAccepted =
        terms['policy'] == 'same_day_after_worker_acceptance';

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Cancel this service?'),
        content: Text(
          sameDayAccepted
              ? 'A professional has accepted this same-day service. Cancellation is non-refundable.'
              : refund > 0
                  ? 'Estimated refund: ₹${refund.toStringAsFixed(2)}'
                      '${fee > 0 ? '\nPlatform fee: ₹${fee.toStringAsFixed(2)}' : ''}'
                      '\nOnly this service will be cancelled. Other services in the order will continue.'
                  : 'This service is not eligible for a refund. Only this service will be cancelled; the remaining services will continue.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: const Text('Keep service'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(dialogContext, true),
            style: FilledButton.styleFrom(
              backgroundColor: Colors.red.shade700,
            ),
            child: const Text('Cancel service'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;

    try {
      final result = await BookingApi.request(
        '/api/v1/bookings/orders/${widget.orderId}/items/$bookingId/cancel/',
        method: 'POST',
        data: {'reason': 'Cancelled by customer from order details.'},
      );
      await loadOrder(showLoader: false);
      await loadWalletBalance();
      if (!mounted) return;
      final message = result is Map
          ? result['refund_message']?.toString()
          : null;
      final refundStatus = result is Map
          ? result['refund_status']?.toString() ?? 'unknown'
          : 'unknown';
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            message != null && message.isNotEmpty
                ? 'Service cancelled. $message'
                : 'Service cancelled. Refund status: $refundStatus.',
          ),
        ),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Could not cancel this service: $e')),
      );
    }
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
    final orderStatus = order?['status']?.toString() ?? '';
    final paid = orderStatus == 'paid' || orderStatus == 'completed';
    final awaitingFinal = orderStatus == 'awaiting_final_payment';
    final total = amount(order?['active_total_amount'] ?? order?['total_amount']);
    final partiallyCancelled = order?['partially_cancelled'] == true;
    final allCancelled = rows.isNotEmpty &&
        rows.every((row) => row['booking_status'] == 'cancelled');
    return Column(children: [
      Expanded(child: ListView(
        padding: const EdgeInsets.all(18),
        children: [
          Container(
            padding: const EdgeInsets.all(18),
            decoration: BoxDecoration(color: pale, borderRadius: BorderRadius.circular(20)),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(
                  allCancelled ? 'All services cancelled'
                      : paid ? 'Payment and services complete'
                      : awaitingFinal ? 'Services completed — final payment due'
                      : partiallyCancelled ? 'Some services cancelled'
                      : ready ? 'All professionals assigned'
                      : 'Your order is being arranged',
                  style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w900, color: ink)),
              const SizedBox(height: 6),
              Text(
                  allCancelled ? 'There are no active services remaining in this order.'
                      : paid ? 'All active services and final balances are complete.'
                      : awaitingFinal ? 'Open each completed service to review and pay its remaining balance.'
                      : partiallyCancelled ? 'Cancelled services are excluded. Your remaining services continue under this order.'
                      : ready ? 'All services have an assigned professional.'
                      : 'We are assigning professionals for each service. This page refreshes automatically.',
                  style: const TextStyle(color: sub, height: 1.4)),
              const SizedBox(height: 12),
              Text('Order total  ₹' + total.toStringAsFixed(0), style: const TextStyle(fontSize: 21, fontWeight: FontWeight.w900, color: violet)),
            ]),
          ),
          const SizedBox(height: 14),
          orderProgress(rows, paid),
          const SizedBox(height: 18),
          const Text('Your services', style: TextStyle(fontSize: 17, fontWeight: FontWeight.w900, color: ink)),
          const SizedBox(height: 10),
          for (final row in rows) serviceRow(row),
          if (ready && !paid) ...[
            const SizedBox(height: 10),
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: line),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('AIRway wallet', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w900, color: ink)),
                  const SizedBox(height: 5),
                  Text(
                    walletLoading
                        ? 'Loading available balance…'
                        : 'Available balance: ₹${walletBalance.toStringAsFixed(2)}',
                    style: const TextStyle(color: sub, fontSize: 13),
                  ),
                  const SizedBox(height: 10),
                  TextField(
                    controller: walletAmountController,
                    enabled: !walletLoading,
                    keyboardType: const TextInputType.numberWithOptions(decimal: true),
                    onChanged: (_) => setState(() {}),
                    decoration: const InputDecoration(
                      labelText: 'Use wallet amount (₹)',
                      hintText: '0.00',
                      border: OutlineInputBorder(),
                      prefixIcon: Icon(Icons.account_balance_wallet_outlined),
                    ),
                  ),
                  const SizedBox(height: 10),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Text('Order total', style: TextStyle(color: sub)),
                      Text('₹${total.toStringAsFixed(2)}', style: const TextStyle(fontWeight: FontWeight.w700, color: ink)),
                    ],
                  ),
                  const SizedBox(height: 5),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Text('Wallet applied', style: TextStyle(color: sub)),
                      Text('− ₹${selectedWalletAmount.toStringAsFixed(2)}', style: const TextStyle(fontWeight: FontWeight.w700, color: ink)),
                    ],
                  ),
                  const Divider(height: 18),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Text('Pay online', style: TextStyle(fontWeight: FontWeight.w900, color: ink)),
                      Text(
                        '₹${(total - selectedWalletAmount).clamp(0, total).toStringAsFixed(2)}',
                        style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w900, color: violet),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ],
      )),
      Container(
        padding: const EdgeInsets.fromLTRB(18, 12, 18, 18),
        decoration: const BoxDecoration(color: Colors.white, border: Border(top: BorderSide(color: line))),
        child: SafeArea(top: false, child: Column(mainAxisSize: MainAxisSize.min, children: [
          if (ready && !paid)
            SizedBox(width: double.infinity, child: FilledButton(
              onPressed: paying ? null : startPayment,
              child: paying ? const SizedBox(height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white)) : Text(
                  selectedWalletAmount > 0 && selectedWalletAmount >= total
                      ? 'Pay with AIRway wallet'
                      : 'Pay ₹' + (total - selectedWalletAmount).clamp(0, total).toStringAsFixed(2),
                ),
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


  Widget orderProgress(List<Map<String, dynamic>> rows, bool paid) {
    final assigned = rows.isNotEmpty && rows.every((row) {
      final status = row['booking_status']?.toString();
      return status == 'assigned' || status == 'in_progress' || status == 'completed';
    });
    final completed = rows.isNotEmpty &&
        rows.every((row) => row['booking_status']?.toString() == 'completed');
    final hasSplitLedger = rows.any((row) => row['payment_summary'] is Map);
    final advancesPaid = hasSplitLedger && rows.every((row) {
      final summary = row['payment_summary'];
      return summary is! Map || summary['advance_status'] == 'paid';
    });
    final finalBalancesPaid = hasSplitLedger && rows.every((row) {
      final summary = row['payment_summary'];
      return summary is! Map || summary['final_balance_status'] == 'paid';
    });
    final steps = <(String, String, bool)>[
      ('Order placed', 'Your service request is received.', true),
      ('Booking advances', advancesPaid ? 'Required booking advances have been received.' : assigned ? 'Payment is being prepared.' : 'Advance is collected before worker dispatch.', advancesPaid || (!hasSplitLedger && paid)),
      ('Professionals assigned', assigned ? 'Every service has a professional.' : 'Waiting for worker acceptance.', assigned),
      ('Service completed', completed ? 'All services are completed.' : 'Updates appear as work progresses.', completed),
      ('Final balances', finalBalancesPaid ? 'All final balances are settled.' : completed ? 'Open each service to pay its remaining balance.' : 'Due after each service completion.', finalBalancesPaid || (!hasSplitLedger && paid)),
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
        if (status != 'cancelled')
          SizedBox(width: double.infinity, child: OutlinedButton.icon(
            onPressed: () => trackService(row),
            icon: const Icon(Icons.location_searching_rounded, size: 17),
            label: const Text('Track this service'),
          )),
        if (row['can_cancel'] == true) ...[
          const SizedBox(height: 6),
          SizedBox(width: double.infinity, child: OutlinedButton.icon(
            onPressed: () => cancelServiceLine(row),
            icon: const Icon(Icons.cancel_outlined, size: 17),
            label: const Text('Cancel this service'),
            style: OutlinedButton.styleFrom(
              foregroundColor: Colors.red,
            ),
          )),
        ],
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
