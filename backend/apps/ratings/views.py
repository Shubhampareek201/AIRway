from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from apps.ratings.models import BookingRating, RatingSummary
from apps.ratings.serializers import (
    BookingRatingSerializer,
    RatingSummarySerializer,
    RateBookingSerializer,
)


class BookingRatingViewSet(viewsets.ModelViewSet):
    queryset = BookingRating.objects.all()
    serializer_class = BookingRatingSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(rater=self.request.user)

    @action(detail=True, methods=['post'], url_path='rating')
    def rate_booking(self, request, pk=None):
        booking = self.get_object()
        serializer = RateBookingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        rating_type = request.data.get('rating_type', 'customer')
        rated_id = request.data.get('rated_id')

        if not rated_id:
            return Response(
                {'detail': 'rated_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        rating = self.get_queryset().create(
            booking=booking,
            rater=request.user,
            rated_id=rated_id,
            rating_type=rating_type,
            comment=serializer.validated_data.get('comment', ''),
        )

        return Response(BookingRatingSerializer(rating).data, status=status.HTTP_201_CREATED)


class RatingSummaryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = RatingSummary.objects.all()
    serializer_class = RatingSummarySerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'], url_path='user-ratings')
    def user_ratings(self, request):
        user_ids = request.query_params.getlist('user_ids')
        if user_ids:
            queryset = self.get_queryset().filter(user_id__in=user_ids)
        else:
            queryset = self.get_queryset().filter(user=request.user)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)