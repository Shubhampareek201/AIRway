import 'package:flutter/material.dart';
import 'package:airway/core/theme/airway_colors.dart';
import 'package:airway/core/theme/airway_spacing.dart';
import 'package:airway/core/widgets/airway_components.dart';
import 'package:airway/features/catalog/data/catalog_api.dart';
import 'package:airway/features/catalog/data/catalog_models.dart';
import 'package:airway/features/catalog/presentation/service_list_screen.dart';
import 'package:airway/features/catalog/presentation/category_decision_screen.dart';
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

    if (category.slug == 'beauty' && answers['beauty_audience'] == null) {
      final audience = await BeautyAudienceScreen.choose(
        context,
        options: category.audienceOptions,
      );
      if (audience == null || !mounted) return;
      answers['beauty_audience'] = audience;
    }

    if (selectedCategory.customerFlowSteps.isNotEmpty) {
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
      answers.addAll(selected);
    }

    // The backend owns the category/service relationship. Reload its filtered
    // tree after each decision so choices such as Electrical > Repair only show
    // relevant subcategories instead of relying on title matching in Flutter.
    if (answers.isNotEmpty) {
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
          final configuredSlugs = configuredMap is Map
              ? configuredMap[selected]
              : null;
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
    return Ingram(
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
              padding: const EdgeInsets.fromLTRB(14, 10, 14, 11),
              child: Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          category.title,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.w900,
                            color: AirwayColors.text,
                          ),
                        ),
                        if (category.children.isNotEmpty) ...[
                          const SizedBox(height: 3),
                          Text(
                            '${category.children.length} subcategories',
                            style: const TextStyle(
                              fontSize: 12,
                              color: AirwayColors.textSecondary,
                            ),
                          ),
                        ],
                      ],
                    ),
                  ),
                  const SizedBox(width: 8),
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
          mainAxisExtent: 174,
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
