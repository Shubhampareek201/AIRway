
import 'dart:convert';
import 'dart:io';

import 'package:airway/core/network/auth_api.dart';
import 'package:airway/core/storage/secure_session_storage.dart';

class LocationApi {
  LocationApi._();

  static Future<dynamic> request(
    String path, {
    String method = 'GET',
    Map<String, dynamic>? data,
  }) async {
    final session = await SecureSessionStorage.readSession();

    if (session == null) {
      throw Exception('Please sign in again.');
    }

    // Each attempt has its own client, fully closed after
    // the response body has been read.
    Future<({int status, dynamic body})> call(
      String token,
    ) async {
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
            refreshed['refresh'] as String? ??
            session.refreshToken,
      );

      result = await call(access);
    }

    if (result.status < 200 || result.status >= 300) {
      throw Exception(
        'AIRway request failed (${result.status}): '
        '${result.body}',
      );
    }

    return result.body;
  }

  static Future<Map<String, dynamic>> reverse(
    double latitude,
    double longitude,
  ) async {
    final path =
        '/api/v1/auth/locations/reverse/'
        '?lat=$latitude&lon=$longitude';

    final result = await request(path);
    return Map<String, dynamic>.from(result as Map);
  }

  static Future<List<dynamic>> cities() async {
    final result = await request('/api/v1/auth/cities/');
    return result as List<dynamic>;
  }

  static Future<List<dynamic>> zones(int cityId) async {
    final result = await request(
      '/api/v1/auth/zones/?city_id=$cityId',
    );
    return result as List<dynamic>;
  }

  static Future<Map<String, dynamic>> saveAddress(
    Map<String, dynamic> address,
  ) async {
    final result = await request(
      '/api/v1/auth/addresses/',
      method: 'POST',
      data: address,
    );
    return Map<String, dynamic>.from(result as Map);
  }
}
