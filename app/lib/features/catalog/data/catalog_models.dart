import 'package:airway/core/network/auth_api.dart';

bool _catalogBool(dynamic value, {bool fallback = false}) {
  if (value is bool) return value;
  if (value is num) return value != 0;
  if (value is String) {
    switch (value.trim().toLowerCase()) {
      case 'true':
      case '1':
      case 'yes':
        return true;
      case 'false':
      case '0':
      case 'no':
        return false;
    }
  }
  return fallback;
}

/// Resolve media paths returned by Django and repair loopback hosts that are
/// unusable from a physical Android device.
String? _resolveMediaUrl(dynamic value) {
  final raw = value?.toString().trim() ?? '';
  if (raw.isEmpty) return null;

  final uri = Uri.tryParse(raw);
  if (uri == null) return null;
  final apiBase = Uri.parse(AuthApi.baseUrl);

  if (!uri.hasScheme || uri.host.isEmpty) {
    return apiBase.resolve(raw).toString();
  }

  const loopbackHosts = {'localhost', '127.0.0.1', '0.0.0.0'};
  if (loopbackHosts.contains(uri.host) &&
      !loopbackHosts.contains(apiBase.host)) {
    return uri.replace(
      scheme: apiBase.scheme,
      host: apiBase.host,
      port: apiBase.hasPort ? apiBase.port : null,
    ).toString();
  }

  return uri.toString();
}

class CatalogBanner {
  final int id;
  final String title;
  final String? image;
  final int? linkServiceId;

  const CatalogBanner({
    required this.id,
    required this.title,
    this.image,
    this.linkServiceId,
  });

  factory CatalogBanner.fromMap(Map<String, dynamic> map) => CatalogBanner(
        id: map['id'] as int,
        title: map['title']?.toString() ?? '',
        image: _resolveMediaUrl(map['image']),
        linkServiceId: map['link_service'] as int?,
      );
}

class Category {
  final int id;
  final String title;
  final String? titleHi;
  final String slug;
  final int? parentId;
  final String? image;
  final List<Map<String, dynamic>> flowSteps;
  final List<Map<String, dynamic>> audienceOptions;
  final bool isActive;
  final List<Category> children;

  Category({
    required this.id,
    required this.title,
    this.titleHi,
    required this.slug,
    this.parentId,
    this.image,
    this.flowSteps = const [],
    this.audienceOptions = const [],
    required this.isActive,
    this.children = const [],
  });

  /// Customer decision steps are database-owned; no client-side catalogue defaults.
  List<Map<String, dynamic>> get customerFlowSteps => flowSteps;

  factory Category.fromMap(Map<String, dynamic> map) {
    return Category(
      id: map['id'],
      title: map['title'] ?? '',
      titleHi: map['title_hi'],
      slug: map['slug'] ?? '',
      parentId: int.tryParse(map['parent']?.toString() ?? ''),
      image: _resolveMediaUrl(map['image']),
      audienceOptions: (map['audience_options'] as List? ?? [])
          .whereType<Map>()
          .map((rawOption) {
            final option = Map<String, dynamic>.from(rawOption);
            option['image'] = _resolveMediaUrl(option['image']);
            option['image_secondary'] = _resolveMediaUrl(option['image_secondary']);
            return option;
          })
          .toList(),
      flowSteps: (map['flow_steps'] as List? ?? [])
          .whereType<Map>()
          .map((step) => Map<String, dynamic>.from(step))
          .toList(),
      isActive: _catalogBool(map['is_active']),
      children: (map['children'] as List? ?? [])
          .whereType<Map>()
          .map((e) => Category.fromMap(Map<String, dynamic>.from(e)))
          .toList(),
    );
  }
}

class ServiceImage {
  final int id;
  final String image;
  final int sortOrder;

  ServiceImage({
    required this.id,
    required this.image,
    required this.sortOrder,
  });

  factory ServiceImage.fromMap(Map<String, dynamic> map) {
    return ServiceImage(
      id: map['id'],
      image: _resolveMediaUrl(map['image']) ?? '',
      sortOrder: map['sort_order'] ?? 0,
    );
  }
}

class ServiceVariant {
  final int id;
  final String title;
  final String? titleHi;
  final String? description;
  final String? image;
  final Map<String, dynamic> attributes;
  final List<String> includedTasks;
  final double mrp;
  final double price;
  final int discountPercent;
  final int? durationMinutes;
  final int sortOrder;
  final bool isActive;

  ServiceVariant({
    required this.id,
    required this.title,
    this.titleHi,
    this.description,
    this.image,
    this.attributes = const {},
    this.includedTasks = const [],
    required this.mrp,
    required this.price,
    required this.discountPercent,
    this.durationMinutes,
    required this.sortOrder,
    required this.isActive,
  });

  factory ServiceVariant.fromMap(Map<String, dynamic> map) {
    return ServiceVariant(
      id: map['id'],
      title: map['title'] ?? '',
      titleHi: map['title_hi'],
      description: map['description']?.toString(),
      image: _resolveMediaUrl(map['image']),
      attributes: Map<String, dynamic>.from(map['attributes'] as Map? ?? {}),
      includedTasks: (map['included_tasks'] as List? ?? []).map((item) => item.toString()).toList(),
      mrp: double.tryParse(map['mrp'].toString()) ?? 0,
      price: double.tryParse(map['price'].toString()) ?? 0,
      discountPercent: map['discount_percent'] ?? 0,
      durationMinutes: map['duration_minutes'],
      sortOrder: map['sort_order'] ?? 0,
      isActive: _catalogBool(map['is_active']),
    );
  }
}

class AddOn {
  final int id;
  final String title;
  final String? titleHi;
  final String? description;
  final String? image;
  final double mrp;
  final double price;
  final int discountPercent;
  final int sortOrder;
  final bool isActive;

  AddOn({
    required this.id,
    required this.title,
    this.titleHi,
    this.description,
    this.image,
    required this.mrp,
    required this.price,
    required this.discountPercent,
    required this.sortOrder,
    required this.isActive,
  });

  factory AddOn.fromMap(Map<String, dynamic> map) {
    return AddOn(
      id: map['id'],
      title: map['title'] ?? '',
      titleHi: map['title_hi'],
      description: map['description']?.toString(),
      image: _resolveMediaUrl(map['image']),
      mrp: double.tryParse(map['mrp'].toString()) ?? 0,
      price: double.tryParse(map['price'].toString()) ?? 0,
      discountPercent: map['discount_percent'] ?? 0,
      sortOrder: map['sort_order'] ?? 0,
      isActive: _catalogBool(map['is_active']),
    );
  }
}

class CatalogFormField {
  final int id;
  final String key;
  final String label;
  final String? labelHi;
  final String fieldType;
  final String fieldTypeDisplay;
  final List<dynamic> options;
  final bool isRequired;
  final List<Map<String, dynamic>> visibilityRules;
  final int sortOrder;

  CatalogFormField({
    required this.id,
    required this.key,
    required this.label,
    this.labelHi,
    required this.fieldType,
    required this.fieldTypeDisplay,
    required this.options,
    required this.isRequired,
    this.visibilityRules = const [],
    required this.sortOrder,
  });

  bool isVisibleFor(Map<String, dynamic> answers) {
    for (final rule in visibilityRules) {
      final dependency = rule['field']?.toString();
      if (dependency == null || dependency.isEmpty || !answers.containsKey(dependency)) {
        return false;
      }
      final actual = answers[dependency].toString();
      final expected = rule['value'];
      final operator = rule['operator']?.toString() ?? 'equals';
      var matches = false;
      switch (operator) {
        case 'equals':
          matches = actual == expected?.toString();
          break;
        case 'not_equals':
          matches = actual != expected?.toString();
          break;
        case 'in':
          final values = expected is List ? expected : [expected];
          matches = values.any((item) => item?.toString() == actual);
          break;
        default:
          return false;
      }
      if (!matches) return false;
    }
    return true;
  }

  factory CatalogFormField.fromMap(Map<String, dynamic> map) {
    return CatalogFormField(
      id: map['id'],
      key: map['key'] ?? '',
      label: map['label'] ?? '',
      labelHi: map['label_hi'],
      fieldType: map['field_type'] ?? '',
      fieldTypeDisplay: map['field_type_display'] ?? '',
      options: List<dynamic>.from(map['options'] ?? []),
      isRequired: _catalogBool(map['is_required']),
      visibilityRules: (map['visibility_rules'] as List? ?? [])
          .whereType<Map>()
          .map((rule) => Map<String, dynamic>.from(rule))
          .toList(),
      sortOrder: map['sort_order'] ?? 0,
    );
  }
}

class Service {
  final int id;
  final int categoryId;
  final String categoryName;
  final String? categorySlug;
  final String categoryRootName;
  final String categoryRootSlug;
  final String title;
  final String? titleHi;
  final String? description;
  final String? image;
  final String bookingMode;
  final String bookingModeDisplay;
  final String pricingType;
  final String pricingTypeDisplay;
  final String unitLabel;
  final double visitFee;
  final int durationMinutes;
  final int bufferMinutes;
  final String audience;
  final String audienceDisplay;
  final bool requiresFemaleWorker;
  final bool supportsProfessionalPreference;
  final bool isPopular;
  final int sortOrder;
  final bool isActive;
  final bool isAvailable;
  final List<ServiceImage> images;
  final List<ServiceVariant> variants;
  final List<AddOn> addons;
  final List<CatalogFormField> formFields;
  final String createdAt;
  final String updatedAt;

  Service({
    required this.id,
    required this.categoryId,
    required this.categoryName,
    this.categorySlug,
    this.categoryRootName = '',
    this.categoryRootSlug = '',
    required this.title,
    this.titleHi,
    this.description,
    this.image,
    required this.bookingMode,
    required this.bookingModeDisplay,
    required this.pricingType,
    required this.pricingTypeDisplay,
    required this.unitLabel,
    required this.visitFee,
    required this.durationMinutes,
    required this.bufferMinutes,
    required this.audience,
    required this.audienceDisplay,
    required this.requiresFemaleWorker,
    this.supportsProfessionalPreference = false,
    required this.isPopular,
    required this.sortOrder,
    required this.isActive,
    required this.isAvailable,
    required this.images,
    required this.variants,
    required this.addons,
    required this.formFields,
    required this.createdAt,
    required this.updatedAt,
  });

  factory Service.fromMap(Map<String, dynamic> map) {
    return Service(
      id: map['id'],
      categoryId: map['category'],
      categoryName: map['category_name'] ?? '',
      categorySlug: map['category_slug'],
      categoryRootName: map['category_root_name'] ?? map['category_name'] ?? '',
      categoryRootSlug: map['category_root_slug'] ?? map['category_slug'] ?? '',
      title: map['title'] ?? '',
      titleHi: map['title_hi'],
      description: map['description'],
      image: _resolveMediaUrl(map['image']),
      bookingMode: map['booking_mode'] ?? '',
      bookingModeDisplay: map['booking_mode_display'] ?? '',
      pricingType: map['pricing_type'] ?? '',
      pricingTypeDisplay: map['pricing_type_display'] ?? '',
      unitLabel: map['unit_label'] ?? '',
      visitFee: double.tryParse(map['visit_fee'].toString()) ?? 0,
      durationMinutes: map['duration_minutes'] ?? 0,
      bufferMinutes: map['buffer_minutes'] ?? 0,
      audience: map['audience'] ?? '',
      audienceDisplay: map['audience_display'] ?? '',
      requiresFemaleWorker: _catalogBool(map['requires_female_worker']),
      supportsProfessionalPreference:
          _catalogBool(map['supports_professional_preference']),
      isPopular: _catalogBool(map['is_popular']),
      sortOrder: map['sort_order'] ?? 0,
      isActive: _catalogBool(map['is_active']),
      isAvailable: _catalogBool(map['is_available'], fallback: true),
      images: (map['images'] as List? ?? [])
          .map((e) => ServiceImage.fromMap(Map<String, dynamic>.from(e)))
          .toList(),
      variants: (map['variants'] as List? ?? [])
          .map((e) => ServiceVariant.fromMap(Map<String, dynamic>.from(e)))
          .toList(),
      addons: (map['addons'] as List? ?? [])
          .map((e) => AddOn.fromMap(Map<String, dynamic>.from(e)))
          .toList(),
      formFields: (map['form_fields'] as List? ?? [])
          .map((e) => CatalogFormField.fromMap(Map<String, dynamic>.from(e)))
          .toList(),
      createdAt: map['created_at'] ?? '',
      updatedAt: map['updated_at'] ?? '',
    );
  }
}