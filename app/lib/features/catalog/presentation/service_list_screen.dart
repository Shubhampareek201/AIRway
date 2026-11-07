import 'package:flutter/material.dart';
import 'package:airway/core/theme/airway_colors.dart';
import 'package:airway/features/catalog/data/catalog_api.dart';
import 'package:airway/features/catalog/data/catalog_models.dart';
import 'package:airway/features/catalog/presentation/service_detail_screen.dart';

/// Service listing screen for a specific category.
/// Fetches and displays services from the backend API.
class ServiceListScreen extends StatefulWidget {
  final int categoryId;
  final String? categoryTitle;
  final int? addressId;
  final Map<String, dynamic> initialAnswers;

  const ServiceListScreen({
    super.key,
    required this.categoryId,
    this.categoryTitle,
    this.addressId,
    this.initialAnswers = const {},
  });

  @override
  State<ServiceListScreen> createState() => _ServiceListScreenState();
}

class _ServiceListScreenState extends State<ServiceListScreen> {
  List<Service> _services = [];
  final Map<int, String> _categoryImages = {};
  bool _loading = true;
  String? _error;
  final _searchController = TextEditingController();
  String _query = '';

  @override
  void initState() {
    super.initState();
    _loadServices();
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  Future<void> _loadServices() async {
    setState(() {
      _loading = true;
      _error = null;
    });

    try {
      final results = await Future.wait([
        CatalogApi.listServices(
          category: widget.categoryId,
          addressId: widget.addressId,
        ),
        CatalogApi.listCategories(addressId: widget.addressId),
      ]);
      final services = results[0] as List<Service>;
      final categories = results[1] as List<Category>;
      final images = <int, String>{};
      void collectImages(List<Category> items) {
        for (final category in items) {
          if (category.image?.isNotEmpty == true) {
            images[category.id] = category.image!;
          }
          collectImages(category.children);
        }
      }
      collectImages(categories);
      if (!mounted) return;
      setState(() {
        _services = services;
        _categoryImages
          ..clear()
          ..addAll(images);
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString();
        _loading = false;
      });
    }
  }

  List<Service> get _filteredServices {
    if (_query.trim().isEmpty) return _services;
    final lower = _query.trim().toLowerCase();
    return _services
        .where((s) {
          final beautyType = widget.initialAnswers['beauty_type']?.toString();
          if (beautyType == "Men's Beauty" && s.audience != 'men' && s.audience != 'all') return false;
          if (beautyType == "Women's Beauty" && s.audience != 'women' && s.audience != 'all') return false;
          if (beautyType == 'Common Services' && s.audience != 'all') return false;
          return
              s.title.toLowerCase().contains(lower) ||
              s.description?.toLowerCase().contains(lower) == true ||
              s.categoryName.toLowerCase().contains(lower);
        })
        .toList();
  }

  @override
  Widget build(BuildContext context) {
    final title = widget.categoryTitle ?? 'Services';
    return Scaffold(
      backgroundColor: AirwayColors.background,
      appBar: AppBar(
        title: Text(title),
        backgroundColor: AirwayColors.background,
      ),
      body: Column(
        children: [
          _searchBar(),
          Expanded(
            child: _loading
                ? const Center(
                    child: CircularProgressIndicator(
                      color: AirwayColors.primary,
                    ),
                  )
                : _error != null
                ? _errorWidget(_error!)
                : _filteredServices.isEmpty
                ? _emptyState()
                : _buildList(),
          ),
        ],
      ),
    );
  }

  Widget _searchBar() => Padding(
    padding: const EdgeInsets.fromLTRB(20, 8, 20, 12),
    child: TextField(
      controller: _searchController,
      textInputAction: TextInputAction.search,
      onChanged: (v) => setState(() => _query = v),
      decoration: InputDecoration(
        hintText: 'Search ${widget.categoryTitle ?? "Services"}...',
        hintStyle: const TextStyle(
          fontSize: 13.5,
          color: AirwayColors.textSecondary,
        ),
        prefixIcon: const Icon(
          Icons.search_rounded,
          color: AirwayColors.primary,
        ),
        suffixIcon: _query.isNotEmpty
            ? IconButton(
                tooltip: 'Clear search',
                onPressed: () {
                  _searchController.clear();
                  setState(() => _query = '');
                },
                icon: const Icon(
                  Icons.close_rounded,
                  size: 19,
                  color: AirwayColors.textSecondary,
                ),
              )
            : null,
        filled: true,
        fillColor: AirwayColors.surface,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(17),
          borderSide: BorderSide.none,
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(17),
          borderSide: BorderSide.none,
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(17),
          borderSide: const BorderSide(color: AirwayColors.primary, width: 1.5),
        ),
        contentPadding: const EdgeInsets.symmetric(vertical: 15),
      ),
    ),
  );

  Widget _buildList() => ListView.separated(
    padding: const EdgeInsets.fromLTRB(20, 4, 20, 24),
    itemCount: _filteredServices.length,
    separatorBuilder: (_, _) => const SizedBox(height: 10),
    itemBuilder: (context, index) {
      final service = _filteredServices[index];
      final imageUrl = service.image?.isNotEmpty == true
          ? service.image
          : service.images.isNotEmpty
          ? service.images.first.image
          : _categoryImages[service.categoryId];
      final price = service.variants.isNotEmpty
          ? service.variants.first.price
          : service.visitFee;
      return Material(
        color: AirwayColors.surface,
        borderRadius: BorderRadius.circular(14),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          // Browsing must not be blocked just because a worker is currently offline.
          // Real slot availability is checked during booking and dispatch.
          onTap: () => _openService(service),
          child: Container(
            padding: const EdgeInsets.all(9),
            decoration: BoxDecoration(
              border: Border.all(color: AirwayColors.border),
              borderRadius: BorderRadius.circular(14),
            ),
            child: Row(
              children: [
                ClipRRect(
                  borderRadius: BorderRadius.circular(11),
                  child: SizedBox(
                    width: 82,
                    height: 82,
                    child: imageUrl?.isNotEmpty == true
                        ? Image.network(
                            imageUrl!,
                            fit: BoxFit.cover,
                            errorBuilder: (_, _, _) =>
                                _serviceImagePlaceholder(),
                          )
                        : _serviceImagePlaceholder(),
                  ),
                ),
                const SizedBox(width: 13),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Text(
                        service.title,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          color: AirwayColors.text,
                          fontSize: 14,
                          fontWeight: FontWeight.w800,
                        ),
                      ),
                      const SizedBox(height: 5),
                      Text(
                        service.durationMinutes > 0
                            ? '${service.durationMinutes} min'
                            : service.categoryName,
                        style: const TextStyle(
                          color: AirwayColors.textSecondary,
                          fontSize: 11.5,
                        ),
                      ),
                      const SizedBox(height: 5),
                      if (!service.isAvailable) ...[
                        const Text(
                          'Check available slots',
                          style: TextStyle(
                            color: AirwayColors.textSecondary,
                            fontSize: 11.5,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                        const SizedBox(height: 4),
                      ],
                      Text(
                        price > 0
                            ? '₹${price.toStringAsFixed(0)}'
                            : 'Price on request',
                        style: const TextStyle(
                          color: AirwayColors.text,
                          fontSize: 13,
                          fontWeight: FontWeight.w800,
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 6),
                Icon(
                  Icons.chevron_right_rounded,
                  color: AirwayColors.primary,
                ),
              ],
            ),
          ),
        ),
      );
    },
  );

  Widget _serviceImagePlaceholder() => Container(
    color: AirwayColors.primarySoft,
    alignment: Alignment.center,
    child: const Icon(
      Icons.home_repair_service_rounded,
      color: AirwayColors.primary,
      size: 30,
    ),
  );

  Widget _emptyState() => Center(
    child: Padding(
      padding: const EdgeInsets.all(32),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(
            Icons.design_services_outlined,
            size: 64,
            color: AirwayColors.textSecondary,
          ),
          const SizedBox(height: 20),
          const Text(
            'No services available',
            style: TextStyle(
              fontSize: 20,
              fontWeight: FontWeight.w700,
              color: AirwayColors.text,
            ),
          ),
          const SizedBox(height: 8),
          const Text(
            'Services in this category will appear here once they are added.',
            style: TextStyle(color: AirwayColors.textSecondary),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 20),
          FilledButton(onPressed: _loadServices, child: const Text('Retry')),
        ],
      ),
    ),
  );

  Widget _errorWidget(String message) => Center(
    child: Padding(
      padding: const EdgeInsets.all(28),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.error_outline, color: Colors.redAccent, size: 52),
          const SizedBox(height: 14),
          Text(
            message,
            textAlign: TextAlign.center,
            style: const TextStyle(color: AirwayColors.textSecondary),
          ),
          const SizedBox(height: 20),
          FilledButton(onPressed: _loadServices, child: const Text('Retry')),
        ],
      ),
    ),
  );

  void _openService(Service service) {
    Navigator.push<void>(
      context,
      MaterialPageRoute(
        builder: (_) => ServiceDetailScreen(
          serviceId: service.id,
          addressId: widget.addressId,
          initialAnswers: widget.initialAnswers,
        ),
      ),
    );
  }
}
