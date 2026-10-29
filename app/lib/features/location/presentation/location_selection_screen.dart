import 'dart:async';
import 'dart:math' show Point;
import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';
import 'package:latlong2/latlong.dart' as ll;
import 'package:maplibre_gl/maplibre_gl.dart' as ml;

import 'package:airway/core/theme/airway_theme.dart';
import 'package:airway/features/location/data/location_api.dart';
import 'package:airway/features/location/presentation/address_details_screen.dart';
import 'package:airway/features/location/presentation/address_picker_screen.dart';
import 'package:airway/features/customer/presentation/customer_home_screen.dart';

class LocationSelectionScreen extends StatefulWidget {
  const LocationSelectionScreen({super.key, this.initialLocation});

  final ll.LatLng? initialLocation;

  @override
  State<LocationSelectionScreen> createState() =>
      _LocationSelectionScreenState();
}

class _LocationSelectionScreenState extends State<LocationSelectionScreen> {
  // Starting map view only; this is NOT the customer's saved location.
  static const ml.LatLng _initialLocation = ml.LatLng(24.930000, 75.590000);
  static const String _mapStyle =
      'https://tiles.openfreemap.org/styles/liberty';

  ml.MapLibreMapController? _mapController;
  ml.LatLng _selectedLocation = _initialLocation;

  @override
  void initState() {
    super.initState();
    if (widget.initialLocation != null) {
      _selectedLocation = ml.LatLng(
        widget.initialLocation!.latitude,
        widget.initialLocation!.longitude,
      );
    }
  }

  String _selectedAddress = '';
  String? _addressError;
  bool _addressLoading = false;
  bool _detectingLocation = false;
  bool _mapReady = false;
  bool _openingAddressForm = false;
  int _lookupVersion = 0;
  Timer? _addressDebounce;
  double _zoom = 14;

  void _scheduleAddressLookup() {
    _addressDebounce?.cancel();
    final version = ++_lookupVersion;
    if (!mounted || !_mapReady) return;
    setState(() {
      _addressLoading = true;
      _selectedAddress = '';
      _addressError = null;
    });
    _addressDebounce = Timer(const Duration(seconds: 2), () {
      if (!mounted || version != _lookupVersion) return;
      _updateSelectedAddress();
    });
  }

  Future<void> _updateSelectedAddress() async {
    if (!_mapReady || !mounted) return;

    final version = ++_lookupVersion;
    final latitude = _selectedLocation.latitude;
    final longitude = _selectedLocation.longitude;

    try {
      final result = await LocationApi.reverse(latitude, longitude);
      if (!mounted || version != _lookupVersion) return;

      setState(() {
        _selectedAddress = (result['formatted'] ?? '').toString().trim();
        _addressLoading = false;
        _addressError = null;
      });
    } catch (error) {
      if (!mounted || version != _lookupVersion) return;
      setState(() {
        _selectedAddress = '';
        _addressLoading = false;
        _addressError = 'Address lookup failed. Move the map or check the connection.';
      });
    }
  }

  Future<void> _moveMap(ml.LatLng position, {double zoom = 17}) async {
    final controller = _mapController;
    if (controller == null || !_mapReady) return;

    await controller.animateCamera(
      ml.CameraUpdate.newLatLngZoom(position, zoom),
    );
    if (!mounted) return;

    // onCameraIdle schedules reverse geocoding after map movement stops.
    setState(() {
      _selectedLocation = position;
      _zoom = zoom;
    });
  }

  Future<void> _useCurrentLocation() async {
    if (_detectingLocation) return;
    setState(() => _detectingLocation = true);

    try {
      if (!await Geolocator.isLocationServiceEnabled()) {
        throw Exception('Please turn on Location in your phone settings.');
      }

      var permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
      }
      if (permission == LocationPermission.deniedForever) {
        throw Exception(
          'Enable location permission in AIRway app settings, '
          'or use address search.',
        );
      }
      if (permission == LocationPermission.denied) {
        throw Exception('Location permission denied. Try address search.');
      }

      final position = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.high,
          timeLimit: Duration(seconds: 20),
        ),
      );
      if (!mounted) return;

      await _moveMap(ml.LatLng(position.latitude, position.longitude));
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(error.toString().replaceFirst('Exception: ', '')),
        ),
      );
    } finally {
      if (mounted) setState(() => _detectingLocation = false);
    }
  }

  Future<void> _searchAddress() async {
    final result = await Navigator.of(context).push<AddressPickerResult>(
      MaterialPageRoute(
        builder: (_) => AddressPickerScreen(
          mapCenter: ll.LatLng(
            _selectedLocation.latitude,
            _selectedLocation.longitude,
          ),
        ),
      ),
    );
    if (!mounted || result == null) return;
    if (result.savedAddress != null) {
      _openHome();
      return;
    }
    final point = result.location;
    if (point != null) {
      await _moveMap(ml.LatLng(point.latitude, point.longitude));
    }
  }

  Future<void> _changeZoom(double difference) async {
    final controller = _mapController;
    if (controller == null || !_mapReady) return;

    final newZoom = (_zoom + difference).clamp(3.0, 19.0).toDouble();
    await controller.animateCamera(
      ml.CameraUpdate.newLatLngZoom(_selectedLocation, newZoom),
    );
    if (mounted) setState(() => _zoom = newZoom);
  }

  Future<void> _confirmLocation() async {
    if (!_mapReady || _addressLoading || _openingAddressForm) return;

    setState(() => _openingAddressForm = true);
    try {
      final saved = await Navigator.of(context).push<bool>(
        MaterialPageRoute(
          builder: (_) => AddressDetailsScreen(
            latitude: _selectedLocation.latitude,
            longitude: _selectedLocation.longitude,
            address: _selectedAddress,
          ),
        ),
      );

      if (!mounted) return;
      if (saved == true) {
        _openHome();
      }
    } finally {
      if (mounted) setState(() => _openingAddressForm = false);
    }
  }

  void _openHome() {
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute(builder: (_) => const CustomerHomeScreen()),
      (route) => false,
    );
  }

  Widget _mapControl({
    required IconData icon,
    required VoidCallback? onPressed,
    required String tooltip,
  }) {
    return Material(
      color: Colors.white,
      elevation: 3,
      borderRadius: BorderRadius.circular(14),
      child: IconButton(
        tooltip: tooltip,
        onPressed: onPressed,
        icon: Icon(icon, color: AirwayColors.text),
      ),
    );
  }

  @override
  void dispose() {
    _lookupVersion++;
    _addressDebounce?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Stack(
          children: [
            Positioned.fill(
              child: ml.MapLibreMap(
                styleString: _mapStyle,
                initialCameraPosition: ml.CameraPosition(
                  target: _selectedLocation,
                  zoom: widget.initialLocation == null ? 14 : 17,
                ),
                onMapCreated: (controller) {
                  _mapController = controller;
                },
                onStyleLoadedCallback: () {
                  if (!mounted) return;
                  setState(() => _mapReady = true);
                  _scheduleAddressLookup();
                },
                onCameraMove: (position) {
                  _selectedLocation = position.target;
                  _zoom = position.zoom;
                  // Invalidate any in-flight lookup as soon as the pin moves.
                  _lookupVersion++;
                  _addressDebounce?.cancel();
                },
                onCameraIdle: () async {
                  final controller = _mapController;
                  if (!mounted || !_mapReady || controller == null) return;
                  try {
                    final screenSize = MediaQuery.sizeOf(context);
                    final actualCenter = await controller.toLatLng(
                      Point<double>(screenSize.width / 2, screenSize.height / 2),
                    );
                    if (!mounted) return;
                    _selectedLocation = actualCenter;
                    _scheduleAddressLookup();
                  } catch (_) {
                    // An occasional map projection failure should not block
                    // manual search or address confirmation.
                    if (mounted) _scheduleAddressLookup();
                  }
                },
              ),
            ),

            // The pin's pointed tip indicates the map's camera center.
            Center(
              child: IgnorePointer(
                child: Transform.translate(
                  offset: const Offset(0, -24),
                  child: const Icon(
                    Icons.location_on,
                    size: 48,
                    color: AirwayColors.primary,
                    shadows: [
                      Shadow(blurRadius: 10, color: Colors.black26),
                    ],
                  ),
                ),
              ),
            ),

            Positioned(
              top: 16,
              left: 16,
              right: 16,
              child: Material(
                elevation: 4,
                color: Colors.white,
                borderRadius: BorderRadius.circular(18),
                child: InkWell(
                  onTap: _searchAddress,
                  borderRadius: BorderRadius.circular(18),
                  child: const Padding(
                    padding: EdgeInsets.all(17),
                    child: Row(
                      children: [
                        Icon(Icons.search, color: AirwayColors.primary),
                        SizedBox(width: 12),
                        Expanded(
                          child: Text(
                            'Search or choose a saved address',
                            style: TextStyle(color: AirwayColors.text),
                          ),
                        ),
                        Icon(Icons.chevron_right, color: AirwayColors.muted),
                      ],
                    ),
                  ),
                ),
              ),
            ),

            Positioned(
              right: 16,
              bottom: 232,
              child: Column(
                children: [
                  _mapControl(
                    icon: Icons.my_location,
                    tooltip: 'Use current location',
                    onPressed: _mapReady && !_detectingLocation
                        ? _useCurrentLocation
                        : null,
                  ),
                  const SizedBox(height: 10),
                  _mapControl(
                    icon: Icons.add,
                    tooltip: 'Zoom in',
                    onPressed:
                        _mapReady ? () => _changeZoom(1) : null,
                  ),
                  const SizedBox(height: 8),
                  _mapControl(
                    icon: Icons.remove,
                    tooltip: 'Zoom out',
                    onPressed:
                        _mapReady ? () => _changeZoom(-1) : null,
                  ),
                ],
              ),
            ),

            Positioned(
              left: 0,
              right: 0,
              bottom: 0,
              child: Container(
                padding: const EdgeInsets.fromLTRB(20, 20, 20, 20),
                decoration: const BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.vertical(
                    top: Radius.circular(26),
                  ),
                  boxShadow: [
                    BoxShadow(blurRadius: 20, color: Color(0x18000000)),
                  ],
                ),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'Confirm your location',
                      style: TextStyle(
                        fontSize: 20,
                        fontWeight: FontWeight.bold,
                        color: AirwayColors.text,
                      ),
                    ),
                    const SizedBox(height: 10),
                    if (_addressLoading)
                      const Row(
                        children: [
                          SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          ),
                          SizedBox(width: 12),
                          Expanded(child: Text('Finding your address...')),
                        ],
                      )
                    else
                      Text(
                        _selectedAddress.isEmpty
                            ? (_addressError ?? 'Address unavailable. You can enter it in the next step.')
                            : _selectedAddress,
                        maxLines: 3,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          color: AirwayColors.text,
                          fontSize: 14,
                        ),
                      ),
                    const SizedBox(height: 8),
                    const SizedBox(height: 8),
                    SizedBox(
                      width: double.infinity,
                      child: FilledButton(
                        onPressed: _mapReady &&
                                !_addressLoading &&
                                !_openingAddressForm
                            ? _confirmLocation
                            : null,
                        child: const Text('Confirm location'),
                      ),
                    ),
                  ],
                ),
              ),
            ),

            const Positioned(
              left: 8,
              bottom: 213,
              child: Text(
                '© OpenStreetMap contributors',
                style: TextStyle(
                  fontSize: 10,
                  backgroundColor: Colors.white70,
                  color: Colors.black87,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
