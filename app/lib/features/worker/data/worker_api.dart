import 'dart:convert';
import 'dart:io';
import 'package:airway/core/network/auth_api.dart';
import 'package:airway/core/storage/secure_session_storage.dart';
import 'package:airway/features/worker/data/worker_models.dart';

class WorkerApi {
  WorkerApi._();

  static Future<dynamic> _request(
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
    return result.body;
  }

  static Future<WorkerProfile> getMyProfile() async {
    final result = Map<String, dynamic>.from(
      await _request('/api/v1/auth/me/') as Map,
    );
    final workerData = result['worker_profile'];
    if (workerData is! Map) {
      throw Exception('No worker profile found for this account.');
    }
    return WorkerProfile.fromMap({
      ...Map<String, dynamic>.from(workerData),
      'name': result['name'],
      'phone': result['phone'],
    });
  }

  static Future<List<WorkerOffer>> getJobOffers() async {
    final result = await _request('/api/v1/workers/offers/');
    final list = (result as Map)['results'] as List;

    return list
        .whereType<Map>()
        .map((e) => WorkerOffer.fromMap(Map<String, dynamic>.from(e)))
        .toList();
  }

  static Future<WorkerOffer> acceptOffer(int offerId) async {
    final result = await _request(
      '/api/v1/workers/offers/$offerId/accept/',
      method: 'POST',
    );
    return WorkerOffer.fromMap(Map<String, dynamic>.from(result as Map));
  }

  static Future<void> declineOffer(int offerId) async {
    await _request(
      '/api/v1/workers/offers/$offerId/decline/',
      method: 'POST',
    );
  }

  static Future<void> withdrawOffer(int offerId) async {
    await _request(
      '/api/v1/workers/offers/$offerId/withdraw/',
      method: 'POST',
    );
  }

  static Future<Map<String, dynamic>> startJob(int assignmentId) async {
    final result = await _request(
      '/api/v1/workers/jobs/$assignmentId/start/',
      method: 'POST',
    );
    return Map<String, dynamic>.from(result as Map);
  }

  static Future<Map<String, dynamic>> completeJob(
    int assignmentId, {
    String? otp,
  }) async {
    final result = await _request(
      '/api/v1/workers/jobs/$assignmentId/complete/',
      method: 'POST',
      data: otp == null ? null : {'otp': otp},
    );
    return Map<String, dynamic>.from(result as Map);
  }

  static Future<List<Map<String, dynamic>>> getAssignedJobs() async {
    final result = await _request('/api/v1/workers/jobs/');
    final list = result as List;
    return list.map((e) => Map<String, dynamic>.from(e)).toList();
  }

  static Future<Map<String, dynamic>> getJobDetail(int jobId) async {
    final result = await _request('/api/v1/workers/jobs/$jobId/');
    return Map<String, dynamic>.from(result as Map);
  }

  static Future<List<Map<String, dynamic>>> getEarnings() async {
    final result = await _request('/api/v1/workers/earnings/');
    if (result is! List) {
      throw const FormatException('Unexpected earnings response');
    }
    return result
        .whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item))
        .toList();
  }

  static Future<bool> updateOnlineStatus(bool isOnline) async {
    final result = await _request(
      '/api/v1/workers/status/',
      method: 'POST',
      data: {'is_online': isOnline},
    );
    return (result as Map)['is_online'] as bool? ?? isOnline;
  }
}