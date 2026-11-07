/// Service-specific fallback imagery used only when Admin has not uploaded
/// a service image. Match against the service title first; category names are
/// used only for a final category-level fallback. This prevents words such as
/// "cleaning" or "cleanup" from accidentally selecting an unrelated image.
class CatalogImageResolver {
  static String? forService({
    required String title,
    required String categoryName,
  }) {
    final titleText = _normalize(title);
    final categoryText = _normalize(categoryName);

    // Electrical: identify the actual job from its service title.
    if (_has(titleText, ['fan'])) {
      return _image('1558618666-fcd25c85cd64');
    }
    if (_has(titleText, ['chandelier', 'ceiling light', 'lighting', 'light', 'bulb', 'led'])) {
      return _image('1507473885765-e6ed057f782c');
    }
    if (_has(titleText, ['switch', 'socket', 'plug', 'wiring', 'short circuit', 'mcb', 'fuse', 'electrician', 'electrical repair', 'electrical inspection'])) {
      return _image('1621905251189-08b45d6a269e');
    }
    if (_has(titleText, ['inverter', 'ups', 'battery backup'])) {
      return _image('1621905251189-08b45d6a269e');
    }
    if (_has(titleText, ['geyser', 'water heater'])) {
      return _image('1621905251189-08b45d6a269e');
    }

    // Home cleaning: use service-specific terms, not the broad word "clean".
    if (_has(titleText, ['sofa', 'upholstery', 'cushion', 'chair cleaning'])) {
      return _image('1555041469-a586c61ea9bc');
    }
    if (_has(titleText, ['kitchen', 'chimney', 'refrigerator', 'fridge', 'microwave', 'oven'])) {
      return _image('1600489000022-c2086d79f9d4');
    }
    if (_has(titleText, ['bathroom', 'toilet', 'washbasin', 'sanitary'])) {
      return _image('1620626011761-996317b8d101');
    }
    if (_has(titleText, ['window', 'glass', 'glass door'])) {
      return _image('1497366754035-f200968a6e72');
    }
    if (_has(titleText, ['mattress', 'bedroom', 'bed cleaning'])) {
      return _image('1616594039964-ae9021a400a0');
    }
    if (_has(titleText, ['carpet', 'rug'])) {
      return _image('1600210492486-724fe5c67fb0');
    }
    if (_has(titleText, ['floor', 'tile', 'marble', 'grout', 'terrace', 'balcony', 'outdoor'])) {
      return _image('1600607687939-ce8a6c25118c');
    }
    if (_has(titleText, ['garden', 'plant', 'lawn'])) {
      return _image('1416879595882-3373a0480b5b');
    }
    if (_has(titleText, ['full home', 'deep home', 'move-in', 'move-out', 'home cleaning', 'house cleaning', 'general cleaning', 'dusting', 'maid'])) {
      return _image('1581578731548-c64695cc6952');
    }

    // Car wash and detailing.
    if (_has(titleText, ['car', 'vehicle', 'exterior wash', 'interior car', 'detailing', 'paint protection', 'rubbing', 'polishing', 'ceramic coating'])) {
      return _image('1607860108855-64acf2078ed9');
    }

    // Beauty services.
    if (_has(titleText, ['haircut', 'hair styling', 'hair wash', 'beard', 'shave', 'barber'])) {
      return _image('1503951914875-452162b0f3f1');
    }
    if (_has(titleText, ['facial', 'skin care', 'skin treatment', 'bleach'])) {
      return _image('1570172619644-dfd03ed5d881');
    }
    if (_has(titleText, ['threading', 'waxing', 'wax'])) {
      return _image('1512290923902-8a9f81dc236c');
    }
    if (_has(titleText, ['nail', 'manicure', 'pedicure'])) {
      return _image('1610992015732-2449b76344bc');
    }
    if (_has(titleText, ['makeup', 'bridal', 'hairstyle', 'saree draping'])) {
      return _image('1522335789203-aabd1fc54bc9');
    }
    if (_has(titleText, ['massage', 'spa', 'grooming'])) {
      return _image('1540555700478-4be289fbecef');
    }

    // Category fallback is deliberately last, and never overrides a title match.
    if (_has(categoryText, ['electrical'])) {
      return _image('1621905251189-08b45d6a269e');
    }
    if (_has(categoryText, ['home cleaning', 'cleaning'])) {
      return _image('1581578731548-c64695cc6952');
    }
    if (_has(categoryText, ['car wash'])) {
      return _image('1607860108855-64acf2078ed9');
    }
    if (_has(categoryText, ['beauty'])) {
      return _image('1522335789203-aabd1fc54bc9');
    }
    return null;
  }

  static String _normalize(String value) =>
      value.toLowerCase().replaceAll(RegExp(r'[^a-z0-9]+'), ' ').trim();

  static bool _has(String value, List<String> terms) =>
      terms.any((term) => value.contains(term));

  static String _image(String photoId) =>
      'https://images.unsplash.com/photo-$photoId?auto=format&fit=crop&w=900&q=85';
}
