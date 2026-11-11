import 'dart:convert';
import 'dart:io';
import 'package:airway/core/network/auth_api.dart';
import 'package:airway/core/storage/secure_session_storage.dart';
import 'package:airway/features/catalog/data/catalog_models.dart';

class WorkerAppApi {
  WorkerAppApi._();

  static Future<Map<String, dynamic>> _authenticatedRequest(
    String path, {
    String method = 'GET',
    Map<String, dynamic>? data,
    File? file,
    String? fileFieldName,
  }) async {
    final session = await SecureSessionStorage.readSession();
    if (session == null) throw Exception('Please sign in again.');

    final client = HttpClient()
      ..connectionTimeout = const Duration(seconds: 10);

    try {
      final request = await client.openUrl(
        method,
        Uri.parse('${AuthApi.baseUrl}$path'),
      );

      request.headers.set(
        HttpHeaders.authorizationHeader,
        'Bearer ${session.accessToken}',
      );

      if (file != null && fileFieldName != null) {
        // Multipart form data for file upload
        final bytes = await file.readAsBytes();
        final boundary = '----AIRwayBoundary${DateTime.now().millisecondsSinceEpoch}';

        final body = <List<int>>[];

        void addField(String key, dynamic value) {
          if (value is List) {
            final strValue = value.toString().replaceAll(']', '').replaceAll('[', '');
            body.add(utf8.encode('--$boundary\r\n'));
            body.add(utf8.encode('Content-Disposition: form-data; name="$key"\r\n\r\n'));
            body.add(utf8.encode('$strValue\r\n'));
          } else if (value is int || value is String) {
            body.add(utf8.encode('--$boundary\r\n'));
            body.add(utf8.encode('Content-Disposition: form-data; name="$key"\r\n\r\n'));
            body.add(utf8.encode('$value\r\n'));
          }
        }

        if (data != null) {
          data.forEach((key, value) => addField(key, value));
        }

        body.add(utf8.encode('--$boundary\r\n'));
        body.add(utf8.encode(
            'Content-Disposition: form-data; name="$fileFieldName"; filename="photo.jpg"\r\n'));
        body.add(utf8.encode('Content-Type: image/jpeg\r\n\r\n'));
        body.add(bytes);
        body.add(utf8.encode('\r\n'));
        body.add(utf8.encode('--$boundary--\r\n'));

        final totalLength = body.fold<int>(0, (prev, elem) => prev + elem.length);
        request.headers
            .set('content-type', 'multipart/form-data; boundary=$boundary');
        request.contentLength = totalLength;

        for (final chunk in body) {
          request.add(chunk);
        }
      } else if (data != null) {
        // JSON body for regular requests
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
        try {
          result = jsonDecode(text);
        } catch (_) {
          result = text;
        }
      }

      return {
        'status': response.statusCode,
        'body': result,
      };
    } finally {
      client.close(force: true);
    }
  }

  static Future<Map<String, dynamic>> getUserInfo() async {
    final session = await SecureSessionStorage.readSession();
    if (session == null) throw Exception('Please sign in again.');

    final result = await AuthApi.validateSession(accessToken: session.accessToken);
    if (!result) throw Exception('Session invalid');

    // Fetch user info from /me/ endpoint
    final client = HttpClient()
      ..connectionTimeout = const Duration(seconds: 10);

    try {
      final request = await client.getUrl(
        Uri.parse('${AuthApi.baseUrl}/api/v1/auth/me/'),
      );
      request.headers.set(
        HttpHeaders.authorizationHeader,
        'Bearer ${session.accessToken}',
      );

      final response = await request.close().timeout(
        const Duration(seconds: 15),
      );
      final text = await utf8.decoder.bind(response).join();

      final result = jsonDecode(text);
      return Map<String, dynamic>.from(result as Map);
    } finally {
      client.close(force: true);
    }
  }

  static Future<Map<String, dynamic>> submitWorkerApplication({
    required List<int> serviceIds,
    required List<int> zoneIds,
    int? experienceYears,
    String? bio,
    required String name,
    required String email,
    required String gender,
    String? qualification,
    String? equipmentDetails,
    required String residentialAddress,
    String? landmark,
    required Map<int, Map<String, String>> schedule,
    File? profilePhoto,
  }) async {
    final data = <String, dynamic>{
      'services': serviceIds,
      'zones': zoneIds,
      'name': name,
      'email': email,
      'gender': gender,
      'residential_address': residentialAddress,
      'schedule': jsonEncode(schedule.map((key, value) => MapEntry(key.toString(), value))),
    };
    if (qualification != null && qualification.trim().isNotEmpty) {
      data['qualification'] = qualification.trim();
    }
    if (equipmentDetails != null && equipmentDetails.trim().isNotEmpty) {
      data['equipment_details'] = equipmentDetails.trim();
    }
    if (landmark != null && landmark.trim().isNotEmpty) {
      data['landmark'] = landmark.trim();
    }

    if (experienceYears != null && experienceYears > 0) {
      data['experience_years'] = experienceYears;
    }
    if (bio != null && bio.isNotEmpty) {
      data['bio'] = bio;
    }

    final result = await _authenticatedRequest(
      '/api/v1/workers/apply/',
      method: 'POST',
      data: profilePhoto != null ? data : null,
      file: profilePhoto,
      fileFieldName: profilePhoto != null ? 'profile_photo' : null,
    );

    if (result['status'] == 401) {
      throw Exception('Session expired. Please sign in again.');
    }

    if (result['status'] < 200 || result['status'] >= 300) {
      throw Exception(
        'Application failed (${result['status']}): ${result['body']}',
      );
    }

    if (result['body'] is! Map<String, dynamic>) {
      throw const FormatException('Unexpected server response');
    }

    return Map<String, dynamic>.from(result['body'] as Map);
  }

  static Future<Map<String, dynamic>> uploadIdDocument({
    required String docType,
    required File file,
  }) async {
    if (!['aadhaar', 'id'].contains(docType)) {
      throw Exception('Invalid document type. Must be "aadhaar" or "id".');
    }

    final result = await _authenticatedRequest(
      '/api/v1/workers/documents/upload/',
      method: 'POST',
      data: {'doc_type': docType},
      file: file,
      fileFieldName: 'file',
    );

    if (result['status'] == 401) {
      throw Exception('Session expired. Please sign in again.');
    }

    if (result['status'] < 200 || result['status'] >= 300) {
      throw Exception(
        'Document upload failed (${result['status']}): ${result['body']}',
      );
    }

    if (result['body'] is! Map<String, dynamic>) {
      throw const FormatException('Unexpected server response');
    }

    return Map<String, dynamic>.from(result['body'] as Map);
  }

  static Future<List<dynamic>> fetchWorkerDocuments() async {
    final session = await SecureSessionStorage.readSession();
    if (session == null) throw Exception('Please sign in again.');

    final client = HttpClient()
      ..connectionTimeout = const Duration(seconds: 10);

    try {
      final request = await client.getUrl(
        Uri.parse('${AuthApi.baseUrl}/api/v1/workers/documents/'),
      );
      request.headers.set(
        HttpHeaders.authorizationHeader,
        'Bearer ${session.accessToken}',
      );

      final response = await request.close().timeout(
        const Duration(seconds: 15),
      );

      if (response.statusCode == 401) {
        throw Exception('Session expired. Please sign in again.');
      }

      if (response.statusCode < 200 || response.statusCode >= 300) {
        final text = await utf8.decoder.bind(response).join();
        throw Exception('Failed to fetch documents: $text');
      }

      final text = await utf8.decoder.bind(response).join();
      final result = jsonDecode(text);
      final list = result is List ? result : (result is Map ? result['results'] : null);

      if (list is! List) {
        throw const FormatException('Unexpected documents response');
      }

      return list
          .whereType<Map>()
          .map((e) => Map<String, dynamic>.from(e))
          .toList();
    } finally {
      client.close(force: true);
    }
  }

  static Future<void> switchToWorkerMode({
    required String accessToken,
  }) async {
    final result = await _authenticatedRequest(
      '/api/v1/auth/switch-mode/',
      method: 'POST',
      data: {'mode': 'worker'},
    );

    if (result['status'] == 401) {
      throw Exception('Session expired. Please sign in again.');
    }

    if (result['status'] < 200 || result['status'] >= 300) {
      throw Exception('Mode switch failed: ${result['body']}');
    }
  }

  static Future<void> switchToCustomerMode() async {
    final result = await _authenticatedRequest('/api/v1/auth/switch-mode/', method: 'POST', data: {'mode': 'customer'});
    if (result['status'] == 401) throw Exception('Session expired. Please sign in again.');
    if (result['status'] < 200 || result['status'] >= 300) {
      final body = result['body'];
      final message = body is Map ? body['error']?.toString() ?? body['detail']?.toString() : null;
      throw Exception(message ?? 'Mode switch failed.');
    }
  }
  static Future<List<Service>> fetchServicesForWorkerApplication() async {
    final client = HttpClient()
      ..connectionTimeout = const Duration(seconds: 10);

    try {
      final request = await client.getUrl(
        Uri.parse('${AuthApi.baseUrl}/api/v1/catalog/services/?is_active=true&for_worker=true'),
      );
      request.headers.set(
        HttpHeaders.authorizationHeader,
        'Bearer ${(await SecureSessionStorage.readSession())?.accessToken}',
      );

      final response = await request.close().timeout(
        const Duration(seconds: 15),
      );
      final text = await utf8.decoder.bind(response).join();

      final result = jsonDecode(text);
      final list = result is List ? result : (result is Map ? result['results'] : null);

      if (list is! List) {
        throw const FormatException('Unexpected services response');
      }

      return list
          .whereType<Map>()
          .map((e) => Service.fromMap(Map<String, dynamic>.from(e)))
          .toList();
    } finally {
      client.close(force: true);
    }
  }

  static Future<List<dynamic>> fetchZones({int? cityId}) async {
    final client = HttpClient()
      ..connectionTimeout = const Duration(seconds: 10);

    try {
      var uri = '${AuthApi.baseUrl}/api/v1/auth/zones/';
      if (cityId != null) {
        uri += '?city_id=$cityId';
      }

      final request = await client.getUrl(Uri.parse(uri));
      request.headers.set(
        HttpHeaders.authorizationHeader,
        'Bearer ${(await SecureSessionStorage.readSession())?.accessToken}',
      );

      final response = await request.close().timeout(
        const Duration(seconds: 15),
      );
      final text = await utf8.decoder.bind(response).join();

      final result = jsonDecode(text);
      final list = result is List ? result : (result is Map ? result['results'] : null);

      if (list is! List) {
        throw const FormatException('Unexpected zones response');
      }

      return list
          .whereType<Map>()
          .map((e) => Map<String, dynamic>.from(e))
          .toList();
    } finally {
      client.close(force: true);
    }
  }

  static Future<Map<String, dynamic>?> fetchWorkerApplicationStatus() async {
    final session = await SecureSessionStorage.readSession();
    if (session == null) return null;

    final client = HttpClient()
      ..connectionTimeout = const Duration(seconds: 10);

    try {
      final request = await client.getUrl(
        Uri.parse('${AuthApi.baseUrl}/api/v1/auth/me/'),
      );
      request.headers.set(
        HttpHeaders.authorizationHeader,
        'Bearer ${session.accessToken}',
      );

      final response = await request.close().timeout(
        const Duration(seconds: 15),
      );

      if (response.statusCode != 200) {
        return null;
      }

      final text = await utf8.decoder.bind(response).join();
      final result = jsonDecode(text) as Map<String, dynamic>;

      return result;
    } catch (e) {
      return null;
    } finally {
      client.close(force: true);
    }
  }
}