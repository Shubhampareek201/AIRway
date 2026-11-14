/// Category photography fallback for the launch catalogue.
/// Admin-uploaded category images always take precedence over these mappings.
class CatalogCategoryImageResolver {
  static const Map<String, String> _images = {
    'beauty': 'https://images.unsplash.com/photo-1560066984-138dadb4c035?w=900&auto=format&fit=crop',
    'hair-services': 'https://images.unsplash.com/photo-1521590832167-7bcbfaa6381f?w=900&auto=format&fit=crop',
    'facial-skin-care': 'https://images.unsplash.com/photo-1570172619644-dfd03ed5d881?w=900&auto=format&fit=crop',
    'grooming-massage': 'https://images.unsplash.com/photo-1540555700478-4be289fbecef?w=900&auto=format&fit=crop',
    'makeup-occasion-styling': 'https://images.unsplash.com/photo-1522335789203-aabd1fc54bc9?w=900&auto=format&fit=crop',
    'manicure-pedicure': 'https://images.unsplash.com/photo-1610992015732-2449b76344bc?w=900&auto=format&fit=crop',
    'threading': 'https://images.unsplash.com/photo-1512290923902-8a9f81dc236c?w=900&auto=format&fit=crop',
    'waxing': 'https://images.unsplash.com/photo-1512290923902-8a9f81dc236c?w=900&auto=format&fit=crop',
    'car-wash': 'https://images.unsplash.com/photo-1492144534655-ae79c964c9d7?w=900&auto=format&fit=crop',
    'car': 'https://images.unsplash.com/photo-1492144534655-ae79c964c9d7?w=900&auto=format&fit=crop',
    'bike': 'https://images.unsplash.com/photo-1558981806-ec527fa84c39?w=900&auto=format&fit=crop',
    'exterior-car-cleaning': 'https://images.unsplash.com/photo-1607860108855-64acf2078ed9?w=900&auto=format&fit=crop',
    'interior-car-cleaning': 'https://images.unsplash.com/photo-1607860108855-64acf2078ed9?w=900&auto=format&fit=crop',
    'complete-car-cleaning': 'https://images.unsplash.com/photo-1492144534655-ae79c964c9d7?w=900&auto=format&fit=crop',
    'car-detailing-paint-protection': 'https://images.unsplash.com/photo-1607860108855-64acf2078ed9?w=900&auto=format&fit=crop',
    'monthly-car-wash-plans': 'https://images.unsplash.com/photo-1492144534655-ae79c964c9d7?w=900&auto=format&fit=crop',
    'bike-exterior-cleaning': 'https://images.unsplash.com/photo-1558981806-ec527fa84c39?w=900&auto=format&fit=crop',
    'bike-complete-cleaning': 'https://images.unsplash.com/photo-1558981806-ec527fa84c39?w=900&auto=format&fit=crop',
    'bike-detailing': 'https://images.unsplash.com/photo-1558981806-ec527fa84c39?w=900&auto=format&fit=crop',
    'home-cleaning': 'https://images.unsplash.com/photo-1581578731548-c64695cc6952?w=900&auto=format&fit=crop',
    'full-home': 'https://images.unsplash.com/photo-1581578731548-c64695cc6952?w=900&auto=format&fit=crop',
    'full-home-cleaning': 'https://images.unsplash.com/photo-1581578731548-c64695cc6952?w=900&auto=format&fit=crop',
    'specific-area': 'https://images.unsplash.com/photo-1600489000022-c2086d79f9d4?w=900&auto=format&fit=crop',
    'specific-item': 'https://images.unsplash.com/photo-1555041469-a586c61ea9bc?w=900&auto=format&fit=crop',
    'kitchen-cleaning': 'https://images.unsplash.com/photo-1600489000022-c2086d79f9d4?w=900&auto=format&fit=crop',
    'bathroom-cleaning': 'https://images.unsplash.com/photo-1620626011761-996317b8d101?w=900&auto=format&fit=crop',
    'bedroom-cleaning': 'https://images.unsplash.com/photo-1616594039964-ae9021a400a0?w=900&auto=format&fit=crop',
    'living-room-dining-room': 'https://images.unsplash.com/photo-1600210492486-724fe5c67fb0?w=900&auto=format&fit=crop',
    'garden-cleaning': 'https://images.unsplash.com/photo-1416879595882-3373a0480b5b?w=900&auto=format&fit=crop',
    'balcony-terrace-cleaning': 'https://images.unsplash.com/photo-1600607687939-ce8a6c25118c?w=900&auto=format&fit=crop',
    'window-glass-cleaning': 'https://images.unsplash.com/photo-1497366754035-f200968a6e72?w=900&auto=format&fit=crop',
    'floor-cleaning': 'https://images.unsplash.com/photo-1581578731548-c64695cc6952?w=900&auto=format&fit=crop',
    'sofa-upholstery-cleaning': 'https://images.unsplash.com/photo-1555041469-a586c61ea9bc?w=900&auto=format&fit=crop',
    'mattress-cleaning': 'https://images.unsplash.com/photo-1616594039964-ae9021a400a0?w=900&auto=format&fit=crop',
    'carpet-rug-cleaning': 'https://images.unsplash.com/photo-1600210492486-724fe5c67fb0?w=900&auto=format&fit=crop',
    'electrical': 'https://images.unsplash.com/photo-1621905251918-48416bd8575a?w=900&auto=format&fit=crop',
    'fan-services': 'https://images.unsplash.com/photo-1706973320036-b5049d93b580?w=900&auto=format&fit=crop',
    'lighting-services': 'https://images.unsplash.com/photo-1724054913772-afffd0933162?w=900&auto=format&fit=crop',
    'switch-socket': 'https://images.unsplash.com/photo-1621905251189-08b45d6a269e?w=900&auto=format&fit=crop',
    'switch-socket-services': 'https://images.unsplash.com/photo-1621905251189-08b45d6a269e?w=900&auto=format&fit=crop',
    'wiring-services': 'https://images.unsplash.com/photo-1621905251189-08b45d6a269e?w=900&auto=format&fit=crop',
    'wiring-electrical-repairs': 'https://images.unsplash.com/photo-1621905251189-08b45d6a269e?w=900&auto=format&fit=crop',
    'inverter-ups': 'https://images.unsplash.com/photo-1621905251918-48416bd8575a?w=900&auto=format&fit=crop',
    'geyser-electrical-connections': 'https://images.unsplash.com/photo-1621905251918-48416bd8575a?w=900&auto=format&fit=crop',
    'electrical-inspection-setup': 'https://images.unsplash.com/photo-1621905251918-48416bd8575a?w=900&auto=format&fit=crop',
  };

  static String? forCategory({required String slug, required String title}) {
    final normalized = slug.trim().toLowerCase();
    final exact = _images[normalized];
    if (exact != null) return exact;

    final text = '$normalized ${title.trim().toLowerCase()}';
    if (text.contains('bathroom') || text.contains('washroom')) return _images['bathroom-cleaning'];
    if (text.contains('kitchen')) return _images['kitchen-cleaning'];
    if (text.contains('sofa') || text.contains('upholstery') || text.contains('cushion')) return _images['specific-item'];
    if (text.contains('mattress') || text.contains('bedroom')) return _images['mattress-cleaning'];
    if (text.contains('carpet') || text.contains('rug')) return _images['carpet-rug-cleaning'];
    if (text.contains('fan')) return _images['fan-services'];
    if (text.contains('light') || text.contains('bulb')) return _images['lighting-services'];
    if (text.contains('switch') || text.contains('socket') || text.contains('wiring') || text.contains('electrical')) return _images['electrical'];
    if (text.contains('bike') || text.contains('scooter') || text.contains('motorcycle')) return _images['bike'];
    if (text.contains('car') || text.contains('vehicle') || text.contains('wash')) return _images['car-wash'];
    if (text.contains('clean') || text.contains('home') || text.contains('room')) return _images['home-cleaning'];
    if (text.contains('beauty') || text.contains('hair') || text.contains('skin') || text.contains('nail')) return _images['beauty'];
    return null;
  }
}
