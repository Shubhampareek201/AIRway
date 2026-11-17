import 'package:flutter/material.dart';

class AirwayLocale {
  AirwayLocale._();

  static final ValueNotifier<Locale> notifier =
      ValueNotifier<Locale>(const Locale('hi'));

  static Locale get current => notifier.value;

  static void setLanguage(String language) {
    final code = language == 'en' ? 'en' : 'hi';
    if (notifier.value.languageCode != code) {
      notifier.value = Locale(code);
    }
  }
}
