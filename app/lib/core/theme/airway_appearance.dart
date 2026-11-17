import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// App-wide appearance preference. Stored locally on this device.
class AirwayAppearance {
  AirwayAppearance._();

  static const FlutterSecureStorage _storage = FlutterSecureStorage();
  static const String _key = 'airway_appearance_mode';
  static final ValueNotifier<ThemeMode> mode =
      ValueNotifier<ThemeMode>(ThemeMode.system);

  static Future<void> load() async {
    try {
      final saved = await _storage.read(key: _key);
      mode.value = switch (saved) {
        'light' => ThemeMode.light,
        'dark' => ThemeMode.dark,
        _ => ThemeMode.system,
      };
    } catch (_) {
      // A preference-storage failure must never prevent the app from starting.
      mode.value = ThemeMode.system;
    }
  }

  static Future<void> setMode(ThemeMode value) async {
    final previous = mode.value;
    mode.value = value;
    try {
      await _storage.write(
        key: _key,
        value: switch (value) {
          ThemeMode.light => 'light',
          ThemeMode.dark => 'dark',
          ThemeMode.system => 'system',
        },
      );
    } catch (_) {
      mode.value = previous;
      rethrow;
    }
  }
}
