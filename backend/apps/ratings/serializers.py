from rest_framework import serializers

from apps.ratings.models import BookingRating, RatingSummary


class BookingRatingSerializer(serializers.ModelSerializer):
    rating_type_display = serializers.CharField(
        source="get_rating_type_display",
        read_only=True,
    )

    class Meta:
        model = BookingRating
        fields = [
            "id", "rating_type", "rating_type_display", "booking",
            "rater", "rated", "rating", "comment", "created_at",
        ]
        read_only_fields = fields


class RatingSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = RatingSummary
        fields = ["average_rating", "total_ratings", "created_at", "updated_at"]
        read_only_fields = fields


class RateBookingSerializer(serializers.Serializer):
    rated_id = serializers.IntegerField(min_value=1)
    rating_type = serializers.ChoiceField(choices=BookingRating._meta.get_field("rating_type").choices)
    rating = serializers.IntegerField(min_value=1, max_value=5)
    comment = serializers.CharField(max_length=500, required=False, allow_blank=True)
