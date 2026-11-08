/// Single fallback image source for category tiles throughout AIRway.
/// Admin-uploaded category images take precedence over these reviewed mappings.
class CatalogCategoryImageResolver {
  static const Map<String, String> _images = {
    'beauty': 'https://images.unsplash.com/photo-1560066984-138dadb4c035?w=900&auto=format&fit=crop',
    'hair-services': 'https://images.unsplash.com/photo-1503951914875-452162b0f3f1?w=900&auto=format&fit=crop',
    'facial-skin-care': 'https://images.unsplash.com/photo-1570172619644-dfd03ed5d881?w=900&auto=format&fit=crop',
    'grooming-massage': 'https://images.unsplash.com/photo-1540555700478-4be289fbecef?w=900&auto=format&fit=crop',
    'makeup-occasion-styling': 'https://images.unsplash.com/photo-1522335789203-aabd1fc54bc9?w=900&auto=format&fit=crop',
    'manicure-pedicure': 'https://images.unsplash.com/photo-1610992015732-2449b76344bc?w=900&auto=format&fit=crop',
    'threading': 'https://images.unsplash.com/photo-1512290923902-8a9f81dc236c?w=900&auto=format&fit=crop',
    'waxing': 'https://images.unsplash.com/photo-1512290923902-8a9f81dc236c?w=900&auto=format&fit=crop',
    'car-wash': 'https://images.unsplash.com/photo-1492144534655-ae79c964c9d7?w=900&auto=format&fit=crop',
    'electrical': 'https://images.unsplash.com/photo-1621905251918-48416bd8575a?w=900&auto=format&fit=crop',
    'home-cleaning': 'https://images.unsplash.com/photo-1581578731548-c64695cc6952?w=900&auto=format&fit=crop',
  };

  static String? forCategory({required String slug, required String title}) {
    final normalized = slug.trim().toLowerCase();
    if (_images.containsKey(normalized)) return _images[normalized];
    final titleKey = title.trim().toLowerCase().replaceAll(RegExp(r'[^a-z0-9]+'), '-');
    return _images[titleKey];
  }
}
