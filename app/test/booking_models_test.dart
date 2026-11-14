import 'package:airway/features/booking/data/booking_models.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('BookingStatus', () {
    test('display returns correct labels', () {
      expect(BookingStatus.display('pending'), 'Pending');
      expect(BookingStatus.display('confirmed'), 'Confirmed');
      expect(BookingStatus.display('assigned'), 'Assigned');
      expect(BookingStatus.display('in_progress'), 'In Progress');
      expect(BookingStatus.display('completed'), 'Completed');
      expect(BookingStatus.display('cancelled'), 'Cancelled');
      expect(BookingStatus.display('disputed'), 'Disputed');
      expect(BookingStatus.display('unknown'), 'unknown');
    });
  });

  group('PaymentMethod', () {
    test('display returns correct labels', () {
      expect(PaymentMethod.display('cod'), 'Cash on Delivery');
      expect(PaymentMethod.display('razorpay'), 'Razorpay');
      expect(PaymentMethod.display('unknown'), 'unknown');
    });
  });

  group('BookingAddOn', () {
    test('fromMap parses correctly', () {
      final map = {
        'id': 1, 'addon': 1, 'addon_title': 'Extra Cleaning',
        'quantity': 2, 'unit_price': '100.00', 'total_price': '200.00',
      };
      final a = BookingAddOn.fromMap(map);
      expect(a.addonId, 1);
      expect(a.addonTitle, 'Extra Cleaning');
      expect(a.quantity, 2);
      expect(a.unitPrice, 100.00);
      expect(a.totalPrice, 200.00);
    });
  });

  group('BookingFormResponse', () {
    test('fromMap parses correctly', () {
      final map = {
        'id': 1, 'form_field': 1, 'field_key': 'address',
        'field_label': 'Address', 'field_type': 'text', 'value': '123 Main St',
      };
      final f = BookingFormResponse.fromMap(map);
      expect(f.formFieldId, 1);
      expect(f.fieldKey, 'address');
      expect(f.fieldLabel, 'Address');
      expect(f.value, '123 Main St');
    });
  });

  group('BookingStatusHistory', () {
    test('fromMap parses correctly', () {
      final map = {
        'id': 1, 'from_status': 'pending', 'to_status': 'confirmed',
        'changed_by_name': 'Shubham', 'note': 'Auto-confirmed',
        'created_at': '2026-11-02T10:00:00+05:30',
      };
      final h = BookingStatusHistory.fromMap(map);
      expect(h.fromStatus, 'pending');
      expect(h.toStatus, 'confirmed');
      expect(h.changedByName, 'Shubham');
      expect(h.note, 'Auto-confirmed');
      expect(h.createdAt.year, 2026);
    });
  });

  group('BookingAssignment', () {
    test('fromMap parses with all fields', () {
      final map = {
        'id': 1, 'worker': 2, 'worker_name': 'Test Worker',
        'worker_phone': '+919999999998', 'worker_rating': '4.5',
        'worker_photo': null, 'assigned_at': '2026-11-02T09:00:00+05:30',
        'accepted_at': '2026-11-02T09:05:00+05:30',
        'started_at': null, 'completed_at': null,
      };
      final a = BookingAssignment.fromMap(map);
      expect(a.workerId, 2);
      expect(a.workerName, 'Test Worker');
      expect(a.workerPhone, '+919999999998');
      expect(a.workerRating, 4.5);
      expect(a.workerPhoto, isNull);
      expect(a.acceptedAt, isNotNull);
      expect(a.startedAt, isNull);
    });

    test('fromMap handles null optional fields', () {
      final map = {
        'id': 2, 'worker': 3, 'worker_name': 'Worker B',
        'worker_phone': '+919876543210', 'worker_rating': null,
        'worker_photo': null, 'assigned_at': '2026-11-02T10:00:00+05:30',
        'accepted_at': null, 'started_at': null, 'completed_at': null,
      };
      final a = BookingAssignment.fromMap(map);
      expect(a.workerRating, isNull);
      expect(a.acceptedAt, isNull);
    });
  });

  group('Booking', () {
    test('fromMap parses full booking with all fields', () {
      final map = {
        'id': 1, 'service': 1, 'service_title': 'Exterior Car Wash',
        'service_image': null, 'variant': 1, 'variant_title': 'Hatchback',
        'booking_mode': 'scheduled', 'status': 'pending',
        'scheduled_at': '2026-11-05T10:00:00+05:30',
        'drop_scheduled_at': null,
        'pricing_snapshot': {
          'subtotal': '299.00', 'addons_total': '100.00',
          'visit_fee': '0.00', 'tax': '71.88', 'total': '470.88',
        },
        'addons': [
          {'id': 1, 'addon': 1, 'addon_title': 'Extra Cleaning', 'quantity': 1, 'unit_price': '100.00', 'total_price': '100.00'}
        ],
        'form_responses': [
          {'id': 1, 'form_field': 1, 'field_key': 'address', 'field_label': 'Address', 'field_type': 'text', 'value': '123 Main St'}
        ],
        'status_history': [
          {'id': 1, 'from_status': '', 'to_status': 'pending', 'changed_by_name': null, 'note': 'Created', 'created_at': '2026-11-02T10:00:00+05:30'}
        ],
        'assignment': null, 'can_cancel': true,
      };
      final b = Booking.fromMap(map);
      expect(b.id, 1);
      expect(b.serviceId, 1);
      expect(b.serviceTitle, 'Exterior Car Wash');
      expect(b.variantId, 1);
      expect(b.bookingMode, 'scheduled');
      expect(b.status, 'pending');
      expect(b.canCancel, true);
      expect(b.totalAmount, 470.88);
      expect(b.addons.length, 1);
      expect(b.addons.first.addonTitle, 'Extra Cleaning');
      expect(b.formResponses.length, 1);
      expect(b.statusHistory.length, 1);
      expect(b.assignment, isNull);
    });

    test('fromMap handles booking without variant or assignment', () {
      final map = {
        'id': 2, 'service': 2, 'service_title': 'Home Cleaning',
        'service_image': null, 'variant': null, 'variant_title': null,
        'booking_mode': 'scheduled', 'status': 'confirmed',
        'scheduled_at': '2026-11-06T14:00:00+05:30',
        'drop_scheduled_at': null,
        'pricing_snapshot': {'subtotal': '0.00', 'addons_total': '0.00', 'visit_fee': '50.00', 'tax': '9.00', 'total': '59.00'},
        'addons': [], 'form_responses': [], 'status_history': [],
        'assignment': null, 'can_cancel': true,
      };
      final b = Booking.fromMap(map);
      expect(b.variantId, isNull);
      expect(b.variantTitle, isNull);
      expect(b.addons.isEmpty, true);
      expect(b.formResponses.isEmpty, true);
      expect(b.statusHistory.isEmpty, true);
      expect(b.totalAmount, 59.00);
    });
  });
}
