import 'dart:convert';
import 'dart:io';

import 'package:airway/core/network/auth_api.dart';
import 'package:airway/core/storage/secure_session_storage.dart';
import 'package:airway/features/booking/data/booking_models.dart';

class BookingApi {
  BookingApi._();

  static Future<dynamic> request(
    String path, {
    String method = 'GET',
    Map<String, dynamic>? data,
    Set<int> acceptedStatusCodes = const {},
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

    if ((result.status < 200 || result.status >= 300) &&
        !acceptedStatusCodes.contains(result.status)) {
      throw Exception(
        'AIRway request failed (${result.status}): ${result.body}',
      );
    }

    return result.body;
  }


  static Future<Map<String, dynamic>> getCart() async {
    final result = await request('/api/v1/bookings/cart/');
    return Map<String, dynamic>.from(result);
  }

  static Future<Map<String, dynamic>> addCartItem({
    required int serviceId,
    int? variantId,
    int quantity = 1,
    required List<Map<String, dynamic>> addonSelections,
    required Map<String, dynamic> formAnswers,
    Map<String, dynamic> categoryAnswers = const {},
  }) async {
    final data = <String, dynamic>{
      'service': serviceId,
      'quantity': quantity,
      'addon_selections': addonSelections,
      'form_answers': formAnswers,
      'category_answers': categoryAnswers,
    };
    if (variantId != null) data['variant'] = variantId;
    final result = await request(
      '/api/v1/bookings/cart/',
      method: 'POST',
      data: data,
    );
    return Map<String, dynamic>.from(result);
  }

  static Future<Map<String, dynamic>> updateCartAddress(int? addressId) async {
    final result = await request(
      '/api/v1/bookings/cart/',
      method: 'PATCH',
      data: {'address_id': addressId},
    );
    return Map<String, dynamic>.from(result);
  }

  static Future<Map<String, dynamic>> updateCartItem({
    required int itemId,
    required Map<String, dynamic> data,
  }) async {
    final result = await request(
      '/api/v1/bookings/cart/items/$itemId/',
      method: 'PATCH',
      data: data,
    );
    return Map<String, dynamic>.from(result);
  }

  static Future<Map<String, dynamic>> deleteCartItem(int itemId) async {
    final result = await request(
      '/api/v1/bookings/cart/items/$itemId/',
      method: 'DELETE',
    );
    return Map<String, dynamic>.from(result);
  }

  static Future<Map<String, dynamic>> checkoutCart({
    required List<Map<String, dynamic>> items,
  }) async {
    final result = await request(
      '/api/v1/bookings/cart/checkout/',
      method: 'POST',
      data: {
        'items': items,
        // Opt the migrated Flutter cart into the server-gated 50/50 lifecycle.
        // Older clients that omit this version flag retain legacy checkout.
        'payment_flow': 'split_v1',
      },
    );
    return Map<String, dynamic>.from(result);
  }

  static Future<Booking> createBooking({
    required int serviceId,
    int? variantId,
    required String bookingMode,
    required DateTime scheduledAt,
    DateTime? dropScheduledAt,
    required int addressId,
    List<int>? addonIds,
    Map<String, dynamic>? formResponses,
    String? notes,
  }) async {
    final data = <String, dynamic>{
      'service': serviceId,
      'booking_mode': bookingMode,
      'scheduled_at': scheduledAt.toUtc().toIso8601String(),
      'address_id': addressId,
    };

    if (variantId != null) {
      data['variant'] = variantId;
    }
    if (dropScheduledAt != null) {
      data['drop_scheduled_at'] = dropScheduledAt.toUtc().toIso8601String();
    }
    if (addonIds != null && addonIds.isNotEmpty) {
      data['addon_ids'] = addonIds;
    }
    if (formResponses != null && formResponses.isNotEmpty) {
      data['form_responses'] = formResponses;
    }
    if (notes != null && notes.isNotEmpty) {
      data['notes'] = notes;
    }

    final result = await request(
      '/api/v1/bookings/',
      method: 'POST',
      data: data,
    );

    return Booking.fromMap(Map<String, dynamic>.from(result));
  }

  static Future<List<Booking>> listBookings({String? status}) async {
    var path = '/api/v1/bookings/';
    if (status != null) {
      path += '?status=$status';
    }

    final result = await request(path);
    final list = result is List
        ? result
        : (result is Map ? result['results'] : null);

    if (list is! List) throw const FormatException('Unexpected booking list response');

    return list
        .whereType<Map>()
        .map((e) => Booking.fromMap(Map<String, dynamic>.from(e)))
        .toList();
  }

  static Future<List<Map<String, dynamic>>> listOrders() async {
    final result = await request('/api/v1/bookings/orders/');
    final list = result is List ? result : (result is Map ? result['results'] : null);
    if (list is! List) throw const FormatException('Unexpected order list response');
    return list.whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList();
  }

  static Future<Map<String, dynamic>> trackBooking(int bookingId) async {
    final result = await request('/api/v1/bookings/$bookingId/track/');
    return Map<String, dynamic>.from(result);
  }

  static Future<Map<String, dynamic>> requestServiceOtp(
    int bookingId, {
    required String purpose,
  }) async {
    final result = await request(
      '/api/v1/bookings/$bookingId/service-otp/',
      method: 'POST',
      data: {'purpose': purpose},
    );
    return Map<String, dynamic>.from(result);
  }

  static Future<Booking> getBooking(int id) async {
    final result = await request('/api/v1/bookings/$id/');
    return Booking.fromMap(Map<String, dynamic>.from(result));
  }

  static Future<void> cancelBooking(int id, {String? reason}) async {
    final data = <String, dynamic>{};
    if (reason != null && reason.isNotEmpty) {
      data['reason'] = reason;
    }

    await request(
      '/api/v1/bookings/$id/cancel/',
      method: 'POST',
      data: data,
    );
  }

  static Future<Map<String, dynamic>> createRazorpayOrder(int bookingId) async {
    final result = await request(
      '/api/v1/payments/create-order/',
      method: 'POST',
      data: {'booking_id': bookingId},
    );

    return Map<String, dynamic>.from(result);
  }

  static Future<Map<String, dynamic>> checkSlotAvailability({
    required int serviceId,
    required DateTime scheduledAt,
    DateTime? dropScheduledAt,
    int? variantId,
    int? addressId,
    int quantity = 1,
    String bookingMode = 'scheduled',
    Map<String, dynamic> categoryAnswers = const {},
  }) async {
    final data = {
      'service': serviceId,
      'category_answers': categoryAnswers,
      'scheduled_at': scheduledAt.toUtc().toIso8601String(),
      'booking_mode': bookingMode,
      'quantity': quantity,
    };
    if (addressId != null) data['address_id'] = addressId;

    if (dropScheduledAt != null) {
      data['drop_scheduled_at'] = dropScheduledAt.toUtc().toIso8601String();
    }
    if (variantId != null) {
      data['variant_id'] = variantId;
    }

    final result = await request(
      '/api/v1/bookings/check_availability/',
      method: 'POST',
      data: data,
      acceptedStatusCodes: const {409},
    );

    return Map<String, dynamic>.from(result);
  }
}