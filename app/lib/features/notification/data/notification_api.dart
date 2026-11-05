import 'dart:convert';
import 'dart:io';
import 'package:airway/core/network/auth_api.dart';
import 'package:airway/core/storage/secure_session_storage.dart';
import 'package:airway/features/notification/data/notification_models.dart';

class NotificationApi {
  NotificationApi._();

  static Future<Map<String, dynamic>> _request(
    String path, {
    String method = 'GET',
    Map<String, dynamic>? data,
  }) async {
    final session = await SecureSessionStorage.readSession();
    if (session == null) throw Exception('Please sign in again.');

    Future<({int status, dynamic body})> call(String token) async {
      final client = HttpClient()
        ..connectionTimeout = const Duration(seconds: 10);
      try {
        final request = await client.openUrl(
          method,
          Uri.parse('${AuthApi.baseUrl}$path'),
        );
        request.headers.set(
          HttpHeaders.authorizationHeader,
          'Bearer $token',
        );
        if (data != null) {
          final bytes = utf8.encode(jsonEncode(data));
          request.headers.contentType = ContentType.json;
          request.contentLength = bytes.length;
          request.add(bytes);
        }
        final response = await request.close().timeout(
          const Duration(seconds: 15),
        );
        final text = await utf8.decoder.bind(response).join();
        dynamic result;
        if (text.isNotEmpty) {
          result = jsonDecode(text);
        }
        return (status: response.statusCode, body: result);
      } finally {
        client.close(force: true);
      }
    }

    var result = await call(session.accessToken);
    if (result.status == 401) {
      final refreshed = await AuthApi.refreshSession(
        refreshToken: session.refreshToken,
      );
      if (refreshed == null) {
        await SecureSessionStorage.clearSession();
        throw Exception('Session expired. Please sign in again.');
      }
      final access = refreshed['access'] as String;
      await SecureSessionStorage.saveSession(
        accessToken: access,
        refreshToken:
            refreshed['refresh'] as String? ?? session.refreshToken,
      );
      result = await call(access);
    }
    if (result.status < 200 || result.status >= 300) {
      throw Exception(
        'AIRway request failed (${result.status}): ${result.body}',
      );
    }
    return Map<String, dynamic>.from(result.body as Map);
  }

  static Future<List<Notification>> listNotifications() async {
    final result = await _request('/api/v1/notifications/');
    final list = result['results'] as List;

    return list
        .whereType<Map>()
        .map((e) => Notification.fromMap(Map<String, dynamic>.from(e)))
        .toList();
  }

  static Future<Notification> markRead(int notificationId) async {
    final result = await _request(
      '/api/v1/notifications/$notificationId/mark-read/',
      method: 'POST',
    );
    return Notification.fromMap(Map<String, dynamic>.from(result));
  }

  static Future<Map<String, dynamic>> markAllRead() async {
    final result = await _request(
      '/api/v1/notifications/mark-all-read/',
      method: 'POST',
    );
    return Map<String, dynamic>.from(result);
  }

  static Future<void> deleteNotification(int notificationId) async {
    await _request(
      '/api/v1/notifications/$notificationId/',
      method: 'DELETE',
    );
  }
}