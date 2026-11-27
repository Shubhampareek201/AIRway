import 'dart:async';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:image_picker/image_picker.dart';
import 'package:razorpay_flutter/razorpay_flutter.dart';
import 'package:airway/features/booking/data/booking_api.dart';
import 'package:airway/features/booking/presentation/booking_list_screen.dart';
import 'package:airway/features/booking/presentation/booking_tracking_screen.dart';
import 'package:airway/features/booking/presentation/booking_schedule_screen.dart';
import 'package:airway/features/payment/data/payment_api.dart';
import 'package:airway/features/ratings/data/rating_api.dart';
import 'package:airway/core/localization/airway_text.dart';

class CustomerOrderScreen extends StatefulWidget {
  final int orderId;
  const CustomerOrderScreen({super.key, required this.orderId});

  @override
  State<CustomerOrderScreen> createState() => _CustomerOrderScreenState();
}

class _CustomerOrderScreenState extends State<CustomerOrderScreen> {
  static const violet = Color(0xFF6C4AE3);
  static const ink = Color(0xFF1E2923);
  static const sub = Color(0xFF748078);
  static const bg = Color(0xFFFFFFFF);
  static const pale = Color(0xFFF1EDFF);
  static const line = Color(0xFFE8E2F5);

  final Razorpay razorpay = Razorpay();
  final TextEditingController walletAmountController = TextEditingController(text: '0.00');
  Map<String, dynamic>? order;
  List<Map<String, dynamic>> disputes = [];
  bool _disputesLoaded = false;
  final Set<int> _reworkResponding = {};
  double walletBalance = 0;
  bool walletLoading = true;
  bool loading = true;
  bool paying = false;
  bool _quoteResponding = false;
  bool _rescheduling = false;
  int? _currentExtraWorkId;
  int? _extraWorkBusyId;
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
      await loadDisputes();
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


  Future<void> respondToExtraWork(Map<String, dynamic> proposal, String decision, {String? paymentChoice}) async {
    final id = int.tryParse(proposal['id']?.toString() ?? '');
    if (id == null || _extraWorkBusyId != null) return;
    setState(() => _extraWorkBusyId = id);
    try {
      final result = await BookingApi.request(
        '/api/v1/bookings/extra-work/' + id.toString() + '/decision/',
        method: 'POST',
        data: {'decision': decision, if (paymentChoice != null) 'payment_choice': paymentChoice},
      );
      await loadOrder(showLoader: false);
      if (!mounted) return;
      if (decision == 'approve' && paymentChoice == 'separate') {
        await startExtraWorkPayment(result);
      } else {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text(decision == 'reject' ? 'Extra-work request rejected.' : 'Approved amount will be included in this appointment’s final balance.'),
        ));
      }
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Could not update extra-work request: ' + e.toString())));
      await loadOrder(showLoader: false);
    } finally {
      if (mounted) setState(() => _extraWorkBusyId = null);
    }
  }

  Future<void> startExtraWorkPayment(Map<String, dynamic> proposal) async {
    final id = int.tryParse(proposal['id']?.toString() ?? '');
    final total = amount(proposal['total_amount']);
    if (id == null || total <= 0 || paying) return;
    final walletController = TextEditingController(text: '0.00');
    final walletAmount = await showDialog<double>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Pay for approved extra work'),
        content: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('Total: ₹' + total.toStringAsFixed(2)),
          const SizedBox(height: 12),
          Text('Available AIRway wallet: ₹' + walletBalance.toStringAsFixed(2)),
          const SizedBox(height: 8),
          TextField(controller: walletController, keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: const InputDecoration(labelText: 'Use wallet amount (₹)', border: OutlineInputBorder())),
        ]),
        actions: [
          TextButton(onPressed: () => Navigator.pop(dialogContext), child: const Text('Pay later')),
          FilledButton(onPressed: () {
            final value = double.tryParse(walletController.text.trim());
            if (value == null || !value.isFinite || value < 0 || value > walletBalance || value > total ||
                (value * 100).roundToDouble() != value * 100) {
              ScaffoldMessenger.of(dialogContext).showSnackBar(const SnackBar(content: Text('Enter a valid wallet amount within your available balance and proposal total.')));
              return;
            }
            Navigator.pop(dialogContext, value);
          }, child: const Text('Continue')),
        ],
      ),
    );
    walletController.dispose();
    if (walletAmount == null || !mounted) return;
    setState(() { paying = true; _currentExtraWorkId = id; });
    try {
      final payment = await PaymentApi.createExtraWorkPayment(id, walletAmount: walletAmount.toStringAsFixed(2));
      await loadWalletBalance();
      if (payment['already_paid'] == true || payment['payment_status']?.toString() == 'paid') {
        if (!mounted) return;
        setState(() { paying = false; _currentExtraWorkId = null; });
        await loadOrder(showLoader: false);
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Extra-work payment is complete.')));
        return;
      }
      final gatewayOrderId = payment['order_id']?.toString() ?? '';
      final key = payment['key_id']?.toString() ?? '';
      if (gatewayOrderId.isEmpty || key.isEmpty) throw Exception('Payment gateway order could not be initialized.');
      razorpay.open({
        'key': key, 'amount': payment['amount'], 'currency': payment['currency'] ?? 'INR',
        'name': 'AIRway', 'description': 'Approved extra work #' + id.toString(),
        'order_id': gatewayOrderId, 'theme': {'color': '#075B43'},
      });
    } catch (e) {
      if (mounted) {
        setState(() { paying = false; _currentExtraWorkId = null; });
        await loadOrder(showLoader: false);
        await loadWalletBalance();
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Could not start extra-work payment: ' + e.toString())));
      }
    }
  }

  Widget _extraWorkRefundSection(
    Map<String, dynamic> row,
    Map<String, dynamic> proposal,
  ) {
    final proposalId = proposal['id']?.toString();
    final refunds = (row['refunds'] as List? ?? [])
        .whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item))
        .where((refund) => refund['extra_work_id']?.toString() == proposalId)
        .toList();
    if (refunds.isEmpty) return const SizedBox.shrink();
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(top: 10),
      padding: const EdgeInsets.all(11),
      decoration: BoxDecoration(
        color: const Color(0xFFF7F4FF),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFFE5DDFB)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            const Icon(Icons.account_balance_wallet_outlined, size: 16, color: violet),
            const SizedBox(width: 6),
            const Text(
              'Refund for this additional work',
              style: TextStyle(fontWeight: FontWeight.w800, color: ink, fontSize: 12),
            ),
          ]),
          const SizedBox(height: 7),
          for (var index = 0; index < refunds.length; index++) ...[
            if (index > 0) const Divider(height: 12, color: Color(0xFFE5DDFB)),
            _refundRow(refunds[index]),
          ],
        ],
      ),
    );
  }

  Widget extraWorkSection(Map<String, dynamic> row) {
    final proposals = (row['extra_work'] as List? ?? []).whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item)).toList();
    if (proposals.isEmpty) return const SizedBox.shrink();
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const SizedBox(height: 12),
      for (final proposal in proposals)
        Container(
          margin: const EdgeInsets.only(bottom: 8), padding: const EdgeInsets.all(13),
          decoration: BoxDecoration(color: const Color(0xFFFBFAFF), borderRadius: BorderRadius.circular(15), border: Border.all(color: const Color(0xFFE8E2F5))),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              const Icon(Icons.add_task_rounded, color: violet, size: 18), const SizedBox(width: 7),
              const Expanded(child: Text('Additional work request', style: TextStyle(fontWeight: FontWeight.w900, color: ink))),
              Text('₹' + amount(proposal['total_amount']).toStringAsFixed(2), style: const TextStyle(fontWeight: FontWeight.w900, color: ink)),
            ]),
            const SizedBox(height: 7),
            Text(proposal['reason']?.toString() ?? '', style: const TextStyle(color: sub, fontSize: 13)),
            for (final item in (proposal['line_items'] as List? ?? []).whereType<Map>())
              Padding(padding: const EdgeInsets.only(top: 5), child: Row(children: [
                Expanded(child: Text(item['description'].toString() + ' × ' + item['quantity'].toString(), style: const TextStyle(color: ink, fontSize: 12))),
                Text('₹' + amount(item['line_total']).toStringAsFixed(2), style: const TextStyle(color: ink, fontSize: 12, fontWeight: FontWeight.w700)),
              ])),
            if ((proposal['additional_duration_minutes'] as num? ?? 0) > 0)
              Padding(padding: const EdgeInsets.only(top: 5), child: Text('Additional time: ' + proposal['additional_duration_minutes'].toString() + ' minutes', style: const TextStyle(color: sub, fontSize: 12))),
            const SizedBox(height: 8),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
              decoration: BoxDecoration(
                color: const Color(0xFFF1EDFF),
                borderRadius: BorderRadius.circular(9),
              ),
              child: Text(
                proposal['status'] == 'pending_customer' ? 'Awaiting your decision'
                  : proposal['status'] == 'approved'
                    ? 'Approved • ' + (proposal['payment_choice'] == 'separate' ? 'Separate payment' : 'Added to appointment balance') + ' • ' + (proposal['payment_status'] == 'paid' ? 'Paid' : 'Payment pending')
                    : 'Request ' + proposal['status'].toString(),
                style: const TextStyle(color: violet, fontSize: 12, fontWeight: FontWeight.w800),
              ),
            ),
            _extraWorkRefundSection(row, proposal),
            if (proposal['status'] == 'pending_customer') ...[
              const SizedBox(height: 10),
              if (_extraWorkBusyId == proposal['id'])
                const Center(child: CircularProgressIndicator())
              else
                Wrap(spacing: 8, children: [
                  OutlinedButton(onPressed: () => respondToExtraWork(proposal, 'reject'), child: const Text('Reject')),
                  FilledButton(onPressed: () => showDialog<String>(
                    context: context,
                    builder: (dialogContext) => AlertDialog(
                      title: const Text('Approve extra work'),
                      content: Text('Choose how to pay ₹' + amount(proposal['total_amount']).toStringAsFixed(2) + '.'),
                      actions: [
                        TextButton(onPressed: () => Navigator.pop(dialogContext, 'separate'), child: const Text('Pay separately')),
                        FilledButton(onPressed: () => Navigator.pop(dialogContext, 'add_to_balance'), child: const Text('Add to final balance')),
                      ],
                    ),
                  ).then((choice) { if (choice != null) respondToExtraWork(proposal, 'approve', paymentChoice: choice); }),
                    child: const Text('Approve')),
                ]),
            ] else if (proposal['status'] == 'approved' && proposal['payment_choice'] == 'separate' && proposal['payment_status'] != 'paid') ...[
              const SizedBox(height: 8),
              SizedBox(width: double.infinity, child: OutlinedButton.icon(
                onPressed: paying ? null : () => startExtraWorkPayment(proposal),
                icon: const Icon(Icons.payment_rounded, size: 17), label: const Text('Pay approved extra work'),
              )),
            ],
          ]),
        ),
    ]);
  }

  Future<void> startPayment({int? appointmentGroupId}) async {
    Map<String, dynamic>? selectedGroup;
    if (appointmentGroupId != null) {
      for (final rawGroup in (order?['appointment_groups'] as List? ?? [])) {
        if (rawGroup is Map &&
            rawGroup['id']?.toString() == appointmentGroupId.toString()) {
          selectedGroup = Map<String, dynamic>.from(rawGroup);
          break;
        }
      }
    }
    final hasAppointmentGroups =
        (order?['appointment_groups'] as List? ?? []).isNotEmpty;
    final advanceReady = appointmentGroupId == null &&
        order?['ready_for_advance'] == true;
    final balanceReady = selectedGroup != null
        ? selectedGroup['ready_for_balance'] == true
        : !hasAppointmentGroups && order?['ready_for_balance'] == true;
    final legacyReady = appointmentGroupId == null &&
        order?['ready_for_legacy_payment'] == true;
    if ((!advanceReady && !balanceReady && !legacyReady) || paying) return;
    final stage = selectedGroup != null
        ? 'balance'
        : advanceReady ? 'advance' : balanceReady ? 'balance' : 'legacy';
    _currentPaymentStage = stage;
    final stageDue = selectedGroup != null
        ? amount(selectedGroup['balance_due'])
        : amount(order == null
            ? null
            : order![advanceReady
                ? 'advance_due'
                : balanceReady ? 'balance_due' : 'legacy_payment_due']);
    final rawWalletAmount = walletAmountController.text.trim();
    final parsedWalletAmount = rawWalletAmount.isEmpty ? 0.0 : double.tryParse(rawWalletAmount);
    if (parsedWalletAmount == null || !parsedWalletAmount.isFinite) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(AirwayText.tr('Enter a valid wallet amount.', 'वॉलेट की सही राशि दर्ज करें।'))),
      );
      return;
    }
    final walletAmount = selectedGroup != null
        ? parsedWalletAmount.clamp(0.0, stageDue).toDouble()
        : parsedWalletAmount;
    if (walletAmount < 0 || walletAmount > walletBalance || walletAmount > stageDue) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(AirwayText.tr('Enter a wallet amount within your available balance and the amount due now.', 'उपलब्ध वॉलेट बैलेंस और अभी देय राशि के भीतर रकम दर्ज करें।'))),
      );
      return;
    }
    if ((walletAmount * 100).roundToDouble() != walletAmount * 100) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(AirwayText.tr('Wallet amount can have at most two decimal places.', 'वॉलेट राशि में अधिकतम दो दशमलव स्थान हो सकते हैं।'))),
      );
      return;
    }

    setState(() => paying = true);
    try {
      final payment = await PaymentApi.createOrderForParent(
        widget.orderId,
        walletAmount: walletAmount.toStringAsFixed(2),
        stage: stage,
        appointmentGroupId: appointmentGroupId,
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
            title: Text(AirwayText.tr('Payment successful', 'भुगतान सफल')),
            content: Text(
              paidByWallet
                  ? 'Your ${_currentPaymentStage == 'advance' ? '30% advance' : _currentPaymentStage == 'balance' ? 'final 70% balance' : 'full payment'} was paid using your AIRway wallet.'
                  : 'Your ${_currentPaymentStage == 'advance' ? '30% advance' : _currentPaymentStage == 'balance' ? 'final 70% balance' : 'full payment'} has already been paid.',
            ),
            actions: [FilledButton(onPressed: () => Navigator.pop(ctx), child: Text(AirwayText.tr('Done', 'हो गया')))],
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
        'description': selectedGroup != null
            ? 'Appointment #' + selectedGroup['group_number'].toString() + ' balance'
            : 'Service order #' + widget.orderId.toString(),
        'order_id': gatewayOrderId,
        'theme': {'color': '#075B43'},
      });
    } catch (e) {
      if (mounted) {
        setState(() => paying = false);
        loadWalletBalance();
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(AirwayText.tr('Could not start payment: $e', 'भुगतान शुरू नहीं हो सका: $e'))));
      }
    }
  }

  Future<void> onPaymentSuccess(PaymentSuccessResponse response) async {
    final orderId = response.orderId;
    final paymentId = response.paymentId;
    final signature = response.signature;
    if (orderId == null || paymentId == null || signature == null) {
      if (mounted) {
        setState(() {
          paying = false;
          _currentExtraWorkId = null;
        });
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(AirwayText.tr('Payment could not be verified. Please check your order before retrying.', 'भुगतान वेरिफ़ाई नहीं हो सका। दोबारा कोशिश करने से पहले अपना ऑर्डर जाँचें।'))),
        );
        await loadOrder(showLoader: false);
      }
      return;
    }
    try {
      final extraWorkId = _currentExtraWorkId;
      final verification = await PaymentApi.verifyPayment(
        razorpayOrderId: orderId,
        razorpayPaymentId: paymentId,
        razorpaySignature: signature,
      );
      if (!mounted) return;
      setState(() {
        paying = false;
        _currentExtraWorkId = null;
      });
      await loadOrder(showLoader: false);
      await loadWalletBalance();
      if (!mounted) return;
      if (extraWorkId != null) {
        final extraPaid = verification['status']?.toString().toLowerCase() == 'paid';
        showDialog<void>(
          context: context,
          builder: (ctx) => AlertDialog(
            icon: Icon(extraPaid ? Icons.verified_rounded : Icons.hourglass_top_rounded, color: extraPaid ? violet : sub, size: 44),
            title: Text(extraPaid ? 'Extra-work payment successful' : 'Extra-work payment not confirmed'),
            content: Text(extraPaid
                ? 'Your approved additional work payment has been verified.'
                : 'AIRway has not confirmed this payment as paid yet. Refresh the order before retrying.'),
            actions: [FilledButton(onPressed: () => Navigator.pop(ctx), child: const Text('Done'))],
          ),
        );
        return;
      }

      // Razorpay's client callback only means the checkout flow returned.
      // The backend's verified PAID state is the only success condition.
      final paymentStatus = verification['status']?.toString().toLowerCase();
      final paid = paymentStatus == 'paid';
      final refunded = paymentStatus == 'refunded';
      final title = paid
          ? 'Payment successful'
          : refunded
              ? 'Payment refunded'
              : 'Payment not confirmed';
      final message = paid
          ? 'Your ${_currentPaymentStage == 'advance' ? '30% advance' : 'final 70% balance'} has been verified successfully.'
          : refunded
              ? 'The late payment was refunded because the wallet funds were no longer available. You can retry checkout.'
              : 'Razorpay returned control, but AIRway has not confirmed this payment as paid. Do not pay again yet. Refresh your order or contact support if the status does not update.';

      showDialog<void>(
        context: context,
        builder: (ctx) => AlertDialog(
          icon: Icon(
            paid
                ? Icons.verified_rounded
                : refunded
                    ? Icons.currency_rupee_rounded
                    : Icons.hourglass_top_rounded,
            color: paid ? violet : sub,
            size: 48,
          ),
          title: Text(title),
          content: Text(message),
          actions: [FilledButton(onPressed: () => Navigator.pop(ctx), child: Text(AirwayText.tr('Done', 'हो गया')))],
        ),
      );
    } catch (e) {
      if (mounted) {
        setState(() {
          paying = false;
          _currentExtraWorkId = null;
        });
        await loadOrder(showLoader: false);
        await loadWalletBalance();
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(AirwayText.tr('Payment verification is still unresolved: $e', 'भुगतान वेरिफ़िकेशन अभी स्पष्ट नहीं है: $e'))),
        );
      }
    }
  }

  void onPaymentError(PaymentFailureResponse response) {
    if (!mounted) return;
    setState(() {
      paying = false;
      _currentExtraWorkId = null;
    });
    loadWalletBalance();
    loadOrder(showLoader: false);
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(response.message ?? 'Payment was not completed. You can try again.')),
    );
  }

  void onExternalWallet(ExternalWalletResponse response) {
    if (!mounted) return;
    setState(() {
      paying = false;
      _currentExtraWorkId = null;
    });
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(AirwayText.tr('External wallet selected: ${response.walletName ?? 'Wallet'}', 'बाहरी वॉलेट चुना गया: ${response.walletName ?? 'वॉलेट'}'))),
    );
  }


  Future<void> raiseDispute(Map<String, dynamic> row, {bool isNoShow = false}) async {
    final bookingId = int.tryParse(row['booking_id']?.toString() ?? '');
    if (bookingId == null) return;
    final descriptionController = TextEditingController(
      text: isNoShow ? 'The assigned professional did not arrive for the scheduled appointment.' : '',
    );
    var category = isNoShow ? 'worker_conduct' : 'service_quality';
    var outcome = isNoShow ? 'investigation' : 'refund_review';
    File? evidencePhoto;
    final payload = await showDialog<Map<String, String>>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (dialogContext, setDialogState) => AlertDialog(
          title: const Text('Report a service issue'),
          content: SingleChildScrollView(
            child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
              DropdownButtonFormField<String>(
                value: category,
                decoration: const InputDecoration(labelText: 'Issue type'),
                items: const [
                  DropdownMenuItem(value: 'service_quality', child: Text('Service quality')),
                  DropdownMenuItem(value: 'damage', child: Text('Property damage')),
                  DropdownMenuItem(value: 'payment', child: Text('Payment or refund')),
                  DropdownMenuItem(value: 'worker_conduct', child: Text('Professional conduct')),
                  DropdownMenuItem(value: 'safety', child: Text('Safety concern')),
                  DropdownMenuItem(value: 'other', child: Text('Other')),
                ],
                onChanged: (value) => setDialogState(() => category = value ?? category),
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<String>(
                value: outcome,
                decoration: const InputDecoration(labelText: 'What would help?'),
                items: const [
                  DropdownMenuItem(value: 'refund_review', child: Text('Review my refund')),
                  DropdownMenuItem(value: 'rework', child: Text('Request service recovery')),
                  DropdownMenuItem(value: 'investigation', child: Text('Investigate this issue')),
                  DropdownMenuItem(value: 'other', child: Text('Other')),
                ],
                onChanged: (value) => setDialogState(() => outcome = value ?? outcome),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: descriptionController,
                maxLines: 4,
                maxLength: 5000,
                decoration: const InputDecoration(
                  labelText: 'Describe what happened',
                  hintText: 'Include the relevant details so AIRway support can review it.',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 8),
              Align(
                alignment: Alignment.centerLeft,
                child: TextButton.icon(
                  onPressed: () async {
                    final picked = await ImagePicker().pickImage(
                      source: ImageSource.gallery,
                      imageQuality: 85,
                    );
                    if (picked != null) {
                      setDialogState(() => evidencePhoto = File(picked.path));
                    }
                  },
                  icon: const Icon(Icons.add_photo_alternate_outlined),
                  label: Text(evidencePhoto == null
                      ? 'Attach an evidence photo (optional)'
                      : 'Evidence photo selected'),
                ),
              ),
            ]),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(dialogContext), child: const Text('Cancel')),
            FilledButton(
              onPressed: () {
                if (descriptionController.text.trim().isEmpty) return;
                Navigator.pop(dialogContext, {
                  'category': category,
                  'requested_outcome': outcome,
                  'description': descriptionController.text.trim(),
                });
              },
              child: const Text('Submit report'),
            ),
          ],
        ),
      ),
    );
    descriptionController.dispose();
    if (payload == null || !mounted) return;
    try {
      final dispute = await BookingApi.createDispute(
        bookingId: bookingId,
        category: payload['category']!,
        description: payload['description']!,
        requestedOutcome: payload['requested_outcome']!,
      );
      var message = 'Your report has been sent to AIRway support.';
      if (evidencePhoto != null) {
        try {
          await BookingApi.uploadDisputeEvidence(
            disputeId: int.parse(dispute['id'].toString()),
            photo: evidencePhoto!,
          );
        } catch (uploadError) {
          message = 'Report submitted, but the evidence photo could not be uploaded: $uploadError';
        }
      }
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
      await loadDisputes(force: true);
      await loadOrder(showLoader: false);
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Could not submit report: $e')),
      );
    }
  }

  Future<void> loadDisputes({bool force = false}) async {
    if (_disputesLoaded && !force) return;
    try {
      final result = await BookingApi.getDisputes();
      if (!mounted) return;
      setState(() { disputes = result; _disputesLoaded = true; });
    } catch (_) {
      // Order details remain usable if support history is temporarily unavailable.
    }
  }

  Widget disputeSection(Map<String, dynamic> row) {
    final bookingId = int.tryParse(row['booking_id']?.toString() ?? '');
    if (bookingId == null) return const SizedBox.shrink();
    final items = disputes.where((item) =>
        int.tryParse(item['booking_id']?.toString() ?? '') == bookingId).toList();
    if (items.isEmpty) return const SizedBox.shrink();
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(top: 10),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: pale,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: line),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Row(children: [
          Icon(Icons.support_agent_rounded, color: violet, size: 17),
          SizedBox(width: 7),
          Text('Your AIRway support reports', style: TextStyle(fontWeight: FontWeight.w800, color: ink, fontSize: 12)),
        ]),
        const SizedBox(height: 8),
        for (final item in items) ...[
          Row(children: [
            Expanded(child: Text(
              (item['category']?.toString() ?? 'other').replaceAll('_', ' '),
              style: const TextStyle(fontWeight: FontWeight.w700, color: ink, fontSize: 12),
            )),
            Text(
              (item['status']?.toString() ?? 'open').replaceAll('_', ' ').toUpperCase(),
              style: const TextStyle(fontWeight: FontWeight.w800, color: violet, fontSize: 10),
            ),
          ]),
          if ((item['resolution_note']?.toString() ?? '').isNotEmpty) ...[
            const SizedBox(height: 4),
            Text(item['resolution_note'].toString(), style: const TextStyle(color: sub, fontSize: 12)),
          ],
          for (final event in (item['status_history'] as List? ?? const []).whereType<Map>())
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text(
                '${(event['to_status']?.toString() ?? '').replaceAll('_', ' ').toUpperCase()}${(event['note']?.toString() ?? '').isNotEmpty ? ' — ${event['note']}' : ''}',
                style: const TextStyle(color: sub, fontSize: 11),
              ),
            ),
          finalEvidenceCount(item),
          reworkProposalCard(item, row),
          if (items.last != item) const Divider(height: 14, color: line),
        ],
      ]),
    );
  }


  Widget reworkProposalCard(Map<String, dynamic> item, Map<String, dynamic> orderRow) {
    final proposal = item['rework_proposal'];
    if (proposal is! Map) return const SizedBox.shrink();
    final data = Map<String, dynamic>.from(proposal);
    final proposalId = int.tryParse(data['id']?.toString() ?? '');
    if (proposalId == null) return const SizedBox.shrink();
    final statusValue = data['status']?.toString() ?? '';
    final scheduled = data['scheduled_at']?.toString() ?? '';
    final pending = statusValue == 'pending_customer';
    final responding = _reworkResponding.contains(proposalId);
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(top: 9),
      padding: const EdgeInsets.all(11),
      decoration: BoxDecoration(
        color: const Color(0xFFF2EEFF),
        borderRadius: BorderRadius.circular(11),
        border: Border.all(color: const Color(0xFFDCD2FF)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Row(children: [
          Icon(Icons.replay_circle_filled_rounded, color: violet, size: 17),
          SizedBox(width: 7),
          Expanded(child: Text('No-charge service recovery', style: TextStyle(fontWeight: FontWeight.w900, color: ink, fontSize: 12))),
        ]),
        const SizedBox(height: 5),
        Text('Professional: ${data['worker_name'] ?? 'AIRway Professional'}',
            style: const TextStyle(color: ink, fontSize: 12)),
        Text('Proposed visit: ${DateFormatForOrder.format(scheduled)}',
            style: const TextStyle(color: ink, fontSize: 12)),
        if (pending) ...[
          const SizedBox(height: 9),
          const Text('AIRway has proposed a free follow-up visit. Confirm the time to schedule it.',
              style: TextStyle(color: sub, fontSize: 11)),
          const SizedBox(height: 8),
          Row(children: [
            Expanded(child: OutlinedButton(
              onPressed: responding ? null : () => _respondToRework(proposalId, int.tryParse(item['id']?.toString() ?? '') ?? 0, false),
              child: const Text('Decline'),
            )),
            const SizedBox(width: 8),
            Expanded(child: FilledButton(
              style: FilledButton.styleFrom(backgroundColor: violet),
              onPressed: responding ? null : () => _respondToRework(proposalId, int.tryParse(item['id']?.toString() ?? '') ?? 0, true),
              child: responding
                  ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                  : const Text('Accept visit'),
            )),
          ]),
        ] else ...[
          Padding(
            padding: const EdgeInsets.only(top: 5),
            child: Text(
              statusValue == 'accepted'
                  ? 'Confirmed • No payment required'
                  : statusValue == 'declined'
                      ? 'You declined this proposed visit'
                      : 'This proposal is no longer active',
              style: const TextStyle(color: sub, fontSize: 11, fontWeight: FontWeight.w700),
            ),
          ),
          if (statusValue == 'accepted' && data['followup_booking_id'] != null)
            Align(
              alignment: Alignment.centerLeft,
              child: TextButton.icon(
                onPressed: () async {
                  final bookingId = int.tryParse(data['followup_booking_id'].toString());
                  if (bookingId == null) return;
                  await Navigator.of(context).push<void>(
                    MaterialPageRoute(
                      builder: (_) => BookingTrackingScreen(
                        bookingId: bookingId,
                        serviceTitle: (orderRow['service'] is Map
                            ? orderRow['service']['service_title']?.toString()
                            : null) ?? 'AIRway Service',
                        initialStatus: data['followup_status']?.toString() ?? 'assigned',
                      ),
                    ),
                  );
                  if (mounted) await loadOrder(showLoader: false);
                },
                icon: const Icon(Icons.location_on_outlined, size: 16),
                label: const Text('Track recovery visit'),
              ),
            ),
        ],
      ]),
    );
  }

  Future<void> _respondToRework(int proposalId, int disputeId, bool accept) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text(accept ? 'Accept recovery visit?' : 'Decline recovery visit?'),
        content: Text(accept
            ? 'Confirm this proposed time. AIRway will schedule the follow-up visit at no extra charge.'
            : 'Are you sure you want to decline this proposed visit?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(dialogContext, false), child: const Text('Back')),
          FilledButton(
            onPressed: () => Navigator.pop(dialogContext, true),
            child: Text(accept ? 'Confirm visit' : 'Decline visit'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    setState(() => _reworkResponding.add(proposalId));
    try {
      await BookingApi.respondToRework(disputeId: disputeId, accept: accept);
      await loadDisputes(force: true);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(accept
            ? 'Your no-charge recovery visit is confirmed.'
            : 'The proposed recovery visit was declined.'),
      ));
    } catch (e) {
      await loadDisputes(force: true);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Could not update the recovery visit: $e')),
      );
    } finally {
      if (mounted) setState(() => _reworkResponding.remove(proposalId));
    }
  }

  Widget finalEvidenceCount(Map<String, dynamic> item) {
    final files = item['evidence_files'] as List? ?? const [];
    if (files.isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(top: 4),
      child: Text('${files.length} evidence photo(s) attached', style: const TextStyle(color: sub, fontSize: 11)),
    );
  }

  Future<void> cancelService(Map<String, dynamic> row) async {
    final bookingId = int.tryParse(row['booking_id']?.toString() ?? '');
    if (bookingId == null || row['can_cancel'] != true) return;
    final service = row['service'] is Map
        ? (row['service']['service_title']?.toString() ?? 'this service')
        : 'this service';
    final cancellationPolicy = row['cancellation_policy'] is Map
        ? Map<String, dynamic>.from(row['cancellation_policy'])
        : <String, dynamic>{};
    final lateFeeApplies = cancellationPolicy['late_fee_applies'] == true;
    final lateFeePercent = cancellationPolicy['late_fee_percent']?.toString() ?? '30';
    final cancellationMessage = lateFeeApplies
        ? 'This is within AIRway’s late-cancellation window. $lateFeePercent% of the already-paid advance will be retained as the cancellation fee; the remaining eligible amount will be refunded. Refund status will appear in this order.'
        : 'Do you want to cancel $service? Any eligible captured payment will be sent for refund. Refund status will appear in this order.';
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text(AirwayText.tr('Cancel this service?', 'यह सेवा रद्द करें?')),
        content: Text(cancellationMessage),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: Text(AirwayText.tr('Keep service', 'सेवा जारी रखें')),
          ),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: const Color(0xFFB3261E)),
            onPressed: () => Navigator.pop(dialogContext, true),
            child: Text(AirwayText.tr('Cancel service', 'सेवा रद्द करें')),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    try {
      await BookingApi.cancelBooking(bookingId, reason: 'Cancelled by customer');
      if (!mounted) return;
      await loadOrder(showLoader: false);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(AirwayText.tr('Service cancelled. Any eligible refund will be updated here.', 'सेवा रद्द हो गई। लागू रिफंड की जानकारी यहाँ अपडेट होगी।'))),
      );
    } catch (e) {
      if (!mounted) return;
      await loadOrder(showLoader: false);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(AirwayText.tr('Could not cancel this service: $e', 'सेवा रद्द नहीं हो सकी: $e'))),
      );
    }
  }

  Future<void> rescheduleService(Map<String, dynamic> row) async {
    if (_rescheduling) return;
    final bookingId = int.tryParse(row['booking_id']?.toString() ?? '');
    final service = row['service'] is Map
        ? Map<String, dynamic>.from(row['service'] as Map)
        : <String, dynamic>{};
    final serviceId = int.tryParse(service['service_id']?.toString() ?? '');
    final addressId = int.tryParse(order?['address_id']?.toString() ?? '');
    final scheduledAt = DateTime.tryParse(row['scheduled_at']?.toString() ?? '');
    if (bookingId == null || serviceId == null || addressId == null || scheduledAt == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(AirwayText.tr('Rescheduling details are unavailable. Please refresh the order.', 'रीशेड्यूल की जानकारी उपलब्ध नहीं है। ऑर्डर रीफ़्रेश करें।'))),
      );
      return;
    }

    final categoryAnswers = service['category_answers'] is Map
        ? Map<String, dynamic>.from(service['category_answers'] as Map)
        : <String, dynamic>{};
    final dropAt = DateTime.tryParse(row['drop_scheduled_at']?.toString() ?? '');
    final result = await Navigator.of(context).push<BookingScheduleResult>(
      MaterialPageRoute(
        builder: (_) => BookingScheduleScreen(
          serviceId: serviceId,
          addressId: addressId,
          variantId: int.tryParse(service['variant_id']?.toString() ?? ''),
          quantity: int.tryParse(row['quantity']?.toString() ?? '1') ?? 1,
          bookingMode: row['booking_mode']?.toString() ?? 'scheduled',
          categoryAnswers: categoryAnswers,
          excludeBookingId: bookingId,
          initialDate: scheduledAt.toLocal(),
          initialTime: TimeOfDay.fromDateTime(scheduledAt.toLocal()),
          initialDropTime: dropAt == null ? null : TimeOfDay.fromDateTime(dropAt.toLocal()),
        ),
      ),
    );
    if (result == null || !mounted) return;

    final shared = (order?['scheduling'] as Map?)?['mode'] == 'same_appointment';
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text(AirwayText.tr('Confirm reschedule', 'नया समय पक्का करें')),
        content: Text(shared
            ? AirwayText.tr('This order uses one shared appointment. All eligible services in this order will move to the new time.', 'इस ऑर्डर में सभी सेवाओं का समय एक है। इस ऑर्डर की सभी योग्य सेवाओं का समय बदल जाएगा।')
            : AirwayText.tr('Only this service will move to the selected time.', 'केवल इस सेवा का समय बदलेगा।')),
        actions: [
          TextButton(onPressed: () => Navigator.pop(dialogContext, false), child: Text(AirwayText.tr('Keep current time', 'पुराना समय रखें'))),
          FilledButton(onPressed: () => Navigator.pop(dialogContext, true), child: Text(AirwayText.tr('Confirm', 'पक्का करें'))),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    setState(() => _rescheduling = true);
    try {
      await BookingApi.rescheduleBooking(
        bookingId: bookingId,
        scheduledAt: result.scheduledAt,
        dropScheduledAt: result.dropScheduledAt,
      );
      await loadOrder(showLoader: false);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(AirwayText.tr('Booking time updated successfully.', 'बुकिंग का समय सफलतापूर्वक बदल गया।'))),
      );
    } catch (e) {
      if (!mounted) return;
      await loadOrder(showLoader: false);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(AirwayText.tr('Could not reschedule: $e', 'समय नहीं बदला जा सका: $e'))),
      );
    } finally {
      if (mounted) setState(() => _rescheduling = false);
    }
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

  Future<void> cancelAppointmentGroup(
    int groupId,
    List<Map<String, dynamic>> groupRows,
  ) async {
    final lateFeeRow = groupRows.cast<Map<String, dynamic>?>().firstWhere(
      (row) => row?['cancellation_policy'] is Map &&
          (row!['cancellation_policy'] as Map)['late_fee_applies'] == true,
      orElse: () => null,
    );
    final lateFeeApplies = lateFeeRow != null;
    final lateFeePercent = lateFeeApplies
        ? (lateFeeRow['cancellation_policy'] as Map)['late_fee_percent']?.toString() ?? '30'
        : '30';
    final cancellationMessage = lateFeeApplies
        ? 'At least one service in this appointment is within AIRway’s late-cancellation window. $lateFeePercent% of the already-paid advance for each affected service will be retained as the cancellation fee; remaining eligible amounts will be refunded. Other appointments in this order will remain unchanged.'
        : 'All services in this appointment will be cancelled. Other appointments in this order will remain unchanged. Eligible refunds will be processed separately.';
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text(AirwayText.tr('Cancel this appointment?', 'यह अपॉइंटमेंट रद्द करें?')),
        content: Text(cancellationMessage),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: Text(AirwayText.tr('Keep appointment', 'अपॉइंटमेंट जारी रखें')),
          ),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: const Color(0xFFB3261E)),
            onPressed: () => Navigator.pop(dialogContext, true),
            child: Text(AirwayText.tr('Cancel appointment', 'अपॉइंटमेंट रद्द करें')),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;
    try {
      await BookingApi.cancelAppointmentGroup(groupId);
      await loadOrder(showLoader: false);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(AirwayText.tr(
          'Appointment cancelled. Other appointments were not changed.',
          'अपॉइंटमेंट रद्द हो गया। दूसरे अपॉइंटमेंट नहीं बदले गए।',
        ))),
      );
    } catch (e) {
      if (!mounted) return;
      await loadOrder(showLoader: false);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(AirwayText.tr(
          'Could not cancel this appointment: $e',
          'अपॉइंटमेंट रद्द नहीं हो सका: $e',
        ))),
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

  Future<void> cancelRecurringPlan(int planId) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text(AirwayText.tr('Cancel recurring plan?', 'बार-बार आने वाला प्लान रद्द करें?')),
        content: Text(AirwayText.tr(
          'All undelivered visits will be cancelled. Any unused prepaid amount will be sent for refund processing. Completed visits will not be refunded.',
          'सभी डिलीवर न हुई विज़िट रद्द होंगी। बिना उपयोग की गई प्रीपेड राशि रिफंड के लिए भेजी जाएगी। पूरी हो चुकी विज़िट का रिफंड नहीं होगा।',
        )),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: Text(AirwayText.tr('Keep plan', 'प्लान जारी रखें')),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(dialogContext, true),
            child: Text(AirwayText.tr('Cancel plan', 'प्लान रद्द करें')),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    try {
      await BookingApi.cancelRecurringPlan(planId);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(AirwayText.tr('Recurring plan cancelled. Unused prepaid visits are being refunded.', 'प्लान रद्द हो गया। बिना उपयोग की गई प्रीपेड विज़िट का रिफंड किया जा रहा है।'))),
      );
      await loadOrder(showLoader: false);
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(e.toString().replaceFirst('Exception: ', ''))),
      );
    }
  }

  Future<void> rescheduleRecurringVisit(Map<String, dynamic> visit) async {
    final visitId = visit['id'] as int?;
    if (visitId == null) return;
    final current = DateTime.tryParse(visit['scheduled_at']?.toString() ?? '')?.toLocal()
        ?? DateTime.now().add(const Duration(days: 1));
    final today = DateTime.now();
    final initialDate = current.isBefore(DateTime(today.year, today.month, today.day))
        ? today
        : current;
    final date = await showDatePicker(
      context: context,
      initialDate: initialDate,
      firstDate: today,
      lastDate: today.add(const Duration(days: 180)),
    );
    if (date == null || !mounted) return;
    final time = await showTimePicker(
      context: context,
      initialTime: TimeOfDay.fromDateTime(current),
    );
    if (time == null || !mounted) return;
    final selected = DateTime(date.year, date.month, date.day, time.hour, time.minute);
    if (selected.isBefore(DateTime.now())) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(AirwayText.tr('Choose a future date and time.', 'भविष्य की तारीख और समय चुनें।'))),
      );
      return;
    }
    if (selected.isAtSameMomentAs(current)) return;
    try {
      await BookingApi.rescheduleRecurringVisit(
        visitId: visitId,
        scheduledAt: selected,
      );
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(AirwayText.tr('Visit rescheduled successfully.', 'विज़िट का समय सफलतापूर्वक बदला गया।'))),
      );
      await loadOrder(showLoader: false);
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(e.toString().replaceFirst('Exception: ', ''))),
      );
    }
  }

  Widget recurringWashSection(Map<String, dynamic> plan) {
    final visits = (plan['visits'] as List? ?? [])
        .whereType<Map>()
        .map((row) => Map<String, dynamic>.from(row))
        .toList();
    final refunds = (plan['refunds'] as List? ?? [])
        .whereType<Map>()
        .map((row) => Map<String, dynamic>.from(row))
        .toList();
    String label(String value) {
      switch (value) {
        case 'pending_setup': return 'Schedule setup pending';
        case 'booked': return 'Visit booked';
        case 'in_progress': return 'In progress';
        case 'completed': return 'Completed';
        case 'cancelled': return 'Cancelled';
        case 'skipped': return 'Skipped';
        default: return value.replaceAll('_', ' ');
      }
    }
    String dateLabel(dynamic raw) {
      final parsed = DateTime.tryParse(raw?.toString() ?? '')?.toLocal();
      if (parsed == null) return 'Schedule to be confirmed';
      const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
      final hour = parsed.hour % 12 == 0 ? 12 : parsed.hour % 12;
      final minute = parsed.minute.toString().padLeft(2, '0');
      final period = parsed.hour >= 12 ? 'PM' : 'AM';
      return '${parsed.day} ${months[parsed.month - 1]} ${parsed.year} • $hour:$minute $period';
    }
    return Container(
      padding: const EdgeInsets.all(15),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: line),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(AirwayText.tr('Recurring Car Wash', 'नियमित कार वॉश'), style: TextStyle(fontSize: 16, fontWeight: FontWeight.w900, color: ink)),
          const SizedBox(height: 5),
          Text(
            '${plan['frequency'] ?? 'Scheduled'} • ${plan['duration_days'] ?? ''} days • ${plan['vehicle_quantity'] ?? 1} vehicle(s)',
            style: const TextStyle(color: sub, fontSize: 13),
          ),
          const SizedBox(height: 4),
          Text(AirwayText.tr('Plan status: ${label(plan['status']?.toString() ?? '')}', 'प्लान की स्थिति: ${label(plan['status']?.toString() ?? '')}'), style: const TextStyle(color: sub, fontSize: 13)),
          for (final refund in refunds)
            Padding(
              padding: const EdgeInsets.only(top: 5),
              child: Text(
                'Unused balance refund ₹${amount(refund['amount']).toStringAsFixed(2)} • ${label(refund['status']?.toString() ?? '')}',
                style: TextStyle(
                  color: refund['status'] == 'processed' ? const Color(0xFF16834A) : sub,
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
          const SizedBox(height: 10),
          for (final visit in visits)
            Padding(
              padding: const EdgeInsets.only(top: 9),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    width: 30,
                    height: 30,
                    alignment: Alignment.center,
                    decoration: BoxDecoration(color: pale, borderRadius: BorderRadius.circular(9)),
                    child: Text('${visit['visit_number'] ?? ''}', style: const TextStyle(fontWeight: FontWeight.w900, color: violet)),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(dateLabel(visit['scheduled_at']), style: const TextStyle(fontWeight: FontWeight.w800, color: ink)),
                        const SizedBox(height: 2),
                        Text(label(visit['status']?.toString() ?? ''), style: const TextStyle(color: sub, fontSize: 12)),
                        if (visit['can_reschedule'] == true)
                          TextButton.icon(
                            onPressed: () => rescheduleRecurringVisit(visit),
                            icon: const Icon(Icons.edit_calendar_outlined, size: 15),
                            label: Text(AirwayText.tr('Reschedule', 'समय बदलें')),
                            style: TextButton.styleFrom(
                              padding: EdgeInsets.zero,
                              minimumSize: const Size(0, 28),
                              tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                              alignment: Alignment.centerLeft,
                            ),
                          ),
                        if (visit['booking_id'] is int)
                          TextButton.icon(
                            onPressed: () => Navigator.push(
                              context,
                              MaterialPageRoute(
                                builder: (_) => BookingTrackingScreen(
                                  bookingId: visit['booking_id'] as int,
                                  serviceTitle: plan['service_title']?.toString() ?? 'Car Wash',
                                  initialStatus: visit['booking_status']?.toString() ?? 'pending',
                                ),
                              ),
                            ),
                            icon: const Icon(Icons.location_searching_rounded, size: 15),
                            label: Text(AirwayText.tr('Track visit', 'विज़िट ट्रैक करें')),
                            style: TextButton.styleFrom(
                              padding: EdgeInsets.zero,
                              minimumSize: const Size(0, 28),
                              tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                              alignment: Alignment.centerLeft,
                            ),
                          ),
                      ],
                    ),
                  ),
                  Text('₹${amount(visit['prepaid_amount']).toStringAsFixed(0)}', style: const TextStyle(fontWeight: FontWeight.w700, color: ink)),
                ],
              ),
            ),
          if (visits.isEmpty)
            Text(AirwayText.tr('Your visit schedule is being prepared.', 'आपका विज़िट शेड्यूल तैयार किया जा रहा है।'), style: TextStyle(color: sub)),
          if (plan['can_cancel'] == true) ...[
            const SizedBox(height: 12),
            Align(
              alignment: Alignment.centerRight,
              child: TextButton(
                onPressed: () => cancelRecurringPlan(plan['id'] as int),
                style: TextButton.styleFrom(foregroundColor: Colors.red.shade700),
                child: Text(AirwayText.tr('Cancel recurring plan', 'नियमित प्लान रद्द करें')),
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _orderPriceRow(String label, double value, {bool isTotal = false, Color? valueColor}) {
    final formatted = (value < 0 ? '-₹' : '₹') + value.abs().toStringAsFixed(2);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        children: [
          Expanded(
            child: Text(label, style: TextStyle(
              color: isTotal ? ink : sub,
              fontWeight: isTotal ? FontWeight.w900 : FontWeight.w500,
              fontSize: isTotal ? 14 : 12,
            )),
          ),
          Text(formatted, style: TextStyle(
            color: valueColor ?? (isTotal ? violet : ink),
            fontWeight: isTotal ? FontWeight.w900 : FontWeight.w700,
            fontSize: isTotal ? 16 : 12,
          )),
        ],
      ),
    );
  }

  Widget orderBody() {
    final rows = (order?['items'] as List? ?? []).whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList();
    final serviceInProgress = rows.any((row) => row['booking_status'] == 'in_progress');
    final advanceReady = order?['ready_for_advance'] == true;
    final balanceReady = order?['ready_for_balance'] == true;
    final legacyReady = order?['ready_for_legacy_payment'] == true;
    final hasAppointmentGroups =
        (order?['appointment_groups'] as List? ?? []).isNotEmpty;
    final ready = advanceReady || balanceReady || legacyReady;
    final footerPaymentReady =
        advanceReady || (balanceReady && !hasAppointmentGroups) || legacyReady;
    final advancePaid = order?['advance_paid'] == true;
    final paid = order?['balance_paid'] == true || order?['legacy_paid'] == true || order?['status'] == 'paid';
    final total = amount(order?['total_amount']);
    final orderSubtotal = amount(order?['subtotal']);
    final orderDiscount = amount(order?['discount_amount']);
    final orderTax = amount(order?['tax_amount']);
    final advanceTotal = amount(order?['advance_total']);
    final balanceTotal = amount(order?['balance_total']);
    final campaignRows = (order?['campaigns'] as List? ?? [])
        .whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item))
        .toList();
    final checkoutExpiry = DateTime.tryParse(order?['checkout_expires_at']?.toString() ?? '')?.toLocal();
    final checkoutExpiryKind = order?['checkout_expiry_kind']?.toString();
    final checkoutRemaining = checkoutExpiry?.difference(DateTime.now());
    final checkoutSeconds = checkoutRemaining?.inSeconds ?? 0;
    final checkoutHour = checkoutExpiry == null
        ? 0
        : (checkoutExpiry.hour % 12 == 0 ? 12 : checkoutExpiry.hour % 12);
    final checkoutMinute = checkoutExpiry?.minute.toString().padLeft(2, '0') ?? '00';
    final checkoutPeriod = checkoutExpiry != null && checkoutExpiry.hour >= 12 ? 'PM' : 'AM';
    final checkoutTimeLabel = checkoutExpiry == null
        ? ''
        : '$checkoutHour:$checkoutMinute $checkoutPeriod';
    final checkoutCountdownLabel = checkoutSeconds <= 0
        ? 'Checkout hold has expired. Refresh the order to see the latest status.'
        : checkoutSeconds >= 3600
            ? 'About ${checkoutSeconds ~/ 3600} hr ${(checkoutSeconds % 3600) ~/ 60} min remaining'
            : 'About ${(checkoutSeconds / 60).ceil()} min remaining';
    final dueNowKey = advanceReady
        ? 'advance_due'
        : balanceReady
            ? 'balance_due'
            : 'legacy_payment_due';
    final dueNow = amount(order == null ? null : order![dueNowKey]);
    final advancePercentage = double.tryParse(order?['advance_percentage']?.toString() ?? '30') ?? 30.0;
    final balancePercentage = 100.0 - advancePercentage;
    final acceptedInspectionQuote = rows.any((row) =>
        row['quote'] is Map && row['quote']['status'] == 'accepted');
    final advancePercentLabel = advancePercentage == advancePercentage.roundToDouble()
        ? advancePercentage.toStringAsFixed(0)
        : advancePercentage.toStringAsFixed(1);
    final balancePercentLabel = balancePercentage == balancePercentage.roundToDouble()
        ? balancePercentage.toStringAsFixed(0)
        : balancePercentage.toStringAsFixed(1);
    final initialPaymentLabel = acceptedInspectionQuote ? 'initial payment' : '$advancePercentLabel% advance';
    final stageLabel = advanceReady ? initialPaymentLabel
        : balanceReady ? (acceptedInspectionQuote ? 'Remaining balance' : 'Final $balancePercentLabel% balance')
        : 'Full payment';
    return Column(children: [
      Expanded(child: ListView(
        padding: const EdgeInsets.all(18),
        children: [
          Container(
            padding: const EdgeInsets.all(18),
            decoration: BoxDecoration(color: pale, borderRadius: BorderRadius.circular(20)),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(paid ? 'Payment complete' : balanceReady ? 'An appointment is complete' : advancePaid ? 'Your professionals are being arranged' : advanceReady ? 'Confirm your order' : legacyReady ? 'Complete your payment' : 'Payment required',
                  style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w900, color: ink)),
              const SizedBox(height: 6),
              Text(paid ? 'Your order is fully paid.' : balanceReady
                  ? 'One or more appointments are complete. Pay each completed appointment balance; other appointments continue independently.'
                  : advancePaid
                      ? 'Your $initialPaymentLabel is received. Worker matching and service progress will appear here.'
                      : advanceReady
                          ? 'Pay $initialPaymentLabel now to start worker matching. The remaining balance is due only after all services are completed and verified.'
                          : legacyReady
                              ? 'This order was created before staged payments. Complete the remaining full payment to confirm it.'
                              : 'Pay the $initialPaymentLabel to start worker matching. This page refreshes automatically.',
                  style: const TextStyle(color: sub, height: 1.4)),
              const SizedBox(height: 12),
              Text(AirwayText.tr('Order total ₹${total.toStringAsFixed(0)}', 'ऑर्डर कुल ₹${total.toStringAsFixed(0)}'), style: const TextStyle(fontSize: 21, fontWeight: FontWeight.w900, color: violet)),
            ]),
          ),
          if (orderSubtotal > 0 || orderDiscount > 0 || orderTax > 0) ...[
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: line),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Order price breakdown', style: TextStyle(fontSize: 15, fontWeight: FontWeight.w900, color: ink)),
                  const SizedBox(height: 10),
                  _orderPriceRow('Service subtotal', orderSubtotal),
                  if (orderDiscount > 0) ...[
                    _orderPriceRow('Campaign savings', -orderDiscount, valueColor: const Color(0xFF2E7D52)),
                    for (final campaign in campaignRows)
                      Padding(
                        padding: const EdgeInsets.only(top: 2),
                        child: Text(
                          campaign['name']?.toString() ?? 'Applied offer',
                          style: const TextStyle(color: sub, fontSize: 11),
                        ),
                      ),
                  ],
                  _orderPriceRow('Taxes', orderTax),
                  const Divider(height: 20),
                  _orderPriceRow('Total after offer', total, isTotal: true),
                  if (order?['is_staged_payment'] == true) ...[
                    const SizedBox(height: 8),
                    _orderPriceRow(
                      advancePaid ? 'Advance received' : (acceptedInspectionQuote ? 'Initial payment' : '$advancePercentLabel% advance'),
                      advanceTotal,
                    ),
                    _orderPriceRow('Remaining balance', balanceTotal),
                  ],
                ],
              ),
            ),
            const SizedBox(height: 14),
          ],
          if (advanceReady && checkoutExpiry != null) ...[
            const SizedBox(height: 10),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(13),
              decoration: BoxDecoration(
                color: checkoutSeconds <= 0 ? const Color(0xFFFFEEEE) : const Color(0xFFFFF5E9),
                borderRadius: BorderRadius.circular(13),
                border: Border.all(color: checkoutSeconds <= 0 ? const Color(0xFFE7A0A3) : const Color(0xFFE8C99E)),
              ),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(Icons.timer_outlined, color: checkoutSeconds <= 0 ? const Color(0xFFB4232C) : const Color(0xFF80551D), size: 19),
                  const SizedBox(width: 9),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          checkoutExpiryKind == 'payment_attempt'
                              ? 'Payment attempt expires at $checkoutTimeLabel'
                              : 'Checkout reservation expires at $checkoutTimeLabel',
                          style: const TextStyle(fontWeight: FontWeight.w800, color: ink, fontSize: 12),
                        ),
                        const SizedBox(height: 3),
                        Text(
                          checkoutCountdownLabel,
                          style: const TextStyle(color: sub, fontSize: 11),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ],
          const SizedBox(height: 14),
          orderProgress(rows, paid, advancePaid, order?['is_staged_payment'] == true, advancePercentage.round(), acceptedInspectionQuote),
          const SizedBox(height: 14),
          appointmentGroupsOverview(rows),
          if (order?['recurring_wash_plan'] is Map) ...[
            const SizedBox(height: 14),
            recurringWashSection(Map<String, dynamic>.from(order!['recurring_wash_plan'] as Map)),
          ],
          const SizedBox(height: 18),
          Text(AirwayText.tr('Your services', 'आपकी सेवाएँ'), style: TextStyle(fontSize: 17, fontWeight: FontWeight.w900, color: ink)),
          const SizedBox(height: 10),
          if (serviceInProgress) ...[
            Container(
              padding: const EdgeInsets.all(13),
              decoration: BoxDecoration(color: pale, borderRadius: BorderRadius.circular(13)),
              child: Text(
                AirwayText.tr('When your professional requests completion verification, the secure code will appear inside that service below. Share it only after the work is finished.', 'जब आपका प्रोफ़ेशनल सेवा पूरी होने की पुष्टि माँगेगा, सुरक्षित कोड नीचे उस सेवा के अंदर दिखाई देगा। इसे केवल काम पूरा होने के बाद साझा करें।'),
                style: const TextStyle(color: sub, height: 1.4),
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
                Text(AirwayText.tr('Order total ₹${total.toStringAsFixed(2)}', 'ऑर्डर कुल ₹${total.toStringAsFixed(2)}'), style: const TextStyle(color: sub)),
                const SizedBox(height: 3),
                Text(AirwayText.tr('Due now ₹${dueNow.toStringAsFixed(2)}', 'अभी देय ₹${dueNow.toStringAsFixed(2)}'), style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w900, color: violet)),
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
                  Text(AirwayText.tr('AIRway wallet', 'AIRway वॉलेट'), style: TextStyle(fontSize: 16, fontWeight: FontWeight.w900, color: ink)),
                  const SizedBox(height: 5),
                  Text(
                    walletLoading
                        ? AirwayText.tr('Loading available balance…', 'उपलब्ध बैलेंस लोड हो रहा है…')
                        : AirwayText.tr('Available balance: ₹${walletBalance.toStringAsFixed(2)}', 'उपलब्ध बैलेंस: ₹${walletBalance.toStringAsFixed(2)}'),
                    style: const TextStyle(color: sub, fontSize: 13),
                  ),
                  const SizedBox(height: 10),
                  TextField(
                    controller: walletAmountController,
                    enabled: !walletLoading,
                    keyboardType: const TextInputType.numberWithOptions(decimal: true),
                    onChanged: (_) => setState(() {}),
                    decoration: InputDecoration(
                      labelText: AirwayText.tr('Use wallet amount (₹)', 'वॉलेट से इस्तेमाल की राशि (₹)'),
                      hintText: '0.00',
                      border: OutlineInputBorder(),
                      prefixIcon: Icon(Icons.account_balance_wallet_outlined),
                    ),
                  ),
                  const SizedBox(height: 10),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(AirwayText.tr('Amount due now', 'अभी देय राशि'), style: TextStyle(color: sub)),
                      Text('₹${dueNow.toStringAsFixed(2)}', style: const TextStyle(fontWeight: FontWeight.w700, color: ink)),
                    ],
                  ),
                  const SizedBox(height: 5),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(AirwayText.tr('Wallet applied', 'वॉलेट से भुगतान'), style: TextStyle(color: sub)),
                      Text('− ₹${selectedWalletAmount.toStringAsFixed(2)}', style: const TextStyle(fontWeight: FontWeight.w700, color: ink)),
                    ],
                  ),
                  const Divider(height: 18),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(AirwayText.tr('Pay online', 'ऑनलाइन भुगतान करें'), style: TextStyle(fontWeight: FontWeight.w900, color: ink)),
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
          if (footerPaymentReady && !paid)
            SizedBox(width: double.infinity, child: FilledButton(
              onPressed: paying ? null : startPayment,
              child: paying ? const SizedBox(height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white)) : Text(
                  selectedWalletAmount > 0 && selectedWalletAmount >= dueNow
                      ? AirwayText.tr('Pay with AIRway wallet', 'AIRway वॉलेट से भुगतान करें')
                      : AirwayText.tr('Pay ₹${(dueNow - selectedWalletAmount).clamp(0, dueNow).toStringAsFixed(2)}', '₹${(dueNow - selectedWalletAmount).clamp(0, dueNow).toStringAsFixed(2)} का भुगतान करें'),
                ),
            )),
          if (!ready && !paid)
            Text(AirwayText.tr('Pay the 30% advance to start worker matching. The remaining 70% is due after all active services are verified.', 'वर्कर मिलान शुरू करने के लिए 30% अग्रिम दें। बाकी 70% सभी सक्रिय सेवाओं के वेरिफ़ाई होने के बाद देय होगा।'), textAlign: TextAlign.center, style: TextStyle(color: sub, fontSize: 12)),
          if (paid)
            Text(AirwayText.tr('Paid successfully', 'भुगतान सफलतापूर्वक हो गया'), style: TextStyle(color: Color(0xFF2E7D52), fontWeight: FontWeight.w800)),
          const SizedBox(height: 8),
          SizedBox(width: double.infinity, child: OutlinedButton(
            onPressed: () => Navigator.push(context, MaterialPageRoute(builder: (_) => const BookingListScreen())),
            child: Text(AirwayText.tr('View My Bookings', 'मेरी बुकिंग देखें')),
          )),
        ])),
      ),
    ]);
  }


  Widget appointmentGroupsOverview(List<Map<String, dynamic>> rows) {
    final groups = (order?['appointment_groups'] as List? ?? [])
        .whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item))
        .toList()
      ..sort((a, b) => (a['group_number'] as int? ?? 0).compareTo(b['group_number'] as int? ?? 0));
    if (groups.isEmpty) return scheduleOverview(rows);

    return Container(
      padding: const EdgeInsets.all(15),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: line),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Icon(Icons.calendar_month_rounded, color: violet, size: 19),
            const SizedBox(width: 8),
            Text(AirwayText.tr('Your appointments', 'आपके अपॉइंटमेंट'),
                style: const TextStyle(fontWeight: FontWeight.w900, color: ink)),
          ]),
          const SizedBox(height: 8),
          for (var index = 0; index < groups.length; index++) ...[
            if (index > 0) const Divider(height: 18),
            Builder(builder: (context) {
              final group = groups[index];
              final groupId = int.tryParse(group['id']?.toString() ?? '');
              final groupNumber = group['group_number']?.toString() ?? '${index + 1}';
              final groupRows = rows.where((row) =>
                  row['appointment_group_id']?.toString() == group['id']?.toString()
              ).toList();
              final serviceNames = groupRows.map((row) {
                final service = row['service'] is Map
                    ? (row['service']['service_title']?.toString() ?? 'Service')
                    : 'Service';
                return service;
              }).toList();
              final groupStatus = group['status']?.toString() ?? 'pending';
              final canCancel = groupId != null &&
                  ['pending', 'confirmed', 'assigned'].contains(groupStatus);
              return Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(children: [
                    Container(
                      width: 28,
                      height: 28,
                      alignment: Alignment.center,
                      decoration: BoxDecoration(color: pale, borderRadius: BorderRadius.circular(9)),
                      child: Text(groupNumber, style: const TextStyle(color: violet, fontWeight: FontWeight.w900)),
                    ),
                    const SizedBox(width: 9),
                    Expanded(child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          AirwayText.tr('Appointment $groupNumber', 'अपॉइंटमेंट $groupNumber'),
                          style: const TextStyle(fontWeight: FontWeight.w800, color: ink),
                        ),
                        Text(
                          DateFormatForOrder.format(group['scheduled_at']?.toString() ?? ''),
                          style: const TextStyle(color: sub, fontSize: 12),
                        ),
                      ],
                    )),
                    Text(statusLabel(groupStatus), style: const TextStyle(color: violet, fontSize: 11, fontWeight: FontWeight.w700)),
                  ]),
                  if (serviceNames.isNotEmpty)
                    Padding(
                      padding: const EdgeInsets.only(left: 37, top: 5),
                      child: Text(serviceNames.join(' • '), style: const TextStyle(color: sub, fontSize: 12)),
                    ),
                  if (group['customer_message']?.toString().trim().isNotEmpty == true)
                    Padding(
                      padding: const EdgeInsets.only(left: 37, top: 5),
                      child: Text(
                        AirwayText.tr(
                          'Message to professional: ${group['customer_message']}',
                          'प्रोफेशनल के लिए संदेश: ${group['customer_message']}',
                        ),
                        style: const TextStyle(color: sub, fontSize: 12),
                      ),
                    ),
                  if (group['ready_for_balance'] == true && groupId != null)
                    Padding(
                      padding: const EdgeInsets.only(left: 37, top: 5),
                      child: Align(
                        alignment: Alignment.centerLeft,
                        child: FilledButton.tonalIcon(
                          onPressed: paying
                              ? null
                              : () => startPayment(appointmentGroupId: groupId),
                          icon: const Icon(Icons.payment_rounded, size: 16),
                          label: Text(AirwayText.tr(
                            'Pay balance ₹${amount(group['balance_due']).toStringAsFixed(2)}',
                            'शेष ₹${amount(group['balance_due']).toStringAsFixed(2)} दें',
                          )),
                        ),
                      ),
                    ),
                  if (group['balance_paid'] == true)
                    Padding(
                      padding: const EdgeInsets.only(left: 37, top: 5),
                      child: Text(
                        AirwayText.tr('Appointment balance paid', 'अपॉइंटमेंट का शेष भुगतान हो गया'),
                        style: const TextStyle(color: Color(0xFF2E7D52), fontSize: 11, fontWeight: FontWeight.w700),
                      ),
                    ),
                  if (canCancel)
                    Padding(
                      padding: const EdgeInsets.only(left: 37, top: 5),
                      child: Align(
                        alignment: Alignment.centerLeft,
                        child: TextButton.icon(
                          onPressed: () => cancelAppointmentGroup(groupId!, groupRows),
                          icon: const Icon(Icons.cancel_outlined, size: 15),
                          label: Text(AirwayText.tr('Cancel this appointment', 'यह अपॉइंटमेंट रद्द करें')),
                          style: TextButton.styleFrom(
                            foregroundColor: const Color(0xFFB3261E),
                            padding: EdgeInsets.zero,
                            visualDensity: VisualDensity.compact,
                          ),
                        ),
                      ),
                    ),
                ],
              );
            }),
          ],
        ],
      ),
    );
  }

  Widget scheduleOverview(List<Map<String, dynamic>> rows) {
    final groups = <String, List<String>>{};
    for (final row in rows) {
      final raw = row['scheduled_at']?.toString();
      if (raw == null || raw.isEmpty) continue;
      final service = row['service'] is Map
          ? (row['service']['service_title']?.toString() ?? 'Service')
          : 'Service';
      groups.putIfAbsent(raw, () => <String>[]).add(service);
    }
    if (groups.isEmpty) return const SizedBox.shrink();
    final entries = groups.entries.toList()
      ..sort((a, b) => DateTime.tryParse(a.key)?.compareTo(DateTime.tryParse(b.key) ?? DateTime(9999)) ?? 0);
    return Container(
      padding: const EdgeInsets.all(15),
      decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(16), border: Border.all(color: line)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Icon(Icons.calendar_month_rounded, color: violet, size: 19),
          SizedBox(width: 8),
          Text(AirwayText.tr('Your service schedule', 'आपका सेवा शेड्यूल'), style: TextStyle(fontWeight: FontWeight.w900, color: ink)),
        ]),
        const SizedBox(height: 5),
        Text(AirwayText.tr('Services sharing the same appointment are grouped together.', 'एक ही अपॉइंटमेंट वाली सेवाएँ एक साथ दिखाई गई हैं।'), style: TextStyle(color: sub, fontSize: 12)),
        const SizedBox(height: 10),
        for (var i = 0; i < entries.length; i++) ...[
          if (i > 0) const Divider(height: 16),
          Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Container(
              width: 28, height: 28,
              alignment: Alignment.center,
              decoration: BoxDecoration(color: pale, borderRadius: BorderRadius.circular(9)),
              child: Text('${i + 1}', style: const TextStyle(color: violet, fontWeight: FontWeight.w900)),
            ),
            const SizedBox(width: 10),
            Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(DateFormatForOrder.format(entries[i].key), style: const TextStyle(color: ink, fontWeight: FontWeight.w800)),
              const SizedBox(height: 3),
              Text(entries[i].value.join(' • '), style: const TextStyle(color: sub, fontSize: 12)),
            ])),
          ]),
        ],
      ]),
    );
  }

  Widget orderProgress(List<Map<String, dynamic>> rows, bool paid, bool advancePaid, bool staged, int advancePercentage, bool acceptedInspectionQuote) {
    final balancePercentage = 100 - advancePercentage;
    final firstPaymentLabel = acceptedInspectionQuote ? 'Initial payment' : '$advancePercentage% advance';
    final remainingLabel = acceptedInspectionQuote ? 'Remaining balance' : 'Remaining $balancePercentage%';
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
            (firstPaymentLabel, advancePaid ? 'Initial payment verified.' : 'Pay the initial amount to start worker matching.', advancePaid),
            ('Professionals assigned', assigned ? 'Every service has a professional.' : 'Waiting for worker acceptance.', assigned),
            ('Service completion', completed ? 'All services are verified with customer OTP.' : 'Each service is verified after the customer shares a code.', completed),
            (remainingLabel, paid ? 'Final balance paid. Order complete.' : completed ? 'Final balance is now due.' : 'Unlocked after all active services are verified.', paid),
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
        Text(AirwayText.tr('Order progress', 'ऑर्डर की प्रगति'), style: TextStyle(fontWeight: FontWeight.w900, color: ink)),
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
        if (row['appointment_group_number'] != null)
          Padding(
            padding: const EdgeInsets.only(top: 5),
            child: Text(
              AirwayText.tr(
                'Appointment ${row['appointment_group_number']}',
                'अपॉइंटमेंट ${row['appointment_group_number']}',
              ),
              style: const TextStyle(color: violet, fontSize: 11, fontWeight: FontWeight.w800),
            ),
          ),
        if (row['appointment_group_message']?.toString().trim().isNotEmpty == true)
          Padding(
            padding: const EdgeInsets.only(top: 5),
            child: Text(
              AirwayText.tr(
                'Message for professional: ${row['appointment_group_message']}',
                'प्रोफेशनल के लिए संदेश: ${row['appointment_group_message']}',
              ),
              style: const TextStyle(color: sub, fontSize: 12),
            ),
          ),
        if (snapshot['variant_title'] != null) Text(snapshot['variant_title'].toString(), style: const TextStyle(color: sub, fontSize: 12)),
        if (snapshot['unit_label']?.toString().isNotEmpty ?? false)
          Text('${row['quantity']} ${snapshot['unit_label']}', style: const TextStyle(color: sub, fontSize: 12)),
        const SizedBox(height: 6),
        Text(statusLabel(status), style: const TextStyle(color: violet, fontWeight: FontWeight.w700, fontSize: 12)),
        if (row['form_responses'] is List && (row['form_responses'] as List).isNotEmpty) ...[
          const SizedBox(height: 10),
          Text(AirwayText.tr('Service details', 'सेवा का विवरण'), style: TextStyle(fontWeight: FontWeight.w800, color: ink)),
          const SizedBox(height: 6),
          for (final answer in (row['form_responses'] as List).whereType<Map>())
            Padding(
              padding: const EdgeInsets.only(bottom: 9),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('${answer['label'] ?? answer['key']}: ${answer['value'] ?? ''}',
                      style: const TextStyle(color: sub, fontSize: 12)),
                  if (answer['photo_url']?.toString().isNotEmpty == true)
                    Padding(
                      padding: const EdgeInsets.only(top: 6),
                      child: FutureBuilder<Map<String, String>>(
                        future: BookingApi.getAuthHeaders(),
                        builder: (context, snapshot) {
                          if (!snapshot.hasData) {
                            return const SizedBox(height: 55, child: Center(child: CircularProgressIndicator()));
                          }
                          if (snapshot.hasError) return Text(AirwayText.tr('Could not load the attached photo.', 'संलग्न फ़ोटो लोड नहीं हो सकी।'));
                          return ClipRRect(
                            borderRadius: BorderRadius.circular(10),
                            child: Image.network(
                              answer['photo_url'].toString(),
                              headers: snapshot.data,
                              height: 130,
                              width: double.infinity,
                              fit: BoxFit.cover,
                              errorBuilder: (_, __, ___) => Text(AirwayText.tr('Attached photo is unavailable.', 'संलग्न फ़ोटो उपलब्ध नहीं है।')),
                            ),
                          );
                        },
                      ),
                    ),
                ],
              ),
            ),
        ],
        if (row['work_evidence'] is List && (row['work_evidence'] as List).isNotEmpty) ...[
          const SizedBox(height: 10),
          Text(AirwayText.tr('Work progress photos', 'काम की प्रगति की फ़ोटो'), style: TextStyle(fontWeight: FontWeight.w800, color: ink)),
          const SizedBox(height: 7),
          for (final evidence in (row['work_evidence'] as List).whereType<Map>())
            Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    evidence['stage'] == 'before' ? 'Before work' : 'After work',
                    style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: sub),
                  ),
                  if (evidence['note']?.toString().isNotEmpty == true)
                    Text(evidence['note'].toString(), style: const TextStyle(fontSize: 12, color: sub)),
                  const SizedBox(height: 5),
                  FutureBuilder<Map<String, String>>(
                    future: BookingApi.getAuthHeaders(),
                    builder: (context, snapshot) {
                      if (!snapshot.hasData) return const SizedBox(height: 55, child: Center(child: CircularProgressIndicator()));
                      if (snapshot.hasError) return Text(AirwayText.tr('Could not load work photo.', 'काम की फ़ोटो लोड नहीं हो सकी।'));
                      return ClipRRect(
                        borderRadius: BorderRadius.circular(10),
                        child: Image.network(
                          evidence['photo_url'].toString(),
                          headers: snapshot.data,
                          height: 130,
                          width: double.infinity,
                          fit: BoxFit.cover,
                          errorBuilder: (_, __, ___) => Text(AirwayText.tr('Work photo unavailable.', 'काम की फ़ोटो उपलब्ध नहीं है।')),
                        ),
                      );
                    },
                  ),
                ],
              ),
            ),
        ],
        if (row['quote'] is Map) ...[
          const SizedBox(height: 12),
          _quoteCard(row),
        ],
        extraWorkSection(row),
        disputeSection(row),
        if (row['completion_otp'] is Map &&
            (row['completion_otp']['code']?.toString().isNotEmpty ?? false)) ...[
          const SizedBox(height: 12),
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: const Color(0xFFEAF1EA),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: const Color(0xFFB9D4C0)),
            ),
            child: Row(children: [
              const Icon(Icons.lock_clock_outlined, color: violet),
              const SizedBox(width: 10),
              Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(AirwayText.tr('Service completion code', 'सेवा पूरी करने का कोड'), style: TextStyle(fontWeight: FontWeight.w800, color: ink, fontSize: 12)),
                const SizedBox(height: 3),
                SelectableText(
                  row['completion_otp']['code'].toString(),
                  style: const TextStyle(fontSize: 24, letterSpacing: 5, fontWeight: FontWeight.w900, color: violet),
                ),
                Text(AirwayText.tr('Share with your assigned professional after the service is finished.', 'सेवा पूरी होने के बाद यह कोड अपने असाइन किए गए प्रोफ़ेशनल को बताएँ।'), style: TextStyle(fontSize: 11, color: sub)),
              ])),
              IconButton(
                tooltip: AirwayText.tr('Copy code', 'कोड कॉपी करें'),
                onPressed: () {
                  Clipboard.setData(ClipboardData(text: row['completion_otp']['code'].toString()));
                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(AirwayText.tr('Completion code copied.', 'सेवा पूरी करने का कोड कॉपी हो गया।'))));
                },
                icon: const Icon(Icons.copy_rounded),
              ),
            ]),
          ),
        ],
        if (scheduled.isNotEmpty) ...[
          const SizedBox(height: 8),
          Row(children: [
            const Icon(Icons.event_available_rounded, size: 15, color: violet),
            const SizedBox(width: 6),
            Expanded(child: Text(AirwayText.tr('Service time: $scheduled', 'सेवा का समय: $scheduled'), style: const TextStyle(color: sub, fontSize: 12, fontWeight: FontWeight.w600))),
          ]),
        ],
        if (row['drop_scheduled_at']?.toString().isNotEmpty == true)
          Padding(
            padding: const EdgeInsets.only(top: 4, left: 21),
            child: Text(AirwayText.tr('Expected drop-off: ${DateFormatForOrder.format(row['drop_scheduled_at'].toString())}', 'अपेक्षित ड्रॉप-ऑफ़: ${DateFormatForOrder.format(row['drop_scheduled_at'].toString())}'), style: const TextStyle(color: sub, fontSize: 12)),
          ),
        if (worker != null) Text(AirwayText.tr('Professional: ${worker['name']?.toString() ?? 'Assigned'}', 'प्रोफ़ेशनल: ${worker['name']?.toString() ?? 'असाइन किया गया'}'), style: const TextStyle(color: sub, fontSize: 12)),
        if (row['advance_amount'] != null && row['balance_amount'] != null) ...[
          const SizedBox(height: 7),
          Row(
            children: [
              Expanded(child: Text(AirwayText.tr('Advance ₹${amount(row['advance_amount']).toStringAsFixed(2)}', 'अग्रिम ₹${amount(row['advance_amount']).toStringAsFixed(2)}'), style: const TextStyle(color: sub, fontSize: 11))),
              Expanded(child: Text(AirwayText.tr('Balance ₹${amount(row['balance_amount']).toStringAsFixed(2)}', 'शेष ₹${amount(row['balance_amount']).toStringAsFixed(2)}'), textAlign: TextAlign.end, style: const TextStyle(color: sub, fontSize: 11))),
            ],
          ),
        ],
        if (_bookingLevelRefunds(row).isNotEmpty) ...[
          const SizedBox(height: 10),
          refundSection(_bookingLevelRefunds(row)),
        ],
        const SizedBox(height: 8),
        SizedBox(width: double.infinity, child: OutlinedButton.icon(
          onPressed: status == 'cancelled' ? null : () => trackService(row),
          icon: const Icon(Icons.location_searching_rounded, size: 17),
          label: Text(AirwayText.tr('Track this service', 'यह सेवा ट्रैक करें')),
        )),
        if (row['can_reschedule'] == true) ...[
          const SizedBox(height: 8),
          SizedBox(width: double.infinity, child: OutlinedButton.icon(
            onPressed: _rescheduling ? null : () => rescheduleService(row),
            icon: const Icon(Icons.edit_calendar_outlined, size: 17),
            label: Text(_rescheduling
                ? AirwayText.tr('Updating time…', 'समय अपडेट हो रहा है…')
                : AirwayText.tr('Reschedule service', 'सेवा का समय बदलें')),
          )),
        ],
        if (row['can_cancel'] == true) ...[
          const SizedBox(height: 8),
          SizedBox(width: double.infinity, child: OutlinedButton.icon(
            onPressed: () => cancelService(row),
            icon: const Icon(Icons.cancel_outlined, size: 17),
            label: Text(AirwayText.tr('Cancel this service', 'यह सेवा रद्द करें')),
            style: OutlinedButton.styleFrom(
              foregroundColor: const Color(0xFFB3261E),
              side: const BorderSide(color: Color(0xFFE7B9B6)),
            ),
          )),
        ],
        if (status == 'in_progress' || status == 'completed' || row['can_report_no_show'] == true) ...[
          const SizedBox(height: 8),
          SizedBox(width: double.infinity, child: OutlinedButton.icon(
            onPressed: () => raiseDispute(
              row,
              isNoShow: status == 'assigned' && row['can_report_no_show'] == true,
            ),
            icon: const Icon(Icons.support_agent_rounded, size: 18),
            label: Text(
              status == 'assigned'
                  ? 'Report worker no-show'
                  : 'Report a problem',
            ),
          )),
        ],
        if (status == 'completed' && worker != null) ...[
          const SizedBox(height: 8),
          if (row['customer_has_rated'] == true)
            Row(children: [
              Icon(Icons.verified_rounded, size: 17, color: Color(0xFF2E7D52)),
              SizedBox(width: 7),
              Text(AirwayText.tr('Thank you for rating this professional.', 'इस प्रोफ़ेशनल को रेट करने के लिए धन्यवाद।'),
                  style: TextStyle(color: Color(0xFF2E7D52), fontSize: 12, fontWeight: FontWeight.w700)),
            ])
          else
            SizedBox(width: double.infinity, child: OutlinedButton.icon(
              onPressed: () => rateProfessional(row),
              icon: const Icon(Icons.star_rounded, size: 18),
              label: Text(AirwayText.tr('Rate professional', 'प्रोफ़ेशनल को रेट करें')),
            )),
        ],
      ]),
    );
  }

  Widget _quoteCard(Map<String, dynamic> row) {
    final quote = Map<String, dynamic>.from(row['quote'] as Map);
    final quoteStatus = quote['status']?.toString() ?? '';
    final lineItems = (quote['line_items'] as List? ?? [])
        .whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item))
        .toList();
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(13),
      decoration: BoxDecoration(
        color: pale,
        borderRadius: BorderRadius.circular(13),
        border: Border.all(color: line),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Expanded(child: Text(AirwayText.tr('Inspection estimate', 'निरीक्षण का अनुमान'), style: TextStyle(fontWeight: FontWeight.w900, color: ink))),
            Text('v${quote['version']}', style: const TextStyle(color: sub, fontSize: 11)),
          ]),
          const SizedBox(height: 7),
          for (final item in lineItems)
            Padding(
              padding: const EdgeInsets.only(bottom: 5),
              child: Row(children: [
                Expanded(child: Text('${item['description']} • ${item['type']}',
                    style: const TextStyle(color: sub, fontSize: 12))),
                Text('₹${amount(item['line_total']).toStringAsFixed(2)}',
                    style: const TextStyle(fontWeight: FontWeight.w700, color: ink, fontSize: 12)),
              ]),
            ),
          const Divider(height: 16),
          Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
            Text(AirwayText.tr('Repair estimate including tax', 'टैक्स सहित मरम्मत अनुमान'), style: TextStyle(fontWeight: FontWeight.w800, color: ink)),
            Text('₹${amount(quote['total_amount']).toStringAsFixed(2)}',
                style: const TextStyle(fontWeight: FontWeight.w900, color: violet, fontSize: 16)),
          ]),
          if (amount(quote['inspection_fee_credit']) > 0) ...[
            const Divider(height: 16),
            Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
              Expanded(child: Text(AirwayText.tr('Inspection visit already paid', 'निरीक्षण विज़िट का भुगतान हो चुका है'), style: const TextStyle(color: sub, fontSize: 12))),
              Text('− ₹${amount(quote['inspection_fee_credit']).toStringAsFixed(2)}', style: const TextStyle(color: Color(0xFF2E7D52), fontWeight: FontWeight.w800, fontSize: 12)),
            ]),
            const SizedBox(height: 5),
            Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
              Text(AirwayText.tr('Remaining repair balance', 'मरम्मत का बाकी भुगतान'), style: const TextStyle(color: ink, fontWeight: FontWeight.w900, fontSize: 13)),
              Text('₹${(amount(quote['total_amount']) - amount(quote['inspection_fee_credit'])).clamp(0, double.infinity).toStringAsFixed(2)}', style: const TextStyle(color: violet, fontWeight: FontWeight.w900, fontSize: 15)),
            ]),
          ],
          if (quote['notes']?.toString().isNotEmpty == true) ...[
            const SizedBox(height: 6),
            Text(quote['notes'].toString(), style: const TextStyle(color: sub, fontSize: 12)),
          ],
          const SizedBox(height: 7),
          Text(
            quoteStatus == 'pending_customer'
                ? AirwayText.tr('Please review this estimate and choose whether to approve it or request a revision.', 'इस अनुमान की समीक्षा करें और इसे स्वीकार करें या संशोधन माँगें।')
                : quoteStatus == 'accepted'
                    ? AirwayText.tr('You approved this estimate.', 'आपने यह अनुमान स्वीकार कर लिया है।')
                    : quoteStatus == 'rejected'
                        ? AirwayText.tr('You requested a revised estimate.', 'आपने संशोधित अनुमान माँगा है।')
                        : AirwayText.tr('Estimate status: ${quoteStatus.replaceAll('_', ' ')}', 'अनुमान की स्थिति: ${quoteStatus.replaceAll('_', ' ')}'),
            style: const TextStyle(color: sub, fontSize: 12),
          ),
          if (quoteStatus == 'pending_customer' && row['booking_status'] == 'in_progress') ...[
            const SizedBox(height: 10),
            Row(children: [
              Expanded(child: OutlinedButton(
                onPressed: _quoteResponding ? null : () => respondToQuote(row, 'reject'),
                child: Text(AirwayText.tr('Request revision', 'संशोधन माँगें')),
              )),
              const SizedBox(width: 8),
              Expanded(child: FilledButton(
                onPressed: _quoteResponding ? null : () => respondToQuote(row, 'accept'),
                child: _quoteResponding
                    ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
                    : Text(AirwayText.tr('Approve estimate', 'अनुमान स्वीकार करें')),
              )),
            ]),
            Align(
              alignment: Alignment.centerRight,
              child: TextButton(
                onPressed: _quoteResponding ? null : () => respondToQuote(row, 'cancel'),
                style: TextButton.styleFrom(foregroundColor: Colors.red.shade700),
                child: Text(AirwayText.tr('Decline repair', 'मरम्मत नहीं करवानी')),
              ),
            ),
          ],
        ],
      ),
    );
  }

  Future<void> respondToQuote(Map<String, dynamic> row, String decision) async {
    if (_quoteResponding) return;
    final bookingId = int.tryParse(row['booking_id']?.toString() ?? '');
    if (bookingId == null) return;
    if (decision == 'reject' || decision == 'cancel') {
      final isCancel = decision == 'cancel';
      final confirmed = await showDialog<bool>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          title: Text(isCancel
              ? AirwayText.tr('Decline this repair?', 'क्या यह मरम्मत नहीं करवानी है?')
              : AirwayText.tr('Request a revised estimate?', 'संशोधित अनुमान माँगें?')),
          content: Text(isCancel
              ? AirwayText.tr('This repair booking will be closed. Your already-paid inspection visit fee will remain settled; no repair balance will be charged.', 'यह मरम्मत बुकिंग बंद हो जाएगी। पहले से दिया गया निरीक्षण शुल्क समायोजित रहेगा और मरम्मत का बाकी भुगतान नहीं लिया जाएगा।')
              : AirwayText.tr('The professional will be asked to review your feedback and submit a revised estimate.', 'प्रोफ़ेशनल से आपकी प्रतिक्रिया देखकर नया अनुमान भेजने को कहा जाएगा।')),
          actions: [
            TextButton(onPressed: () => Navigator.pop(dialogContext, false), child: Text(AirwayText.tr('Go back', 'वापस जाएँ'))),
            FilledButton(
              onPressed: () => Navigator.pop(dialogContext, true),
              child: Text(isCancel
                  ? AirwayText.tr('Close repair booking', 'मरम्मत बुकिंग बंद करें')
                  : AirwayText.tr('Request revision', 'संशोधन माँगें')),
            ),
          ],
        ),
      );
      if (confirmed != true || !mounted) return;
    }
    setState(() => _quoteResponding = true);
    try {
      await BookingApi.request(
        '/api/v1/bookings/$bookingId/quote/respond/',
        method: 'POST',
        data: {'decision': decision},
      );
      await loadOrder(showLoader: false);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(decision == 'accept'
            ? 'Estimate approved. Your order total has been updated.'
            : 'Revision request sent to the professional.'),
      ));
    } catch (e) {
      if (mounted) {
        try {
          await loadOrder(showLoader: false);
        } catch (_) {}
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(AirwayText.tr('Could not update estimate: $e', 'अनुमान अपडेट नहीं हो सका: $e'))),
        );
      }
    } finally {
      if (mounted) setState(() => _quoteResponding = false);
    }
  }

  Future<void> rateProfessional(Map<String, dynamic> row) async {
    final bookingId = int.tryParse(row['booking_id']?.toString() ?? '');
    if (bookingId == null) return;
    var selectedRating = 5;
    final commentController = TextEditingController();
    final result = await showDialog<({int rating, String comment})>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (dialogContext, setDialogState) => AlertDialog(
          title: Text(AirwayText.tr('Rate your professional', 'अपने प्रोफ़ेशनल को रेट करें')),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(AirwayText.tr('How was your service experience?', 'आपका सेवा अनुभव कैसा रहा?')),
              const SizedBox(height: 12),
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: List.generate(5, (index) => IconButton(
                  onPressed: () => setDialogState(() => selectedRating = index + 1),
                  icon: Icon(
                    index < selectedRating ? Icons.star_rounded : Icons.star_outline_rounded,
                    color: const Color(0xFFFFB020),
                    size: 30,
                  ),
                )),
              ),
              TextField(
                controller: commentController,
                maxLength: 500,
                maxLines: 3,
                decoration: InputDecoration(
                  labelText: AirwayText.tr('Comment (optional)', 'टिप्पणी (वैकल्पिक)'),
                  border: OutlineInputBorder(),
                ),
              ),
            ],
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(dialogContext), child: Text(AirwayText.tr('Not now', 'अभी नहीं'))),
            FilledButton(
              onPressed: () => Navigator.pop(
                dialogContext,
                (rating: selectedRating, comment: commentController.text.trim()),
              ),
              child: Text(AirwayText.tr('Submit rating', 'रेटिंग भेजें')),
            ),
          ],
        ),
      ),
    );
    commentController.dispose();
    if (result == null || !mounted) return;
    try {
      await RatingApi.submitRating(
        bookingId: bookingId,
        rating: result.rating,
        ratingType: 'customer',
        comment: result.comment,
      );
      await loadOrder(showLoader: false);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(AirwayText.tr('Thank you. Your rating has been submitted.', 'धन्यवाद। आपकी रेटिंग भेज दी गई है।'))),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(AirwayText.tr('Could not submit rating: $e', 'रेटिंग भेजी नहीं जा सकी: $e'))),
      );
    }
  }

  List<Map<String, dynamic>> _bookingLevelRefunds(Map<String, dynamic> row) {
    return (row['refunds'] as List? ?? [])
        .whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item))
        .where((refund) => refund['extra_work_id'] == null)
        .toList();
  }

  Widget refundSection(List<Map<String, dynamic>> refunds) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFFF7F4FF),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFFE5DDFB)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.account_balance_wallet_outlined, color: violet, size: 19),
              SizedBox(width: 7),
              Text(AirwayText.tr('Refund updates', 'रिफंड अपडेट'), style: TextStyle(fontWeight: FontWeight.w900, color: ink)),
            ],
          ),
          const SizedBox(height: 9),
          for (var index = 0; index < refunds.length; index++) ...[
            if (index > 0) const Divider(height: 16, color: Color(0xFFE5DDFB)),
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
    final reasonText = switch (reason) {
      'platform_unfulfilled' => 'AIRway could not fulfil this service',
      'admin_adjustment' => 'AIRway adjustment',
      'dispute_resolution' => 'Dispute resolution',
      'recurring_plan_cancellation' => 'Unused recurring plan visits',
      _ => 'Service cancellation',
    };
    final amountValue = amount(refund['amount']);
    final walletValue = amount(refund['wallet_amount']);
    final gatewayValue = amount(refund['gateway_amount']);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(child: Text(statusText, style: TextStyle(fontWeight: FontWeight.w800, color: statusColor))),
            Text('₹${amountValue.toStringAsFixed(2)}', style: const TextStyle(fontWeight: FontWeight.w900, color: violet)),
          ],
        ),
        const SizedBox(height: 4),
        Text(reasonText, style: const TextStyle(color: sub, fontSize: 12)),
        Text(AirwayText.tr('AIRway wallet: ₹${walletValue.toStringAsFixed(2)}', 'AIRway वॉलेट: ₹${walletValue.toStringAsFixed(2)}'), style: const TextStyle(color: sub, fontSize: 12)),
        Text(AirwayText.tr('Original payment method: ₹${gatewayValue.toStringAsFixed(2)}', 'मूल भुगतान माध्यम: ₹${gatewayValue.toStringAsFixed(2)}'), style: const TextStyle(color: sub, fontSize: 12)),
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
        FilledButton(onPressed: action, child: Text(AirwayText.tr('Retry', 'फिर कोशिश करें'))),
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
