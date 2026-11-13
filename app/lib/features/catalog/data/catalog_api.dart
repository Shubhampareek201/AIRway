import 'dart:convert';
import 'dart:io';

import 'package:airway/core/network/auth_api.dart';
import 'package:airway/core/storage/secure_session_storage.dart';
import 'package:airway/features/catalog/data/catalog_models.dart';

class CatalogApi {
  CatalogApi._();

  static Future<dynamic> request(
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

    if (result.status < 200 || result.status >= 300) {
      throw Exception(
        'AIRway request failed (${result.status}): ${result.body}',
      );
    }

    return result.body;
  }

  static Future<List<T>> _parseList<T>(
    dynamic result,
    T Function(Map<String, dynamic>) parse,
  ) async {
    final items = <T>[];
    dynamic page = result;
    final baseUri = Uri.parse(AuthApi.baseUrl);
    while (true) {
      if (page is List) {
        items.addAll(page.whereType<Map>().map(
          (e) => parse(Map<String, dynamic>.from(e)),
        ));
        break;
      }
      if (page is! Map || page['results'] is! List) {
        throw const FormatException('Unexpected catalog list response');
      }
      items.addAll((page['results'] as List).whereType<Map>().map(
        (e) => parse(Map<String, dynamic>.from(e)),
      ));
      final next = page['next'];
      if (next == null || next.toString().isEmpty) break;
      final nextUri = Uri.parse(next.toString());
      if (nextUri.hasAuthority &&
          (nextUri.scheme != baseUri.scheme ||
              nextUri.host != baseUri.host ||
              nextUri.port != baseUri.port)) {
        throw const FormatException('Catalog pagination URL changed API host');
      }
      final nextPath = '${nextUri.path}${nextUri.hasQuery ? '?${nextUri.query}' : ''}';
      page = await request(nextPath);
    }
    return items;
  }

  static Future<List<CatalogBanner>> listBanners({
    int? addressId,
  }) async {
    final query = <String, String>{};
    if (addressId != null) query['address_id'] = addressId.toString();
    final uri = Uri(
      path: '/api/v1/catalog/banners/',
      queryParameters: query.isEmpty ? null : query,
    );
    final result = await request(uri.toString());
    return _parseList(result, CatalogBanner.fromMap);
  }

  static Future<List<Category>> listCategories({
    int? addressId,
    String? audience,
  }) async {
    final query = <String, String>{'launch_only': 'true'};
    if (addressId != null) query['address_id'] = addressId.toString();
    if (audience != null) query['audience'] = audience;
    final uri = Uri(
      path: '/api/v1/catalog/categories/',
      queryParameters: query.isEmpty ? null : query,
    );
    final result = await request(uri.toString());
    return _parseList(result, Category.fromMap);
  }

  static Future<List<Service>> listServices({
    int? category,
    bool? popular,
    int? addressId,
    String? audience,
  }) async {
    final query = <String, String>{'launch_only': 'true'};
    if (category != null) query['category'] = category.toString();
    if (popular == true) query['is_popular'] = 'true';
    if (addressId != null) query['address_id'] = addressId.toString();
    if (audience != null) query['audience'] = audience;
    final uri = Uri(
      path: '/api/v1/catalog/services/',
      queryParameters: query.isEmpty ? null : query,
    );
    final result = await request(uri.toString());
    return _parseList(result, Service.fromMap);
  }

  static Future<Service> getService(
    int id, {
    int? addressId,
    String? audience,
  }) async {
    final uri = Uri(
      path: '/api/v1/catalog/services/$id/',
      queryParameters: {'launch_only': 'true', if (addressId != null) 'address_id': addressId.toString(), if (audience != null) 'audience': audience},
    );
    final result = await request(uri.toString());
    if (result is! Map<String, dynamic>) {
      throw const FormatException('Unexpected service detail response');
    }
    return Service.fromMap(Map<String, dynamic>.from(result));
  }
}