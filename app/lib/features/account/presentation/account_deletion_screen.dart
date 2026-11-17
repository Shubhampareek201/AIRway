import 'package:flutter/material.dart';
import 'package:airway/features/account/data/account_api.dart';

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
    if (_submitting) return;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Request account deletion?'),
        content: const Text(
          'This submits a request for AIRway review. Your account will not be closed immediately. '
          'Active bookings, disputes, payments and legally required records must be handled first.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: const Text('Keep account'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(dialogContext, true),
            child: const Text('Submit request'),
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
        SnackBar(content: Text(result['detail']?.toString() ?? 'Request submitted.')),
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
    switch (status) {
      case 'requested':
        return 'Request submitted';
      case 'under_review':
        return 'Under review';
      case 'rejected':
        return 'Request not approved';
      case 'completed':
        return 'Account closed';
      case 'cancelled':
        return 'Request cancelled';
      default:
        return 'Status unavailable';
    }
  }

  @override
  Widget build(BuildContext context) {
    final request = _request;
    final status = request?['status']?.toString();
    return Scaffold(
      appBar: AppBar(title: const Text('Delete account')),
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
                        FilledButton(onPressed: _load, child: const Text('Retry')),
                      ],
                    ),
                  ),
                )
              : ListView(
                  padding: const EdgeInsets.all(20),
                  children: [
                    const Icon(Icons.person_off_outlined, size: 48),
                    const SizedBox(height: 12),
                    const Text(
                      'Your account and personal information',
                      style: TextStyle(fontSize: 19, fontWeight: FontWeight.w800),
                    ),
                    const SizedBox(height: 8),
                    const Text(
                      'You can request closure of your AIRway account. AIRway will review active bookings, worker assignments, disputes, wallet balances and payment obligations before closure.',
                    ),
                    const SizedBox(height: 12),
                    const Text(
                      'Booking, payment, refund, tax and other legally required records may be retained where required. The account is not physically deleted from historical transactions.',
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
                                      ? 'There are ${request['active_booking_count'] ?? 0} active bookings or disputes to resolve first.'
                                      : request['has_financial_obligations'] == true
                                          ? 'Outstanding wallet funds or reservations must be settled before closure.'
                                          : 'Your request is waiting for admin review.')),
                              if (request['admin_notes']?.toString().isNotEmpty == true) ...[
                                const SizedBox(height: 8),
                                Text('AIRway review: ${request['admin_notes']}'),
                              ],
                            ],
                          ),
                        ),
                      ),
                      const SizedBox(height: 12),
                      OutlinedButton.icon(
                        onPressed: _load,
                        icon: const Icon(Icons.refresh),
                        label: const Text('Refresh status'),
                      ),
                    ] else ...[
                      TextField(
                        controller: _reasonController,
                        maxLines: 4,
                        maxLength: 1000,
                        decoration: const InputDecoration(
                          labelText: 'Reason (optional)',
                          hintText: 'Tell us why you want to close your account.',
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
                              : const Text('Submit deletion request'),
                        ),
                      ),
                    ],
                  ],
                ),
    );
  }
}
