import 'dart:convert';
import 'dart:io';

import 'package:airway/core/network/auth_api.dart';
import 'package:airway/core/storage/secure_session_storage.dart';
import 'package:airway/features/wallet/data/wallet_models.dart';

class WalletApi {
  WalletApi._();

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
    return result;
  }

  static Future<WalletModel> fetchBalance() async {
    final result = await request('/api/v1/wallet/balance/');
    if (result.status != 200) {
      throw Exception(_errorMessage(result.body, 'Could not load balance.'));
    }
    return WalletModel.fromMap(result.body as Map<String, dynamic>);
  }

  static Future<List<WalletTransactionModel>> fetchTransactions() async {
    final result = await request('/api/v1/wallet/transactions/');
    if (result.status != 200) {
      throw Exception(_errorMessage(result.body, 'Could not load transactions.'));
    }
    final list = result.body as List<dynamic>;
    return list
        .map((e) => WalletTransactionModel.fromMap(e as Map<String, dynamic>))
        .toList();
  }

  static Future<WalletTransactionModel> topUp({
    required double amount,
    String? referenceId,
  }) async {
    final result = await request(
      '/api/v1/wallet/top-up/',
      method: 'POST',
      data: {
        'amount': amount,
        if (referenceId != null) 'reference_id': referenceId,
      },
    );
    if (result.status != 201) {
      throw Exception(_errorMessage(result.body, 'Top-up failed.'));
    }
    return WalletTransactionModel.fromMap(result.body as Map<String, dynamic>);
  }

  static Future<WalletTransactionModel> confirmTopUp({
    required int transactionId,
    String? razorpayPaymentId,
  }) async {
    final result = await request(
      '/api/v1/wallet/top-up/$transactionId/confirm/',
      method: 'POST',
      data: {
        if (razorpayPaymentId != null) 'razorpay_payment_id': razorpayPaymentId,
      },
    );
    if (result.status != 200) {
      throw Exception(_errorMessage(result.body, 'Top-up confirmation failed.'));
    }
    return WalletTransactionModel.fromMap(result.body as Map<String, dynamic>);
  }

  static String _errorMessage(dynamic body, String fallback) {
    if (body is Map<String, dynamic>) {
      final detail = body['detail'];
      if (detail is String) return detail;
    }
    return fallback;
  }
}