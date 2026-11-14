import 'package:flutter/material.dart';
import 'package:airway/core/theme/airway_colors.dart';
import 'package:airway/features/catalog/data/catalog_api.dart';
import 'package:airway/features/catalog/data/catalog_models.dart';
import 'package:airway/features/catalog/data/catalog_image_resolver.dart';
import 'package:airway/features/catalog/data/beauty_audience.dart';
import 'package:airway/features/catalog/presentation/service_detail_screen.dart';
import 'package:airway/features/booking/presentation/customer_cart_screen.dart';
import 'package:airway/features/booking/presentation/customer_cart_badge.dart';
import 'package:airway/features/booking/data/booking_api.dart';
import 'package:airway/features/booking/presentation/booking_scheduled_screen.dart';

class _PackageSelection {
  final ServiceVariant? variant;
  final String notes;
  final bool openDetails;

  const _PackageSelection.add(this.variant, this.notes) : openDetails = false;
  const _PackageSelection.openDetails()
      : variant = null, notes = '', openDetails = true;
}

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
  final _packageNotesController = TextEditingController();
  String _query = '';

  @override
  void initState() {
    super.initState();
    _loadServices();
  }

  @override
  void dispose() {
    _searchController.dispose();
    _packageNotesController.dispose();
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

  String _packageDescription(ServiceVariant variant) {
    final description = variant.description?.trim() ?? '';
    if (description.isNotEmpty) return description;
    final title = variant.title.toLowerCase();
    if (title.contains('basic') || title.contains('essential')) {
      return 'Essential care for everyday service needs.';
    }
    if (title.contains('standard') || title.contains('regular') || title.contains('normal')) {
      return 'A balanced option for regular upkeep and care.';
    }
    if (title.contains('premium') || title.contains('deep')) {
      return 'Enhanced care for a more detailed service experience.';
    }
    return 'A service package tailored to your selected requirements.';
  }

  Future<_PackageSelection?> _showBeautyPackageSheet(
    Service service,
    List<ServiceVariant> variants,
  ) async {
    _packageNotesController.clear();
    return showModalBottomSheet<_PackageSelection>(
        context: context,
        isScrollControlled: true,
        backgroundColor: Colors.transparent,
        builder: (sheetContext) {
          ServiceVariant? selectedVariant;
          return StatefulBuilder(
            builder: (context, setSheetState) => SafeArea(
              child: Container(
                constraints: BoxConstraints(
                  maxHeight: MediaQuery.sizeOf(context).height * 0.88,
                ),
                padding: EdgeInsets.fromLTRB(
                  18, 12, 18, 16 + MediaQuery.viewInsetsOf(context).bottom,
                ),
                decoration: const BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.vertical(top: Radius.circular(26)),
                ),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Center(child: Container(
                      width: 40, height: 4,
                      decoration: BoxDecoration(
                        color: AirwayColors.border,
                        borderRadius: BorderRadius.circular(8),
                      ),
                    )),
                    const SizedBox(height: 16),
                    Row(children: [
                      Expanded(child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(service.title, style: const TextStyle(
                            fontSize: 19, fontWeight: FontWeight.w900,
                            color: AirwayColors.text,
                          )),
                          const SizedBox(height: 4),
                          const Text('Choose the package that suits you best',
                            style: TextStyle(fontSize: 12, color: AirwayColors.textSecondary)),
                        ],
                      )),
                      const Icon(Icons.auto_awesome_rounded, color: AirwayColors.primary, size: 25),
                    ]),
                    const SizedBox(height: 14),
                    Flexible(child: SingleChildScrollView(
                      child: Column(
                        children: [
                          if (variants.isEmpty)
                            Container(
                              width: double.infinity,
                              padding: const EdgeInsets.all(14),
                              decoration: BoxDecoration(
                                color: AirwayColors.primarySoft,
                                borderRadius: BorderRadius.circular(14),
                              ),
                              child: const Text(
                                'This service will be added at its listed price. Our team will confirm any service-specific details.',
                                style: TextStyle(fontSize: 12, height: 1.4, color: AirwayColors.text),
                              ),
                            ),
                          for (final variant in variants) ...[
                            _buildPackageOption(
                              variant,
                              selected: selectedVariant?.id == variant.id,
                              description: _packageDescription(variant),
                              onTap: () => setSheetState(() => selectedVariant = variant),
                            ),
                            const SizedBox(height: 9),
                          ],
                          const SizedBox(height: 5),
                          const Align(
                            alignment: Alignment.centerLeft,
                            child: Text('Anything we should know?',
                              style: TextStyle(fontSize: 14, fontWeight: FontWeight.w800, color: AirwayColors.text)),
                          ),
                          const SizedBox(height: 7),
                          TextField(
                            controller: _packageNotesController,
                            minLines: 2,
                            maxLines: 4,
                            maxLength: 300,
                            textCapitalization: TextCapitalization.sentences,
                            decoration: InputDecoration(
                              hintText: 'Add a request or special instruction (optional)',
                              hintStyle: const TextStyle(fontSize: 12, color: AirwayColors.textSecondary),
                              filled: true,
                              fillColor: AirwayColors.background,
                              border: OutlineInputBorder(
                                borderRadius: BorderRadius.circular(13),
                                borderSide: const BorderSide(color: AirwayColors.border),
                              ),
                              enabledBorder: OutlineInputBorder(
                                borderRadius: BorderRadius.circular(13),
                                borderSide: const BorderSide(color: AirwayColors.border),
                              ),
                              contentPadding: const EdgeInsets.all(13),
                            ),
                          ),
                          TextButton.icon(
                            onPressed: () => Navigator.of(sheetContext).push<void>(
                              MaterialPageRoute(
                                builder: (_) => ServiceDetailScreen(
                                  serviceId: service.id,
                                  addressId: widget.addressId,
                                  initialAnswers: widget.initialAnswers,
                                ),
                              ),
                            ),
                            icon: const Icon(Icons.info_outline_rounded, size: 18),
                            label: const Text('View full service details'),
                            style: TextButton.styleFrom(foregroundColor: AirwayColors.primary),
                          ),
                        ],
                      ),
                    )),
                    const SizedBox(height: 8),
                    SizedBox(
                      width: double.infinity,
                      child: FilledButton.icon(
                        onPressed: variants.isNotEmpty && selectedVariant == null
                            ? null
                            : () => Navigator.pop(
                                sheetContext,
                                _PackageSelection.add(
                                  selectedVariant,
                                  _packageNotesController.text.trim(),
                                ),
                              ),
                        icon: const Icon(Icons.shopping_bag_outlined, size: 18),
                        label: const Text('Add to Cart'),
                        style: FilledButton.styleFrom(
                          backgroundColor: AirwayColors.primary,
                          foregroundColor: Colors.white,
                          padding: const EdgeInsets.symmetric(vertical: 15),
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(13)),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          );
        },
      );
  }

  Widget _buildPackageOption(
    ServiceVariant variant, {
    required bool selected,
    required String description,
    required VoidCallback onTap,
  }) {
    return Material(
      color: selected ? AirwayColors.primarySoft : Colors.white,
      borderRadius: BorderRadius.circular(15),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(15),
        child: Container(
          padding: const EdgeInsets.all(13),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(15),
            border: Border.all(
              color: selected ? AirwayColors.primary : AirwayColors.border,
              width: selected ? 1.7 : 1,
            ),
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(
                selected ? Icons.radio_button_checked_rounded : Icons.radio_button_off_rounded,
                color: AirwayColors.primary,
                size: 21,
              ),
              const SizedBox(width: 10),
              Expanded(child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(variant.title, style: const TextStyle(
                    fontSize: 14, fontWeight: FontWeight.w900, color: AirwayColors.text,
                  )),
                  const SizedBox(height: 4),
                  Text(description, style: const TextStyle(
                    fontSize: 11.5, height: 1.35, color: AirwayColors.textSecondary,
                  )),
                  if (variant.includedTasks.isNotEmpty) ...[
                    const SizedBox(height: 7),
                    for (final task in variant.includedTasks.take(4))
                      Padding(
                        padding: const EdgeInsets.only(top: 3),
                        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                          const Icon(Icons.check_rounded, size: 14, color: AirwayColors.primary),
                          const SizedBox(width: 5),
                          Expanded(child: Text(task, style: const TextStyle(
                            fontSize: 11, color: AirwayColors.text,
                          ))),
                        ]),
                      ),
                    if (variant.includedTasks.length > 4)
                      Text('+ ${variant.includedTasks.length - 4} more included',
                        style: const TextStyle(fontSize: 10.5, color: AirwayColors.primary, fontWeight: FontWeight.w700)),
                  ],
                  if (variant.durationMinutes != null && variant.durationMinutes! > 0)
                    Padding(
                      padding: const EdgeInsets.only(top: 6),
                      child: Text('${variant.durationMinutes} min',
                        style: const TextStyle(fontSize: 10.5, color: AirwayColors.textSecondary)),
                    ),
                ],
              )),
              const SizedBox(width: 8),
              Text('₹${variant.price.toStringAsFixed(0)}', style: const TextStyle(
                fontSize: 15, fontWeight: FontWeight.w900, color: AirwayColors.primary,
              )),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _startAddFlow(Service service) async {
    // Keep the existing booking flow unchanged for non-Beauty categories.
    if (widget.initialAnswers['beauty_audience'] == null) {
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
      return;
    }

    final availableVariants = service.variants.where((variant) {
      if (variant.attributes.isEmpty) return true;
      return variant.attributes.entries.every((entry) =>
          widget.initialAnswers[entry.key]?.toString() == entry.value.toString());
    }).toList();
    if (service.variants.isNotEmpty && availableVariants.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('No package is available for this selection.')),
      );
      return;
    }

    final selection = await _showBeautyPackageSheet(service, availableVariants);
    if (!mounted || selection == null) return;
    if (selection.openDetails) {
      _openService(service);
      return;
    }

    try {
      final updatedCart = await BookingApi.addCartItem(
        serviceId: service.id,
        variantId: selection.variant?.id,
        addonSelections: const [],
        formAnswers: const {},
        categoryAnswers: widget.initialAnswers,
        notes: selection.notes,
      );
      CustomerCartState.updateFromCart(updatedCart);
      if (!mounted) return;
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
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Could not add service: $e')),
      );
    }
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
