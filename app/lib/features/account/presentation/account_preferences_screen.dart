import 'package:flutter/material.dart';
import 'package:airway/core/theme/airway_appearance.dart';

class AccountPreferencesScreen extends StatefulWidget {
  const AccountPreferencesScreen({super.key});

  @override
  State<AccountPreferencesScreen> createState() =>
      _AccountPreferencesScreenState();
}

class _AccountPreferencesScreenState extends State<AccountPreferencesScreen> {
  bool _saving = false;

  Future<void> _changeAppearance(ThemeMode value) async {
    if (_saving || value == AirwayAppearance.mode.value) return;
    setState(() => _saving = true);
    try {
      await AirwayAppearance.setMode(value);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Appearance preference saved on this device.')),
      );
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Could not save appearance. Please try again.')),
      );
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  String _label(ThemeMode value) => switch (value) {
    ThemeMode.system => 'System default',
    ThemeMode.light => 'Light',
    ThemeMode.dark => 'Dark',
  };

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('App preferences')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text('Appearance', style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
          const SizedBox(height: 6),
          Text(
            'Choose how AIRway looks on this device. System default follows your phone setting.',
            style: Theme.of(context).textTheme.bodyMedium,
          ),
          const SizedBox(height: 12),
          Card(
            child: ValueListenableBuilder<ThemeMode>(
              valueListenable: AirwayAppearance.mode,
              builder: (context, selected, _) => Column(
                children: ThemeMode.values.map((mode) => RadioListTile<ThemeMode>(
                  value: mode,
                  groupValue: selected,
                  onChanged: _saving ? null : (value) {
                    if (value != null) _changeAppearance(value);
                  },
                  title: Text(_label(mode)),
                )).toList(),
              ),
            ),
          ),
          if (_saving) const LinearProgressIndicator(),
          const SizedBox(height: 20),
          Text('Language', style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
          const SizedBox(height: 6),
          const Text('English is currently the supported app language. Hindi selection will be enabled after the app screens are fully translated.'),
          const SizedBox(height: 20),
          Text('Biometric sign-in', style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
          const SizedBox(height: 6),
          const Text('Biometric unlock is not enabled yet. It will be offered after secure device enrolment and fallback sign-in are implemented.'),
        ],
      ),
    );
  }
}
