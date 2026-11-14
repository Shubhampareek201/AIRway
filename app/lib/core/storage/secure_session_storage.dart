
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class AuthSession {
  const AuthSession({
    required this.accessToken,
    required this.refreshToken,
  });

  final String accessToken;
  final String refreshToken;
}

class SecureSessionStorage {
  SecureSessionStorage._();

  static const FlutterSecureStorage _storage =
      FlutterSecureStorage();

  static const String _accessKey = 'airway_access_token';
  static const String _refreshKey = 'airway_refresh_token';

  static Future<void> saveSession({
    required String accessToken,
    required String refreshToken,
  }) async {
    if (accessToken.isEmpty || refreshToken.isEmpty) {
      throw ArgumentError('Authentication tokens cannot be empty.');
    }

    // Remove any previous session before saving a new one.
    await clearSession();

    try {
      await _storage.write(
        key: _accessKey,
        value: accessToken,
      );

      await _storage.write(
        key: _refreshKey,
        value: refreshToken,
      );
    } catch (_) {
      // Avoid keeping an incomplete session.
      await clearSession();
      rethrow;
    }
  }

  static Future<AuthSession?> readSession() async {
    final access = await _storage.read(key: _accessKey);
    final refresh = await _storage.read(key: _refreshKey);

    if (access == null ||
        refresh == null ||
        access.isEmpty ||
        refresh.isEmpty) {
      return null;
    }

    return AuthSession(
      accessToken: access,
      refreshToken: refresh,
    );
  }

  static Future<void> clearSession() async {
    await _storage.delete(key: _accessKey);
    await _storage.delete(key: _refreshKey);
  }
}
