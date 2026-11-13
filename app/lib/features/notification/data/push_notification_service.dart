import 'dart:async';

import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:airway/firebase_options.dart';
import 'package:airway/features/notification/data/notification_api.dart';

@pragma('vm:entry-point')
Future<void> airwayFirebaseBackgroundHandler(RemoteMessage message) async {
  await Firebase.initializeApp(
    options: DefaultFirebaseOptions.currentPlatform,
  );
}

class PushNotificationService {
  PushNotificationService._();

  static final FirebaseMessaging _messaging = FirebaseMessaging.instance;
  static StreamSubscription<String>? _tokenRefreshSubscription;
  static bool _initialized = false;

  static void registerBackgroundHandler() {
    FirebaseMessaging.onBackgroundMessage(airwayFirebaseBackgroundHandler);
  }

  static Future<void> initializeForAuthenticatedUser() async {
    if (_initialized) return;
    final settings = await _messaging.requestPermission(
      alert: true,
      badge: true,
      sound: true,
      provisional: false,
    );
    final token = await _messaging.getToken();
    if (token != null && token.isNotEmpty) {
      await NotificationApi.registerDeviceToken(token);
    }
    _tokenRefreshSubscription ??= _messaging.onTokenRefresh.listen((value) {
      if (value.isNotEmpty) {
        unawaited(NotificationApi.registerDeviceToken(value));
      }
    });
    _initialized = true;
    // Permission denial is user-controlled; token registration can still be
    // retained so the device is ready if permission is enabled later.
    if (settings.authorizationStatus == AuthorizationStatus.denied) return;
  }
}
