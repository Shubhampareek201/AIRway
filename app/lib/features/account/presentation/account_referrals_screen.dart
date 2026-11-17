import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:share_plus/share_plus.dart';
import 'package:airway/features/account/data/account_api.dart';

class AccountReferralsScreen extends StatefulWidget {
  const AccountReferralsScreen({super.key});

  @override
  State<AccountReferralsScreen> createState() => _AccountReferralsScreenState();
}

class _AccountReferralsScreenState extends State<AccountReferralsScreen> {
  final _codeController = TextEditingController();
  Map<String, dynamic>? _data;
  bool _loading = true;
  bool _applying = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _codeController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final data = await AccountApi.fetchReferrals();
      if (!mounted) return;
      setState(() {
        _data = data;
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

  Future<void> _applyCode() async {
    final code = _codeController.text.trim().toUpperCase();
    if (code.isEmpty || _applying) return;
    setState(() => _applying = true);
    try {
      await AccountApi.applyReferralCode(code);
      _codeController.clear();
      await _load();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Referral code applied. Your ₹100 reward is pending until your first service is completed.'),
          ),
        );
      }
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(error.toString().replaceFirst('Exception: ', ''))),
      );
    } finally {
      if (mounted) setState(() => _applying = false);
    }
  }

  Future<void> _shareCode() async {
    final code = _data?['referral_code']?.toString();
    if (code == null || code.isEmpty) return;
    await SharePlus.instance.share(
      ShareParams(
        text: 'Join me on AIRway! Use my referral code $code when you create your account. '
            'After your first AIRway service is completed, you get ₹100 in your wallet and I get ₹200. '
            'Referral code: $code',
        subject: 'Join AIRway with my referral code',
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final data = _data ?? const <String, dynamic>{};
    final code = data['referral_code']?.toString() ?? '';
    final referrals = data['referrals'] is List
        ? List<Map<String, dynamic>>.from(
            (data['referrals'] as List).whereType<Map>().map(
              (row) => Map<String, dynamic>.from(row),
            ),
          )
        : <Map<String, dynamic>>[];
    final applied = data['applied_referral'] is Map
        ? Map<String, dynamic>.from(data['applied_referral'] as Map)
        : null;

    return Scaffold(
      appBar: AppBar(title: const Text('Share & earn')),
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
                        FilledButton.icon(
                          onPressed: _load,
                          icon: const Icon(Icons.refresh),
                          label: const Text('Try again'),
                        ),
                      ],
                    ),
                  ),
                )
              : RefreshIndicator(
                  onRefresh: _load,
                  child: ListView(
                    padding: const EdgeInsets.all(20),
                    children: [
                      Container(
                        padding: const EdgeInsets.all(20),
                        decoration: BoxDecoration(
                          color: Theme.of(context).colorScheme.primaryContainer,
                          borderRadius: BorderRadius.circular(20),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text(
                              'Invite friends to AIRway',
                              style: TextStyle(fontSize: 20, fontWeight: FontWeight.w800),
                            ),
                            const SizedBox(height: 8),
                            const Text('Your friend gets ₹100 and you get ₹200 after their first service is successfully completed.'),
                            const SizedBox(height: 18),
                            Row(
                              children: [
                                Expanded(
                                  child: SelectableText(
                                    code,
                                    style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w900, letterSpacing: 2),
                                  ),
                                ),
                                IconButton(
                                  tooltip: 'Copy referral code',
                                  onPressed: code.isEmpty
                                      ? null
                                      : () async {
                                          await Clipboard.setData(ClipboardData(text: code));
                                          if (mounted) {
                                            ScaffoldMessenger.of(context).showSnackBar(
                                              const SnackBar(content: Text('Referral code copied.')),
                                            );
                                          }
                                        },
                                  icon: const Icon(Icons.copy_rounded),
                                ),
                              ],
                            ),
                            SizedBox(
                              width: double.infinity,
                              child: FilledButton.icon(
                                onPressed: code.isEmpty ? null : _shareCode,
                                icon: const Icon(Icons.share_outlined),
                                label: const Text('Share referral code'),
                              ),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 24),
                      Text('How it works', style: Theme.of(context).textTheme.titleMedium),
                      const SizedBox(height: 10),
                      const _StepLine(number: '1', text: 'Share your unique referral code with a new customer.'),
                      const _StepLine(number: '2', text: 'They install AIRway, create an account and apply your code.'),
                      const _StepLine(number: '3', text: 'After their first service is completed and verified, ₹200 and ₹100 are credited to your respective wallets.'),
                      const SizedBox(height: 24),
                      Text('Have a referral code?', style: Theme.of(context).textTheme.titleMedium),
                      const SizedBox(height: 8),
                      if (applied != null)
                        ListTile(
                          contentPadding: EdgeInsets.zero,
                          leading: const Icon(Icons.check_circle_outline),
                          title: Text('Code applied: ${applied['code'] ?? 'Referral'}'),
                          subtitle: Text(applied['rewarded'] == true
                              ? 'Your ₹100 welcome reward has been credited.'
                              : 'Your ₹100 welcome reward is pending your first completed service.'),
                        )
                      else
                        Column(
                          children: [
                            TextField(
                              controller: _codeController,
                              textCapitalization: TextCapitalization.characters,
                              inputFormatters: [FilteringTextInputFormatter.allow(RegExp('[A-Za-z0-9]'))],
                              decoration: const InputDecoration(
                                labelText: 'Enter referral code',
                                border: OutlineInputBorder(),
                              ),
                            ),
                            const SizedBox(height: 10),
                            SizedBox(
                              width: double.infinity,
                              child: OutlinedButton(
                                onPressed: _applying ? null : _applyCode,
                                child: _applying
                                    ? const SizedBox(height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2))
                                    : const Text('Apply code'),
                              ),
                            ),
                          ],
                        ),
                      const SizedBox(height: 24),
                      Text(
                        'Your invitations',
                        style: Theme.of(context).textTheme.titleMedium,
                      ),
                      const SizedBox(height: 8),
                      if (referrals.isEmpty)
                        const Text('No invitations yet. Share your code to get started.')
                      else
                        ...referrals.map((row) => ListTile(
                              contentPadding: EdgeInsets.zero,
                              leading: const CircleAvatar(child: Icon(Icons.person_outline)),
                              title: Text(row['name']?.toString() ?? 'AIRway customer'),
                              subtitle: Text(row['status'] == 'rewarded'
                                  ? 'Reward credited'
                                  : 'Waiting for first completed service'),
                              trailing: row['status'] == 'rewarded'
                                  ? const Icon(Icons.check_circle, color: Colors.green)
                                  : const Icon(Icons.schedule),
                            )),
                    ],
                  ),
                ),
    );
  }
}

class _StepLine extends StatelessWidget {
  const _StepLine({required this.number, required this.text});

  final String number;
  final String text;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 6),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            CircleAvatar(radius: 13, child: Text(number, style: const TextStyle(fontSize: 12))),
            const SizedBox(width: 12),
            Expanded(child: Text(text)),
          ],
        ),
      );
}
