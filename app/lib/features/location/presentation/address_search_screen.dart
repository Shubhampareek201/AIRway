
import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:latlong2/latlong.dart';

import 'package:airway/core/network/auth_api.dart';
import 'package:airway/core/storage/secure_session_storage.dart';

class AddressSearchScreen extends StatefulWidget {
  const AddressSearchScreen({
    super.key,
    required this.mapCenter,
  });

  final LatLng mapCenter;

  @override
  State<AddressSearchScreen> createState() =>
      _AddressSearchScreenState();
}

class _Place {
  const _Place({
    required this.name,
    required this.type,
    this.latitude,
    this.longitude,
  });

  final String name;
  final String type;
  final double? latitude;
  final double? longitude;

  bool get hasLocation =>
      latitude != null && longitude != null;
}

class _AddressSearchScreenState
    extends State<AddressSearchScreen> {
  final _controller = TextEditingController();
  Timer? _debounce;
  int _searchVersion = 0;

  List<_Place> _places = [];
  bool _loading = false;
  String? _error;

  void _onQueryChanged(String value) {
    _debounce?.cancel();
    final version = ++_searchVersion;
    final query = value.trim();

    if (query.length < 2) {
      setState(() {
        _places = [];
        _loading = false;
        _error = null;
      });
      return;
    }

    setState(() {
      _loading = true;
      _error = null;
    });

    _debounce = Timer(
      const Duration(milliseconds: 550),
      () => _search(query, version),
    );
  }

  Future<Map<String, dynamic>> _getJson(
    String path,
    String token,
  ) async {
    final client = HttpClient()
      ..connectionTimeout = const Duration(seconds: 8);

    try {
      final request = await client.getUrl(
        Uri.parse('${AuthApi.baseUrl}$path'),
      );

      request.headers.set(
        HttpHeaders.authorizationHeader,
        'Bearer $token',
      );

      final response = await request.close().timeout(
        const Duration(seconds: 12),
      );

      final body = await utf8.decoder.bind(response).join();

      if (response.statusCode == 401) {
        throw const HttpException('Session expired');
      }

      if (response.statusCode != 200) {
        throw HttpException(
          'Search unavailable (${response.statusCode})',
        );
      }

      final decoded = jsonDecode(body);

      if (decoded is! Map<String, dynamic>) {
        throw const FormatException('Invalid search response');
      }

      return decoded;
    } finally {
      client.close(force: true);
    }
  }

  Future<List<_Place>> _fetchPlaces(
    String path,
    String token,
  ) async {
    final data = await _getJson(path, token);
    final results = data['results'];

    if (results is! List) return [];

    final places = <_Place>[];

    for (final item in results) {
      if (item is! Map) continue;

      final name = (item['display_name'] ??
              item['name'] ??
              '')
          .toString();

      if (name.trim().isEmpty) continue;

      final lat = double.tryParse(
        item['latitude']?.toString() ?? '',
      );
      final lon = double.tryParse(
        item['longitude']?.toString() ?? '',
      );

      places.add(
        _Place(
          name: name,
          type: (item['type'] ?? 'external').toString(),
          latitude: lat,
          longitude: lon,
        ),
      );
    }

    return places;
  }

  Future<void> _search(
    String query,
    int version,
  ) async {
    try {
      var session = await SecureSessionStorage.readSession();

      if (session == null) {
        throw const HttpException('Please log in again.');
      }

      final localPath =
          '/api/v1/auth/locations/search/'
          '?q=${Uri.encodeQueryComponent(query)}';

      final externalPath =
          '/api/v1/auth/locations/autocomplete/'
          '?q=${Uri.encodeQueryComponent(query)}'
          '&lat=${widget.mapCenter.latitude}'
          '&lon=${widget.mapCenter.longitude}';

      // Try both providers independently, so one failure
      // does not hide all the results.
      Future<List<_Place>> load(String path) async {
        try {
          return await _fetchPlaces(
            path,
            session!.accessToken,
          );
        } on HttpException catch (error) {
          if (error.message != 'Session expired') rethrow;

          final refreshed = await AuthApi.refreshSession(
            refreshToken: session!.refreshToken,
          );

          if (refreshed == null) {
            throw const HttpException('Please log in again.');
          }

          final access = refreshed['access'] as String;
          final refresh =
              refreshed['refresh'] as String? ??
              session!.refreshToken;

          await SecureSessionStorage.saveSession(
            accessToken: access,
            refreshToken: refresh,
          );

          session = await SecureSessionStorage.readSession();

          return _fetchPlaces(path, access);
        }
      }

      final responses = await Future.wait([
        load(localPath).catchError(
          (Object _) => <_Place>[],
        ),
        load(externalPath).catchError(
          (Object _) => <_Place>[],
        ),
      ]);

      if (!mounted || version != _searchVersion) return;

      final combined = <_Place>[
        ...responses[0],
        ...responses[1],
      ];

      final seen = <String>{};
      final unique = combined.where((place) {
        final key = place.name.trim().toLowerCase();
        return seen.add(key);
      }).toList();

      setState(() {
        _places = unique;
        _loading = false;
        _error = unique.isEmpty
            ? 'No matching places found. Try a nearby area.'
            : null;
      });
    } catch (_) {
      if (!mounted || version != _searchVersion) return;

      setState(() {
        _loading = false;
        _error = 'Unable to search locations. Try again.';
      });
    }
  }

  void _selectPlace(_Place place) {
    if (!place.hasLocation) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
            'This locality is registered in AIRway, '
            'but its map pin is not configured yet. '
            'Use GPS or select the location on the map.',
          ),
        ),
      );
      return;
    }

    Navigator.pop(
      context,
      LatLng(place.latitude!, place.longitude!),
    );
  }

  @override
  void dispose() {
    _searchVersion++;
    _debounce?.cancel();
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final color = Theme.of(context).colorScheme.primary;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Search location'),
      ),
      body: SafeArea(
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.all(16),
              child: TextField(
                controller: _controller,
                autofocus: true,
                onChanged: _onQueryChanged,
                decoration: InputDecoration(
                  hintText: 'Search area, address or PIN',
                  prefixIcon: const Icon(Icons.search),
                  suffixIcon: IconButton(
                    onPressed: () {
                      _controller.clear();
                      _onQueryChanged('');
                    },
                    icon: const Icon(Icons.close),
                  ),
                ),
              ),
            ),

            if (_loading)
              const LinearProgressIndicator(),

            Expanded(
              child: _places.isNotEmpty
                  ? ListView.separated(
                      itemCount: _places.length,
                      separatorBuilder: (_, _) =>
                          const Divider(height: 1),
                      itemBuilder: (context, index) {
                        final place = _places[index];

                        return ListTile(
                          leading: Icon(
                            place.type == 'zone'
                                ? Icons.home_work_outlined
                                : Icons.location_on_outlined,
                            color: color,
                          ),
                          title: Text(place.name),
                          subtitle: place.hasLocation
                              ? null
                              : const Text(
                                  'Map pin not configured',
                                ),
                          trailing:
                              const Icon(Icons.chevron_right),
                          onTap: () => _selectPlace(place),
                        );
                      },
                    )
                  : Center(
                      child: Padding(
                        padding: const EdgeInsets.all(24),
                        child: Text(
                          _error ??
                              'Start typing to see nearby '
                                  'and matching locations.',
                          textAlign: TextAlign.center,
                        ),
                      ),
                    ),
            ),
          ],
        ),
      ),
    );
  }
}
