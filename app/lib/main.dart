
import 'package:flutter/material.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:airway/features/auth/presentation/startup_gate.dart';
import 'package:airway/core/theme/airway_theme.dart';
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
    return MaterialApp(
      title: 'AIRway',
      debugShowCheckedModeBanner: false,
      theme: AirwayTheme.light,
      home: const StartupGate(),
    );
  }
}
