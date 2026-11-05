from rest_framework import serializers

from apps.ratings.models import BookingRating, RatingSummary


class BookingRatingSerializer(serializers.ModelSerializer):
    rating_type_display = serializers.CharField(
        source='get_rating_type_display',
        read_only=True
    )
    rater_phone = serializers.CharField(source='rater.phone', read_only=True)
    rated_phone = serializers.CharField(source='rated.phone', read_only=True)

    class Meta:
        model = BookingRating
        fields = [
            'id', 'rating_type', 'rating_type_display', 'booking',
            'rater', 'rater_phone', 'rated', 'rated_phone',
            'rating', 'comment', 'created_at'
        ]
        read_only_fields = ['id', 'booking', 'rater', 'created_at']


class RatingSummarySerializer(serializers.ModelSerializer):
    user_phone = serializers.CharField(source='user.phone', read_only=True)

    class Meta:
        model = RatingSummary
        fields = [
            'user_phone', 'average_rating', 'total_ratings',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['user', 'average_rating', 'total_ratings', 'created_at', 'updated_at']


class RateBookingSerializer(serializers.Serializer):
    rating = serializers.IntegerField(min_value=1, max_value=5)
    comment = serializers.CharField(max_length=500, required=False, allow_blank=True)