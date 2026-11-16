import 'package:flutter/material.dart';
import 'package:airway/core/theme/airway_colors.dart';
import 'package:airway/core/theme/airway_spacing.dart';
import 'package:airway/core/widgets/airway_components.dart';
import 'package:airway/features/catalog/data/catalog_api.dart';
import 'package:airway/features/catalog/data/catalog_models.dart';
import 'package:airway/features/catalog/presentation/service_list_screen.dart';
import 'package:airway/features/catalog/presentation/category_decision_screen.dart';
import 'package:airway/features/catalog/presentation/car_wash_vehicle_screen.dart';
import 'package:airway/features/catalog/presentation/beauty_audience_screen.dart';
import 'package:airway/features/catalog/data/catalog_category_image_resolver.dart';
import 'package:airway/features/catalog/data/beauty_audience.dart';

class ServiceCategoriesScreen extends StatefulWidget {
  final List<Category>? initialCategories;
  final int? addressId;
  final String title;
  final Map<String, dynamic> initialAnswers;

  const ServiceCategoriesScreen({
    super.key,
    this.initialCategories,
    this.addressId,
    this.title = 'Browse Services',
    this.initialAnswers = const {},
  });

  @override
  State<ServiceCategoriesScreen> createState() => _ServiceCategoriesScreenState();
}

class _ServiceCategoriesScreenState extends State<ServiceCategoriesScreen> {
  List<Category> _categories = [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    if (widget.initialCategories != null) {
      _categories = widget.initialCategories!;
      _loading = false;
    } else {
      _loadCategories();
    }
  }

  Future<void> _loadCategories() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final categories = await CatalogApi.listCategories(
        addressId: widget.addressId,
        audience: widget.initialAnswers['beauty_audience']?.toString(),
      );
      if (!mounted) return;
      setState(() {
        _categories = categories;
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

  Category? _findCategoryById(List<Category> categories, int id) {
    for (final category in categories) {
      if (category.id == id) return category;
      final nested = _findCategoryById(category.children, id);
      if (nested != null) return nested;
    }
    return null;
  }

  Future<void> _openCategory(Category category) async {
    var selectedCategory = category;
    final answers = Map<String, dynamic>.from(widget.initialAnswers);
    var followsExplicitAdminRoute = false;

    if (category.slug == 'beauty' && answers['beauty_audience'] == null) {
      final audience = await BeautyAudienceScreen.choose(
        context,
        options: category.audienceOptions,
      );
      if (audience == null || !mounted) return;
      answers['beauty_audience'] = audience;
    }

    final categoryIdentity = '${selectedCategory.slug} ${selectedCategory.title}'.toLowerCase().replaceAll(RegExp(r'[^a-z0-9]+'), ' ').trim();
    final isCarWashCategory = categoryIdentity.contains('car wash') ||
        categoryIdentity.replaceAll(' ', '').contains('carwash') ||
        selectedCategory.children.any(
          (child) => child.slug == 'car' || child.slug == 'bike',
        );
    final isCarWashVehicleBranch =
        selectedCategory.slug == 'car' || selectedCategory.slug == 'bike';

    if ((isCarWashCategory || isCarWashVehicleBranch) &&
        (answers['vehicle_kind'] == null ||
            answers['vehicle_kind'].toString().trim().isEmpty)) {
      final selected = await Navigator.push<Map<String, dynamic>>(
        context,
        MaterialPageRoute(
          builder: (_) => CarWashVehicleScreen(
            initialVehicleType:
                isCarWashVehicleBranch ? selectedCategory.slug : null,
            vehicleTypeSteps: isCarWashVehicleBranch
                ? {selectedCategory.slug: selectedCategory.customerFlowSteps}
                : {
                    for (final child in selectedCategory.children)
                      if (child.slug == 'car' || child.slug == 'bike')
                        child.slug: child.customerFlowSteps,
                  },
          ),
        ),
      );
      if (selected == null || !mounted) return;
      answers.addAll(selected);

      // If this screen was opened at the Car Wash root, move into the
      // selected vehicle branch. The next screen is its service categories.
      if (isCarWashCategory) {
        final vehicleSlug =
            answers['vehicle_kind']?.toString().toLowerCase() == 'bike'
                ? 'bike'
                : 'car';
        final vehicleBranches = selectedCategory.children
            .where((child) => child.slug.toLowerCase() == vehicleSlug)
            .toList();
        if (vehicleBranches.isEmpty) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('No $vehicleSlug categories are configured yet.')),
          );
          return;
        }
        selectedCategory = vehicleBranches.first;
      }
    } else if (selectedCategory.customerFlowSteps.isNotEmpty &&
        !(answers['vehicle_kind'] != null &&
            (selectedCategory.slug == 'car' || selectedCategory.slug == 'bike'))) {
      final selected = await Navigator.push<Map<String, dynamic>>(
        context,
        MaterialPageRoute(
          builder: (_) => CategoryDecisionScreen(
            categoryTitle: selectedCategory.title,
            steps: selectedCategory.customerFlowSteps,
          ),
        ),
      );
      if (selected == null || !mounted) return;
      final nextCategorySlug = selected.remove('__next_category_slug')?.toString();
      final nextCategoryId = int.tryParse(
        selected.remove('__next_category_id')?.toString() ?? '',
      );
      answers.addAll(selected);

      // Navigation is driven by the parent category's Admin configuration:
      // an option can name its next child explicitly. Otherwise the parent's
      // child_slugs mapping below selects the permitted next-level children.
      if (nextCategoryId != null || (nextCategorySlug?.isNotEmpty ?? false)) {
        final target = selectedCategory.children.where((child) {
          if (nextCategoryId != null) return child.id == nextCategoryId;
          return child.slug.toLowerCase() == nextCategorySlug!.toLowerCase();
        }).toList();
        if (target.length != 1) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text('The next category is not configured correctly. Please contact support.'),
            ),
          );
          return;
        }
        selectedCategory = target.first;
        followsExplicitAdminRoute = true;

        // Resolve the configured branch from a fresh, unfiltered category
        // tree. The current screen may have been opened with a partial/stale
        // tree, while an answer-filtered request can prune sibling/child nodes.
        try {
          final fullRoots = await CatalogApi.listCategories(
            addressId: widget.addressId,
            audience: answers['beauty_audience']?.toString(),
          );
          final refreshedTarget = _findCategoryById(fullRoots, target.first.id);
          if (refreshedTarget != null) {
            selectedCategory = refreshedTarget;
          }
        } catch (_) {
          // Keep the exact Admin-selected child already resolved above.
        }
      }
    }

    // An explicit Admin next_category_slug/id is an authoritative hierarchy
    // transition. Keep the already-loaded child tree for that branch instead
    // of re-querying the root catalogue with branch answers (which can rebuild
    // the tree at the wrong level). Other flows still refresh their filtered
    // catalogue, e.g. Electrical work-type selection.
    if (answers.isNotEmpty && !followsExplicitAdminRoute) {
      try {
        final filteredRoots = await CatalogApi.listCategories(
          addressId: widget.addressId,
          audience: answers['beauty_audience']?.toString(),
          categoryAnswers: answers,
        );
        final refreshed = _findCategoryById(filteredRoots, selectedCategory.id);
        if (refreshed != null) selectedCategory = refreshed;
      } catch (e) {
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Could not load matching categories: $e')),
        );
        return;
      }
    }

    if (!mounted) return;

    // A vehicle choice narrows the backend catalogue, but the customer
    // still chooses a service category before seeing individual services.
    if (selectedCategory.children.isNotEmpty) {
      var children = selectedCategory.children;
      final filterStep = selectedCategory.customerFlowSteps.where(
        (step) => step['filter_children'] == true,
      ).toList();
      if (filterStep.isNotEmpty) {
        final step = filterStep.first;
        final key = step['key']?.toString();
        final selected = key == null ? null : answers[key]?.toString();
        if (selected != null && selected.isNotEmpty) {
          final configuredMap = step['child_slugs'];
          dynamic configuredSlugs;
          if (configuredMap is Map) {
            for (final entry in configuredMap.entries) {
              if (entry.key.toString().trim().toLowerCase() ==
                  selected.trim().toLowerCase()) {
                configuredSlugs = entry.value;
                break;
              }
            }
          }
          if (configuredSlugs is List && configuredSlugs.isNotEmpty) {
            final allowedSlugs = configuredSlugs.map((slug) => slug.toString()).toSet();
            children = children.where((child) => allowedSlugs.contains(child.slug)).toList();
          } else {
            // Compatibility fallback for older Admin-authored flow steps.
            final normalized = selected.toLowerCase().replaceAll(RegExp(r'[^a-z0-9]'), '');
            final matches = children.where((child) {
              final title = child.title.toLowerCase().replaceAll(RegExp(r'[^a-z0-9]'), '');
              return title.contains(normalized) || normalized.contains(title);
            }).toList();
            if (matches.isNotEmpty) children = matches;
          }
        }
      }
      if (children.isEmpty) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('No matching service categories are configured yet.')),
        );
        return;
      }
      Navigator.push<void>(
        context,
        MaterialPageRoute(
          builder: (_) => ServiceCategoriesScreen(
            initialCategories: children,
            addressId: widget.addressId,
            title: selectedCategory.title,
            initialAnswers: answers,
          ),
        ),
      );
      return;
    }

    Navigator.push<void>(
      context,
      MaterialPageRoute(
        builder: (_) => ServiceListScreen(
          categoryId: selectedCategory.id,
          categoryTitle: selectedCategory.title,
          addressId: widget.addressId,
          initialAnswers: answers,
        ),
      ),
    );
  }

  String? _categoryPhoto(Category category) =>
      CatalogCategoryImageResolver.forCategory(
        slug: category.slug,
        title: category.title,
      );

  IconData _categoryIcon(String name) {
    final value = name.toLowerCase();
    if (value.contains('clean')) return Icons.cleaning_services_rounded;
    if (value.contains('repair') || value.contains('electric')) return Icons.handyman_rounded;
    if (value.contains('plumb')) return Icons.plumbing_rounded;
    if (value.contains('paint')) return Icons.format_paint_rounded;
    if (value.contains('shift') || value.contains('move')) return Icons.local_shipping_rounded;
    if (value.contains('beauty') || value.contains('salon') || value.contains('wellness')) return Icons.spa_rounded;
    if (value.contains('car')) return Icons.directions_car_rounded;
    return Icons.grid_view_rounded;
  }

  String get _audienceSubtitle {
    switch (widget.initialAnswers['beauty_audience']?.toString()) {
      case BeautyAudience.men:
        return "Men's services available in your selected area";
      case BeautyAudience.women:
        return "Women's services available in your selected area";
      case BeautyAudience.both:
        return "Unisex services available in your selected area";
      default:
        return 'Explore services available in your selected area';
    }
  }

  Widget _categoryCard(Category category) {
    final imageUrl = category.image?.isNotEmpty == true
        ? category.image!
        : _categoryPhoto(category);
    return GestureDetector(
      onTap: () => _openCategory(category),
      child: Container(
        decoration: BoxDecoration(
          color: AirwayColors.surface,
          border: Border.all(color: AirwayColors.border),
          borderRadius: BorderRadius.circular(16),
        ),
        clipBehavior: Clip.antiAlias,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            SizedBox(
              height: 93,
              child: imageUrl == null
                  ? Container(
                      color: AirwayColors.primarySoft,
                      alignment: Alignment.center,
                      child: Icon(
                        _categoryIcon(category.title),
                        color: AirwayColors.primary,
                        size: 38,
                      ),
                    )
                  : Image.network(
                      imageUrl,
                      fit: BoxFit.cover,
                      errorBuilder: (_, __, ___) => Container(
                        color: AirwayColors.primarySoft,
                        alignment: Alignment.center,
                        child: Icon(
                          _categoryIcon(category.title),
                          color: AirwayColors.primary,
                          size: 48,
                        ),
                      ),
                    ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(10, 2, 10, 2),
              child: Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          category.title,
                          maxLines: 3,
                          softWrap: true,
                          overflow: TextOverflow.visible,
                          style: const TextStyle(
                            fontSize: 14,
                            height: 1.15,
                            fontWeight: FontWeight.w900,
                            color: AirwayColors.text,
                          ),
                        ),
                        if (category.children.isNotEmpty) ...[
                          const SizedBox(height: 2),
                          Text(
                            '${category.children.length} subcategories',
                            style: const TextStyle(
                              fontSize: 10,
                              color: AirwayColors.textSecondary,
                            ),
                          ),
                        ],
                      ],
                    ),
                  ),
                  const SizedBox(width: 4),
                  const Icon(
                    Icons.arrow_forward_rounded,
                    color: AirwayColors.primary,
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildCategoryGrid() => GridView.builder(
        shrinkWrap: true,
        physics: const NeverScrollableScrollPhysics(),
        padding: const EdgeInsets.symmetric(horizontal: 16),
        itemCount: _categories.length,
        gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
          crossAxisCount: 2,
          crossAxisSpacing: 12,
          mainAxisSpacing: 14,
          mainAxisExtent: 164,
        ),
        itemBuilder: (context, index) => _categoryCard(_categories[index]),
      );

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AirwayColors.background,
      appBar: AppBar(title: Text(widget.title), backgroundColor: AirwayColors.background),
      body: _loading
          ? const Center(child: CircularProgressIndicator(color: AirwayColors.primary))
          : _error != null
              ? _errorWidget(_error!)
              : _categories.isEmpty
                  ? _emptyState()
                  : ListView(
                      padding: const EdgeInsets.symmetric(vertical: 16),
                      children: [
                        Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 20),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                widget.title == 'Browse Services' ? 'Choose a category' : 'Choose a service',
                                style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w800, color: AirwayColors.text),
                              ),
                              const SizedBox(height: 6),
                              Text(
                                _audienceSubtitle,
                                style: const TextStyle(fontSize: 13, color: AirwayColors.textSecondary),
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(height: 20),
                        _buildCategoryGrid(),
                      ],
                    ),
    );
  }

  Widget _emptyState() => Center(
    child: Padding(
      padding: const EdgeInsets.all(32),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.category_outlined, size: 64, color: AirwayColors.textSecondary),
          const SizedBox(height: 20),
          const Text('No categories available', style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700, color: AirwayColors.text)),
          const SizedBox(height: 8),
          const Text('Services for this area will appear here once they are available.', style: TextStyle(color: AirwayColors.textSecondary), textAlign: TextAlign.center),
          const SizedBox(height: 20),
          FilledButton(onPressed: _loadCategories, child: const Text('Retry')),
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
          FilledButton(onPressed: _loadCategories, child: const Text('Retry')),
        ],
      ),
    ),
  );
}
