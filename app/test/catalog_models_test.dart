import 'package:airway/features/catalog/data/catalog_models.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('ServiceVariant', () {
    test('fromMap parses all fields correctly', () {
      final map = {
        'id': 1,
        'title': 'Hatchback',
        'title_hi': 'ہیشبیک',
        'mrp': '399.00',
        'price': '299.00',
        'discount_percent': 25,
        'duration_minutes': 45,
        'sort_order': 1,
        'is_active': true,
      };
      final v = ServiceVariant.fromMap(map);
      expect(v.id, 1);
      expect(v.title, 'Hatchback');
      expect(v.titleHi, 'ہیشبیک');
      expect(v.mrp, 399.00);
      expect(v.price, 299.00);
      expect(v.discountPercent, 25);
      expect(v.durationMinutes, 45);
      expect(v.isActive, true);
    });

    test('fromMap handles missing optional fields', () {
      final map = {'id': 2, 'title': 'Sedan', 'mrp': '499.00', 'price': '399.00', 'discount_percent': 0, 'sort_order': 2, 'is_active': true};
      final v = ServiceVariant.fromMap(map);
      expect(v.durationMinutes, isNull);
      expect(v.titleHi, isNull);
    });
  });

  group('AddOn', () {
    test('fromMap parses correctly', () {
      final map = {
        'id': 1,
        'title': 'Extra Cleaning',
        'mrp': '150.00',
        'price': '100.00',
        'discount_percent': 33,
        'sort_order': 1,
        'is_active': true,
      };
      final a = AddOn.fromMap(map);
      expect(a.id, 1);
      expect(a.title, 'Extra Cleaning');
      expect(a.price, 100.00);
      expect(a.mrp, 150.00);
      expect(a.discountPercent, 33);
    });
  });

  group('Service', () {
    test('fromMap parses nested variants and addons', () {
      final map = {
        'id': 1,
        'category': 1,
        'category_name': 'Car Wash',
        'category_slug': 'car-wash',
        'title': 'Exterior Car Wash',
        'title_hi': 'एक्स्टीरियर कार वॉश',
        'description': 'Exterior car washing',
        'image': null,
        'booking_mode': 'scheduled',
        'booking_mode_display': 'Scheduled',
        'pricing_type': 'fixed',
        'pricing_type_display': 'Fixed price',
        'unit_label': 'sq ft',
        'visit_fee': '0.00',
        'duration_minutes': 45,
        'buffer_minutes': 13,
        'audience': 'all',
        'audience_display': 'All',
        'requires_female_worker': false,
        'is_popular': true,
        'sort_order': 0,
        'is_active': true,
        'images': [],
        'variants': [
          {'id': 1, 'title': 'Hatchback', 'title_hi': 'हैचबैक', 'mrp': '399.00', 'price': '299.00', 'discount_percent': 25, 'duration_minutes': 45, 'sort_order': 1, 'is_active': true}
        ],
        'addons': [],
        'form_fields': [],
        'created_at': '2026-10-27T00:35:46.356348+05:30',
        'updated_at': '2026-10-27T00:35:46.356404+05:30',
      };
      final s = Service.fromMap(map);
      expect(s.id, 1);
      expect(s.categoryName, 'Car Wash');
      expect(s.categorySlug, 'car-wash');
      expect(s.isPopular, true);
      expect(s.supportsProfessionalPreference, false);
      expect(s.variants.length, 1);
      expect(s.variants.first.title, 'Hatchback');
      expect(s.addons.isEmpty, true);
      expect(s.formFields.isEmpty, true);
    });

    test('fromMap reads Beauty professional preference capability', () {
      final map = {
        'id': 8, 'category': 3, 'category_name': 'Beauty',
        'category_slug': 'beauty', 'title': 'Facial',
        'booking_mode': 'scheduled', 'booking_mode_display': 'Scheduled',
        'pricing_type': 'fixed', 'pricing_type_display': 'Fixed price',
        'unit_label': '', 'visit_fee': '0.00', 'duration_minutes': 60,
        'buffer_minutes': 30, 'audience': 'all', 'audience_display': 'All',
        'requires_female_worker': false,
        'supports_professional_preference': true,
        'is_popular': false, 'sort_order': 0, 'is_active': true,
        'images': [], 'variants': [], 'addons': [], 'form_fields': [],
        'created_at': '', 'updated_at': '',
      };
      final service = Service.fromMap(map);
      expect(service.supportsProfessionalPreference, isTrue);
    });

    test('fromMap handles empty nested lists', () {
      final map = {
        'id': 2, 'category': 5, 'category_name': 'Cleaning', 'category_slug': 'cleaning',
        'title': 'Home Cleaning', 'booking_mode': 'scheduled', 'booking_mode_display': 'Scheduled',
        'pricing_type': 'fixed', 'pricing_type_display': 'Fixed price',
        'unit_label': '', 'visit_fee': '0.00', 'duration_minutes': 60, 'buffer_minutes': 30,
        'audience': 'all', 'audience_display': 'Sab', 'requires_female_worker': false,
        'is_popular': true, 'sort_order': 0, 'is_active': true,
        'images': [], 'variants': [], 'addons': [], 'form_fields': [],
        'created_at': '2026-11-01T01:20:24.807410+05:30', 'updated_at': '2026-11-01T01:20:24.837741+05:30',
      };
      final s = Service.fromMap(map);
      expect(s.variants.isEmpty, true);
      expect(s.addons.isEmpty, true);
      expect(s.formFields.isEmpty, true);
      expect(s.isActive, true);
    });

    test('fromMap handles QA Admin Test Service with multiple addons', () {
      final map = {
        'id': 6, 'category': 7, 'category_name': 'QA Test Category', 'category_slug': 'qa-test-category',
        'title': 'QA Admin Test Service', 'title_hi': 'QA एडमिन टेस्ट सर्विस',
        'description': 'Created through Django Admin form',
        'booking_mode': 'scheduled', 'booking_mode_display': 'Scheduled (slot book karo)',
        'pricing_type': 'fixed', 'pricing_type_display': 'Fixed price',
        'unit_label': 'sq ft', 'visit_fee': '50.00', 'duration_minutes': 90, 'buffer_minutes': 15,
        'audience': 'all', 'audience_display': 'Sab', 'requires_female_worker': false,
        'is_popular': true, 'sort_order': 51, 'is_active': true,
        'images': [],
        'variants': [
          {'id': 3, 'title': 'QA Admin Premium', 'title_hi': 'QA एडमिन प्रीमियम', 'mrp': '1099.00', 'price': '899.00', 'discount_percent': 18, 'duration_minutes': 120, 'sort_order': 1, 'is_active': true}
        ],
        'addons': [
          {'id': 3, 'title': 'QA Admin Deep Clean', 'title_hi': '', 'mrp': '200.00', 'price': '150.00', 'discount_percent': 25, 'sort_order': 1, 'is_active': true}
        ],
        'form_fields': [],
        'created_at': '2026-11-02T10:29:16.615263+05:30',
        'updated_at': '2026-11-02T10:29:16.615302+05:30',
      };
      final s = Service.fromMap(map);
      expect(s.id, 6);
      expect(s.title, 'QA Admin Test Service');
      expect(s.categoryName, 'QA Test Category');
      expect(s.visitFee, 50.00);
      expect(s.variants.length, 1);
      expect(s.variants.first.price, 899.00);
      expect(s.addons.length, 1);
      expect(s.addons.first.price, 150.00);
    });
  });

  group('Category', () {
    test('Beauty root does not show the legacy duplicate audience form', () {
      final category = Category.fromMap({
        'id': 6,
        'title': 'Beauty',
        'slug': 'beauty',
        'parent': null,
        'image': null,
        'flow_steps': [],
        'is_active': true,
        'children': [],
      });
      expect(category.customerFlowSteps, isEmpty);
    });

    test('fromMap parses correctly', () {
      final map = {'id': 1, 'title': 'Car Wash', 'title_hi': null, 'slug': 'car-wash', 'image': null, 'is_active': true};
      final c = Category.fromMap(map);
      expect(c.id, 1);
      expect(c.title, 'Car Wash');
      expect(c.slug, 'car-wash');
      expect(c.isActive, true);
    });
  });

  group('CatalogFormField', () {
    test('fromMap parses correctly', () {
      final map = {
        'id': 1, 'key': 'address', 'label': 'Address', 'label_hi': 'पता',
        'field_type': 'text', 'field_type_display': 'Text',
        'options': [], 'is_required': true, 'sort_order': 1,
      };
      final f = CatalogFormField.fromMap(map);
      expect(f.key, 'address');
      expect(f.label, 'Address');
      expect(f.isRequired, true);
      expect(f.options.isEmpty, true);
    });

    test('fromMap parses conditional visibility rules', () {
      final f = CatalogFormField.fromMap({
        'id': 2,
        'key': 'seat_count',
        'label': 'Seat count',
        'field_type': 'number',
        'field_type_display': 'Number',
        'options': [],
        'is_required': true,
        'visibility_rules': [
          {'field': 'vehicle_type', 'operator': 'equals', 'value': 'SUV'},
        ],
        'sort_order': 2,
      });

      expect(f.visibilityRules, hasLength(1));
      expect(f.visibilityRules.first['field'], 'vehicle_type');
      expect(f.visibilityRules.first['value'], 'SUV');
      expect(f.isVisibleFor({'vehicle_type': 'SUV'}), isTrue);
      expect(f.isVisibleFor({'vehicle_type': 'Sedan'}), isFalse);
      expect(f.isVisibleFor({}), isFalse);
    });
  });
}
