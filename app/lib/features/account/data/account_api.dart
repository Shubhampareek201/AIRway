import 'dart:convert';
import 'dart:io';

import 'package:airway/core/network/auth_api.dart';
import 'package:airway/core/storage/secure_session_storage.dart';
import 'package:airway/features/location/data/location_api.dart';

class AccountApi {
  AccountApi._();

  static Future<Map<String, dynamic>> fetchProfile() async {
    final result = await LocationApi.request('/api/v1/auth/me/');
    if (result is! Map) {
      throw const FormatException('Unexpected account profile response.');
    }
    return Map<String, dynamic>.from(result);
  }

  static Future<Map<String, dynamic>> fetchReferrals() async {
    final result = await LocationApi.request('/api/v1/auth/referrals/');
    if (result is! Map) throw const FormatException('Unexpected referral response.');
    return Map<String, dynamic>.from(result);
  }

  static Future<Map<String, dynamic>> applyReferralCode(String code) async {
    final result = await LocationApi.request(
      '/api/v1/auth/referrals/',
      method: 'POST',
      data: {'referral_code': code.trim().toUpperCase()},
    );
    if (result is! Map) throw const FormatException('Unexpected referral response.');
    return Map<String, dynamic>.from(result);
  }

  static Future<Map<String, dynamic>> fetchDeletionRequest() async {
    final result = await LocationApi.request('/api/v1/auth/delete-account/');
    if (result is! Map) {
      throw const FormatException('Unexpected account deletion response.');
    }
    return Map<String, dynamic>.from(result);
  }

  static Future<Map<String, dynamic>> requestAccountDeletion({String reason = ''}) async {
    final result = await LocationApi.request(
      '/api/v1/auth/delete-account/',
      method: 'POST',
      data: {'reason': reason.trim()},
    );
    if (result is! Map) {
      throw const FormatException('Unexpected account deletion response.');
    }
    return Map<String, dynamic>.from(result);
  }

  static Future<Map<String, dynamic>> updateLanguage(String language) async {
    final result = await LocationApi.request(
      '/api/v1/auth/language/',
      method: 'PATCH',
      data: {'language': language},
    );
    if (result is! Map) throw const FormatException('Unexpected language response.');
    return Map<String, dynamic>.from(result);
  }

  static Future<Map<String, dynamic>> updateProfile({
    required Map<String, dynamic> data,
    File? photo,
  }) async {
    if (photo == null) {
      final result = await LocationApi.request(
        '/api/v1/auth/profile/',
        method: 'PATCH',
        data: data,
      );
      if (result is! Map) {
        throw const FormatException('Unexpected profile update response.');
      }
      return Map<String, dynamic>.from(result);
    }
    if (await photo.length() > 5 * 1024 * 1024) {
      throw Exception('Profile photo must be 5 MB or smaller.');
    }

    final session = await SecureSessionStorage.readSession();
    if (session == null) throw Exception('Please sign in again.');

    Future<({int status, dynamic body})> send(String token) async {
      final baseUri = Uri.parse(AuthApi.baseUrl);
      final uri = baseUri.resolve('/api/v1/auth/profile/');
      if (uri.origin != baseUri.origin) {
        throw const FormatException('Unexpected AIRway API host.');
      }

      final boundary = 'AIRwayProfile${DateTime.now().microsecondsSinceEpoch}';
      final bytes = await photo.readAsBytes();
      final rawFilename = photo.uri.pathSegments.isEmpty
          ? 'profile-photo.jpg'
          : photo.uri.pathSegments.last;
      final filename = rawFilename.replaceAll(RegExp(r'[^A-Za-z0-9._-]'), '_');
      final extension = filename.toLowerCase().split('.').last;
      final mime = extension == 'png'
          ? 'image/png'
          : extension == 'webp'
              ? 'image/webp'
              : 'image/jpeg';

      final chunks = <List<int>>[];
      for (final entry in data.entries) {
        chunks.add(utf8.encode(
          '--$boundary\r\n'
          'Content-Disposition: form-data; name="${entry.key}"\r\n\r\n'
          '${entry.value}\r\n',
        ));
      }
      chunks.add(utf8.encode(
        '--$boundary\r\n'
        'Content-Disposition: form-data; name="photo"; filename="$filename"\r\n'
        'Content-Type: $mime\r\n\r\n',
      ));
      chunks.add(bytes);
      chunks.add(utf8.encode('\r\n--$boundary--\r\n'));

      final client = HttpClient()
        ..connectionTimeout = const Duration(seconds: 10);
      try {
        final request = await client.patchUrl(uri);
        request.headers.set(HttpHeaders.authorizationHeader, 'Bearer $token');
        request.headers.set(
          HttpHeaders.contentTypeHeader,
          'multipart/form-data; boundary=$boundary',
        );
        request.contentLength =
            chunks.fold<int>(0, (sum, chunk) => sum + chunk.length);
        for (final chunk in chunks) {
          request.add(chunk);
        }
        final response = await request.close().timeout(
          const Duration(seconds: 25),
        );
        final responseText = await utf8.decoder.bind(response).join();
        dynamic body;
        if (responseText.isNotEmpty) {
          try {
            body = jsonDecode(responseText);
          } catch (_) {
            body = responseText;
          }
        }
        return (status: response.statusCode, body: body);
      } finally {
        client.close(force: true);
      }
    }

    var result = await send(session.accessToken);
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
        refreshToken: refreshed['refresh'] as String? ?? session.refreshToken,
      );
      result = await send(access);
    }

    if (result.status < 200 || result.status >= 300) {
      final body = result.body;
      final detail = body is Map
          ? body['detail'] ?? body['error'] ?? body.toString()
          : body;
      throw Exception('Profile update failed (${result.status}): $detail');
    }
    if (result.body is! Map) {
      throw const FormatException('Unexpected profile update response.');
    }
    return Map<String, dynamic>.from(result.body as Map);
  }
}
