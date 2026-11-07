/// Service-specific fallback imagery used only when Admin has not uploaded
/// a service image. Uploaded catalogue media always takes priority.
class CatalogImageResolver {
  static String forService({required String title, required String categoryName}) {
    final title = title.toLowerCase();
    final category = categoryName.toLowerCase();
    final name = '$title $category';

    // Match the actual service first. Do not let a broad category word such
    // as "cleaning" override a more specific car, electrical or beauty image.
    if (name.contains('car') || name.contains('vehicle') ||
        name.contains('wash') || name.contains('detailing') ||
        name.contains('paint protection') || name.contains('rubbing') ||
        name.contains('polishing') || name.contains('ceramic coating')) {
      return 'https://images.unsplash.com/photo-1607860108855-64acf2078ed9?auto=format&fit=crop&w=900&q=85';
    }
    if (name.contains('fan')) {
      return 'https://images.unsplash.com/photo-1631545806609-8f7e4f7b7f1d?auto=format&fit=crop&w=900&q=85';
    }
    if (name.contains('light') || name.contains('bulb') ||
        name.contains('led') || name.contains('chandelier')) {
      return 'https://images.unsplash.com/photo-1507473885765-e6ed057f782c?auto=format&fit=crop&w=900&q=85';
    }
    if (name.contains('switch') || name.contains('socket') ||
        name.contains('plug') || name.contains('wiring') ||
        name.contains('short circuit') || name.contains('mcb') ||
        name.contains('inverter') || name.contains('geyser') ||
        name.contains('electrical') || name.contains('electrician')) {
      return 'https://images.unsplash.com/photo-1621905251189-08b45d6a269e?auto=format&fit=crop&w=900&q=85';
    }
    if (name.contains('hair') || name.contains('haircut') ||
        name.contains('beard') || name.contains('shave') ||
        name.contains('barber')) {
      return 'https://images.unsplash.com/photo-1503951914875-452162b0f3f1?auto=format&fit=crop&w=900&q=85';
    }
    if (name.contains('facial') || name.contains('skin') ||
        name.contains('cleanup') || name.contains('bleach')) {
      return 'https://images.unsplash.com/photo-1570172619644-dfd03ed5d881?auto=format&fit=crop&w=900&q=85';
    }
    if (name.contains('thread') || name.contains('wax')) {
      return 'https://images.unsplash.com/photo-1512290923902-8a9f81dc236c?auto=format&fit=crop&w=900&q=85';
    }
    if (name.contains('nail') || name.contains('manicure') ||
        name.contains('pedicure')) {
      return 'https://images.unsplash.com/photo-1610992015732-2449b76344bc?auto=format&fit=crop&w=900&q=85';
    }
    if (name.contains('makeup') || name.contains('bridal') ||
        name.contains('hairstyl') || name.contains('saree')) {
      return 'https://images.unsplash.com/photo-1522335789203-aabd1fc54bc9?auto=format&fit=crop&w=900&q=85';
    }
    if (name.contains('massage') || name.contains('spa') ||
        name.contains('grooming')) {
      return 'https://images.unsplash.com/photo-1540555700478-4be289fbecef?auto=format&fit=crop&w=900&q=85';
    }
    if (name.contains('sofa') || name.contains('upholstery')) {
      return 'https://images.unsplash.com/photo-1555041469-a586c61ea9bc?auto=format&fit=crop&w=900&q=85';
    }
    if (name.contains('garden') || name.contains('plant') ||
        name.contains('lawn')) {
      return 'https://images.unsplash.com/photo-1416879595882-3373a0480b5b?auto=format&fit=crop&w=900&q=85';
    }
    if (name.contains('kitchen') || name.contains('chimney') ||
        name.contains('refrigerator') || name.contains('microwave')) {
      return 'https://images.unsplash.com/photo-1600489000022-c2086d79f9d4?auto=format&fit=crop&w=900&q=85';
    }
    if (name.contains('bathroom') || name.contains('toilet') ||
        name.contains('washbasin')) {
      return 'https://images.unsplash.com/photo-1620626011761-996317b8d101?auto=format&fit=crop&w=900&q=85';
    }
    if (name.contains('window') || name.contains('glass')) {
      return 'https://images.unsplash.com/photo-1497366754035-f200968a6e72?auto=format&fit=crop&w=900&q=85';
    }
    if (name.contains('bedroom') || name.contains('mattress')) {
      return 'https://images.unsplash.com/photo-1616594039964-ae9021a400a0?auto=format&fit=crop&w=900&q=85';
    }
    if (name.contains('carpet') || name.contains('rug')) {
      return 'https://images.unsplash.com/photo-1600210492486-724fe5c67fb0?auto=format&fit=crop&w=900&q=85';
    }
    if (name.contains('floor') || name.contains('tile') ||
        name.contains('marble') || name.contains('grout')) {
      return 'https://images.unsplash.com/photo-1600607687939-ce8a6c25118c?auto=format&fit=crop&w=900&q=85';
    }
    if (name.contains('clean') || name.contains('home')) {
      return 'https://images.unsplash.com/photo-1581578731548-c64695cc6952?auto=format&fit=crop&w=900&q=85';
    }
    return 'https://images.unsplash.com/photo-1581578731548-c64695cc6952?auto=format&fit=crop&w=900&q=85';
  }

}
