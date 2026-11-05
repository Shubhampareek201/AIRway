from django.contrib import admin

from apps.ratings.models import BookingRating, RatingSummary


@admin.register(BookingRating)
class BookingRatingAdmin(admin.ModelAdmin):
    list_display = ['id', 'rating_type', 'rating', 'rater', 'rated', 'booking']
    list_filter = ['rating_type', 'rating']
    search_fields = ['rater__phone', 'rated__phone', 'comment']
    date_hierarchy = 'created_at'


@admin.register(RatingSummary)
class RatingSummaryAdmin(admin.ModelAdmin):
    list_display = ['user', 'average_rating', 'total_ratings']
    search_fields = ['user__phone']
