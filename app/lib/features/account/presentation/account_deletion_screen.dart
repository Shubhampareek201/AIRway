import 'package:flutter/material.dart';
import 'package:airway/features/account/data/account_api.dart';
import 'package:airway/core/localization/airway_text.dart';

class AccountDeletionScreen extends StatefulWidget {
  const AccountDeletionScreen({super.key});

  @override
  State<AccountDeletionScreen> createState() => _AccountDeletionScreenState();
}

class _AccountDeletionScreenState extends State<AccountDeletionScreen> {
  final _reasonController = TextEditingController();
  Map<String, dynamic>? _request;
  bool _loading = true;
  bool _submitting = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _reasonController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final result = await AccountApi.fetchDeletionRequest();
      if (!mounted) return;
      setState(() {
        _request = result['has_request'] == true ? result : null;
        _loading = false;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error.toString().replaceFirst('Exception: ', '');
        _loading = false;
      });
    }
  }

  Future<void> _submit() async {
    final t = AirwayText.tr;
    if (_submitting) return;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: Text(t('Request account deletion?', 'खाता बंद करने का अनुरोध?')),
        content: Text(
          t('This submits a request for AIRway review. Your account will not be closed immediately. ', 'यह अनुरोध AIRway की समीक्षा के लिए भेजेगा। आपका खाता तुरंत बंद नहीं होगा। ')
          t('Active bookings, disputes, payments and legally required records must be handled first.', 'पहले सक्रिय बुकिंग, विवाद, भुगतान और कानूनी रूप से आवश्यक रिकॉर्ड का निपटारा होगा।'),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: Text(t('Keep account', 'खाता जारी रखें')),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(dialogContext, true),
            child: Text(t('Submit request', 'अनुरोध भेजें')),
          ),
        ],
      ),
    );
    if (confirmed != true) return;

    setState(() => _submitting = true);
    try {
      final result = await AccountApi.requestAccountDeletion(
        reason: _reasonController.text,
      );
      if (!mounted) return;
      setState(() => _request = {
            'has_request': true,
            'status': result['status'],
            'has_active_bookings': result['has_active_bookings'],
            'has_financial_obligations': result['has_financial_obligations'],
            'active_booking_count': result['active_booking_count'],
            'detail': result['detail'],
          });
      _reasonController.clear();
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(result['detail']?.toString() ?? t('Request submitted.', 'अनुरोध भेज दिया गया।'))),
      );
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(error.toString().replaceFirst('Exception: ', ''))),
      );
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  String _statusLabel(String? status) {
    final t = AirwayText.tr;
    switch (status) {
      case 'requested':
        return t('Request submitted', 'अनुरोध भेज दिया गया');
      case 'under_review':
        return t('Under review', 'समीक्षा जारी है');
      case 'rejected':
        return t('Request not approved', 'अनुरोध स्वीकृत नहीं हुआ');
      case 'completed':
        return t('Account closed', 'खाता बंद हो गया');
      case 'cancelled':
        return t('Request cancelled', 'अनुरोध रद्द कर दिया गया');
      default:
        return t('Status unavailable', 'स्थिति उपलब्ध नहीं है');
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = AirwayText.tr;
    final request = _request;
    final status = request?['status']?.toString();
    return Scaffold(
      appBar: AppBar(title: Text(t('Delete account', 'खाता बंद करें'))),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(
                  child: Padding(
                    padding: const EdgeInsets.all(24),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(_error!, textAlign: TextAlign.center),
                        const SizedBox(height: 12),
                        FilledButton(onPressed: _load, child: Text(t('Retry', 'फिर कोशिश करें'))),
                      ],
                    ),
                  ),
                )
              : ListView(
                  padding: const EdgeInsets.all(20),
                  children: [
                    const Icon(Icons.person_off_outlined, size: 48),
                    const SizedBox(height: 12),
                    Text(
                      t('Your account and personal information', 'आपका खाता और व्यक्तिगत जानकारी'),
                      style: TextStyle(fontSize: 19, fontWeight: FontWeight.w800),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      t('You can request closure of your AIRway account. AIRway will review active bookings, worker assignments, disputes, wallet balances and payment obligations before closure.', 'आप अपना AIRway खाता बंद करने का अनुरोध कर सकते हैं। बंद करने से पहले AIRway सक्रिय बुकिंग, वर्कर असाइनमेंट, विवाद, वॉलेट बैलेंस और भुगतान दायित्वों की समीक्षा करेगा।'),
                    ),
                    const SizedBox(height: 12),
                    Text(
                      t('Booking, payment, refund, tax and other legally required records may be retained where required. The account is not physically deleted from historical transactions.', 'जहाँ आवश्यक हो, बुकिंग, भुगतान, रिफंड, टैक्स और अन्य कानूनी रिकॉर्ड सुरक्षित रखे जा सकते हैं। पुराने लेन-देन से खाता रिकॉर्ड भौतिक रूप से नहीं हटाया जाता।'),
                    ),
                    const SizedBox(height: 20),
                    if (request != null) ...[
                      Card(
                        child: Padding(
                          padding: const EdgeInsets.all(16),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(_statusLabel(status), style: const TextStyle(fontWeight: FontWeight.w800)),
                              const SizedBox(height: 8),
                              Text(request['detail']?.toString() ??
                                  (request['has_active_bookings'] == true
                                      ? t('There are ${request['active_booking_count'] ?? 0} active bookings or disputes to resolve first.', 'पहले ${request['active_booking_count'] ?? 0} सक्रिय बुकिंग या विवादों का निपटारा करना होगा।')
                                      : request['has_financial_obligations'] == true
                                          ? t('Outstanding wallet funds or reservations must be settled before closure.', 'खाता बंद करने से पहले वॉलेट राशि या आरक्षित राशि का निपटारा करना होगा।')
                                          : t('Your request is waiting for admin review.', 'आपका अनुरोध एडमिन की समीक्षा की प्रतीक्षा में है।'))),
                              if (request['admin_notes']?.toString().isNotEmpty == true) ...[
                                const SizedBox(height: 8),
                                Text(t('AIRway review: ${request['admin_notes']}', 'AIRway की समीक्षा: ${request['admin_notes']}')),
                              ],
                            ],
                          ),
                        ),
                      ),
                      const SizedBox(height: 12),
                      OutlinedButton.icon(
                        onPressed: _load,
                        icon: const Icon(Icons.refresh),
                        label: Text(t('Refresh status', 'स्थिति रीफ़्रेश करें')),
                      ),
                    ] else ...[
                      TextField(
                        controller: _reasonController,
                        maxLines: 4,
                        maxLength: 1000,
                        decoration: InputDecoration(
                          labelText: t('Reason (optional)', 'कारण (वैकल्पिक)'),
                          hintText: t('Tell us why you want to close your account.', 'बताएँ कि आप अपना खाता क्यों बंद करना चाहते हैं।'),
                          border: OutlineInputBorder(),
                        ),
                      ),
                      const SizedBox(height: 16),
                      SizedBox(
                        width: double.infinity,
                        child: FilledButton(
                          onPressed: _submitting ? null : _submit,
                          child: _submitting
                              ? const SizedBox(height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2))
                              : Text(t('Submit deletion request', 'खाता बंद करने का अनुरोध भेजें')),
                        ),
                      ),
                    ],
                  ],
                ),
    );
  }
}
