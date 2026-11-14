from django.urls import path, include
from rest_framework.routers import DefaultRouter

from apps.ratings.views import BookingRatingViewSet, RatingSummaryViewSet

router = DefaultRouter()
router.register(r'', BookingRatingViewSet, basename='bookingrating')
router.register(r'summaries', RatingSummaryViewSet, basename='ratingsummary')

urlpatterns = [
    path('', include(router.urls)),
]