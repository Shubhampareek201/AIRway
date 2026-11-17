import 'package:flutter/material.dart';
import 'package:airway/core/localization/airway_locale.dart';
import 'package:airway/features/account/data/account_api.dart';

class AccountPreferencesScreen extends StatefulWidget {
  const AccountPreferencesScreen({super.key});

  @override
  State<AccountPreferencesScreen> createState() => _AccountPreferencesScreenState();
}

class _AccountPreferencesScreenState extends State<AccountPreferencesScreen> {
  String _language = AirwayLocale.current.languageCode;
  bool _loading = true;
  bool _saving = false;
  String? _error;

  bool get _hindi => _language == 'hi';

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final profile = await AccountApi.fetchProfile();
      if (!mounted) return;
      final language = profile['language']?.toString() == 'en' ? 'en' : 'hi';
      setState(() {
        _language = language;
        _loading = false;
        _error = null;
      });
      AirwayLocale.setLanguage(language);
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = error.toString().replaceFirst('Exception: ', '');
      });
    }
  }

  Future<void> _selectLanguage(String language) async {
    if (_saving || language == _language) return;
    final previous = _language;
    setState(() {
      _language = language;
      _saving = true;
    });
    try {
      await AccountApi.updateLanguage(language);
      AirwayLocale.setLanguage(language);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(language == 'hi'
              ? 'भाषा हिंदी में सेव हो गई।'
              : 'Language preference saved.'),
        ),
      );
    } catch (error) {
      if (!mounted) return;
      setState(() => _language = previous);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(error.toString().replaceFirst('Exception: ', ''))),
      );
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final hindi = _hindi;
    return Scaffold(
      appBar: AppBar(
        title: Text(hindi ? 'ऐप की प्राथमिकताएँ' : 'App preferences'),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                Text(
                  hindi ? 'भाषा चुनें' : 'Choose language',
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.w700,
                      ),
                ),
                const SizedBox(height: 8),
                Card(
                  child: Column(
                    children: [
                      RadioListTile<String>(
                        value: 'hi',
                        groupValue: _language,
                        onChanged: _saving ? null : (value) => _selectLanguage(value!),
                        title: const Text('हिन्दी'),
                        subtitle: Text(hindi ? 'ऐप हिंदी में उपयोग करें' : 'Use AIRway in Hindi'),
                      ),
                      const Divider(height: 1),
                      RadioListTile<String>(
                        value: 'en',
                        groupValue: _language,
                        onChanged: _saving ? null : (value) => _selectLanguage(value!),
                        title: const Text('English'),
                        subtitle: Text(hindi ? 'ऐप अंग्रेज़ी में उपयोग करें' : 'Use AIRway in English'),
                      ),
                    ],
                  ),
                ),
                if (_saving) ...[
                  const SizedBox(height: 12),
                  const LinearProgressIndicator(),
                ],
                if (_error != null) ...[
                  const SizedBox(height: 12),
                  Text(
                    hindi
                        ? 'सेव की गई भाषा लोड नहीं हो सकी। फिर से कोशिश करें।'
                        : 'Could not load your saved language.',
                    style: TextStyle(color: Theme.of(context).colorScheme.error),
                  ),
                  TextButton(
                    onPressed: _load,
                    child: Text(hindi ? 'फिर कोशिश करें' : 'Try again'),
                  ),
                ],
                const SizedBox(height: 20),
                Text(
                  hindi
                      ? 'आपकी भाषा की पसंद आपके AIRway खाते में सेव होती है। ऐप के सभी टेक्स्ट का अनुवाद अभी चरणों में जोड़ा जा रहा है।'
                      : 'Your language preference is saved to your AIRway account. Translations for the remaining app screens are being connected in stages.',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ],
            ),
    );
  }
}
