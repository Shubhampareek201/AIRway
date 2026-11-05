import 'package:flutter/material.dart';
import 'package:airway/core/theme/airway_colors.dart';
import 'package:airway/core/theme/airway_spacing.dart';
import 'package:airway/core/widgets/airway_components.dart';
import 'package:airway/features/catalog/data/catalog_api.dart';
import 'package:airway/features/catalog/data/catalog_models.dart';
import 'package:airway/features/catalog/presentation/service_list_screen.dart';

/// Service category selection screen.
/// Lists all active categories from the backend.
/// Tapping a category navigates to the service listing screen.
class ServiceCategoriesScreen extends StatefulWidget {
  const ServiceCategoriesScreen({super.key});

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
    _loadCategories();
  }

  Future<void> _loadCategories() async {
    setState(() {
      _loading = true;
      _error = null;
    });

    try {
      final result = await CatalogApi.request('/api/v1/catalog/categories/');
      final list = result is List
          ? result
          : (result is Map ? result['results'] : null);

      if (list is! List) {
        throw const FormatException('Unexpected categories response');
      }

      final categories = list
          .whereType<Map>()
          .map((e) => Category.fromMap(Map<String, dynamic>.from(e)))
          .where((c) => c.isActive)
          .toList();

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

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AirwayColors.background,
      appBar: AppBar(
        title: const Text('Browse Services'),
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
        const Text(
          'Choose a category',
          style: TextStyle(
            fontSize: 22,
            fontWeight: FontWeight.w800,
            color: AirwayColors.text,
          ),
        ),
        const SizedBox(height: 6),
        const Text(
          'Find home services by category',
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
              Expanded(
                child: _categoryCard(category),
              ),
              if (pair.length == 2 && category != pair.last) ...[
                const SizedBox(width: 12),
              ],
            ],
            if (pair.length < 2) ...[
              const Expanded(child: SizedBox()),
            ],
          ],
        ),
      );
      if (i + 2 < _categories.length) {
        rows.add(const SizedBox(height: 12));
      }
    }
    return rows;
  }

  Widget _categoryCard(Category category) {
    return Ingram(
      onTap: () {
        Navigator.push<void>(
          context,
          MaterialPageRoute(
            builder: (_) => ServiceListScreen(categoryId: category.id),
          ),
        );
      },
      child: Container(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              width: 48,
              height: 48,
              decoration: BoxDecoration(
                color: AirwayColors.primarySoft,
                borderRadius: const BorderRadius.all(
                  Radius.circular(AirwaySpacing.imageRadius),
                ),
              ),
              child: const Icon(
                Icons.design_services_rounded,
                color: AirwayColors.primary,
                size: 26,
              ),
            ),
            const SizedBox(height: 14),
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
            const SizedBox(height: 4),
            Text(
              category.titleHi ?? '',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                fontSize: 11,
                color: AirwayColors.textSecondary,
              ),
            ),
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
                'Service categories will appear here once they are added.',
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