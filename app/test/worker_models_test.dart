import 'package:airway/features/worker/data/worker_models.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('WorkerProfile', () {
    test('parses rating_avg returned by DRF as a decimal string', () {
      final profile = WorkerProfile.fromMap({
        'id': 12,
        'status': 'approved',
        'is_online': true,
        'rating_avg': '4.75',
      });

      expect(profile.ratingAvg, 4.75);
      expect(profile.isOnline, isTrue);
      expect(profile.status, 'approved');
    });

    test('accepts numeric rating values for API compatibility', () {
      final integerRating = WorkerProfile.fromMap({
        'id': 13,
        'status': 'approved',
        'is_online': false,
        'rating_avg': 5,
      });
      final doubleRating = WorkerProfile.fromMap({
        'id': 14,
        'status': 'approved',
        'is_online': false,
        'rating_avg': 4.5,
      });

      expect(integerRating.ratingAvg, 5.0);
      expect(doubleRating.ratingAvg, 4.5);
    });

    test('keeps missing or invalid ratings null instead of crashing', () {
      final missing = WorkerProfile.fromMap({
        'id': 15,
        'status': 'pending',
        'is_online': false,
      });
      final invalid = WorkerProfile.fromMap({
        'id': 16,
        'status': 'pending',
        'is_online': false,
        'rating_avg': 'not-a-number',
      });

      expect(missing.ratingAvg, isNull);
      expect(invalid.ratingAvg, isNull);
    });
  });
}
