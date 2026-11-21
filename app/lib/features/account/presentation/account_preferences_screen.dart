import 'package:flutter/material.dart';
import 'package:airway/core/localization/airway_locale.dart';
import 'package:airway/features/account/data/account_api.dart';

class AccountPreferencesScreen extends StatefulWidget {
  const AccountPreferencesScreen({super.key});

  @override
  State<AccountPreferencesScreen> createState() =>
      _AccountPreferencesScreenState();
}

class _AccountPreferencesScreenState extends State<AccountPreferencesScreen> {
  String _language = AirwayLocale.current.languageCode;
  bool _saving = false;
  String? _syncError;

  bool get _hindi => _language == 'hi';

  Future<void> _selectLanguage(String language) async {
    if (_saving || language == _language) return;

    setState(() {
      _language = language;
      _saving = true;
      _syncError = null;
    });

    // Save on-device first. This changes the app immediately and remains
    // effective even if the network is unavailable.
    try {
      await AirwayLocale.saveLanguage(language);
    } catch (_) {
      if (!mounted) return;
      setState(() => _syncError = _hindi
          ? 'इस डिवाइस पर भाषा सेव नहीं हो सकी।'
          : 'Could not save the language on this device.');
    }

    try {
      await AccountApi.updateLanguage(language);
    } catch (_) {
      if (!mounted) return;
      setState(() => _syncError = _hindi
          ? 'डिवाइस पर भाषा सेव है, लेकिन खाते से सिंक नहीं हो सकी।'
          : 'Saved on this device, but could not sync with your account.');
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
      body: ListView(
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
                  onChanged: _saving
                      ? null
                      : (value) {
                          if (value != null) _selectLanguage(value);
                        },
                  title: const Text('हिन्दी'),
                  subtitle: Text(
                    hindi ? 'ऐप हिंदी में उपयोग करें' : 'Use AIRway in Hindi',
                  ),
                ),
                const Divider(height: 1),
                RadioListTile<String>(
                  value: 'en',
                  groupValue: _language,
                  onChanged: _saving
                      ? null
                      : (value) {
                          if (value != null) _selectLanguage(value);
                        },
                  title: const Text('English'),
                  subtitle: Text(
                    hindi ? 'ऐप अंग्रेज़ी में उपयोग करें' : 'Use AIRway in English',
                  ),
                ),
              ],
            ),
          ),
          if (_saving) ...[
            const SizedBox(height: 12),
            const LinearProgressIndicator(),
          ],
          if (_syncError != null) ...[
            const SizedBox(height: 12),
            Text(
              _syncError!,
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
          ],
          const SizedBox(height: 20),
          Text(
            hindi
                ? 'आपकी भाषा की पसंद इस डिवाइस पर सेव रहती है और खाते से भी सिंक होती है।'
                : 'Your language choice is saved on this device and synced with your AIRway account.',
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ],
      ),
    );
  }
}
