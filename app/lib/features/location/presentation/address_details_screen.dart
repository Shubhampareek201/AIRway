import 'package:flutter/material.dart';
import 'package:airway/features/location/data/location_api.dart';

/// Shared form for both adding and editing an AIRway address.
class AddressDetailsScreen extends StatefulWidget {
  const AddressDetailsScreen({
    super.key,
    required this.latitude,
    required this.longitude,
    required this.address,
    this.existingAddress,
  });

  final double latitude;
  final double longitude;
  final String address;
  final Map<String, dynamic>? existingAddress;

  @override
  State<AddressDetailsScreen> createState() => _AddressDetailsScreenState();
}

class _AddressDetailsScreenState extends State<AddressDetailsScreen> {
  final _formKey = GlobalKey<FormState>();
  late final TextEditingController _house;
  late final TextEditingController _landmark;
  late final TextEditingController _fullAddress;

  List<Map<String, dynamic>> _cities = [];
  List<Map<String, dynamic>> _zones = [];
  int? _cityId;
  int? _zoneId;
  String _label = 'home';
  bool _loading = true;
  bool _saving = false;
  String? _error;

  bool get _editing => widget.existingAddress != null;

  int? _toInt(Object? value) => value is int ? value : int.tryParse('$value');

  @override
  void initState() {
    super.initState();
    final existing = widget.existingAddress ?? {};
    _house = TextEditingController(text: '${existing['house_details'] ?? ''}');
    _landmark = TextEditingController(text: '${existing['landmark'] ?? ''}');
    _fullAddress = TextEditingController(
      text: '${existing['full_address'] ?? widget.address}',
    );
    final storedLabel = '${existing['label'] ?? 'home'}';
    _label = const ['home', 'work', 'other'].contains(storedLabel)
        ? storedLabel
        : 'other';
    _zoneId = _toInt(existing['zone']);
    _cityId = _toInt(existing['city']);
    _loadCitiesAndZones();
  }

  List<Map<String, dynamic>> _records(dynamic response) {
    final list = response is List
        ? response
        : response is Map
            ? response['results']
            : null;
    if (list is! List) throw const FormatException('Invalid service area list.');
    return list.map((e) => Map<String, dynamic>.from(e as Map)).toList();
  }

  Future<void> _loadCitiesAndZones() async {
    try {
      final cities = _records(await LocationApi.cities());
      if (!mounted) return;
      // When editing, infer the city from the saved zone if city is not
      // directly present in the response. Users can still change it.
      setState(() {
        _cities = cities;
        if (_cityId != null && !cities.any((c) => _toInt(c['id']) == _cityId)) {
          _cityId = null;
        }
      });
      if (_cityId != null) {
        final zones = _records(await LocationApi.zones(_cityId!));
        if (!mounted) return;
        setState(() => _zones = zones);
      } else if (_editing && _zoneId != null) {
        for (final city in cities) {
          final id = _toInt(city['id']);
          if (id == null) continue;
          final zones = _records(await LocationApi.zones(id));
          if (!mounted) return;
          if (zones.any((z) => _toInt(z['id']) == _zoneId)) {
            setState(() { _cityId = id; _zones = zones; });
            break;
          }
        }
      }
    } catch (e) {
      if (mounted) setState(() => _error = 'Could not load service areas: $e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _selectCity(int? cityId) async {
    setState(() {
      _cityId = cityId;
      _zoneId = null;
      _zones = [];
      _error = null;
      _loading = cityId != null;
    });
    if (cityId == null) return;
    try {
      final zones = _records(await LocationApi.zones(cityId));
      if (!mounted || _cityId != cityId) return;
      setState(() => _zones = zones);
    } catch (e) {
      if (mounted) setState(() => _error = 'Could not load service areas: $e');
    } finally {
      if (mounted && _cityId == cityId) setState(() => _loading = false);
    }
  }

  Future<void> _save() async {
    if (_saving || _loading || !_formKey.currentState!.validate()) return;
    if (_zoneId == null) {
      setState(() => _error = 'Select your service area.');
      return;
    }
    setState(() { _saving = true; _error = null; });
    try {
      final data = <String, dynamic>{
        'label': _label,
        'house_details': _house.text.trim(),
        'landmark': _landmark.text.trim(),
        'full_address': _fullAddress.text.trim(),
        'zone': _zoneId,
      };
      Map<String, dynamic>? newAddress;
      if (_editing) {
        final id = _toInt(widget.existingAddress!['id']);
        if (id == null) throw const FormatException('Missing saved address ID.');
        await LocationApi.request(
          '/api/v1/auth/addresses/$id/',
          method: 'PATCH',
          data: data,
        );
      } else {
        data['latitude'] = widget.latitude.toStringAsFixed(6);
        data['longitude'] = widget.longitude.toStringAsFixed(6);
        newAddress = await LocationApi.saveAddress(data);
        final id = _toInt(newAddress['id']);
        if (id == null) {
          throw const FormatException('Address ID missing in save response.');
        }
        await LocationApi.request(
          '/api/v1/auth/addresses/$id/set-default/',
          method: 'POST',
        );
      }
      if (!mounted) return;
      Navigator.of(context).pop(true);
    } catch (e) {
      if (mounted) setState(() => _error = 'Could not save address: $e');
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  void dispose() {
    _house.dispose();
    _landmark.dispose();
    _fullAddress.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(_editing ? 'Edit address' : 'Complete address')),
      body: SafeArea(
        child: Form(
          key: _formKey,
          child: ListView(
            padding: const EdgeInsets.all(20),
            children: [
              Text(
                _editing ? 'Update your saved address' : 'Where should we provide the service?',
                style: const TextStyle(fontSize: 22, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 20),
              TextFormField(
                controller: _fullAddress,
                maxLines: 2,
                decoration: const InputDecoration(labelText: 'Full address'),
                validator: (v) => v == null || v.trim().isEmpty
                    ? 'Address is required' : null,
              ),
              const SizedBox(height: 14),
              TextFormField(
                controller: _house,
                decoration: const InputDecoration(labelText: 'House / Flat / Floor'),
                validator: (v) => v == null || v.trim().isEmpty
                    ? 'House details are required' : null,
              ),
              const SizedBox(height: 14),
              TextFormField(
                controller: _landmark,
                decoration: const InputDecoration(labelText: 'Nearby landmark'),
                validator: (v) => v == null || v.trim().isEmpty
                    ? 'Landmark is required' : null,
              ),
              const SizedBox(height: 14),
              DropdownButtonFormField<int>(
                key: ValueKey('city-$_cityId'),
                initialValue: _cityId,
                isExpanded: true,
                decoration: const InputDecoration(labelText: 'City'),
                items: _cities.map((city) => DropdownMenuItem<int>(
                  value: _toInt(city['id']),
                  child: Text('${city['name'] ?? ''}', overflow: TextOverflow.ellipsis),
                )).toList(),
                onChanged: _loading || _saving ? null : _selectCity,
              ),
              const SizedBox(height: 14),
              DropdownButtonFormField<int>(
                key: ValueKey('zone-$_cityId-$_zoneId'),
                initialValue: _zoneId != null &&
                        _zones.any((z) => _toInt(z['id']) == _zoneId)
                    ? _zoneId : null,
                isExpanded: true,
                decoration: const InputDecoration(labelText: 'Service area / Colony'),
                items: _zones.map((zone) => DropdownMenuItem<int>(
                  value: _toInt(zone['id']),
                  child: Text('${zone['name'] ?? ''}', overflow: TextOverflow.ellipsis),
                )).toList(),
                onChanged: _loading || _saving ? null : (v) => setState(() => _zoneId = v),
              ),
              const SizedBox(height: 18),
              const Text('Save as', style: TextStyle(fontWeight: FontWeight.w600)),
              const SizedBox(height: 10),
              SegmentedButton<String>(
                segments: const [
                  ButtonSegment(value: 'home', label: Text('Home')),
                  ButtonSegment(value: 'work', label: Text('Work')),
                  ButtonSegment(value: 'other', label: Text('Other')),
                ],
                selected: {_label},
                onSelectionChanged: _saving ? null : (values) => setState(() => _label = values.first),
              ),
              if (_loading) const Padding(
                padding: EdgeInsets.all(14),
                child: Center(child: CircularProgressIndicator()),
              ),
              if (_error != null) Padding(
                padding: const EdgeInsets.symmetric(vertical: 12),
                child: Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
              ),
              const SizedBox(height: 24),
              FilledButton(
                onPressed: _loading || _saving ? null : _save,
                child: Text(_saving ? 'Saving...' : _editing ? 'Update Address' : 'Save Address'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
