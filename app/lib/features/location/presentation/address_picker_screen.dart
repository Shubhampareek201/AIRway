import 'package:flutter/material.dart';
import 'package:latlong2/latlong.dart' as ll;
import 'package:share_plus/share_plus.dart';

import 'package:airway/features/location/data/location_api.dart';
import 'package:airway/features/location/presentation/address_search_screen.dart';
import 'package:airway/features/location/presentation/address_details_screen.dart';

/// A search result moves the map; a saved address opens the customer home.
class AddressPickerResult {
  const AddressPickerResult.search(this.location) : savedAddress = null;
  const AddressPickerResult.saved(this.savedAddress) : location = null;
  final ll.LatLng? location;
  final Map<String, dynamic>? savedAddress;
}

class AddressPickerScreen extends StatefulWidget {
  const AddressPickerScreen({super.key, required this.mapCenter});
  final ll.LatLng mapCenter;

  @override
  State<AddressPickerScreen> createState() => _AddressPickerScreenState();
}

class _AddressPickerScreenState extends State<AddressPickerScreen> {
  List<Map<String, dynamic>> _addresses = [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  List<Map<String, dynamic>> _asAddresses(dynamic raw) {
    final data = raw is List ? raw : (raw is Map ? raw['results'] : null);
    if (data is! List) throw const FormatException('Invalid address list.');
    return data.map((e) => Map<String, dynamic>.from(e as Map)).toList();
  }

  Future<void> _load() async {
    if (!mounted) return;
    setState(() { _loading = true; _error = null; });
    try {
      final response = await LocationApi.request('/api/v1/auth/addresses/');
      if (!mounted) return;
      setState(() => _addresses = _asAddresses(response));
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  String _display(Map<String, dynamic> address) {
    final parts = [address['house_details'], address['full_address'], address['landmark']]
        .where((value) => value != null && value.toString().trim().isNotEmpty)
        .map((value) => value.toString().trim());
    return parts.join(', ');
  }

  Future<void> _pick(Map<String, dynamic> address) async {
    final lat = double.tryParse('${address['latitude']}');
    final lon = double.tryParse('${address['longitude']}');
    if (lat == null || lon == null || !lat.isFinite || !lon.isFinite) {
      _notice('This address has no valid map pin. Edit its location first.');
      return;
    }
    try {
      // Choosing an address makes it the default for future app launches.
      await LocationApi.request(
        '/api/v1/auth/addresses/${address['id']}/set-default/',
        method: 'POST',
      );
      if (!mounted) return;
      Navigator.of(context).pop(AddressPickerResult.saved(address));
    } catch (e) {
      _notice('Unable to select saved address: $e');
    }
  }

  void _notice(String text) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));
  }

  Future<void> _setDefault(Map<String, dynamic> address) async {
    try {
      await LocationApi.request(
        '/api/v1/auth/addresses/${address['id']}/set-default/',
        method: 'POST',
      );
      await _load();
    } catch (e) { _notice('Could not set default: $e'); }
  }

  Future<void> _delete(Map<String, dynamic> address) async {
    final yes = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Delete saved address?'),
        content: Text(_display(address)),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Delete')),
        ],
      ),
    );
    if (yes != true) return;
    try {
      await LocationApi.request('/api/v1/auth/addresses/${address['id']}/', method: 'DELETE');
      await _load();
    } catch (e) { _notice('Could not delete address: $e'); }
  }

  Future<void> _edit(Map<String, dynamic> address) async {
    final latitude = double.tryParse('${address['latitude']}');
    final longitude = double.tryParse('${address['longitude']}');
    if (latitude == null || longitude == null) {
      _notice('This address has no valid map coordinates.');
      return;
    }
    final updated = await Navigator.of(context).push<bool>(
      MaterialPageRoute(
        builder: (_) => AddressDetailsScreen(
          latitude: latitude,
          longitude: longitude,
          address: '${address['full_address'] ?? ''}',
          existingAddress: address,
        ),
      ),
    );
    if (!mounted) return;
    if (updated == true) {
      _notice('Address updated successfully.');
      await _load();
    }
  }

  Future<void> _share(Map<String, dynamic> address) async {
    final text = _display(address);
    if (text.isEmpty) return;
    try {
      await SharePlus.instance.share(ShareParams(text: text));
    } catch (e) { _notice('Unable to share: $e'); }
  }

  Future<void> _search() async {
    final result = await Navigator.of(context).push<ll.LatLng>(
      MaterialPageRoute(builder: (_) => AddressSearchScreen(mapCenter: widget.mapCenter)),
    );
    if (!mounted || result == null) return;
    Navigator.of(context).pop(AddressPickerResult.search(result));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Choose your address')),
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: _load,
          child: ListView(padding: const EdgeInsets.all(16), children: [
            Card(
              child: ListTile(
                leading: const Icon(Icons.search),
                title: const Text('Search area, street or PIN code'),
                trailing: const Icon(Icons.chevron_right),
                onTap: _search,
              ),
            ),
            const SizedBox(height: 12),
            Row(children: [
              const Expanded(child: Text('Saved addresses', style: TextStyle(fontSize: 19, fontWeight: FontWeight.bold))),
              IconButton(tooltip: 'Refresh saved addresses', onPressed: _load, icon: const Icon(Icons.refresh)),
            ]),
            if (_loading) const Padding(padding: EdgeInsets.all(16), child: Center(child: CircularProgressIndicator())),
            if (_error != null) ListTile(title: Text(_error!), trailing: TextButton(onPressed: _load, child: const Text('Retry'))),
            if (!_loading && _error == null && _addresses.isEmpty)
              const Padding(padding: EdgeInsets.all(20), child: Text('No saved addresses yet. Choose a location on the map and save it.')),
            for (final address in _addresses) Card(
              child: Column(children: [
                ListTile(
                  leading: Icon('${address['label']}' == 'work' ? Icons.work_outline : Icons.home_outlined),
                  title: Row(children: [
                    Text('${address['label'] ?? 'Address'}'.toUpperCase()),
                    if (address['is_default'] == true) ...[
                      const SizedBox(width: 8),
                      const Text('DEFAULT', style: TextStyle(color: Colors.deepPurple, fontSize: 11)),
                    ],
                  ]),
                  subtitle: Text(_display(address)),
                  trailing: const Icon(Icons.chevron_right),
                  onTap: () => _pick(address),
                ),
                Wrap(alignment: WrapAlignment.end, spacing: 2, children: [
                  TextButton(onPressed: () => _edit(address), child: const Text('Edit')),
                  TextButton(onPressed: () => _delete(address), child: const Text('Delete')),
                  TextButton(onPressed: () => _share(address), child: const Text('Share')),
                  if (address['is_default'] != true)
                    TextButton(onPressed: () => _setDefault(address), child: const Text('Set default')),
                ]),
              ]),
            ),
          ]),
        ),
      ),
    );
  }
}
