import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:share_plus/share_plus.dart';
import 'package:airway/core/localization/airway_text.dart';
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
          SnackBar(
            content: Text(AirwayText.tr(
              'Referral code applied. Your ₹100 promotional credit is pending until your first completed booking has an original service charge over ₹500.',
              'रेफ़रल कोड लागू हो गया। आपका ₹100 प्रमोशनल क्रेडिट पहली ऐसी पूरी बुकिंग के बाद मिलेगा जिसका मूल सर्विस चार्ज ₹500 से अधिक हो।',
            )),
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
    final first = AirwayText.tr(
      'Join me on AIRway! Use my referral code $code before you make your first booking.',
      'AIRway से जुड़ें! पहली बुकिंग से पहले मेरा रेफ़रल कोड $code इस्तेमाल करें।',
    );
    final second = AirwayText.tr(
      'After your first completed AIRway booking with an original service charge over ₹500, you get ₹100 promotional credit and I get ₹200.',
      '₹500 से अधिक मूल सर्विस चार्ज वाली पहली बुकिंग पूरी होने पर आपको ₹100 और मुझे ₹200 प्रमोशनल क्रेडिट मिलेगा।',
    );
    await SharePlus.instance.share(
      ShareParams(
        text: '$first\n$second\nReferral code: $code',
        subject: AirwayText.tr('Join AIRway with my referral code', 'मेरे रेफ़रल कोड से AIRway से जुड़ें'),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final t = AirwayText.tr;
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
      appBar: AppBar(title: Text(t('Share & earn', 'शेयर करें और कमाएँ'))),
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
                          label: Text(t('Try again', 'फिर कोशिश करें')),
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
                            Text(
                              t('Invite friends to AIRway', 'दोस्तों को AIRway पर आमंत्रित करें'),
                              style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w800),
                            ),
                            const SizedBox(height: 8),
                            Text(t(
                              'Your friend gets ₹100 and you get ₹200 in promotional credit after their first completed booking with an original service charge over ₹500.',
                              '₹500 से अधिक मूल सर्विस चार्ज वाली पहली बुकिंग पूरी होने पर आपके दोस्त को ₹100 और आपको ₹200 प्रमोशनल क्रेडिट मिलेगा।',
                            )),
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
                                  tooltip: t('Copy referral code', 'रेफ़रल कोड कॉपी करें'),
                                  onPressed: code.isEmpty
                                      ? null
                                      : () async {
                                          await Clipboard.setData(ClipboardData(text: code));
                                          if (mounted) {
                                            ScaffoldMessenger.of(context).showSnackBar(
                                              SnackBar(content: Text(t('Referral code copied.', 'रेफ़रल कोड कॉपी हो गया।'))),
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
                                label: Text(t('Share referral code', 'रेफ़रल कोड शेयर करें')),
                              ),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 24),
                      Text(t('How it works', 'यह कैसे काम करता है'), style: Theme.of(context).textTheme.titleMedium),
                      const SizedBox(height: 10),
                      _StepLine(number: '1', text: t('Share your unique referral code with a new customer.', 'अपना यूनिक रेफ़रल कोड नए ग्राहक के साथ शेयर करें।')),
                      _StepLine(number: '2', text: t('They install AIRway, create an account and apply your code.', 'वे AIRway इंस्टॉल करके खाता बनाएँ और आपका कोड लागू करें।')),
                      Padding(
                        padding: const EdgeInsets.only(left: 38, top: 2, bottom: 8),
                        child: Text(
                          t('Apply the code before the first booking.', 'कोड पहली बुकिंग से पहले लागू करना होगा।'),
                          style: Theme.of(context).textTheme.bodySmall,
                        ),
                      ),
                      _StepLine(number: '3', text: t('After their first eligible booking is completed and verified, ₹200 and ₹100 promotional credits are added to your respective AIRway wallets. The original service charge must be over ₹500, before tax and offers.', 'पहली योग्य बुकिंग पूरी और सत्यापित होने पर आपके AIRway वॉलेट में ₹200 और उनके वॉलेट में ₹100 प्रमोशनल क्रेडिट जुड़ेंगे। टैक्स और ऑफर से पहले मूल सर्विस चार्ज ₹500 से अधिक होना चाहिए।')),
                      const SizedBox(height: 24),
                      Text(t('Have a referral code?', 'क्या आपके पास रेफ़रल कोड है?'), style: Theme.of(context).textTheme.titleMedium),
                      const SizedBox(height: 8),
                      if (applied != null)
                        ListTile(
                          contentPadding: EdgeInsets.zero,
                          leading: const Icon(Icons.check_circle_outline),
                          title: Text(t(
                            'Code applied: ${applied['code'] ?? 'Referral'}',
                            'लागू कोड: ${applied['code'] ?? 'रेफ़रल'}',
                          )),
                          subtitle: Text(applied['rewarded'] == true
                              ? t('Your ₹100 promotional credit has been credited.', 'आपका ₹100 प्रमोशनल क्रेडिट जमा हो गया है।')
                              : t('Your ₹100 promotional credit is pending. Complete your first booking with an original service charge over ₹500.', 'आपका ₹100 प्रमोशनल क्रेडिट लंबित है। ₹500 से अधिक मूल सर्विस चार्ज वाली पहली बुकिंग पूरी करें।')),
                        )
                      else
                        Column(
                          children: [
                            TextField(
                              controller: _codeController,
                              textCapitalization: TextCapitalization.characters,
                              inputFormatters: [FilteringTextInputFormatter.allow(RegExp('[A-Za-z0-9]'))],
                              decoration: InputDecoration(
                                labelText: t('Enter referral code', 'रेफ़रल कोड दर्ज करें'),
                                border: const OutlineInputBorder(),
                              ),
                            ),
                            const SizedBox(height: 10),
                            SizedBox(
                              width: double.infinity,
                              child: OutlinedButton(
                                onPressed: _applying ? null : _applyCode,
                                child: _applying
                                    ? const SizedBox(height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2))
                                    : Text(t('Apply code', 'कोड लागू करें')),
                              ),
                            ),
                          ],
                        ),
                      const SizedBox(height: 24),
                      Text(t('Your invitations', 'आपके आमंत्रण'), style: Theme.of(context).textTheme.titleMedium),
                      const SizedBox(height: 8),
                      if (referrals.isEmpty)
                        Text(t('No invitations yet. Share your code to get started.', 'अभी कोई आमंत्रण नहीं। शुरुआत करने के लिए अपना कोड शेयर करें।'))
                      else
                        ...referrals.map((row) => ListTile(
                              contentPadding: EdgeInsets.zero,
                              leading: const CircleAvatar(child: Icon(Icons.person_outline)),
                              title: Text(row['name']?.toString() ?? t('AIRway customer', 'AIRway ग्राहक')),
                              subtitle: Text(row['rewarded'] == true
                                  ? t('₹200 promotional credit issued • original service charge ₹${row['original_service_charge'] ?? '—'}', '₹200 प्रमोशनल क्रेडिट जारी • मूल सर्विस चार्ज ₹${row['original_service_charge'] ?? '—'}')
                                  : t('Pending: first completed booking must have an original service charge over ₹500.', 'लंबित: पहली पूरी बुकिंग का मूल सर्विस चार्ज ₹500 से अधिक होना चाहिए.')),
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
