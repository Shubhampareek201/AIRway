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
  static const violet = Color(0xFF075B3C);
  static const ink = Color(0xFF1E2923);
  static const sub = Color(0xFF748078);
  static const bg = Color(0xFFFFFFFF);
  static const pale = Color(0xFFEAF1EA);
  static const line = Color(0xFFE6EBE7);

  final Razorpay razorpay = Razorpay();
  final TextEditingController walletAmountController = TextEditingController(text: '0.00');
  Map<String, dynamic>? order;
  double walletBalance = 0;
  bool walletLoading = true;
  bool loading = true;
  bool paying = false;
  String _currentPaymentStage = 'advance';
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
    final advanceReady = order?['ready_for_advance'] == true;
    final balanceReady = order?['ready_for_balance'] == true;
    final legacyReady = order?['ready_for_legacy_payment'] == true;
    if ((!advanceReady && !balanceReady && !legacyReady) || paying) return;
    final stage = advanceReady ? 'advance' : balanceReady ? 'balance' : 'legacy';
    _currentPaymentStage = stage;
    final stageDueKey = advanceReady
        ? 'advance_due'
        : balanceReady
            ? 'balance_due'
            : 'legacy_payment_due';
    final stageDue = amount(order == null ? null : order![stageDueKey]);
    final rawWalletAmount = walletAmountController.text.trim();
    final parsedWalletAmount = rawWalletAmount.isEmpty ? 0.0 : double.tryParse(rawWalletAmount);
    if (parsedWalletAmount == null || !parsedWalletAmount.isFinite) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Enter a valid wallet amount.')),
      );
      return;
    }
    final walletAmount = parsedWalletAmount;
    if (walletAmount < 0 || walletAmount > walletBalance || walletAmount > stageDue) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Enter a wallet amount within your available balance and the amount due now.')),
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
        stage: stage,
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
                  ? 'Your ${_currentPaymentStage == 'advance' ? '30% advance' : _currentPaymentStage == 'balance' ? 'final 70% balance' : 'full payment'} was paid using your AIRway wallet.'
                  : 'Your ${_currentPaymentStage == 'advance' ? '30% advance' : _currentPaymentStage == 'balance' ? 'final 70% balance' : 'full payment'} has already been paid.',
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
                : 'Your ${_currentPaymentStage == 'advance' ? '30% advance' : 'final 70% balance'} has been verified successfully.',
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
    final serviceInProgress = rows.any((row) => row['booking_status'] == 'in_progress');
    final advanceReady = order?['ready_for_advance'] == true;
    final balanceReady = order?['ready_for_balance'] == true;
    final legacyReady = order?['ready_for_legacy_payment'] == true;
    final ready = advanceReady || balanceReady || legacyReady;
    final advancePaid = order?['advance_paid'] == true;
    final paid = order?['balance_paid'] == true || order?['legacy_paid'] == true || order?['status'] == 'paid';
    final total = amount(order?['total_amount']);
    final dueNowKey = advanceReady
        ? 'advance_due'
        : balanceReady
            ? 'balance_due'
            : 'legacy_payment_due';
    final dueNow = amount(order == null ? null : order![dueNowKey]);
    final advancePercentage = int.tryParse(order?['advance_percentage']?.toString() ?? '30') ?? 30;
    final balancePercentage = 100 - advancePercentage;
    final stageLabel = advanceReady ? '$advancePercentage% advance'
        : balanceReady ? 'Final $balancePercentage% balance' : 'Full payment';
    return Column(children: [
      Expanded(child: ListView(
        padding: const EdgeInsets.all(18),
        children: [
          Container(
            padding: const EdgeInsets.all(18),
            decoration: BoxDecoration(color: pale, borderRadius: BorderRadius.circular(20)),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(paid ? 'Payment complete' : balanceReady ? 'All services verified' : advancePaid ? 'Your professionals are being arranged' : advanceReady ? 'Confirm your order' : legacyReady ? 'Complete your payment' : 'Your order is being arranged',
                  style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w900, color: ink)),
              const SizedBox(height: 6),
              Text(paid ? 'Your order is fully paid.' : balanceReady
                  ? 'Every active service is verified. Pay the remaining balance to close your order.'
                  : advancePaid
                      ? 'Your $advancePercentage% advance is received. Worker matching and service progress will appear here.'
                      : advanceReady
                          ? 'Pay $advancePercentage% now to start worker matching. The remaining $balancePercentage% is due only after all services are completed and verified.'
                          : legacyReady
                              ? 'This order was created before staged payments. Complete the remaining full payment to confirm it.'
                              : 'Pay the $advancePercentage% advance to start worker matching. This page refreshes automatically.',
                  style: const TextStyle(color: sub, height: 1.4)),
              const SizedBox(height: 12),
              Text('Order total  ₹' + total.toStringAsFixed(0), style: const TextStyle(fontSize: 21, fontWeight: FontWeight.w900, color: violet)),
            ]),
          ),
          const SizedBox(height: 14),
          orderProgress(rows, paid, advancePaid, order?['is_staged_payment'] == true, advancePercentage),
          const SizedBox(height: 18),
          const Text('Your services', style: TextStyle(fontSize: 17, fontWeight: FontWeight.w900, color: ink)),
          const SizedBox(height: 10),
          if (serviceInProgress) ...[
            Container(
              padding: const EdgeInsets.all(13),
              decoration: BoxDecoration(color: pale, borderRadius: BorderRadius.circular(13)),
              child: const Text(
                'When your service is finished, check AIRway Notifications for the completion code and share it with your professional.',
                style: TextStyle(color: sub, height: 1.4),
              ),
            ),
            const SizedBox(height: 10),
          ],
          for (final row in rows) serviceRow(row),
          if (ready && !paid) ...[
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(color: pale, borderRadius: BorderRadius.circular(14)),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(stageLabel, style: const TextStyle(fontWeight: FontWeight.w900, color: ink)),
                const SizedBox(height: 5),
                Text('Order total ₹${total.toStringAsFixed(2)}', style: const TextStyle(color: sub)),
                const SizedBox(height: 3),
                Text('Due now ₹${dueNow.toStringAsFixed(2)}', style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w900, color: violet)),
              ]),
            ),
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
                      const Text('Amount due now', style: TextStyle(color: sub)),
                      Text('₹${dueNow.toStringAsFixed(2)}', style: const TextStyle(fontWeight: FontWeight.w700, color: ink)),
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
                        '₹${(dueNow - selectedWalletAmount).clamp(0, dueNow).toStringAsFixed(2)}',
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
                  selectedWalletAmount > 0 && selectedWalletAmount >= dueNow
                      ? 'Pay with AIRway wallet'
                      : 'Pay ₹' + (dueNow - selectedWalletAmount).clamp(0, dueNow).toStringAsFixed(2),
                ),
            )),
          if (!ready && !paid)
            const Text('Pay the 30% advance to start worker matching. The remaining 70% is due after all active services are verified.', textAlign: TextAlign.center, style: TextStyle(color: sub, fontSize: 12)),
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


  Widget orderProgress(List<Map<String, dynamic>> rows, bool paid, bool advancePaid, bool staged, int advancePercentage) {
    final balancePercentage = 100 - advancePercentage;
    final activeRows = rows
        .where((row) => row['booking_status']?.toString() != 'cancelled')
        .toList();
    final assigned = activeRows.isNotEmpty && activeRows.every((row) {
      final status = row['booking_status']?.toString();
      return status == 'assigned' || status == 'in_progress' || status == 'completed';
    });
    final completed = activeRows.isNotEmpty &&
        activeRows.every((row) => row['booking_status']?.toString() == 'completed');
    final steps = staged
        ? <(String, String, bool)>[
            ('Order placed', 'Your service request is received.', true),
            ('$advancePercentage% advance', advancePaid ? 'Advance payment verified.' : 'Pay $advancePercentage% to start worker matching.', advancePaid),
            ('Professionals assigned', assigned ? 'Every service has a professional.' : 'Waiting for worker acceptance.', assigned),
            ('Service completion', completed ? 'All services are verified with customer OTP.' : 'Each service is verified after the customer shares a code.', completed),
            ('Remaining $balancePercentage%', paid ? 'Final balance paid. Order complete.' : completed ? 'Final balance is now due.' : 'Unlocked after all active services are verified.', paid),
          ]
        : <(String, String, bool)>[
            ('Order placed', 'Your service request is received.', true),
            ('Professionals assigned', assigned ? 'Every service has a professional.' : 'Waiting for worker acceptance.', assigned),
            ('Full payment', paid ? 'Payment verified successfully.' : 'Complete payment to confirm your order.', paid),
            ('Service completion', completed ? 'Services completed.' : 'Updates appear as work progresses.', completed),
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
        if (row['advance_amount'] != null && row['balance_amount'] != null) ...[
          const SizedBox(height: 7),
          Row(
            children: [
              Expanded(child: Text('Advance ₹${amount(row['advance_amount']).toStringAsFixed(2)}', style: const TextStyle(color: sub, fontSize: 11))),
              Expanded(child: Text('Balance ₹${amount(row['balance_amount']).toStringAsFixed(2)}', textAlign: TextAlign.end, style: const TextStyle(color: sub, fontSize: 11))),
            ],
          ),
        ],
        if (row['refunds'] is List && (row['refunds'] as List).isNotEmpty) ...[
          const SizedBox(height: 10),
          refundSection((row['refunds'] as List).whereType<Map>().map((item) => Map<String, dynamic>.from(item)).toList()),
        ],
        const SizedBox(height: 8),
        SizedBox(width: double.infinity, child: OutlinedButton.icon(
          onPressed: () => trackService(row),
          icon: const Icon(Icons.location_searching_rounded, size: 17),
          label: const Text('Track this service'),
        )),
      ]),
    );
  }

  Widget refundSection(List<Map<String, dynamic>> refunds) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFFF2F7F3),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFFDCE9DF)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Icon(Icons.account_balance_wallet_outlined, color: Color(0xFF075B3C), size: 19),
              SizedBox(width: 7),
              Text('Refund updates', style: TextStyle(fontWeight: FontWeight.w900, color: ink)),
            ],
          ),
          const SizedBox(height: 9),
          for (var index = 0; index < refunds.length; index++) ...[
            if (index > 0) const Divider(height: 16, color: Color(0xFFDCE9DF)),
            _refundRow(refunds[index]),
          ],
        ],
      ),
    );
  }

  Widget _refundRow(Map<String, dynamic> refund) {
    final status = refund['status']?.toString() ?? 'pending';
    final reason = refund['reason']?.toString() ?? '';
    final statusText = switch (status) {
      'processed' => 'Refund completed',
      'failed' => 'Refund needs attention',
      'processing' => 'Refund processing',
      _ => 'Refund pending',
    };
    final statusColor = switch (status) {
      'processed' => const Color(0xFF167447),
      'failed' => const Color(0xFFB3261E),
      'processing' => const Color(0xFF946200),
      _ => const Color(0xFF52665A),
    };
    final reasonText = reason == 'platform_unfulfilled'
        ? 'AIRway could not fulfil this service'
        : 'Service cancellation';
    final amountValue = amount(refund['amount']);
    final walletValue = amount(refund['wallet_amount']);
    final gatewayValue = amount(refund['gateway_amount']);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(child: Text(statusText, style: TextStyle(fontWeight: FontWeight.w800, color: statusColor))),
            Text('₹${amountValue.toStringAsFixed(2)}', style: const TextStyle(fontWeight: FontWeight.w900, color: Color(0xFF075B3C))),
          ],
        ),
        const SizedBox(height: 4),
        Text(reasonText, style: const TextStyle(color: sub, fontSize: 12)),
        Text('AIRway wallet: ₹${walletValue.toStringAsFixed(2)}', style: const TextStyle(color: sub, fontSize: 12)),
        Text('Original payment method: ₹${gatewayValue.toStringAsFixed(2)}', style: const TextStyle(color: sub, fontSize: 12)),
        if (status == 'failed' && (refund['failure_reason']?.toString().isNotEmpty ?? false)) ...[
          const SizedBox(height: 4),
          Text(refund['failure_reason'].toString(), style: const TextStyle(color: Color(0xFFB3261E), fontSize: 12)),
        ],
      ],
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
