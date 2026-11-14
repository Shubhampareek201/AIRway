import 'dart:convert';
import 'dart:io';

import 'package:airway/core/network/auth_api.dart';
import 'package:airway/core/storage/secure_session_storage.dart';
import 'package:airway/features/ratings/data/rating_models.dart';

class RatingApi {
  RatingApi._();

  static Future<dynamic> _request(
    String path, {
    String method = 'GET',
    Map<String, dynamic>? data,
  }) async {
    final session = await SecureSessionStorage.readSession();
    if (session == null) {
      throw Exception('Please sign in again.');
    }

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
    return result;
  }

  static String _errorMessage(dynamic body, String fallback) {
    if (body is Map<String, dynamic>) {
      final detail = body['detail'];
      if (detail is String) return detail;
    }
    return fallback;
  }

  static Future<List<RatingModel>> fetchUserRatings() async {
    final result = await _request('/api/v1/ratings/');
    if (result.status != 200) {
      throw Exception(_errorMessage(result.body, 'Could not load ratings.'));
    }
    final list = result.body as List<dynamic>;
    return list
        .map((e) => RatingModel.fromMap(e as Map<String, dynamic>))
        .toList();
  }

  static Future<RatingSummaryModel?> fetchRatingSummary() async {
    final result = await _request('/api/v1/ratings/summaries/user-ratings/');
    if (result.status != 200) {
      throw Exception(_errorMessage(result.body, 'Could not load rating summary.'));
    }
    final list = result.body as List<dynamic>;
    if (list.isEmpty) return null;
    return RatingSummaryModel.fromMap(list.first as Map<String, dynamic>);
  }

  static Future<RatingModel> submitRating({
    required int bookingId,
    required int ratedId,
    required int rating,
    required String ratingType,
    String comment = '',
  }) async {
    final request = RateBookingRequest(
      ratedId: ratedId,
      ratingType: ratingType,
      rating: rating,
      comment: comment,
    );
    final result = await _request(
      '/api/v1/ratings/$bookingId/rating/',
      method: 'POST',
      data: request.toMap(),
    );
    if (result.status != 201) {
      throw Exception(_errorMessage(result.body, 'Failed to submit rating.'));
    }
    return RatingModel.fromMap(result.body as Map<String, dynamic>);
  }
}