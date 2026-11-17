import 'package:airway/features/location/data/location_api.dart';

class FavoriteApi {
  FavoriteApi._();

  static Future<List<Map<String, dynamic>>> listFavorites() async {
    final result = await LocationApi.request('/api/v1/auth/favorites/');
    final raw = result is List
        ? result
        : result is Map
            ? result['results']
            : null;
    if (raw is! List) {
      throw const FormatException('Unexpected favorites response.');
    }
    return raw
        .whereType<Map>()
        .map((item) => Map<String, dynamic>.from(item))
        .toList();
  }

  static Future<int?> favoriteIdForService(int serviceId) async {
    final result = await LocationApi.request(
      '/api/v1/auth/favorites/?service_id=$serviceId',
    );
    final raw = result is List
        ? result
        : result is Map
            ? result['results']
            : null;
    if (raw is! List || raw.isEmpty || raw.first is! Map) return null;
    return int.tryParse('${raw.first['id']}');
  }

  static Future<Map<String, dynamic>> addFavorite(int serviceId) async {
    final result = await LocationApi.request(
      '/api/v1/auth/favorites/',
      method: 'POST',
      data: {'service_id': serviceId},
    );
    if (result is! Map) {
      throw const FormatException('Unexpected favorite response.');
    }
    return Map<String, dynamic>.from(result);
  }

  static Future<void> removeFavorite(int favoriteId) async {
    await LocationApi.request(
      '/api/v1/auth/favorites/$favoriteId/',
      method: 'DELETE',
    );
  }
}
