/// Shared audience rules for the Beauty catalogue.
class BeautyAudience {
  static const men = 'men';
  static const women = 'women';
  static const both = 'both';

  static bool includes({
    required String selected,
    required String serviceAudience,
  }) {
    switch (selected) {
      case men:
        return serviceAudience == 'men' || serviceAudience == 'all';
      case women:
        return serviceAudience == 'women' || serviceAudience == 'all';
      case both:
        return serviceAudience == 'all';
      default:
        return true;
    }
  }
}
