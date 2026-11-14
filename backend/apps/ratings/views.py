from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.bookings.models import Booking
from apps.ratings.models import BookingRating, RatingSummary
from apps.ratings.serializers import (
    BookingRatingSerializer,
    RatingSummarySerializer,
    RateBookingSerializer,
)


class BookingRatingViewSet(viewsets.ModelViewSet):
    serializer_class = BookingRatingSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        user = self.request.user
        return BookingRating.objects.filter(
            Q(booking__customer=user)
            | Q(booking__assignment__worker__user=user)
        ).select_related("booking", "rater", "rated")

    def create(self, request, *args, **kwargs):
        return Response(
            {"detail": "Submit a rating through the booking rating endpoint."},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    @action(detail=True, methods=["post"], url_path="rating")
    def rate_booking(self, request, pk=None):
        # The router's pk here is a Booking ID, not a BookingRating ID.
        booking = get_object_or_404(
            Booking.objects.select_related(
                "customer", "assignment__worker__user"
            ),
            pk=pk,
        )

        if booking.status != Booking.Status.COMPLETED:
            return Response(
                {"detail": "A booking can be rated only after it is completed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            assignment = booking.assignment
        except ObjectDoesNotExist:
            return Response(
                {"detail": "This booking has no completed worker assignment."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if request.user.pk == booking.customer_id:
            expected_type = "customer"
            expected_rated_id = assignment.worker.user_id
        elif request.user.pk == assignment.worker.user_id:
            expected_type = "worker"
            expected_rated_id = booking.customer_id
        else:
            return Response(
                {"detail": "You are not a participant in this booking."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = RateBookingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data["rating_type"] != expected_type:
            return Response(
                {"detail": "The rating type does not match your role in this booking."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        requested_rated_id = request.data.get("rated_id")
        if requested_rated_id not in (None, "") and str(requested_rated_id) != str(expected_rated_id):
            return Response(
                {"detail": "You can rate only the other participant in this booking."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if serializer.validated_data["rated_id"] != expected_rated_id:
            return Response(
                {"detail": "You can rate only the other participant in this booking."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                rating = BookingRating.objects.create(
                    booking=booking,
                    rater=request.user,
                    rated_id=expected_rated_id,
                    rating_type=expected_type,
                    rating=serializer.validated_data["rating"],
                    comment=serializer.validated_data.get("comment", ""),
                )
        except IntegrityError:
            return Response(
                {"detail": "You have already rated this booking."},
                status=status.HTTP_409_CONFLICT,
            )

        return Response(
            BookingRatingSerializer(rating, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )


class RatingSummaryViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = RatingSummarySerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        # A user's rating summary is private to that authenticated account.
        return RatingSummary.objects.filter(user=self.request.user)

    @action(detail=False, methods=["get"], url_path="user-ratings")
    def user_ratings(self, request):
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return Response(serializer.data)
