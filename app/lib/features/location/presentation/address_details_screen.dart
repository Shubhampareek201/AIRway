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

  String _label = 'home';
  bool _loading = false;
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
    // Zone is resolved by the backend from the confirmed map coordinates.
  }

  Future<void> _save() async {
    if (_saving || _loading || !_formKey.currentState!.validate()) return;
    setState(() { _saving = true; _error = null; });
    try {
      final data = <String, dynamic>{
        'label': _label,
        'house_details': _house.text.trim(),
        'landmark': _landmark.text.trim(),
        'full_address': _fullAddress.text.trim(),
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
              const Text(
                'AIRway checks service availability automatically from your selected map location.',
                style: TextStyle(color: Colors.grey),
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
