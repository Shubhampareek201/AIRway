import 'package:flutter/material.dart';
import 'package:airway/core/theme/airway_colors.dart';
import 'package:airway/core/theme/airway_spacing.dart';
import 'package:airway/core/widgets/airway_components.dart';
import 'package:airway/features/catalog/data/catalog_api.dart';
import 'package:airway/features/catalog/data/catalog_models.dart';
import 'package:airway/features/catalog/presentation/service_list_screen.dart';
import 'package:airway/features/catalog/presentation/category_decision_screen.dart';

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
  State<ServiceCategoriesScreen> createState() =>
      _ServiceCategoriesScreenState();
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

  Future<void> _openCategory(Category category) async {
    var answers = Map<String, dynamic>.from(widget.initialAnswers);
    if (category.flowSteps.isNotEmpty) {
      final selected = await Navigator.push<Map<String, dynamic>>(
        context,
        MaterialPageRoute(
          builder: (_) => CategoryDecisionScreen(
            categoryTitle: category.title,
            steps: category.flowSteps,
          ),
        ),
      );
      if (selected == null || !mounted) return;
      answers.addAll(selected);
    }
    if (category.children.isNotEmpty) {
      Navigator.push<void>(
        context,
        MaterialPageRoute(
          builder: (_) => ServiceCategoriesScreen(
            initialCategories: category.children,
            addressId: widget.addressId,
            title: category.title,
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
          categoryId: category.id,
          categoryTitle: category.title,
          addressId: widget.addressId,
          initialAnswers: answers,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AirwayColors.background,
      appBar: AppBar(
        title: Text(widget.title),
        backgroundColor: AirwayColors.background,
      ),
      body: _loading
          ? const Center(
              child: CircularProgressIndicator(color: AirwayColors.primary),
            )
          : _error != null
              ? _errorWidget(_error!)
              : _categories.isEmpty
                  ? _emptyState()
                  : _buildBody(),
    );
  }

  Widget _buildBody() {
    return ListView(
      padding: AirwaySpacing.screenPadding,
      children: [
        Text(
          widget.title == 'Browse Services'
              ? 'Choose a category'
              : 'Choose a service',
          style: const TextStyle(
            fontSize: 22,
            fontWeight: FontWeight.w800,
            color: AirwayColors.text,
          ),
        ),
        const SizedBox(height: 6),
        const Text(
          'Explore services available in your selected area',
          style: TextStyle(
            fontSize: 14,
            color: AirwayColors.textSecondary,
          ),
        ),
        const SizedBox(height: 20),
        ..._buildCategoryGrid(),
      ],
    );
  }

  List<Widget> _buildCategoryGrid() {
    final rows = <Widget>[];
    for (var i = 0; i < _categories.length; i += 2) {
      final pair = _categories.sublist(i, (i + 2).clamp(0, _categories.length));
      rows.add(
        Row(
          children: [
            for (final category in pair) ...[
              Expanded(child: _categoryCard(category)),
              if (pair.length == 2 && category != pair.last)
                const SizedBox(width: 12),
            ],
            if (pair.length < 2) const Expanded(child: SizedBox()),
          ],
        ),
      );
      if (i + 2 < _categories.length) {
        rows.add(const SizedBox(height: 12));
      }
    }
    return rows;
  }

  IconData _categoryIcon(String name) {
    final value = name.toLowerCase();
    if (value.contains('clean')) return Icons.cleaning_services_rounded;
    if (value.contains('repair') || value.contains('electric')) {
      return Icons.handyman_rounded;
    }
    if (value.contains('plumb')) return Icons.plumbing_rounded;
    if (value.contains('paint')) return Icons.format_paint_rounded;
    if (value.contains('shift') || value.contains('move')) {
      return Icons.local_shipping_rounded;
    }
    if (value.contains('beauty') || value.contains('salon')) {
      return Icons.spa_rounded;
    }
    if (value.contains('car')) return Icons.directions_car_rounded;
    return Icons.grid_view_rounded;
  }

  Widget _categoryCard(Category category) {
    return Ingram(
      onTap: () => _openCategory(category),
      child: Container(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              width: double.infinity,
              height: 112,
              decoration: BoxDecoration(
                color: AirwayColors.primarySoft,
                borderRadius: BorderRadius.circular(AirwaySpacing.imageRadius),
              ),
              child: Center(
                child: Icon(
                  _categoryIcon(category.title),
                  color: AirwayColors.primary,
                  size: 44,
                ),
              ),
            ),
            const SizedBox(height: 12),
            Text(
              category.title,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.w800,
                color: AirwayColors.text,
              ),
            ),
            if (category.children.isNotEmpty) ...[
              const SizedBox(height: 6),
              Text(
                '${category.children.length} subcategories',
                style: const TextStyle(
                  fontSize: 11,
                  color: AirwayColors.textSecondary,
                ),
              ),
            ],
          ],
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
              const Icon(
                Icons.category_outlined,
                size: 64,
                color: AirwayColors.textSecondary,
              ),
              const SizedBox(height: 20),
              const Text(
                'No categories available',
                style: TextStyle(
                  fontSize: 20,
                  fontWeight: FontWeight.w700,
                  color: AirwayColors.text,
                ),
              ),
              const SizedBox(height: 8),
              const Text(
                'Services for this area will appear here once they are available.',
                style: TextStyle(color: AirwayColors.textSecondary),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 20),
              FilledButton(
                onPressed: _loadCategories,
                child: const Text('Retry'),
              ),
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
              const Icon(
                Icons.error_outline,
                color: Colors.redAccent,
                size: 52,
              ),
              const SizedBox(height: 14),
              Text(
                message,
                textAlign: TextAlign.center,
                style: const TextStyle(color: AirwayColors.textSecondary),
              ),
              const SizedBox(height: 20),
              FilledButton(
                onPressed: _loadCategories,
                child: const Text('Retry'),
              ),
            ],
          ),
        ),
      );
}
