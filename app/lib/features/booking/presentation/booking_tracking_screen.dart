import 'dart:async';
import 'package:flutter/material.dart';
import 'package:razorpay_flutter/razorpay_flutter.dart';
import 'package:airway/features/payment/data/payment_api.dart';
import 'package:airway/features/booking/data/booking_api.dart';

class BookingTrackingScreen extends StatefulWidget {
  final int bookingId;
  final String serviceTitle;
  final String initialStatus;

  const BookingTrackingScreen({
    super.key,
    required this.bookingId,
    required this.serviceTitle,
    this.initialStatus = 'pending',
  });

  @override
  State<BookingTrackingScreen> createState() => _BookingTrackingScreenState();
}

class _BookingTrackingScreenState extends State<BookingTrackingScreen> {
  static const _green = Color(0xFF075B43);
  static const _ink = Color(0xFF1E2923);
  static const _muted = Color(0xFF748078);
  static const _line = Color(0xFFEAE6DE);

  Timer? _poller;
  final Razorpay _razorpay = Razorpay();
  final TextEditingController _walletAmountController = TextEditingController(text: '0.00');
  double _walletBalance = 0;
  bool _walletLoading = true;
  bool _payingFinalBalance = false;
  Map<String, dynamic> _tracking = {};
  String _status = 'pending';
  bool _loading = true;
  bool _refreshing = false;
  String? _error;

  bool get _terminal => _status == 'completed' ||
      _status == 'cancelled' || _status == 'disputed';

  @override
  void initState() {
    super.initState();
    _status = widget.initialStatus;
    _razorpay.on(Razorpay.EVENT_PAYMENT_SUCCESS, _onFinalPaymentSuccess);
    _razorpay.on(Razorpay.EVENT_PAYMENT_ERROR, _onFinalPaymentError);
    _razorpay.on(Razorpay.EVENT_EXTERNAL_WALLET, _onExternalWallet);
    _refresh();
    _loadWalletBalance();
    _poller = Timer.periodic(const Duration(seconds: 20), (_) {
      if (mounted && !_terminal) _refresh(silent: true);
    });
  }

  @override
  void dispose() {
    _poller?.cancel();
    _razorpay.clear();
    _walletAmountController.dispose();
    super.dispose();
  }

  Future<void> _refresh({bool silent = false}) async {
    if (_refreshing) return;
    _refreshing = true;
    if (!silent && mounted) setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final result = await BookingApi.trackBooking(widget.bookingId);
      if (!mounted) return;
      setState(() {
        _tracking = result;
        _status = result['status']?.toString() ?? _status;
        _loading = false;
        _error = null;
      });
      if (_terminal) _poller?.cancel();
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = e.toString();
      });
    } finally {
      _refreshing = false;
    }
  }

  Future<void> _showServiceOtp(String purpose) async {
    try {
      final result = await BookingApi.requestServiceOtp(
        widget.bookingId,
        purpose: purpose,
      );
      if (!mounted) return;
      final otp = result['otp']?.toString() ?? '';
      if (otp.length != 6) throw const FormatException('The server did not return a valid OTP.');
      await showDialog<void>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          title: Text(purpose == 'start' ? 'Service start OTP' : 'Service completion OTP'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text('Share this one-time code with your assigned professional only at this service milestone.'),
              const SizedBox(height: 18),
              SelectableText(
                otp,
                style: const TextStyle(fontSize: 32, fontWeight: FontWeight.w900, letterSpacing: 8),
              ),
              const SizedBox(height: 8),
              Text(
                'Expires: ${result['expires_at'] ?? 'in 10 minutes'}',
                style: const TextStyle(color: _muted, fontSize: 11),
              ),
            ],
          ),
          actions: [
            FilledButton(
              onPressed: () => Navigator.pop(dialogContext),
              child: const Text('Done'),
            ),
          ],
        ),
      );
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Could not generate OTP: $e')),
        );
      }
    }
  }

  double get _selectedWalletAmount =>
      double.tryParse(_walletAmountController.text.trim()) ?? 0;

  Future<void> _loadWalletBalance() async {
    try {
      final result = await BookingApi.request('/api/v1/wallet/balance/');
      if (!mounted) return;
      setState(() {
        _walletBalance = double.tryParse(result['balance']?.toString() ?? '0') ?? 0;
        _walletLoading = false;
      });
    } catch (_) {
      if (mounted) setState(() => _walletLoading = false);
    }
  }

  Future<void> _payFinalBalance() async {
    if (_payingFinalBalance) return;
    final summary = _tracking['payment_summary'] is Map
        ? Map<String, dynamic>.from(_tracking['payment_summary'] as Map)
        : <String, dynamic>{};
    final outstanding = double.tryParse(summary['final_balance_outstanding']?.toString() ?? '0') ?? 0;
    final rawWalletAmount = _walletAmountController.text.trim();
    final walletParts = rawWalletAmount.isEmpty ? <String>['0'] : rawWalletAmount.split('.');
    final walletFormatValid = walletParts.length <= 2 &&
        walletParts.first.isNotEmpty &&
        walletParts.first.codeUnits.every((unit) => unit >= 48 && unit <= 57) &&
        (walletParts.length == 1 ||
            (walletParts[1].length <= 2 &&
                walletParts[1].codeUnits.every((unit) => unit >= 48 && unit <= 57)));
    final walletAmount = _selectedWalletAmount;
    final walletCents = (walletAmount * 100).round();
    final walletBalanceCents = (_walletBalance * 100).round();
    final outstandingCents = (outstanding * 100).round();
    if (!walletFormatValid || !walletAmount.isFinite || walletCents < 0 ||
        walletCents > walletBalanceCents || walletCents > outstandingCents) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Enter a wallet amount within your available balance and final amount, with at most two decimal places.')),
      );
      return;
    }
    setState(() => _payingFinalBalance = true);
    try {
      final payment = await PaymentApi.createFinalBalanceOrder(
        widget.bookingId,
        walletAmount: walletAmount.toStringAsFixed(2),
      );
      if (payment['already_paid'] == true || payment['payment_status'] == 'captured') {
        await _refresh();
        if (mounted) setState(() => _payingFinalBalance = false);
        return;
      }
      final key = payment['key_id']?.toString() ?? '';
      final orderId = payment['order_id']?.toString() ?? '';
      final amount = payment['amount'];
      if (key.isEmpty || orderId.isEmpty || amount is! int || amount <= 0) {
        throw Exception('The final payment gateway order could not be initialized.');
      }
      _razorpay.open({
        'key': key,
        'amount': amount,
        'currency': payment['currency'] ?? 'INR',
        'name': 'AIRway',
        'description': 'Final balance for booking #${widget.bookingId}',
        'order_id': orderId,
        'theme': {'color': '#075B43'},
      });
    } catch (e) {
      if (mounted) {
        setState(() => _payingFinalBalance = false);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Could not start final payment: $e')),
        );
      }
    }
  }

  Future<void> _onFinalPaymentSuccess(PaymentSuccessResponse response) async {
    final orderId = response.orderId;
    final paymentId = response.paymentId;
    final signature = response.signature;
    if (orderId == null || paymentId == null || signature == null) {
      if (mounted) setState(() => _payingFinalBalance = false);
      return;
    }
    try {
      final verification = await PaymentApi.verifyFinalBalancePayment(
        razorpayOrderId: orderId,
        razorpayPaymentId: paymentId,
        razorpaySignature: signature,
      );
      if (mounted) {
        final verificationStatus = verification['status']?.toString();
        final refundStatus = verification['refund_status']?.toString();
        final message = verificationStatus == 'duplicate_capture_refund'
            ? refundStatus == 'processed'
                ? 'Duplicate payment was refunded.'
                : refundStatus == 'failed'
                    ? 'Duplicate payment needs AIRway refund support.'
                    : 'Duplicate payment is being reconciled for refund.'
            : verificationStatus == 'late_capture_refund'
                ? refundStatus == 'processed'
                    ? 'The late payment was refunded. You can retry the final balance.'
                    : refundStatus == 'failed'
                        ? 'The late payment refund needs AIRway support.'
                        : 'The late payment is being refunded. Refresh shortly.'
                : 'Final payment received successfully.';
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(message)),
        );
        await _refresh();
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Payment is awaiting server confirmation: $e')),
        );
        await _refresh();
      }
    } finally {
      if (mounted) setState(() => _payingFinalBalance = false);
    }
  }

  void _onFinalPaymentError(PaymentFailureResponse response) {
    if (!mounted) return;
    setState(() => _payingFinalBalance = false);
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(response.message ?? 'Payment was not completed. You can retry.')),
    );
  }

  void _onExternalWallet(ExternalWalletResponse response) {
    if (!mounted) return;
    setState(() => _payingFinalBalance = false);
  }

  String get _statusText {
    switch (_status) {
      case 'pending': return 'Finding a professional';
      case 'confirmed': return 'Booking confirmed';
      case 'assigned': return 'Professional assigned';
      case 'in_progress': return 'Service in progress';
      case 'completed': return 'Service completed';
      case 'cancelled': return 'Booking cancelled';
      case 'disputed': return 'Booking under review';
      default: return _status.replaceAll('_', ' ');
    }
  }

  @override
  Widget build(BuildContext context) {
    final assigned = _tracking['is_assigned'] == true;
    final started = _status == 'in_progress' || _status == 'completed';
    final completed = _status == 'completed';
    final cancelled = _status == 'cancelled';
    return Scaffold(
      backgroundColor: const Color(0xFFF8FAF8),
      appBar: AppBar(
        backgroundColor: Colors.white,
        title: const Text('Track Service'),
        actions: [
          IconButton(
            onPressed: _loading ? null : () => _refresh(),
            icon: const Icon(Icons.refresh_rounded),
            tooltip: 'Refresh status',
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: _green))
          : RefreshIndicator(
              onRefresh: _refresh,
              child: ListView(
                padding: const EdgeInsets.all(20),
                children: [
                  Container(
                    padding: const EdgeInsets.all(18),
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(18),
                      border: Border.all(color: _line),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(widget.serviceTitle,
                            style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w900, color: _ink)),
                        const SizedBox(height: 5),
                        Text('Booking #${widget.bookingId}',
                            style: const TextStyle(color: _muted, fontSize: 12)),
                        const SizedBox(height: 14),
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                          decoration: BoxDecoration(
                            color: cancelled ? const Color(0xFFFFEEEE) : const Color(0xFFEAF1EA),
                            borderRadius: BorderRadius.circular(30),
                          ),
                          child: Text(_statusText,
                              style: TextStyle(fontWeight: FontWeight.w800,
                                  color: cancelled ? Colors.redAccent : _green)),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 16),
                  if (_error != null)
                    Container(
                      padding: const EdgeInsets.all(14),
                      decoration: BoxDecoration(color: const Color(0xFFFFF5E9), borderRadius: BorderRadius.circular(14)),
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        const Text('Could not refresh tracking', style: TextStyle(fontWeight: FontWeight.w800, color: _ink)),
                        const SizedBox(height: 5),
                        Text(_error!, style: const TextStyle(color: _muted, fontSize: 12)),
                        TextButton.icon(onPressed: () => _refresh(), icon: const Icon(Icons.refresh), label: const Text('Try again')),
                      ]),
                    ),
                  Container(
                    padding: const EdgeInsets.all(18),
                    decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(18), border: Border.all(color: _line)),
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      const Text('Booking journey', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w900, color: _ink)),
                      const SizedBox(height: 18),
                      _step('Booking placed', true, 'Your service request has been received.'),
                      _step('Professional assigned', assigned || started || completed,
                          assigned ? 'A professional has accepted your service.' : 'We are looking for an available professional.'),
                      _step('Service started', started, started ? 'Your professional has started the job.' : 'Updates when work begins.'),
                      _step('Service completed', completed, completed ? 'Your service is complete.' : 'Waiting for completion.'),
                    ]),
                  ),
                  const SizedBox(height: 16),
                  if (assigned)
                    Container(
                      padding: const EdgeInsets.all(18),
                      decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(18), border: Border.all(color: _line)),
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        const Text('Your professional', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w900, color: _ink)),
                        const SizedBox(height: 12),
                        Row(children: [
                          const CircleAvatar(backgroundColor: Color(0xFFEAF1EA), child: Icon(Icons.person_rounded, color: _green)),
                          const SizedBox(width: 12),
                          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                            Text(_tracking['worker_name']?.toString() ?? 'Assigned professional',
                                style: const TextStyle(fontWeight: FontWeight.w800, color: _ink)),
                            if (_tracking['worker_rating'] != null)
                              Text('Rating: ${_tracking['worker_rating']}', style: const TextStyle(color: _muted, fontSize: 12)),
                          ])),

                        ]),
                        if ((_tracking['worker_phone']?.toString() ?? '').isNotEmpty)
                          SelectableText(_tracking['worker_phone'].toString(), style: const TextStyle(color: _muted)),
                      ]),
                    ),
                  if (_tracking['payment_summary'] is Map)
                    _paymentLifecycleCard(Map<String, dynamic>.from(_tracking['payment_summary'] as Map)),
                  if (_tracking['payment_summary'] is Map &&
                      Map<String, dynamic>.from(_tracking['payment_summary'] as Map)['requires_service_otp'] == true &&
                      assigned && !started)
                    SizedBox(
                      width: double.infinity,
                      child: FilledButton.icon(
                        onPressed: () => _showServiceOtp('start'),
                        icon: const Icon(Icons.lock_open_rounded),
                        label: const Text('Show service start OTP'),
                      ),
                    ),
                  if (_tracking['payment_summary'] is Map &&
                      Map<String, dynamic>.from(_tracking['payment_summary'] as Map)['requires_service_otp'] == true &&
                      _status == 'in_progress')
                    SizedBox(
                      width: double.infinity,
                      child: FilledButton.icon(
                        onPressed: () => _showServiceOtp('completion'),
                        icon: const Icon(Icons.verified_rounded),
                        label: const Text('Show service completion OTP'),
                      ),
                    ),
                  const SizedBox(height: 16),
                  Container(
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(18), border: Border.all(color: _line)),
                    child: const Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Icon(Icons.location_searching_rounded, color: _green),
                      SizedBox(width: 10),
                      Expanded(child: Text(
                        'Live map and ETA will appear when the assigned professional shares verified GPS location. We will not display a guessed location.',
                        style: TextStyle(color: _muted, fontSize: 12, height: 1.45),
                      )),
                    ]),
                  ),
                  const SizedBox(height: 14),
                  if (!_terminal)
                    const Center(child: Text('Status refreshes automatically every 20 seconds',
                        style: TextStyle(color: _muted, fontSize: 11))),
                ],
              ),
            ),
    );
  }

  Widget _paymentLifecycleCard(Map<String, dynamic> summary) {
    final outstanding = double.tryParse(summary['final_balance_outstanding']?.toString() ?? '0') ?? 0;
    final advance = double.tryParse(summary['advance_captured']?.toString() ?? '0') ?? 0;
    final walletForLabel = _selectedWalletAmount.isFinite ? _selectedWalletAmount : 0.0;
    final finalPaid = summary['final_balance_status'] == 'paid';
    final finalStatus = summary['final_balance_status']?.toString() ?? 'not_due';
    final finalLabel = finalPaid
        ? 'Paid'
        : finalStatus == 'not_due'
            ? 'Due after service completion'
            : '₹${outstanding.toStringAsFixed(2)} outstanding';
    final isSplit = summary['requires_service_otp'] == true;
    if (!isSplit) return const SizedBox.shrink();
    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: _line),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('Payment summary', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w900, color: _ink)),
          const SizedBox(height: 10),
          _paymentRow('Booking advance received', '₹${advance.toStringAsFixed(2)}'),
          _paymentRow('Final balance', finalLabel),
          if (_status == 'completed' && outstanding > 0) ...[
            Text(
              _walletLoading ? 'Loading wallet balance…' : 'Available AIRway wallet: ₹${_walletBalance.toStringAsFixed(2)}',
              style: const TextStyle(color: _muted, fontSize: 12),
            ),
            const SizedBox(height: 8),
            TextField(
              controller: _walletAmountController,
              enabled: !_walletLoading && !_payingFinalBalance,
              keyboardType: const TextInputType.numberWithOptions(decimal: true),
              onChanged: (_) => setState(() {}),
              decoration: const InputDecoration(
                labelText: 'Use wallet amount (₹)',
                hintText: '0.00',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 10),
            SizedBox(
              width: double.infinity,
              child: FilledButton(
                onPressed: _payingFinalBalance ? null : _payFinalBalance,
                child: _payingFinalBalance
                    ? const SizedBox(height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                    : Text(
                        walletForLabel >= outstanding && outstanding > 0
                            ? 'Pay with AIRway wallet'
                            : 'Pay ₹${(outstanding - walletForLabel).clamp(0, outstanding).toStringAsFixed(2)} online',
                      ),
              ),
            ),
          ],
          if (_status == 'completed' && !finalPaid && outstanding > 0)
            const Padding(
              padding: EdgeInsets.only(top: 8),
              child: Text('Your service remains completed while payment is pending. You can retry payment here.',
                  style: TextStyle(color: _muted, fontSize: 12)),
            ),
        ],
      ),
    );
  }

  Widget _paymentRow(String label, String value) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 5),
        child: Row(
          children: [
            Expanded(child: Text(label, style: const TextStyle(color: _muted, fontSize: 13))),
            Text(value, style: const TextStyle(color: _ink, fontWeight: FontWeight.w800)),
          ],
        ),
      );

  Widget _step(String title, bool complete, String detail) => Padding(
        padding: const EdgeInsets.only(bottom: 18),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Icon(complete ? Icons.check_circle_rounded : Icons.radio_button_unchecked,
              color: complete ? _green : const Color(0xFFB9C2BB), size: 22),
          const SizedBox(width: 11),
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(title, style: const TextStyle(fontWeight: FontWeight.w800, color: _ink)),
            const SizedBox(height: 3),
            Text(detail, style: const TextStyle(color: _muted, fontSize: 12, height: 1.35)),
          ])),
        ]),
      );
}
