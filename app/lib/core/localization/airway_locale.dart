import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Owns AIRway's app language independently of the device language.
///
/// The locally saved choice wins over account data on subsequent launches.
/// If no local choice exists, the authenticated account preference is adopted.
class AirwayLocale {
  AirwayLocale._();

  static const FlutterSecureStorage _storage = FlutterSecureStorage();
  static const String _languageKey = 'airway_language_preference';

  static final ValueNotifier<Locale> notifier =
      ValueNotifier<Locale>(const Locale('en'));

  static bool _initialized = false;
  static bool _hasLocalPreference = false;

  static Locale get current => notifier.value;
  static bool get hasLocalPreference => _hasLocalPreference;

  static Future<void> initialize() async {
    if (_initialized) return;

    String? saved;
    try {
      saved = await _storage.read(key: _languageKey);
    } catch (_) {
      // Storage failures must not prevent the app from opening in English.
    }
    if (saved == 'en' || saved == 'hi') {
      _hasLocalPreference = true;
      notifier.value = Locale(saved);
    } else {
      // A clean installation always starts in English, regardless of the
      // phone's system language.
      notifier.value = const Locale('en');
    }

    _initialized = true;
  }

  /// Applies the account preference only when this device has no saved choice.
  /// Startup uses this so an API response cannot overwrite a user's selection.
  static void setLanguage(String language) {
    if (_hasLocalPreference) return;

    final code = _normalize(language);
    notifier.value = Locale(code);
    _hasLocalPreference = true;
    unawaited(_persist(code));
  }

  /// Saves a user-initiated selection locally before the caller syncs the API.
  /// The notifier updates immediately, rebuilding the app in the new language.
  static Future<void> saveLanguage(String language) async {
    final code = _normalize(language);
    notifier.value = Locale(code);
    _hasLocalPreference = true;
    await _storage.write(key: _languageKey, value: code);
  }

  static Future<void> _persist(String code) async {
    try {
      await _storage.write(key: _languageKey, value: code);
    } catch (_) {
      // The app can still run; the account preference remains the fallback.
    }
  }

  static String _normalize(String language) =>
      language.trim().toLowerCase() == 'hi' ? 'hi' : 'en';
}
