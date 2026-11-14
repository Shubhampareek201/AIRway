class RatingModel {
  final int id;
  final int bookingId;
  final String ratingType;
  final String ratingTypeDisplay;
  final int raterId;
  final String raterPhone;
  final int ratedId;
  final String ratedPhone;
  final int rating;
  final String comment;
  final String createdAt;

  RatingModel({
    required this.id,
    required this.bookingId,
    required this.ratingType,
    required this.ratingTypeDisplay,
    required this.raterId,
    required this.raterPhone,
    required this.ratedId,
    required this.ratedPhone,
    required this.rating,
    required this.comment,
    required this.createdAt,
  });

  factory RatingModel.fromMap(Map<String, dynamic> map) {
    return RatingModel(
      id: map['id'] as int,
      bookingId: map['booking'] as int? ?? 0,
      ratingType: (map['rating_type'] as String?) ?? '',
      ratingTypeDisplay: (map['rating_type_display'] as String?) ?? '',
      raterId: map['rater'] as int? ?? 0,
      raterPhone: (map['rater_phone'] as String?) ?? '',
      ratedId: map['rated'] as int? ?? 0,
      ratedPhone: (map['rated_phone'] as String?) ?? '',
      rating: map['rating'] as int? ?? 0,
      comment: (map['comment'] as String?) ?? '',
      createdAt: (map['created_at'] as String?) ?? '',
    );
  }

  Map<String, dynamic> toMap() {
    return {
      'rating': rating,
      'comment': comment,
    };
  }
}

class RatingSummaryModel {
  final int userId;
  final String userPhone;
  final double averageRating;
  final int totalRatings;
  final String createdAt;
  final String updatedAt;

  RatingSummaryModel({
    required this.userId,
    required this.userPhone,
    required this.averageRating,
    required this.totalRatings,
    required this.createdAt,
    required this.updatedAt,
  });

  factory RatingSummaryModel.fromMap(Map<String, dynamic> map) {
    return RatingSummaryModel(
      userId: map['user'] as int? ?? 0,
      userPhone: (map['user_phone'] as String?) ?? '',
      averageRating: double.tryParse((map['average_rating'] ?? 0).toString()) ?? 0,
      totalRatings: map['total_ratings'] as int? ?? 0,
      createdAt: (map['created_at'] as String?) ?? '',
      updatedAt: (map['updated_at'] as String?) ?? '',
    );
  }
}

class RateBookingRequest {
  final int ratedId;
  final String ratingType;
  final int rating;
  final String comment;

  RateBookingRequest({
    required this.ratedId,
    required this.ratingType,
    required this.rating,
    required this.comment,
  });

  Map<String, dynamic> toMap() {
    return {
      'rated_id': ratedId,
      'rating_type': ratingType,
      'rating': rating,
      'comment': comment,
    };
  }
}