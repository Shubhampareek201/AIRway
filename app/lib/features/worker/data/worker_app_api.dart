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
    bool retried = false,
  }) async {
    final session = await SecureSessionStorage.readSession();
    if (session == null) throw Exception('Please sign in again.');

    final baseUri = Uri.parse(AuthApi.baseUrl);
    final uri = path.startsWith('http') ? Uri.parse(path) : baseUri.resolve(path);
    if (uri.origin != baseUri.origin) {
      throw const FormatException('AIRway API returned an unexpected host.');
    }

    late Map<String, dynamic> result;
    final client = HttpClient()
      ..connectionTimeout = const Duration(seconds: 10);
    try {
      final request = await client.openUrl(method, uri);
      request.headers.set(
        HttpHeaders.authorizationHeader,
        'Bearer ${session.accessToken}',
      );

      if (file != null && fileFieldName != null) {
        final bytes = await file.readAsBytes();
        final boundary = '----AIRwayBoundary${DateTime.now().microsecondsSinceEpoch}';
        final body = <List<int>>[];

        void addField(String key, dynamic value) {
          final fieldValue = value is List || value is Map
              ? jsonEncode(value)
              : value.toString();
          body.add(utf8.encode('--$boundary\r\n'));
          body.add(utf8.encode(
            'Content-Disposition: form-data; name="$key"\r\n\r\n',
          ));
          body.add(utf8.encode('$fieldValue\r\n'));
        }

        data?.forEach(addField);
        body.add(utf8.encode('--$boundary\r\n'));
        body.add(utf8.encode(
          'Content-Disposition: form-data; name="$fileFieldName"; filename="photo.jpg"\r\n',
        ));
        body.add(utf8.encode('Content-Type: image/jpeg\r\n\r\n'));
        body.add(bytes);
        body.add(utf8.encode('\r\n--$boundary--\r\n'));

        request.headers.set(
          HttpHeaders.contentTypeHeader,
          'multipart/form-data; boundary=$boundary',
        );
        request.contentLength =
            body.fold<int>(0, (total, chunk) => total + chunk.length);
        for (final chunk in body) {
          request.add(chunk);
        }
      } else if (data != null) {
        final bytes = utf8.encode(jsonEncode(data));
        request.headers.contentType = ContentType.json;
        request.contentLength = bytes.length;
        request.add(bytes);
      }

      final response = await request.close().timeout(
        const Duration(seconds: 20),
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
      result = {'status': response.statusCode, 'body': body};
    } finally {
      client.close(force: true);
    }

    if (result['status'] == 401 && !retried) {
      final refreshed = await AuthApi.refreshSession(
        refreshToken: session.refreshToken,
      );
      if (refreshed == null) {
        await SecureSessionStorage.clearSession();
        return result;
      }
      final access = refreshed['access'] as String;
      await SecureSessionStorage.saveSession(
        accessToken: access,
        refreshToken: refreshed['refresh'] as String? ?? session.refreshToken,
      );
      return _authenticatedRequest(
        path,
        method: method,
        data: data,
        file: file,
        fileFieldName: fileFieldName,
        retried: true,
      );
    }

    return result;
  }

  static Future<Map<String, dynamic>> getUserInfo() async {
    final result = await _authenticatedRequest('/api/v1/auth/me/');
    if (result['status'] < 200 || result['status'] >= 300) {
      throw Exception('Could not load your account (${result['status']}).');
    }
    if (result['body'] is! Map) {
      throw const FormatException('Unexpected account response.');
    }
    return Map<String, dynamic>.from(result['body'] as Map);
  }

  static Future<Map<String, dynamic>> submitWorkerApplication({
    required List<int> serviceIds,
    required Map<int, List<String>> serviceCapabilities,
    required List<int> zoneIds,
    int? experienceYears,
    Map<int, int>? serviceExperienceYears,
    String? bio,
    required String name,
    required String email,
    required String gender,
    String? qualification,
    String? equipmentDetails,
    required String residentialAddress,
    double? latitude,
    double? longitude,
    String? landmark,
    String? upiId,
    required Map<int, Map<String, String>> schedule,
    File? profilePhoto,
  }) async {
    final data = <String, dynamic>{
      'services': serviceIds,
      'service_capabilities': jsonEncode(serviceCapabilities.map((key, value) => MapEntry(key.toString(), value))),
      if (serviceExperienceYears != null) 'service_experience_years': jsonEncode(serviceExperienceYears.map((key, value) => MapEntry(key.toString(), value))),
      'zones': zoneIds,
      'name': name,
      'email': email,
      'gender': gender,
      'residential_address': residentialAddress,
      if (latitude != null && longitude != null) 'latitude': latitude,
      if (latitude != null && longitude != null) 'longitude': longitude,
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
    if (upiId != null && upiId.trim().isNotEmpty) {
      data['upi_id'] = upiId.trim();
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
      // Send application fields even when reusing an already-uploaded photo.
      // Existing applications are detected by the backend before it validates a new photo.
      data: data,
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
    if (!['aadhaar', 'id', 'qualification', 'address_proof', 'other', 'photo'].contains(docType)) {
      throw Exception('Invalid worker document type.');
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
    final result = await _authenticatedRequest('/api/v1/workers/documents/');
    if (result['status'] < 200 || result['status'] >= 300) {
      throw Exception('Failed to fetch documents: ${result['body']}');
    }
    final body = result['body'];
    final list = body is List ? body : (body is Map ? body['results'] : null);
    if (list is! List) {
      throw const FormatException('Unexpected documents response');
    }
    return list
        .whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item))
        .toList();
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
    final baseUri = Uri.parse(
      '${AuthApi.baseUrl}/api/v1/catalog/services/?is_active=true&for_worker=true&launch_only=true',
    );
    final services = <Service>[];
    Uri? pageUri = baseUri;
    final visitedPages = <String>{};

    while (pageUri != null) {
      if (!visitedPages.add(pageUri.toString()) || visitedPages.length > 50) {
        throw const FormatException('Invalid catalogue pagination response');
      }
      if (pageUri.origin != baseUri.origin) {
        throw const FormatException('Catalogue pagination returned an unexpected host');
      }

      final response = await _authenticatedRequest(pageUri.toString());
      if (response['status'] < 200 || response['status'] >= 300) {
        throw HttpException(
          'Could not load worker services (HTTP ${response['status']}).',
          uri: pageUri,
        );
      }
      final body = response['body'];
      final list = body is List ? body : (body is Map ? body['results'] : null);
      if (list is! List) {
        throw const FormatException('Unexpected services response');
      }
      services.addAll(
        list.whereType<Map>().map(
          (item) => Service.fromMap(Map<String, dynamic>.from(item)),
        ),
      );
      final next = body is Map ? body['next']?.toString() : null;
      pageUri = next == null || next.isEmpty ? null : baseUri.resolve(next);
    }
    return services;
  }

  static Future<List<dynamic>> fetchZones({int? cityId}) async {
    final path = cityId == null
        ? '/api/v1/auth/zones/'
        : '/api/v1/auth/zones/?city_id=$cityId';
    final result = await _authenticatedRequest(path);
    if (result['status'] < 200 || result['status'] >= 300) {
      throw Exception('Could not load service zones.');
    }
    final body = result['body'];
    final list = body is List ? body : (body is Map ? body['results'] : null);
    if (list is! List) {
      throw const FormatException('Unexpected zones response');
    }
    return list
        .whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item))
        .toList();
  }

  static Future<Map<String, dynamic>?> fetchWorkerApplicationStatus() async {
    final session = await SecureSessionStorage.readSession();
    if (session == null) return null;
    try {
      final result = await _authenticatedRequest('/api/v1/auth/me/');
      if (result['status'] != 200 || result['body'] is! Map) return null;
      return Map<String, dynamic>.from(result['body'] as Map);
    } catch (_) {
      return null;
    }
  }
}
