import 'package:flutter/material.dart';
import 'package:airway/core/theme/airway_colors.dart';
import 'package:airway/features/catalog/data/catalog_api.dart';
import 'package:airway/features/catalog/data/catalog_models.dart';
import 'package:airway/features/catalog/data/catalog_image_resolver.dart';
import 'package:airway/features/catalog/data/beauty_audience.dart';
import 'package:airway/features/catalog/presentation/service_detail_screen.dart';
import 'package:airway/features/booking/presentation/booking_scheduled_screen.dart';
import 'package:airway/features/booking/presentation/customer_cart_screen.dart';
import 'package:airway/features/booking/presentation/customer_cart_badge.dart';

/// Backend-driven service listing. Service photography uses the same canonical
/// resolver as Home and service details; admin-uploaded images take priority.
class ServiceListScreen extends StatefulWidget {
  final int categoryId;
  final String? categoryTitle;
  final int? addressId;
  final Map<String, dynamic> initialAnswers;
  final bool includeDescendants;

  const ServiceListScreen({
    super.key,
    required this.categoryId,
    this.categoryTitle,
    this.addressId,
    this.initialAnswers = const {},
    this.includeDescendants = false,
  });

  @override
  State<ServiceListScreen> createState() => _ServiceListScreenState();
}

class _ServiceListScreenState extends State<ServiceListScreen> {
  List<Service> _services = [];
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
          category: widget.includeDescendants ? null : widget.categoryId,
          addressId: widget.addressId,
          audience: widget.initialAnswers['beauty_audience']?.toString(),
          categoryAnswers: widget.initialAnswers,
        ),
        CatalogApi.listCategories(
          addressId: widget.addressId,
          audience: widget.initialAnswers['beauty_audience']?.toString(),
        ),
      ]);
      var services = results[0] as List<Service>;
      final categories = results[1] as List<Category>;
      if (widget.includeDescendants) {
        final descendantIds = <int>{};
        void collect(List<Category> items) {
          for (final item in items) {
            descendantIds.add(item.id);
            collect(item.children);
          }
        }
        void findAndCollect(List<Category> items) {
          for (final item in items) {
            if (item.id == widget.categoryId) {
              descendantIds.add(item.id);
              collect(item.children);
              return;
            }
            findAndCollect(item.children);
          }
        }
        findAndCollect(categories);
        services = services
            .where((service) => descendantIds.contains(service.categoryId))
            .toList();
      }
      if (!mounted) return;
      setState(() {
        _services = services;
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
    final lower = _query.trim().toLowerCase();
    final beautyAudience = widget.initialAnswers['beauty_audience']?.toString();
    return _services.where((service) {
      if (beautyAudience != null &&
          !BeautyAudience.includes(
            selected: beautyAudience,
            serviceAudience: service.audience,
          )) return false;
      if (lower.isEmpty) return true;
      return service.title.toLowerCase().contains(lower) ||
          service.description?.toLowerCase().contains(lower) == true ||
          service.categoryName.toLowerCase().contains(lower);
    }).toList();
  }

  double _displayPrice(Service service) {
    final matchingVariants = service.variants.where((variant) {
      if (variant.attributes.isEmpty) return true;
      return variant.attributes.entries.every((entry) =>
          widget.initialAnswers[entry.key]?.toString() == entry.value.toString());
    }).toList();
    if (matchingVariants.isNotEmpty) {
      return matchingVariants.map((variant) => variant.price).reduce((a, b) => a < b ? a : b);
    }
    if (service.pricingType == "quote") return 0;
    if (service.variants.isEmpty) return 0;
    return 0;
  }

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

  Future<void> _startAddFlow(Service service) async {
    final added = await Navigator.push<bool>(
      context,
      MaterialPageRoute(
        builder: (_) => BookingScheduledScreen(
          serviceId: service.id,
          serviceTitle: service.title,
          addressId: widget.addressId,
          initialCategoryAnswers: widget.initialAnswers,
        ),
      ),
    );
    if (!mounted || added != true) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('${service.title} added to cart'),
        action: SnackBarAction(
          label: 'VIEW CART',
          onPressed: () => Navigator.push<void>(
            context,
            MaterialPageRoute(builder: (_) => const CustomerCartScreen()),
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final title = widget.categoryTitle ?? 'Services';
    return Scaffold(
      backgroundColor: AirwayColors.background,
      appBar: AppBar(
        title: Text(title),
        backgroundColor: AirwayColors.background,
        actions: [
          CustomerCartBadge(
            onTap: () => Navigator.push<void>(
              context,
              MaterialPageRoute(builder: (_) => const CustomerCartScreen()),
            ),
          ),
        ],
      ),
      body: Column(
        children: [
          _searchBar(),
          Expanded(
            child: _loading
                ? const Center(
                    child: CircularProgressIndicator(color: AirwayColors.primary),
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
          onChanged: (value) => setState(() => _query = value),
          decoration: InputDecoration(
            hintText: 'Search ${widget.categoryTitle ?? "services"}...',
            hintStyle: const TextStyle(
              fontSize: 13.5,
              color: AirwayColors.textSecondary,
            ),
            prefixIcon: const Icon(Icons.search_rounded, color: AirwayColors.primary),
            suffixIcon: _query.isNotEmpty
                ? IconButton(
                    tooltip: 'Clear search',
                    onPressed: () {
                      _searchController.clear();
                      setState(() => _query = '');
                    },
                    icon: const Icon(Icons.close_rounded, size: 19),
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

  Widget _buildList() {
    final services = _filteredServices;
    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 4, 16, 28),
      children: [
        Container(
          width: double.infinity,
          margin: const EdgeInsets.only(bottom: 14),
          padding: const EdgeInsets.all(17),
          decoration: BoxDecoration(
            color: AirwayColors.primarySoft,
            borderRadius: BorderRadius.circular(16),
          ),
          child: Row(
            children: [
              const Icon(Icons.home_repair_service_rounded, color: AirwayColors.primary, size: 34),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      _audienceTitle,
                      style: const TextStyle(
                        color: AirwayColors.text,
                        fontSize: 18,
                        fontWeight: FontWeight.w900,
                      ),
                    ),
                    const SizedBox(height: 3),
                    const Text(
                      'Choose the service you need',
                      style: TextStyle(color: AirwayColors.textSecondary, fontSize: 12),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(2, 2, 2, 10),
          child: Text(
            'Services (${services.length})',
            style: const TextStyle(
              color: AirwayColors.text,
              fontSize: 17,
              fontWeight: FontWeight.w900,
            ),
          ),
        ),
        for (final service in services) ...[
          _serviceCard(service),
          const SizedBox(height: 11),
        ],
      ],
    );
  }

  String get _audienceTitle {
    final category = widget.categoryTitle ?? 'Services';
    switch (widget.initialAnswers['beauty_audience']?.toString()) {
      case BeautyAudience.men:
        return "Men's $category";
      case BeautyAudience.women:
        return "Women's $category";
      case BeautyAudience.both:
        return "Unisex $category";
      default:
        return category;
    }
  }

  Widget _serviceImage(Service service) {
    final imageUrl = (service.image?.isNotEmpty == true)
        ? service.image!
        : service.images.isNotEmpty
            ? service.images.first.image
            : CatalogImageResolver.forService(
                title: service.title,
                categoryName: service.categoryName,
                audience: service.audience,
              );
    return ClipRRect(
      borderRadius: BorderRadius.circular(11),
      child: SizedBox(
        width: 76,
        height: 76,
        child: imageUrl == null || imageUrl.isEmpty
            ? Container(
                color: AirwayColors.primarySoft,
                alignment: Alignment.center,
                child: const Icon(
                  Icons.home_repair_service_rounded,
                  color: AirwayColors.primary,
                  size: 30,
                ),
              )
            : Image.network(
                imageUrl,
                fit: BoxFit.cover,
                errorBuilder: (_, __, ___) => Container(
                  color: AirwayColors.primarySoft,
                  alignment: Alignment.center,
                  child: const Icon(
                    Icons.broken_image_outlined,
                    color: AirwayColors.primary,
                    size: 28,
                  ),
                ),
              ),
      ),
    );
  }

  Widget _serviceCard(Service service) {
    final price = _displayPrice(service);
    final description = service.description?.trim() ?? '';
    return Material(
      color: AirwayColors.surface,
      borderRadius: BorderRadius.circular(15),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: service.isAvailable ? () => _openService(service) : null,
        child: Container(
          padding: const EdgeInsets.all(11),
          decoration: BoxDecoration(
            border: Border.all(color: AirwayColors.border),
            borderRadius: BorderRadius.circular(15),
          ),
          child: Row(
            children: [
              _serviceImage(service),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      service.title,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        color: AirwayColors.text,
                        fontSize: 14,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                    if (description.isNotEmpty) ...[
                      const SizedBox(height: 4),
                      Text(
                        description,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          color: AirwayColors.textSecondary,
                          fontSize: 11,
                          height: 1.3,
                        ),
                      ),
                    ],
                    const SizedBox(height: 5),
                    Text(
                      service.durationMinutes > 0
                          ? '${service.durationMinutes} min'
                          : service.categoryName,
                      style: const TextStyle(
                        color: AirwayColors.textSecondary,
                        fontSize: 10.5,
                      ),
                    ),
                    const SizedBox(height: 5),
                    Text(
                      service.pricingType == 'quote'
                          ? (service.visitFee > 0 ? 'Visit fee ₹${service.visitFee.toStringAsFixed(0)}' : 'Inspection & quote')
                          : price > 0
                              ? service.pricingType == 'per_unit' && service.unitLabel.isNotEmpty
                                  ? 'From ₹${price.toStringAsFixed(0)} / ${service.unitLabel}'
                                  : 'From ₹${price.toStringAsFixed(0)}'
                              : 'Price on request',
                      style: const TextStyle(
                        color: AirwayColors.text,
                        fontSize: 13,
                        fontWeight: FontWeight.w900,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 8),
              OutlinedButton(
                onPressed: service.isAvailable ? () => _startAddFlow(service) : null,
                style: OutlinedButton.styleFrom(
                  foregroundColor: AirwayColors.primary,
                  side: const BorderSide(color: AirwayColors.primary),
                  padding: const EdgeInsets.symmetric(horizontal: 15, vertical: 9),
                  minimumSize: Size.zero,
                  tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(9)),
                ),
                child: Text(
                  service.isAvailable ? 'ADD' : 'UNAVAILABLE',
                  style: TextStyle(fontSize: 11, fontWeight: FontWeight.w900),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _emptyState() => Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.design_services_outlined, size: 64, color: AirwayColors.textSecondary),
              const SizedBox(height: 20),
              const Text(
                'No services available',
                style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700, color: AirwayColors.text),
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
              Text(message, textAlign: TextAlign.center, style: const TextStyle(color: AirwayColors.textSecondary)),
              const SizedBox(height: 20),
              FilledButton(onPressed: _loadServices, child: const Text('Retry')),
            ],
          ),
        ),
      );
}
