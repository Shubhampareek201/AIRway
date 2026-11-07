import 'package:airway/core/network/auth_api.dart';

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
    required this.isActive,
    this.children = const [],
  });

  /// Admin configuration wins. These initial AIRway journeys are defaults
  /// for the four launch categories and can be replaced from the Admin panel.
  List<Map<String, dynamic>> get customerFlowSteps {
    if (flowSteps.isNotEmpty) return flowSteps;
    if (parentId != null) return const [];
    final identity = '${slug.toLowerCase()} ${title.toLowerCase()}';
    if (identity.contains('car') || identity.contains('vehicle')) {
      return [
        {
          'key': 'vehicle_type',
          'title': 'Select vehicle type',
          'type': 'select',
          'required': true,
          'options': [
            {'label': 'Hatchback', 'value': 'Hatchback', 'image': 'https://images.pexels.com/photos/31042170/pexels-photo-31042170.jpeg?auto=compress&cs=tinysrgb&w=900'},
            {'label': 'Sedan', 'value': 'Sedan', 'image': 'https://images.pexels.com/photos/4797547/pexels-photo-4797547.jpeg?auto=compress&cs=tinysrgb&w=900'},
            {'label': 'Compact SUV', 'value': 'Compact SUV', 'image': 'https://images.pexels.com/photos/27918358/pexels-photo-27918358.jpeg?auto=compress&cs=tinysrgb&w=900'},
            {'label': 'SUV – 5 Seater', 'value': 'SUV – 5 Seater', 'image': 'https://images.pexels.com/photos/27918358/pexels-photo-27918358.jpeg?auto=compress&cs=tinysrgb&w=900'},
            {'label': 'SUV – 7 Seater', 'value': 'SUV – 7 Seater', 'image': 'https://images.pexels.com/photos/27918358/pexels-photo-27918358.jpeg?auto=compress&cs=tinysrgb&w=900'},
            {'label': 'MUV / MPV', 'value': 'MUV / MPV', 'image': 'https://images.pexels.com/photos/5093241/pexels-photo-5093241.jpeg?auto=compress&cs=tinysrgb&w=900'},
            {'label': 'Mini Bus / Traveller', 'value': 'Mini Bus / Traveller', 'image': 'https://images.pexels.com/photos/5093241/pexels-photo-5093241.jpeg?auto=compress&cs=tinysrgb&w=900'},
            {'label': 'Luxury Car', 'value': 'Luxury Car', 'image': 'https://images.pexels.com/photos/9452235/pexels-photo-9452235.jpeg?auto=compress&cs=tinysrgb&w=900'},
            {'label': 'Luxury SUV / Premium 7-Seater', 'value': 'Luxury SUV / Premium 7-Seater', 'image': 'https://images.pexels.com/photos/27918358/pexels-photo-27918358.jpeg?auto=compress&cs=tinysrgb&w=900'},
          ],
        },
        {'key': 'vehicle_make', 'title': 'Car manufacturer (optional)', 'type': 'text', 'required': false},
        {'key': 'vehicle_model', 'title': 'Car model (optional)', 'type': 'text', 'required': false},
      ];
    }
    if (identity.contains('beauty') || identity.contains('salon') || identity.contains('wellness')) {
      return [
        {
          'key': 'beauty_type',
          'title': 'Who is this service for?',
          'type': 'select',
          'required': true,
          'options': [
            {
              'label': "Men's Beauty",
              'value': "Men's Beauty",
              'image': 'https://images.unsplash.com/photo-1503951914875-452162b0f3f1?w=900&auto=format&fit=crop',
            },
            {
              'label': "Women's Beauty",
              'value': "Women's Beauty",
              'image': 'https://images.unsplash.com/photo-1560066984-138dadb4c035?w=900&auto=format&fit=crop',
            },
            {
              'label': 'Common Services',
              'value': 'Common Services',
              'image': 'https://images.unsplash.com/photo-1521590832167-7bcbfaa6381f?w=900&auto=format&fit=crop',
            },
          ],
        },
      ];
    }
    if (identity.contains('electrical') || identity.contains('electrician')) {
      return [
        {
          'key': 'electrical_group',
          'title': 'Choose electrical service group',
          'type': 'select',
          'required': true,
          'options': [
            'Fan Services', 'Lighting Services', 'Switch & Socket Services',
            'Wiring & Electrical Repairs', 'Inverter & UPS',
            'Geyser & Electrical Connections', 'Electrical Inspection & Setup',
          ],
          'filter_children': true,
        },
      ];
    }
    return const [];
  }

  factory Category.fromMap(Map<String, dynamic> map) {
    return Category(
      id: map['id'],
      title: map['title'] ?? '',
      titleHi: map['title_hi'],
      slug: map['slug'] ?? '',
      parentId: int.tryParse(map['parent']?.toString() ?? ''),
      image: _resolveMediaUrl(map['image']),
      flowSteps: (map['flow_steps'] as List? ?? [])
          .whereType<Map>()
          .map((step) => Map<String, dynamic>.from(step))
          .toList(),
      isActive: map['is_active'] ?? false,
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
      isActive: map['is_active'] ?? false,
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
      isActive: map['is_active'] ?? false,
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
    required this.sortOrder,
  });

  factory CatalogFormField.fromMap(Map<String, dynamic> map) {
    return CatalogFormField(
      id: map['id'],
      key: map['key'] ?? '',
      label: map['label'] ?? '',
      labelHi: map['label_hi'],
      fieldType: map['field_type'] ?? '',
      fieldTypeDisplay: map['field_type_display'] ?? '',
      options: List<dynamic>.from(map['options'] ?? []),
      isRequired: map['is_required'] ?? false,
      sortOrder: map['sort_order'] ?? 0,
    );
  }
}

class Service {
  final int id;
  final int categoryId;
  final String categoryName;
  final String? categorySlug;
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
      requiresFemaleWorker: map['requires_female_worker'] ?? false,
      isPopular: map['is_popular'] ?? false,
      sortOrder: map['sort_order'] ?? 0,
      isActive: map['is_active'] ?? false,
      isAvailable: map['is_available'] ?? true,
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