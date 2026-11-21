import 'package:flutter/material.dart';
import 'package:airway/core/localization/airway_text.dart';
import 'package:airway/core/theme/airway_colors.dart';
import 'package:airway/features/favorites/data/favorite_api.dart';
import 'package:airway/features/catalog/presentation/service_detail_screen.dart';

class FavoriteServicesScreen extends StatefulWidget {
  final int? addressId;

  const FavoriteServicesScreen({super.key, this.addressId});

  @override
  State<FavoriteServicesScreen> createState() => _FavoriteServicesScreenState();
}

class _FavoriteServicesScreenState extends State<FavoriteServicesScreen> {
  List<Map<String, dynamic>> _favorites = [];
  bool _loading = true;
  String? _error;
  final Set<int> _removing = <int>{};

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    if (mounted) {
      setState(() {
        _loading = true;
        _error = null;
      });
    }
    try {
      final items = await FavoriteApi.listFavorites();
      if (mounted) setState(() => _favorites = items);
    } catch (error) {
      if (mounted) {
        setState(() => _error = error.toString().replaceFirst('Exception: ', ''));
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _remove(Map<String, dynamic> item) async {
    final id = int.tryParse('${item['id']}');
    if (id == null || _removing.contains(id)) return;
    final previousIndex = _favorites.indexOf(item);
    setState(() {
      _removing.add(id);
      _favorites = _favorites.where((value) => value['id'] != item['id']).toList();
    });
    try {
      await FavoriteApi.removeFavorite(id);
      if (mounted) setState(() => _removing.remove(id));
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _removing.remove(id);
        if (!_favorites.any((value) => value['id'] == item['id'])) {
          final index = previousIndex.clamp(0, _favorites.length).toInt();
          _favorites.insert(index, item);
        }
      });
      _message('Could not remove this favorite. Please try again.');
    }
  }

  Future<void> _openService(Map<String, dynamic> item) async {
    if (item['service_is_available'] != true) {
      _message('This service is currently unavailable. You can remove it from favorites.');
      return;
    }
    final serviceId = int.tryParse('${item['service_id']}');
    if (serviceId == null) return;
    await Navigator.of(context).push<void>(
      MaterialPageRoute(
        builder: (_) => ServiceDetailScreen(serviceId: serviceId, addressId: widget.addressId),
      ),
    );
    if (mounted) await _load();
  }

  void _message(String value) {
    if (!mounted) return;
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(value)));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(AirwayText.tr('Favorite services', 'पसंदीदा सेवाएँ')),
        actions: [
          IconButton(
            onPressed: _loading ? null : _load,
            tooltip: AirwayText.tr('Refresh', 'रीफ़्रेश करें'),
            icon: const Icon(Icons.refresh_rounded),
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(
                  child: Padding(
                    padding: const EdgeInsets.all(24),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const Icon(Icons.cloud_off_outlined, size: 42),
                        const SizedBox(height: 12),
                        Text(_error!, textAlign: TextAlign.center),
                        const SizedBox(height: 16),
                        FilledButton.icon(
                          onPressed: _load,
                          icon: const Icon(Icons.refresh_rounded),
                          label: Text(AirwayText.tr('Retry', 'फिर कोशिश करें')),
                        ),
                      ],
                    ),
                  ),
                )
              : _favorites.isEmpty
                  ? RefreshIndicator(
                      onRefresh: _load,
                      child: ListView(
                        physics: const AlwaysScrollableScrollPhysics(),
                        padding: const EdgeInsets.all(32),
                        children: [
                          const SizedBox(height: 90),
                          const Icon(Icons.favorite_border_rounded, size: 58, color: AirwayColors.primary),
                          const SizedBox(height: 16),
                          Text(AirwayText.tr('No favorites yet', 'अभी कोई पसंदीदा सेवा नहीं है'), textAlign: TextAlign.center,
                              style: TextStyle(fontSize: 19, fontWeight: FontWeight.w800)),
                          const SizedBox(height: 8),
                          Text(AirwayText.tr('Save services you may want to book later using the heart button on a service page.', 'जिन सेवाओं को बाद में बुक करना चाहते हैं, उन्हें सेवा पेज पर हार्ट बटन दबाकर सेव करें।'),
                              textAlign: TextAlign.center,
                              style: TextStyle(color: AirwayColors.textSecondary, height: 1.45)),
                        ],
                      ),
                    )
                  : RefreshIndicator(
                      onRefresh: _load,
                      child: ListView.separated(
                        physics: const AlwaysScrollableScrollPhysics(),
                        padding: const EdgeInsets.all(16),
                        itemCount: _favorites.length,
                        separatorBuilder: (_, __) => const SizedBox(height: 8),
                        itemBuilder: (context, index) {
                          final item = _favorites[index];
                          final imageUrl = item['image']?.toString();
                          final available = item['service_is_active'] == true;
                          return Card(
                            child: ListTile(
                              onTap: () => _openService(item),
                              leading: CircleAvatar(
                                radius: 26,
                                backgroundColor: AirwayColors.primary.withValues(alpha: 0.10),
                                backgroundImage: imageUrl != null && imageUrl.isNotEmpty
                                    ? NetworkImage(imageUrl)
                                    : null,
                                child: imageUrl == null || imageUrl.isEmpty
                                    ? const Icon(Icons.home_repair_service_outlined, color: AirwayColors.primary)
                                    : null,
                              ),
                              title: Text(
                                item['service_title']?.toString() ?? 'AIRway service',
                                style: const TextStyle(fontWeight: FontWeight.w700),
                              ),
                              subtitle: Text(
                                available
                                    ? item['category_title']?.toString() ?? 'Service'
                                    : 'Currently unavailable',
                                style: TextStyle(
                                  color: available ? AirwayColors.textSecondary : AirwayColors.error,
                                ),
                              ),
                              trailing: IconButton(
                                tooltip: AirwayText.tr('Remove favorite', 'पसंदीदा से हटाएँ'),
                                onPressed: _removing.contains(item['id']) ? null : () => _remove(item),
                                icon: const Icon(Icons.favorite_rounded, color: AirwayColors.error),
                              ),
                            ),
                          );
                        },
                      ),
                    ),
    );
  }
}
