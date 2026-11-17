import 'package:flutter/material.dart';

class AccountPreferencesScreen extends StatelessWidget {
  const AccountPreferencesScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('App preferences')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text(
            'Language',
            style: Theme.of(context).textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.w700,
                ),
          ),
          const SizedBox(height: 6),
          const Text(
            'English and Hindi support is being added across the app. '
            'The language selector will be enabled after the translated '
            'screens are connected, so the app never changes only partially.',
          ),
        ],
      ),
    );
  }
}
