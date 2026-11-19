from django.contrib import admin

from apps.ratings.models import BookingCompletionFeedback, BookingRating, RatingSummary


@admin.register(BookingRating)
class BookingRatingAdmin(admin.ModelAdmin):
    list_display = ['id', 'rating_type', 'rating', 'rater', 'rated', 'booking']
    list_filter = ['rating_type', 'rating']
    search_fields = ['rater__phone', 'rated__phone', 'comment']
    date_hierarchy = 'created_at'


@admin.register(BookingCompletionFeedback)
class BookingCompletionFeedbackAdmin(admin.ModelAdmin):
    list_display = [
        "booking", "customer", "service_quality", "worker_behaviour",
        "satisfaction_level", "skipped", "submitted_at",
    ]
    list_filter = ["skipped", "satisfaction_level"]
    search_fields = ["booking__id", "customer__phone", "comment"]
    readonly_fields = [
        "booking", "customer", "service_quality", "worker_behaviour",
        "satisfaction_level", "comment", "skipped", "submitted_at", "updated_at",
    ]


@admin.register(RatingSummary)
class RatingSummaryAdmin(admin.ModelAdmin):
    list_display = ['user', 'average_rating', 'total_ratings']
    search_fields = ['user__phone']
