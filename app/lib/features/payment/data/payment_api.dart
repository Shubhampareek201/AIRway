import 'dart:convert';
import 'dart:io';
import 'package:airway/core/network/auth_api.dart';
import 'package:airway/core/storage/secure_session_storage.dart';

class PaymentApi {
  PaymentApi._();

  static Future<Map<String, dynamic>> _request(
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
    return Map<String, dynamic>.from(result.body as Map);
  }

  static Future<Map<String, dynamic>> createOrderForParent(
    int orderId, {
    String walletAmount = '0.00',
  }) async {
    return _request(
      '/api/v1/payments/create-order/',
      method: 'POST',
      data: {'order_id': orderId, 'wallet_amount': walletAmount},
    );
  }

  static Future<Map<String, dynamic>> verifyPayment({
    required String razorpayOrderId,
    required String razorpayPaymentId,
    required String razorpaySignature,
  }) async {
    final result = await _request(
      '/api/v1/payments/verify/',
      method: 'POST',
      data: {
        'razorpay_order_id': razorpayOrderId,
        'razorpay_payment_id': razorpayPaymentId,
        'razorpay_signature': razorpaySignature,
      },
    );

    return Map<String, dynamic>.from(result);
  }

  static Future<Map<String, dynamic>> createFinalBalanceOrder(
    int bookingId, {
    String walletAmount = '0.00',
  }) async {
    final result = await _request(
      '/api/v1/payments/final-balance/create-order/',
      method: 'POST',
      data: {'booking_id': bookingId, 'wallet_amount': walletAmount},
    );
    return Map<String, dynamic>.from(result);
  }

  static Future<Map<String, dynamic>> verifyFinalBalancePayment({
    required String razorpayOrderId,
    required String razorpayPaymentId,
    required String razorpaySignature,
  }) async {
    final result = await _request(
      '/api/v1/payments/final-balance/verify/',
      method: 'POST',
      data: {
        'razorpay_order_id': razorpayOrderId,
        'razorpay_payment_id': razorpayPaymentId,
        'razorpay_signature': razorpaySignature,
      },
    );
    return Map<String, dynamic>.from(result);
  }

  static Future<Map<String, dynamic>> getPaymentStatus(int bookingId) async {
    final result = await _request('/api/v1/bookings/$bookingId/');
    return Map<String, dynamic>.from(result);
  }
}