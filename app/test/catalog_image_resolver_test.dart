import 'package:airway/features/catalog/data/catalog_image_resolver.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('CatalogImageResolver electrical catalogue coverage', () {
    const electricalGroups = <String, List<String>>{
      'Fan Services': [
        'Ceiling Fan', 'Wall Fan', 'Exhaust Fan', 'Decorative Fan',
      ],
      'Lighting Services': [
        'Bulb', 'LED', 'Tube Light', 'Panel Light', 'Ceiling Light',
        'Wall Light', 'Chandelier', 'Decorative Lights', 'Outdoor Lights',
        'Strip Lights',
      ],
      'Switch & Socket Services': [
        'Switch', 'Socket', 'Switchboard', 'Plug Point', 'USB Socket',
        'Doorbell', 'Loose Connection', 'Burnt Socket',
      ],
      'Wiring & Electrical Repairs': [
        'New Wiring', 'Old Wiring Replacement', 'Wiring Repair',
        'Short Circuit Diagnosis', 'Power Failure Diagnosis',
        'MCB Installation', 'MCB Tripping Repair', 'Fuse Replacement',
        'Earthing Work', 'RCCB / ELCB Installation',
        'Voltage Fluctuation Diagnosis',
      ],
      'Inverter & UPS': [
        'Inverter Installation', 'Inverter Repair', 'Inverter Wiring',
        'Battery Installation', 'Battery Replacement', 'UPS Installation',
        'UPS Repair', 'Charging Problem Diagnosis',
      ],
      'Geyser & Electrical Connections': [
        'Geyser Installation', 'Geyser Electrical Connection',
        'Geyser Switch Replacement', 'Geyser Power Problem',
        'Water Pump Electrical Connection', 'Motor Wiring',
        'Motor Starter Repair',
      ],
      'Electrical Inspection & Setup': [
        'Full Home Electrical Inspection', 'Electrical Safety Check',
        'New Room Electrical Setup', 'Additional Power Point',
        'Decorative Electrical Setup', 'Smart Switch Installation',
        'Smart Light Installation',
      ],
    };

    test('every seeded electrical service resolves an image fallback', () {
      for (final entry in electricalGroups.entries) {
        for (final title in entry.value) {
          expect(
            CatalogImageResolver.forService(
              title: title,
              categoryName: entry.key,
            ),
            isNotNull,
            reason: '${entry.key} / $title has no fallback image rule',
          );
        }
      }
    });
  });

  group('CatalogImageResolver beauty audience handling', () {
    test('men audience does not replace a nail-service image with barber photo', () {
      final image = CatalogImageResolver.forService(
        title: 'Nail Art',
        categoryName: 'Manicure & Pedicure',
        audience: 'men',
      );
      expect(image, contains('1610992015732-2449b76344bc'));
    });

    test('women audience does not replace a facial image with salon photo', () {
      final image = CatalogImageResolver.forService(
        title: 'Fruit Facial',
        categoryName: 'Facial & Skin Care',
        audience: 'women',
      );
      expect(image, contains('1570172619644-dfd03ed5d881'));
    });

    test('men hair service still uses men-specific hair image', () {
      final image = CatalogImageResolver.forService(
        title: "Men's Haircut",
        categoryName: 'Hair Services',
        audience: 'men',
      );
      expect(image, contains('1503951914875-452162b0f3f1'));
    });
  });
}
