from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.core.exceptions import ObjectDoesNotExist

from .models import Booking, BookingStatusHistory, CustomerCart, CartItem
from .serializers import (
    BookingCreateSerializer,
    BookingListSerializer,
    BookingDetailSerializer,
    BookingCancelSerializer,
    BookingAvailabilitySerializer,
)
from .services import check_slot_availability, check_service_available, create_worker_offers_for_booking, SlotConflictError, ServiceUnavailableError
from apps.notifications.models import Notification
from apps.accounts.models import Address


class BookingViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        queryset = Booking.objects.filter(customer=user).select_related(
            "service", "variant", "address", "assignment__worker__user"
        ).prefetch_related(
            "booking_addons__addon", "form_responses__form_field", "status_history"
        )

        status_param = self.request.query_params.get("status")
        if status_param:
            queryset = queryset.filter(status=status_param)

        return queryset

    def get_serializer_class(self):
        if self.action == "create":
            return BookingCreateSerializer
        elif self.action == "list":
            return BookingListSerializer
        return BookingDetailSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        booking = serializer.save()

        detail_serializer = BookingDetailSerializer(booking, context={"request": request})
        return Response(detail_serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        from apps.bookings.models import WorkerOffer

        booking = self.get_object()
        serializer = BookingCancelSerializer(data=request.data, context={"booking": booking})
        serializer.is_valid(raise_exception=True)

        reason = serializer.validated_data.get("reason", "")
        old_status = booking.status

        booking.status = Booking.Status.CANCELLED
        booking.cancelled_at = timezone.now()
        booking.cancellation_reason = reason
        booking.cancelled_by = request.user
        booking.save()

        BookingStatusHistory.objects.create(
            booking=booking,
            from_status=old_status,
            to_status=Booking.Status.CANCELLED,
            changed_by=request.user,
            note=f"Cancelled by customer. Reason: {reason}",
        )

        # Cancel all pending worker offers for this booking
        WorkerOffer.objects.filter(booking=booking, status=WorkerOffer.Status.PENDING).update(
            status=WorkerOffer.Status.EXPIRED,
            responded_at=timezone.now(),
        )

        Notification.objects.create(
            user=request.user,
            type=Notification.Type.BOOKING_CANCELLED,
            title="Booking Cancelled",
            body="Your booking has been cancelled.",
            channel=Notification.Channel.IN_APP,
            data={"booking_id": booking.id},
        )

        return Response({"detail": "Booking cancelled successfully.", "status": booking.status})

    @action(detail=True, methods=["post"], url_path="confirm")
    def confirm_booking(self, request, pk=None):
        """Confirm a booking and trigger worker offer creation."""
        from apps.notifications.models import Notification

        booking = self.get_object()

        if booking.customer != request.user:
            return Response(
                {"detail": "Only the booking owner can confirm this booking."},
                status=status.HTTP_403_FORBIDDEN
            )

        if booking.status != Booking.Status.PENDING:
            return Response(
                {"detail": f"Booking cannot be confirmed in {booking.get_status_display()} state."},
                status=status.HTTP_400_BAD_REQUEST
            )

        old_status = booking.status
        booking.status = Booking.Status.CONFIRMED
        booking.save()

        BookingStatusHistory.objects.create(
            booking=booking,
            from_status=old_status,
            to_status=Booking.Status.CONFIRMED,
            changed_by=request.user,
            note="Customer confirmed booking",
        )

        # Create worker offers for this booking
        offers = create_worker_offers_for_booking(booking)

        # Notify customer about confirm
        Notification.objects.create(
            user=booking.customer,
            type=Notification.Type.BOOKING_CONFIRMED,
            title="Booking Confirmed",
            body="Your booking is confirmed. A worker will be assigned soon.",
            channel=Notification.Channel.IN_APP,
            data={"booking_id": booking.id},
        )

        return Response({
            "detail": "Booking confirmed and worker offers created.",
            "status": booking.status,
            "offers_count": len(offers),
        })

    @action(detail=False, methods=["post"])
    def check_availability(self, request, pk=None):
        """Check if a slot is available for booking."""
        serializer = BookingAvailabilitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        service = data["service_obj"]
        variant = data["variant"]
        booking_mode = data["booking_mode"]
        scheduled_at = data["scheduled_at"]
        drop_scheduled_at = data.get("drop_scheduled_at")

        try:
            check_service_available(
                service=service,
                address=None,
                audience=data.get("audience", "all"),
            )

            duration = variant.duration_minutes if variant else service.duration_minutes

            check_slot_availability(
                service=service,
                scheduled_at=scheduled_at,
                duration_minutes=duration or 60,
                booking_mode=booking_mode,
                drop_scheduled_at=drop_scheduled_at,
            )

            return Response({"available": True, "message": "Slot is available for booking."})

        except SlotConflictError as e:
            return Response(
                {"available": False, "message": str(e)},
                status=status.HTTP_409_CONFLICT,
            )
        except ServiceUnavailableError as e:
            return Response(
                {"available": False, "message": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=True, methods=["get", "post"])
    def track(self, request, pk=None):
        booking = self.get_object()

        if not hasattr(booking, "assignment") or not booking.assignment:
            return Response(
                {"detail": "No worker assigned to this booking yet.", "is_assigned": False},
                status=status.HTTP_200_OK,
            )

        assignment = booking.assignment
        worker = assignment.worker

        # Check if worker is online and return tracking info
        return Response({
            "is_assigned": True,
            "worker_id": worker.id,
            "worker_name": worker.user.name or worker.user.phone,
            "worker_phone": worker.user.phone,
            "worker_rating": float(worker.rating_avg) if worker.rating_avg else None,
            "status": booking.status,
            "assigned_at": assignment.assigned_at,
            "started_at": assignment.started_at,
            # In a production app with WebSockets / Redis / FCM, live lat/lng would come here
            "worker_latitude": float(booking.address.latitude) + 0.005 if booking.address.latitude else None,
            "worker_longitude": float(booking.address.longitude) + 0.005 if booking.address.longitude else None,
        })
    @action(detail=True, methods=["post"], url_path="start")
    def start_job(self, request, pk=None):
        """Mark booking as in progress (worker started the job)."""
        from apps.notifications.models import Notification

        booking = Booking.objects.filter(pk=pk).first()
        if not booking:
            return Response({"detail": "Booking not found."}, status=status.HTTP_404_NOT_FOUND)

        assignment = getattr(booking, "assignment", None)

        if not assignment:
            return Response(
                {"detail": "This booking has no assignment. Worker must accept offer first."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            user_worker_profile = request.user.worker_profile
        except ObjectDoesNotExist:
            return Response(
                {"detail": "User is not a worker."},
                status=status.HTTP_403_FORBIDDEN
            )

        if assignment.worker != user_worker_profile:
            return Response(
                {"detail": "Only the assigned worker can start this job."},
                status=status.HTTP_403_FORBIDDEN
            )

        if booking.status != Booking.Status.ASSIGNED:
            return Response(
                {"detail": f"Cannot start job in {booking.get_status_display()} state."},
                status=status.HTTP_400_BAD_REQUEST
            )

        old_status = booking.status
        booking.status = Booking.Status.IN_PROGRESS
        booking.save()

        BookingStatusHistory.objects.create(
            booking=booking,
            from_status=old_status,
            to_status=Booking.Status.IN_PROGRESS,
            changed_by=request.user,
            note="Worker started the job",
        )

        if assignment:
            assignment.started_at = timezone.now()
            assignment.save()

        Notification.objects.create(
            user=booking.customer,
            type=Notification.Type.BOOKING_STARTED,
            title="Service Started",
            body="The service has started. You'll receive updates.",
            channel=Notification.Channel.IN_APP,
            data={"booking_id": booking.id},
        )

        return Response({
            "detail": "Job marked as started.",
            "status": booking.status,
            "started_at": assignment.started_at,
        })

    @action(detail=True, methods=["post"], url_path="complete")
    def complete_job(self, request, pk=None):
        """Mark booking as completed (worker finished the job)."""
        from apps.notifications.models import Notification

        booking = Booking.objects.filter(pk=pk).first()
        if not booking:
            return Response({"detail": "Booking not found."}, status=status.HTTP_404_NOT_FOUND)

        assignment = getattr(booking, "assignment", None)

        if not assignment:
            return Response(
                {"detail": "This booking has no assignment."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            user_worker_profile = request.user.worker_profile
        except ObjectDoesNotExist:
            return Response(
                {"detail": "User is not a worker."},
                status=status.HTTP_403_FORBIDDEN
            )

        if assignment.worker != user_worker_profile:
            return Response(
                {"detail": "Only the assigned worker can complete this job."},
                status=status.HTTP_403_FORBIDDEN
            )

        if booking.status != Booking.Status.IN_PROGRESS:
            return Response(
                {"detail": f"Cannot complete job in {booking.get_status_display()} state."},
                status=status.HTTP_400_BAD_REQUEST
            )

        old_status = booking.status
        booking.status = Booking.Status.COMPLETED
        booking.completed_at = timezone.now()
        booking.save()

        BookingStatusHistory.objects.create(
            booking=booking,
            from_status=old_status,
            to_status=Booking.Status.COMPLETED,
            changed_by=request.user,
            note="Worker completed the job",
        )

        if assignment:
            assignment.completed_at = timezone.now()
            assignment.save()

        Notification.objects.create(
            user=booking.customer,
            type=Notification.Type.BOOKING_COMPLETED,
            title="Service Completed",
            body="The service has been completed successfully.",
            channel=Notification.Channel.IN_APP,
            data={"booking_id": booking.id},
        )

        return Response({
            "detail": "Job marked as completed.",
            "status": booking.status,
            "completed_at": assignment.completed_at,
        })


class CustomerCartView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_cart(self, user):
        cart, _ = CustomerCart.objects.get_or_create(customer=user)
        return cart

    def get(self, request):
        cart = self.get_cart(request.user)
        return Response(CustomerCartSerializer(cart, context={"request": request}).data)

    def post(self, request):
        cart = self.get_cart(request.user)
        serializer = CartItemSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save(cart=cart)
        return Response(
            CustomerCartSerializer(cart, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    def patch(self, request):
        cart = self.get_cart(request.user)
        if "address_id" in request.data:
            address_id = request.data.get("address_id")
            if address_id in (None, ""):
                cart.address = None
            else:
                cart.address = get_object_or_404(
                    Address, pk=address_id, user=request.user, deleted_at__isnull=True
                )
            cart.save(update_fields=["address", "updated_at"])
        return Response(CustomerCartSerializer(cart, context={"request": request}).data)


class CustomerCartItemView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_item(self, request, item_id):
        cart = get_object_or_404(CustomerCart, customer=request.user)
        return get_object_or_404(CartItem, cart=cart, pk=item_id)

    def patch(self, request, item_id):
        item = self.get_item(request, item_id)
        serializer = CartItemSerializer(
            item, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(CustomerCartSerializer(item.cart, context={"request": request}).data)

    def delete(self, request, item_id):
        item = self.get_item(request, item_id)
        cart = item.cart
        item.delete()
        return Response(CustomerCartSerializer(cart, context={"request": request}).data)
