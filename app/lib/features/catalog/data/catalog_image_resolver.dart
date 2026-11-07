/// Title-first service photography fallback.
///
/// Admin-uploaded service/gallery photos always take priority. This resolver is
/// intentionally specific: it never falls back to a generic root-category
/// photo, because an unrelated image is worse than a neutral placeholder.
class CatalogImageResolver {
  static String? forService({
    required String title,
    required String categoryName,
    String audience = 'all',
  }) {
    final t = _normalize(title);
    final c = _normalize(categoryName);
    final a = audience.toLowerCase();

    // Audience-specific salon imagery applies only to hair/grooming work.
    // It must not override title-specific images for nails, facials, waxing,
    // threading, or other services just because their audience is men/women.
    final isHairOrGrooming =
        c.contains('hair') || c.contains('grooming');
    if (isHairOrGrooming && (a == 'men' || t.contains('men '))) {
      return _photo('1503951914875-452162b0f3f1');
    }
    if (isHairOrGrooming && (a == 'women' || t.contains('women '))) {
      return _photo('1560066984-138dadb4c035');
    }

    // Exact/high-specificity jobs must be tested before broad terms.
    if (_has(t, ['balcony'])) return _photo('1600607687939-ce8a6c25118c');
    if (_has(t, ['interior car', 'car interior'])) return _photo('1607860108855-64acf2078ed9');

    // Electrical titles are resolved before broad home-cleaning terms (for
    // example, "Full Home Electrical Inspection" is not a cleaning service).
    final isElectrical = c.contains('electrical') ||
        c.contains('fan services') || c.contains('lighting services') ||
        c.contains('switch socket') || c.contains('wiring') ||
        c.contains('inverter') || c.contains('geyser');
    if (isElectrical) {
      // Fan services use distinct Commons photographs per fan type. The
      // source file pages and licence/author details are recorded in
      // ELECTRICAL_IMAGE_ATTRIBUTION.md.
      if (t == 'ceiling fan') {
        return _commonsPhoto('Fan,ceiling,Tamil Nadu493.jpg');
      }
      if (t == 'wall fan') {
        return _commonsPhoto('Wall Mount Electric Fan.jpg');
      }
      if (t == 'exhaust fan') {
        return _commonsPhoto('Exhaust fan.jpg');
      }
      if (t == 'decorative fan') {
        return _commonsPhoto('Ceiling fan with lamp.jpg');
      }
      if (_has(t, ['fan'])) return _photo('1706973320036-b5049d93b580');
      if (_has(t, ['bulb', 'led'])) return _photo('1674659719067-8735479ba10c');
      if (_has(t, ['wall light', 'wall lamp', 'sconce'])) {
        return _photo('1747655760627-c53acf6b9b8c');
      }
      if (_has(t, ['tube light', 'panel light', 'ceiling light', 'chandelier',
                   'decorative light', 'outdoor light', 'strip light', 'lighting'])) {
        return _photo('1724054913772-afffd0933162');
      }
      if (_has(t, ['switch', 'socket', 'plug', 'doorbell', 'loose connection',
                   'burnt socket'])) {
        return _photo('1621905251189-08b45d6a269e');
      }
      if (_has(t, ['wiring', 'short circuit', 'power failure', 'mcb', 'fuse',
                   'earthing', 'rccb', 'elcb', 'voltage', 'electrical',
                   'power point', 'inspection', 'safety check', 'setup',
                   'inverter', 'ups', 'battery', 'geyser', 'water pump',
                   'motor', 'charging'])) {
        return _photo('1621905251189-08b45d6a269e');
      }
    }

    if (_has(t, ['interior cleaning', 'inside cleaning', 'room cleaning', 'full home', 'deep home', 'house cleaning', 'home cleaning'])) {
      return _photo('1581578731548-c64695cc6952');
    }
    // Electrical fan and lighting photo IDs above have not been semantically
    // verified for every individual service; see image audit before release.
    if (_has(t, ['fan'])) {
      // One verified ceiling-fan photograph is suitable for the fan service
      // family; do not let a broad "light" match steal fan titles.
      return _photo('1706973320036-b5049d93b580');
    }
    if (_has(t, ['bulb', 'led'])) {
      return _photo('1674659719067-8735479ba10c');
    }
    if (_has(t, ['wall light', 'wall lamp', 'sconce'])) {
      return _photo('1747655760627-c53acf6b9b8c');
    }
    if (_has(t, ['tube light', 'panel light', 'ceiling light', 'chandelier',
                 'decorative light', 'outdoor light', 'strip light', 'lighting'])) {
      return _photo('1724054913772-afffd0933162');
    }
    if (_has(t, ['nail', 'manicure', 'pedicure'])) return _photo('1610992015732-2449b76344bc');
    if (_has(t, ['eyebrow', 'threading', 'upper lip', 'lower lip', 'chin thread'])) return _photo('1512290923902-8a9f81dc236c');
    if (_has(t, ['wax'])) return _photo('1512290923902-8a9f81dc236c');
    if (_has(t, ['sofa', 'upholstery', 'cushion', 'chair cleaning'])) return _photo('1555041469-a586c61ea9bc');
    if (_has(t, ['bathroom', 'toilet', 'washbasin'])) return _photo('1620626011761-996317b8d101');
    if (_has(t, ['kitchen', 'chimney', 'refrigerator', 'fridge', 'microwave', 'oven'])) return _photo('1600489000022-c2086d79f9d4');
    if (_has(t, ['window', 'glass'])) return _photo('1497366754035-f200968a6e72');
    if (_has(t, ['mattress', 'bedroom', 'bed cleaning'])) return _photo('1616594039964-ae9021a400a0');
    if (_has(t, ['carpet', 'rug'])) return _photo('1600210492486-724fe5c67fb0');
    if (_has(t, ['garden', 'plant', 'lawn'])) return _photo('1416879595882-3373a0480b5b');

    if (_has(t, ['chandelier', 'ceiling light', 'lighting', 'light', 'bulb', 'led'])) {
      return _photo('1507473885765-e6ed057f782c');
    }
    if (_has(t, ['switch', 'socket', 'plug', 'wiring', 'short circuit', 'mcb', 'fuse', 'electrical', 'electrician'])) {
      return _photo('1621905251189-08b45d6a269e');
    }
    if (_has(t, ['inverter', 'ups', 'battery backup', 'geyser', 'water heater'])) {
      return _photo('1621905251189-08b45d6a269e');
    }

    if (_has(t, ['car', 'vehicle', 'exterior wash', 'detailing', 'paint protection', 'rubbing', 'polishing', 'ceramic coating', 'graphene coating'])) {
      return _photo('1607860108855-64acf2078ed9');
    }
    if (_has(t, ['haircut', 'hair styling', 'hair wash', 'beard', 'shave', 'barber'])) {
      return _photo(a == 'women' ? '1560066984-138dadb4c035' : '1503951914875-452162b0f3f1');
    }
    if (_has(t, ['facial', 'skin care', 'skin treatment', 'bleach', 'cleanup'])) return _photo('1570172619644-dfd03ed5d881');
    if (_has(t, ['makeup', 'bridal', 'hairstyle', 'saree draping'])) return _photo('1522335789203-aabd1fc54bc9');
    if (_has(t, ['massage', 'spa'])) return _photo('1540555700478-4be289fbecef');

    // No generic category fallback. Unknown titles show the in-app placeholder.
    return null;
  }

  static String _normalize(String value) =>
      value.toLowerCase().replaceAll(RegExp(r"[^a-z0-9]+"), " ").trim();

  static bool _has(String value, List<String> terms) =>
      terms.any((term) => value.contains(term));

  static String _commonsPhoto(String fileName) =>
      'https://commons.wikimedia.org/wiki/Special:FilePath/${Uri.encodeComponent(fileName)}?width=900';

  static String _photo(String id) =>
      'https://images.unsplash.com/photo-$id?auto=format&fit=crop&w=900&q=85';
}
