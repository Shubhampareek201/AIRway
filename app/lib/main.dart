import 'package:flutter/material.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:airway/features/auth/presentation/startup_gate.dart';
import 'package:airway/core/theme/airway_theme.dart';
import 'package:airway/core/localization/airway_locale.dart';
import 'package:airway/features/notification/data/push_notification_service.dart';
import 'package:airway/firebase_options.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  await Firebase.initializeApp(
    options: DefaultFirebaseOptions.currentPlatform,
  );
  PushNotificationService.registerBackgroundHandler();

  runApp(const AirwayApp());
}

class AirwayApp extends StatelessWidget {
  const AirwayApp({super.key});

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<Locale>(
      valueListenable: AirwayLocale.notifier,
      builder: (context, locale, _) => MaterialApp(
        title: 'AIRway',
        debugShowCheckedModeBanner: false,
        theme: AirwayTheme.light,
        themeMode: ThemeMode.light,
        locale: locale,
        supportedLocales: const [Locale('hi'), Locale('en')],
        home: const StartupGate(),
      ),
    );
  }
}
