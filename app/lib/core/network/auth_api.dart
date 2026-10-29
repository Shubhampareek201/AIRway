
import 'dart:async';
import 'dart:convert';
import 'dart:io';

class AuthApiException implements Exception {
  const AuthApiException(this.message);

  final String message;

  @override
  String toString() => message;
}

class AuthApi {
  AuthApi._();

  static const String baseUrl = String.fromEnvironment(
    'AIRWAY_API_BASE_URL',
    defaultValue: 'http://192.168.1.4:8000',
  );

  static Future<Map<String, dynamic>> register({
    required String phone,
    required String name,
    required String password,
    required String confirmPassword,
  }) async {
    final client = HttpClient()
      ..connectionTimeout = const Duration(seconds: 10);

    try {
      final request = await client.postUrl(
        Uri.parse('$baseUrl/api/v1/auth/register/'),
      );

      final body = utf8.encode(
        jsonEncode({
          'phone': phone,
          'name': name,
          'password': password,
          'confirm_password': confirmPassword,
        }),
      );

      request.headers.contentType = ContentType.json;
      request.contentLength = body.length;
      request.add(body);

      final response = await request.close().timeout(
        const Duration(seconds: 20),
      );

      final responseBody = await utf8.decoder.bind(response).join();
      final decoded = jsonDecode(responseBody);

      if (decoded is! Map<String, dynamic>) {
        throw const AuthApiException('Unexpected server response.');
      }

      if (response.statusCode != HttpStatus.created && response.statusCode != HttpStatus.ok) {
        throw AuthApiException(decoded['error']?.toString() ?? 'Registration failed.');
      }

      if (decoded['access'] is! String || decoded['refresh'] is! String) {
        throw const AuthApiException('Registration response is missing tokens.');
      }

      return decoded;
    } on SocketException {
      throw const AuthApiException('Cannot connect to AIRway server.');
    } on TimeoutException {
      throw const AuthApiException('AIRway server did not respond in time.');
    } on FormatException {
      throw const AuthApiException('Invalid response from AIRway server.');
    } finally {
      client.close(force: true);
    }
  }

  static Future<Map<String, dynamic>> login({
    required String phone,
    required String password,
  }) async {
    final client = HttpClient()
      ..connectionTimeout = const Duration(seconds: 10);

    try {
      final request = await client.postUrl(
        Uri.parse('$baseUrl/api/v1/auth/login/'),
      );

      final body = utf8.encode(
        jsonEncode({
          'phone': phone,
          'password': password,
        }),
      );

      request.headers.contentType = ContentType.json;
      request.contentLength = body.length;
      request.add(body);

      final response = await request.close().timeout(
        const Duration(seconds: 20),
      );

      final responseBody = await utf8.decoder.bind(response).join();
      final decoded = jsonDecode(responseBody);

      if (decoded is! Map<String, dynamic>) {
        throw const AuthApiException('Unexpected server response.');
      }

      if (response.statusCode != HttpStatus.ok) {
        throw AuthApiException(decoded['error']?.toString() ?? 'Login failed.');
      }

      if (decoded['access'] is! String || decoded['refresh'] is! String) {
        throw const AuthApiException('Login response is missing tokens.');
      }

      return decoded;
    } on SocketException {
      throw const AuthApiException('Cannot connect to AIRway server.');
    } on TimeoutException {
      throw const AuthApiException('AIRway server did not respond in time.');
    } on FormatException {
      throw const AuthApiException('Invalid response from AIRway server.');
    } finally {
      client.close(force: true);
    }
  }

  static Future<Map<String, dynamic>> forgotPassword({
    required String phone,
  }) async {
    final client = HttpClient()
      ..connectionTimeout = const Duration(seconds: 10);

    try {
      final request = await client.postUrl(
        Uri.parse('$baseUrl/api/v1/auth/forgot-password/'),
      );

      final body = utf8.encode(jsonEncode({'phone': phone}));

      request.headers.contentType = ContentType.json;
      request.contentLength = body.length;
      request.add(body);

      final response = await request.close().timeout(
        const Duration(seconds: 20),
      );

      final responseBody = await utf8.decoder.bind(response).join();
      final decoded = jsonDecode(responseBody);

      if (decoded is! Map<String, dynamic>) {
        throw const AuthApiException('Unexpected server response.');
      }

      if (response.statusCode != HttpStatus.ok) {
        throw AuthApiException(decoded['error']?.toString() ?? 'Failed to send OTP.');
      }

      return decoded;
    } on SocketException {
      throw const AuthApiException('Cannot connect to AIRway server.');
    } on TimeoutException {
      throw const AuthApiException('AIRway server did not respond in time.');
    } on FormatException {
      throw const AuthApiException('Invalid response from AIRway server.');
    } finally {
      client.close(force: true);
    }
  }

  static Future<Map<String, dynamic>> verifyOtp({
    required String phone,
    required String otp,
  }) async {
    final client = HttpClient()
      ..connectionTimeout = const Duration(seconds: 10);

    try {
      final request = await client.postUrl(
        Uri.parse('$baseUrl/api/v1/auth/verify-otp/'),
      );

      final body = utf8.encode(jsonEncode({'phone': phone, 'otp': otp, 'purpose': 'forgot_password'}));

      request.headers.contentType = ContentType.json;
      request.contentLength = body.length;
      request.add(body);

      final response = await request.close().timeout(
        const Duration(seconds: 20),
      );

      final responseBody = await utf8.decoder.bind(response).join();
      final decoded = jsonDecode(responseBody);

      if (decoded is! Map<String, dynamic>) {
        throw const AuthApiException('Unexpected server response.');
      }

      if (response.statusCode != HttpStatus.ok) {
        throw AuthApiException(decoded['error']?.toString() ?? 'OTP verification failed.');
      }

      return decoded;
    } on SocketException {
      throw const AuthApiException('Cannot connect to AIRway server.');
    } on TimeoutException {
      throw const AuthApiException('AIRway server did not respond in time.');
    } on FormatException {
      throw const AuthApiException('Invalid response from AIRway server.');
    } finally {
      client.close(force: true);
    }
  }

  static Future<Map<String, dynamic>> resetPassword({
    required String phone,
    required String otp,
    required String newPassword,
    required String confirmNewPassword,
  }) async {
    final client = HttpClient()
      ..connectionTimeout = const Duration(seconds: 10);

    try {
      final request = await client.postUrl(
        Uri.parse('$baseUrl/api/v1/auth/reset-password/'),
      );

      final body = utf8.encode(jsonEncode({
        'phone': phone,
        'otp': otp,
        'new_password': newPassword,
        'confirm_new_password': confirmNewPassword,
      }));

      request.headers.contentType = ContentType.json;
      request.contentLength = body.length;
      request.add(body);

      final response = await request.close().timeout(
        const Duration(seconds: 20),
      );

      final responseBody = await utf8.decoder.bind(response).join();
      final decoded = jsonDecode(responseBody);

      if (decoded is! Map<String, dynamic>) {
        throw const AuthApiException('Unexpected server response.');
      }

      if (response.statusCode != HttpStatus.ok) {
        throw AuthApiException(decoded['error']?.toString() ?? 'Password reset failed.');
      }

      return decoded;
    } on SocketException {
      throw const AuthApiException('Cannot connect to AIRway server.');
    } on TimeoutException {
      throw const AuthApiException('AIRway server did not respond in time.');
    } on FormatException {
      throw const AuthApiException('Invalid response from AIRway server.');
    } finally {
      client.close(force: true);
    }
  }

  // 1. Firebase OTP login -> Django JWT tokens
  static Future<Map<String, dynamic>> firebaseLogin({
    required String idToken,
  }) async {
    final client = HttpClient()
      ..connectionTimeout = const Duration(seconds: 10);

    try {
      final request = await client.postUrl(
        Uri.parse('$baseUrl/api/v1/auth/firebase-login/'),
      );

      final body = utf8.encode(
        jsonEncode({'id_token': idToken}),
      );

      request.headers.contentType = ContentType.json;
      request.contentLength = body.length;
      request.add(body);

      final response = await request.close().timeout(
        const Duration(seconds: 20),
      );

      final responseBody = await utf8.decoder.bind(response).join();
      final decoded = jsonDecode(responseBody);

      if (decoded is! Map<String, dynamic>) {
        throw const AuthApiException(
          'Unexpected server response.',
        );
      }

      if (response.statusCode != HttpStatus.ok) {
        throw AuthApiException(
          decoded['error']?.toString() ??
              'Login failed (${response.statusCode}).',
        );
      }

      if (decoded['access'] is! String ||
          decoded['refresh'] is! String ||
          decoded['user'] is! Map) {
        throw const AuthApiException(
          'Login response is missing required fields.',
        );
      }

      return decoded;
    } on SocketException {
      throw const AuthApiException(
        'Cannot connect to AIRway server.',
      );
    } on TimeoutException {
      throw const AuthApiException(
        'AIRway server did not respond in time.',
      );
    } on FormatException {
      throw const AuthApiException(
        'Invalid response from AIRway server.',
      );
    } finally {
      client.close(force: true);
    }
  }

  // 2. Check access token with Django /me/
  static Future<bool> validateSession({
    required String accessToken,
  }) async {
    final client = HttpClient()
      ..connectionTimeout = const Duration(seconds: 10);

    try {
      final request = await client.getUrl(
        Uri.parse('$baseUrl/api/v1/auth/me/'),
      );

      request.headers.set(
        HttpHeaders.authorizationHeader,
        'Bearer $accessToken',
      );

      final response = await request.close().timeout(
        const Duration(seconds: 15),
      );

      await response.drain<void>();

      if (response.statusCode == HttpStatus.ok) {
        return true;
      }

      if (response.statusCode == HttpStatus.unauthorized) {
        return false;
      }

      throw AuthApiException(
        'Session validation failed (${response.statusCode}).',
      );
    } on SocketException {
      throw const AuthApiException(
        'Cannot connect to AIRway server.',
      );
    } on TimeoutException {
      throw const AuthApiException(
        'AIRway server did not respond in time.',
      );
    } finally {
      client.close(force: true);
    }
  }

  // 3. Refresh an expired access token
  static Future<Map<String, dynamic>?> refreshSession({
    required String refreshToken,
  }) async {
    final client = HttpClient()
      ..connectionTimeout = const Duration(seconds: 10);

    try {
      final request = await client.postUrl(
        Uri.parse('$baseUrl/api/v1/auth/refresh/'),
      );

      final body = utf8.encode(
        jsonEncode({'refresh': refreshToken}),
      );

      request.headers.contentType = ContentType.json;
      request.contentLength = body.length;
      request.add(body);

      final response = await request.close().timeout(
        const Duration(seconds: 15),
      );

      final responseBody = await utf8.decoder.bind(response).join();

      if (response.statusCode == HttpStatus.unauthorized ||
          response.statusCode == HttpStatus.badRequest) {
        return null;
      }

      if (response.statusCode != HttpStatus.ok) {
        throw AuthApiException(
          'Session refresh failed (${response.statusCode}).',
        );
      }

      final decoded = jsonDecode(responseBody);

      if (decoded is! Map<String, dynamic> ||
          decoded['access'] is! String) {
        throw const AuthApiException(
          'Invalid session refresh response.',
        );
      }

      return decoded;
    } on SocketException {
      throw const AuthApiException(
        'Cannot connect to AIRway server.',
      );
    } on TimeoutException {
      throw const AuthApiException(
        'AIRway server did not respond in time.',
      );
    } on FormatException {
      throw const AuthApiException(
        'Invalid response from AIRway server.',
      );
    } finally {
      client.close(force: true);
    }
  }
}
