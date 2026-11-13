from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils import timezone
from django.db import transaction
from django.conf import settings
from decimal import Decimal
from django.shortcuts import get_object_or_404
from django.core.exceptions import ObjectDoesNotExist

from .models import Booking, BookingStatusHistory, CustomerCart, CartItem, Order, OrderItem, BookingAddOn, WorkerOffer
from .serializers import (
    BookingCreateSerializer,
    BookingListSerializer,
    BookingDetailSerializer,
    BookingCancelSerializer,
    BookingAvailabilitySerializer,
    CartItemSerializer,
    CustomerCartSerializer,
)
from .services import check_slot_availability, check_service_available, create_worker_offers_for_booking, SlotConflictError, ServiceUnavailableError
from apps.notifications.models import Notification
from apps.accounts.models import Address
from apps.catalog.audience import validate_beauty_audience


def _schedule_booking_refund(booking_id):
    import logging
    from apps.payments.models import PaymentRefund
    from apps.payments.refunds import request_booking_refunds

    try:
        booking = Booking.objects.get(pk=booking_id)
        request_booking_refunds(
            booking,
            reason=PaymentRefund.Reason.CUSTOMER_CANCELLATION,
        )
    except Exception:
        logging.getLogger(__name__).exception(
            "Could not schedule cancellation refund for booking %s", booking_id
        )


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
    @transaction.atomic
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

        assignment = getattr(booking, "assignment", None)
        if assignment:
            Notification.objects.create(
                user=assignment.worker.user,
                type=Notification.Type.WORKER_OFFER_WITHDRAWN,
                title="Service Cancelled",
                body=f"The customer cancelled booking #{booking.id}. This service is no longer assigned to you.",
                channel=Notification.Channel.IN_APP,
                data={"booking_id": booking.id},
            )
            assignment.delete()

        BookingStatusHistory.objects.create(
            booking=booking,
            from_status=old_status,
            to_status=Booking.Status.CANCELLED,
            changed_by=request.user,
            note=f"Cancelled by customer. Reason: {reason}",
        )

        # Cancel pending offers for the affected service. For grouped orders,
        # withdraw the shared order offer and redispatch only if active lines
        # remain unassigned and the required advance has already been captured.
        order_item = getattr(booking, "order_item", None)
        if order_item:
            order = Order.objects.select_for_update().get(pk=order_item.order_id)
            active_remaining = order.items.exclude(
                booking__status=Booking.Status.CANCELLED
            ).exists()
            order.status = (
                Order.Status.PARTIALLY_CANCELLED
                if active_remaining else Order.Status.CANCELLED
            )
            order.save(update_fields=["status", "updated_at"])
            WorkerOffer.objects.filter(
                order=order, status=WorkerOffer.Status.PENDING
            ).update(
                status=WorkerOffer.Status.WITHDRAWN,
                responded_at=timezone.now(),
            )
            if active_remaining:
                from apps.bookings.dispatcher import DispatcherService
                DispatcherService.dispatch_order(order)
        else:
            WorkerOffer.objects.filter(
                booking=booking, status=WorkerOffer.Status.PENDING
            ).update(
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

        # Refund only this service's captured allocations. Run after commit so
        # a gateway/network failure cannot roll back the customer's cancellation.
        transaction.on_commit(
            lambda booking_id=booking.id: _schedule_booking_refund(booking_id)
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

        if hasattr(booking, "order_item"):
            return Response(
                {"detail": "This booking is part of a parent order. Track and manage worker assignment from the complete order, not an individual booking line."},
                status=status.HTTP_400_BAD_REQUEST,
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
        category_answers = data.get("category_answers", {})

        from apps.workers.eligibility import required_worker_gender_for_booking
        try:
            validate_beauty_audience(service, category_answers)
            required_gender = required_worker_gender_for_booking(service, category_answers)
        except ValueError as exc:
            return Response({"available": False, "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        address = None
        if data.get("address_id"):
            address = Address.objects.filter(
                pk=data["address_id"],
                user=request.user,
                deleted_at__isnull=True,
            ).select_related("zone__city").first()
            if address is None:
                return Response({"detail": "Select a valid service address."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            check_service_available(
                service=service,
                address=address,
                audience=data.get("audience", "all"),
            )

            duration = variant.duration_minutes if variant else service.duration_minutes
            duration = (duration or 60) * data.get("quantity", 1)

            check_slot_availability(
                service=service,
                scheduled_at=scheduled_at,
                duration_minutes=duration,
                booking_mode=booking_mode,
                drop_scheduled_at=drop_scheduled_at,
            )
            if required_gender:
                from apps.bookings.services import has_eligible_worker_for_slot
                if not has_eligible_worker_for_slot(
                    service=service,
                    address=address,
                    scheduled_at=scheduled_at,
                    duration_minutes=duration,
                    required_gender=required_gender,
                    drop_scheduled_at=drop_scheduled_at if booking_mode == Booking.BookingMode.PICKUP_DROP else None,
                    exclude_customer_id=request.user.id,
                ):
                    preference_can_change = (
                        category_answers.get("professional_preference") == "female"
                        and not service.requires_female_worker
                    )
                    return Response({
                        "available": False,
                        "message": (
                            "No female professional is available for this time slot. "
                            "Choose another time or change the preference to No preference."
                            if preference_can_change
                            else "No female professional is available for this service at the selected time. Choose another time."
                        ),
                        "reason": (
                            "female_professional_unavailable"
                            if preference_can_change
                            else "required_female_worker_unavailable"
                        ),
                    })

            return Response({"available": True, "message": "Slot is available for booking."})

        except SlotConflictError as e:
            return Response(
                {"available": False, "message": str(e)},
                status=status.HTTP_409_CONFLICT,
            )
        except ServiceUnavailableError as e:
            return Response(
                {"available": False, "message": str(e)},
                status=status.HTTP_200_OK,
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
            # Live worker GPS is not stored by the current WorkerProfile model.
            # Never fabricate a position from the customer's address; clients should
            # show "location unavailable" until a verified worker GPS source is added.
            "worker_latitude": None,
            "worker_longitude": None,
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

        if booking.status not in (Booking.Status.ASSIGNED, Booking.Status.CONFIRMED):
            return Response(
                {"detail": f"Cannot start job in {booking.get_status_display()} state."},
                status=status.HTTP_400_BAD_REQUEST
            )

        order_item = getattr(booking, "order_item", None)
        if order_item and "payment_allocation_v1" in (order_item.order.metadata or {}):
            from apps.payments.models import Payment
            if not Payment.objects.filter(
                order=order_item.order,
                stage=Payment.Stage.ADVANCE,
                status=Payment.Status.PAID,
            ).exists():
                return Response(
                    {"detail": "The customer advance payment has not been verified."},
                    status=status.HTTP_409_CONFLICT,
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
        """Issue a customer-shared OTP, then complete only after worker verification."""
        import secrets
        from datetime import timedelta
        from django.contrib.auth.hashers import check_password, make_password
        from apps.bookings.models import BookingCompletionOTP

        booking = Booking.objects.select_related("customer").filter(pk=pk).first()
        if not booking:
            return Response({"detail": "Booking not found."}, status=status.HTTP_404_NOT_FOUND)
        assignment = getattr(booking, "assignment", None)
        if not assignment:
            return Response({"detail": "This booking has no assignment."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            worker_profile = request.user.worker_profile
        except ObjectDoesNotExist:
            return Response({"detail": "User is not a worker."}, status=status.HTTP_403_FORBIDDEN)
        if assignment.worker_id != worker_profile.id:
            return Response({"detail": "Only the assigned worker can complete this job."}, status=status.HTTP_403_FORBIDDEN)
        if booking.status != Booking.Status.IN_PROGRESS:
            return Response({"detail": f"Cannot complete job in {booking.get_status_display()} state."}, status=status.HTTP_400_BAD_REQUEST)

        supplied_code = str(request.data.get("otp", "")).strip()
        with transaction.atomic():
            locked_booking = Booking.objects.select_for_update().get(pk=booking.pk)
            otp_record = BookingCompletionOTP.objects.select_for_update().filter(booking=locked_booking).first()
            now = timezone.now()

            if not supplied_code:
                if otp_record and otp_record.verified_at:
                    return Response({"detail": "This service has already been verified."}, status=status.HTTP_409_CONFLICT)
                if otp_record and otp_record.expires_at > now:
                    return Response({
                        "detail": "A completion code has already been sent to the customer. Ask the customer to share it.",
                        "otp_required": True,
                        "expires_at": otp_record.expires_at.isoformat(),
                    }, status=status.HTTP_200_OK)
                code = f"{secrets.randbelow(1_000_000):06d}"
                expires_at = now + timedelta(minutes=10)
                values = {
                    "code_hash": make_password(code),
                    "expires_at": expires_at,
                    "attempts": 0,
                    "last_sent_at": now,
                    "verified_at": None,
                }
                if otp_record:
                    for field, value in values.items():
                        setattr(otp_record, field, value)
                    otp_record.save(update_fields=[*values.keys(), "updated_at"])
                else:
                    otp_record = BookingCompletionOTP.objects.create(booking=locked_booking, **values)

                Notification.objects.create(
                    user=locked_booking.customer,
                    type=Notification.Type.SYSTEM_ANNOUNCEMENT,
                    title="Share your service completion code",
                    body=f"Your AIRway completion code for booking #{locked_booking.id} is {code}. Share it with your assigned professional only after the service is finished. It expires in 10 minutes.",
                    channel=Notification.Channel.IN_APP,
                    data={
                        "booking_id": locked_booking.id,
                        "purpose": "service_completion_otp",
                        "completion_code": code,
                        "expires_at": expires_at.isoformat(),
                    },
                )
                return Response({
                    "detail": "Completion code sent to the customer in the AIRway app. Ask the customer to share it.",
                    "otp_required": True,
                    "expires_at": expires_at.isoformat(),
                }, status=status.HTTP_200_OK)

            if not otp_record or otp_record.verified_at:
                return Response({"detail": "No active completion code. Request a new code first."}, status=status.HTTP_400_BAD_REQUEST)
            if otp_record.expires_at <= now:
                return Response({"detail": "Completion code expired. Request a new code."}, status=status.HTTP_400_BAD_REQUEST)
            if otp_record.attempts >= 5:
                return Response({"detail": "Too many incorrect attempts. Request a new code after it expires."}, status=status.HTTP_429_TOO_MANY_REQUESTS)
            if len(supplied_code) != 6 or not supplied_code.isdigit() or not check_password(supplied_code, otp_record.code_hash):
                otp_record.attempts += 1
                otp_record.save(update_fields=["attempts", "updated_at"])
                remaining = max(5 - otp_record.attempts, 0)
                return Response({"detail": "Invalid completion code.", "attempts_remaining": remaining}, status=status.HTTP_400_BAD_REQUEST)

            otp_record.verified_at = now
            otp_record.save(update_fields=["verified_at", "updated_at"])
            old_status = locked_booking.status
            locked_booking.status = Booking.Status.COMPLETED
            locked_booking.completed_at = now
            worker_notes = str(request.data.get("notes", "")).strip()
            if worker_notes:
                locked_booking.worker_notes = worker_notes
            locked_booking.save(update_fields=["status", "completed_at", "worker_notes", "updated_at"])
            assignment.completed_at = now
            assignment.save(update_fields=["completed_at", "updated_at"])
            BookingStatusHistory.objects.create(
                booking=locked_booking,
                from_status=old_status,
                to_status=Booking.Status.COMPLETED,
                changed_by=request.user,
                note="Service completion verified with customer-shared OTP.",
            )

            order = getattr(locked_booking, "order_item", None)
            balance_ready = False
            if order:
                order_items = list(order.order.items.select_related("booking"))
                balance_ready = all(
                    row.booking.status == Booking.Status.COMPLETED
                    or row.booking.status == Booking.Status.CANCELLED
                    for row in order_items
                )
                if balance_ready:
                    Notification.objects.create(
                        user=locked_booking.customer,
                        type=Notification.Type.SYSTEM_ANNOUNCEMENT,
                        title="All services completed",
                        body=f"All active services in AIRway order #{order.order_id} are verified. Your remaining balance is now due.",
                        channel=Notification.Channel.IN_APP,
                        data={"order_id": order.order_id, "payment_stage": "balance"},
                    )

            Notification.objects.create(
                user=locked_booking.customer,
                type=Notification.Type.BOOKING_COMPLETED,
                title="Service Completion Verified",
                body="Your service completion was verified successfully.",
                channel=Notification.Channel.IN_APP,
                data={"booking_id": locked_booking.id, "order_id": order.order_id if order else None},
            )

        return Response({
            "detail": "Service completion verified successfully.",
            "status": Booking.Status.COMPLETED,
            "completed_at": now.isoformat(),
            "order_balance_ready": balance_ready,
        }, status=status.HTTP_200_OK)


class CustomerCheckoutView(APIView):
    """Convert a customer's cart into one parent order with independent bookings."""

    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        cart = get_object_or_404(
            CustomerCart.objects.select_for_update().prefetch_related(
                "items__service", "items__variant"
            ),
            customer=request.user,
        )
        items = list(cart.items.all())
        if not items:
            return Response({"detail": "Your cart is empty."}, status=status.HTTP_400_BAD_REQUEST)
        if not cart.address_id:
            return Response({"detail": "Select a service address before checkout."}, status=status.HTTP_400_BAD_REQUEST)

        requested = request.data.get("items")
        if not isinstance(requested, list) or not requested:
            return Response(
                {"detail": "items must contain cart_item_id, scheduled_at and optional drop_scheduled_at for every cart item."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        requested_by_id = {}
        for row in requested:
            if not isinstance(row, dict) or not row.get("cart_item_id"):
                return Response({"detail": "Each checkout item needs a cart_item_id."}, status=status.HTTP_400_BAD_REQUEST)
            try:
                item_id = int(row["cart_item_id"])
            except (TypeError, ValueError):
                return Response({"detail": "cart_item_id must be an integer."}, status=status.HTTP_400_BAD_REQUEST)
            if item_id in requested_by_id:
                return Response({"detail": "Duplicate cart_item_id values are not allowed."}, status=status.HTTP_400_BAD_REQUEST)
            requested_by_id[item_id] = row

        if set(requested_by_id) != {item.id for item in items}:
            return Response(
                {"detail": "Checkout must include every current cart item exactly once."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        prepared = []
        for item in items:
            try:
                check_service_available(service=item.service, address=cart.address, audience="all")
            except ServiceUnavailableError as exc:
                return Response(
                    {"detail": str(exc), "cart_item_id": item.id},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            schedule = requested_by_id[item.id]
            booking_data = {
                "service": item.service_id,
                "variant": item.variant_id,
                "booking_mode": item.service.booking_mode,
                "scheduled_at": schedule.get("scheduled_at"),
                "drop_scheduled_at": schedule.get("drop_scheduled_at"),
                "address_id": cart.address_id,
                "addon_ids": [row["id"] for row in item.addon_selections],
                "form_responses": item.form_answers,
                "category_answers": item.category_answers,
                "quantity": item.quantity,
                "notes": item.notes,
            }
            serializer = BookingCreateSerializer(
                data=booking_data,
                context={"request": request, "defer_worker_dispatch": True},
            )
            serializer.is_valid(raise_exception=True)
            prepared.append((item, serializer))

        # A parent order is fulfilled by one worker. Reject overlapping
        # service windows before creating any booking/order records; otherwise
        # checkout could succeed but no worker could ever accept the order.
        from apps.bookings.services import _booking_intervals, _intervals_overlap
        occupied_order_intervals = []
        for item, serializer in prepared:
            attrs = serializer.validated_data
            service = attrs["service"]
            variant = attrs.get("variant")
            duration = (
                variant.duration_minutes
                if variant and variant.duration_minutes
                else service.duration_minutes
            ) or 60
            quantity = attrs.get("quantity", 1)
            intervals = _booking_intervals(
                attrs["scheduled_at"],
                duration * quantity,
                service.buffer_minutes,
                attrs.get("drop_scheduled_at")
                if attrs.get("booking_mode") == Booking.BookingMode.PICKUP_DROP
                else None,
            )
            if any(
                _intervals_overlap(candidate, occupied)
                for candidate in intervals
                for occupied in occupied_order_intervals
            ):
                return Response(
                    {
                        "detail": (
                            "Services in one order must have non-overlapping appointment "
                            "times, including service buffer and pickup/drop windows. "
                            "Please choose different times."
                        ),
                        "code": "order_schedule_overlap",
                        "cart_item_id": item.id,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            occupied_order_intervals.extend(intervals)

        order = Order.objects.create(
            customer=request.user,
            address=cart.address,
            status=Order.Status.AWAITING_ASSIGNMENT,
        )
        subtotal = Decimal("0")
        tax_total = Decimal("0")
        grand_total = Decimal("0")
        dispatch_results = []

        for item, serializer in prepared:
            booking = serializer.save()
            quantity = item.quantity
            base_snapshot = dict(booking.pricing_snapshot or {})
            unit_subtotal = Decimal(str(base_snapshot.get("subtotal", "0")))

            # Preserve add-on quantities chosen in the cart and make the
            # immutable booking/order price snapshots reflect those quantities.
            addon_quantities = {row["id"]: int(row.get("quantity", 1)) for row in item.addon_selections}
            adjusted_addons = []
            adjusted_addons_total = Decimal("0")
            for booking_addon in booking.booking_addons.select_related("addon"):
                addon_quantity = addon_quantities.get(booking_addon.addon_id, 1)
                booking_addon.quantity = addon_quantity
                booking_addon.total_price = booking_addon.unit_price * addon_quantity
                booking_addon.save(update_fields=["quantity", "total_price", "updated_at"])
                adjusted_addons_total += booking_addon.total_price
                adjusted_addons.append({
                    "id": booking_addon.addon_id,
                    "title": booking_addon.addon.title,
                    "title_hi": booking_addon.addon.title_hi,
                    "unit_price": str(booking_addon.unit_price),
                    "quantity": addon_quantity,
                    "total": str(booking_addon.total_price),
                })

            base_snapshot["addons"] = adjusted_addons
            base_snapshot["addon_total"] = str(adjusted_addons_total)
            # Recalculate from the variant/visit base plus the selected add-ons.
            variant_base = Decimal(str(base_snapshot.get("variant_price", "0")))
            visit_fee = Decimal(str(base_snapshot.get("visit_fee", "0")))
            unit_subtotal = variant_base + visit_fee + adjusted_addons_total
            unit_tax = unit_subtotal * Decimal("0.18")
            line_subtotal = unit_subtotal * quantity
            line_tax = unit_tax * quantity
            line_total = line_subtotal + line_tax

            base_snapshot.update({
                "cart_item_id": item.id,
                "quantity": quantity,
                "unit_subtotal": str(unit_subtotal),
                "unit_tax": str(unit_tax),
                "subtotal": str(line_subtotal),
                "tax": str(line_tax),
                "total": str(line_total),
                "currency": "INR",
            })
            booking.pricing_snapshot = base_snapshot
            booking.save(update_fields=["pricing_snapshot", "updated_at"])

            OrderItem.objects.create(
                order=order,
                booking=booking,
                quantity=quantity,
                service_snapshot={
                    "service_id": item.service_id,
                    "service_title": item.service.title,
                    "variant_id": item.variant_id,
                    "variant_title": item.variant.title if item.variant else None,
                    "cart_item_id": item.id,
                    "form_answers": item.form_answers,
                    "category_answers": item.category_answers,
                    "notes": item.notes,
                },
                pricing_snapshot=base_snapshot,
                line_subtotal=line_subtotal,
                tax_amount=line_tax,
                line_total=line_total,
            )
            subtotal += line_subtotal
            tax_total += line_tax
            grand_total += line_total

            # Dispatch is deferred until every OrderItem exists.
            dispatch_results.append({"booking_id": booking.id, "offers_sent": 0})

        order.subtotal = subtotal
        order.tax_amount = tax_total
        order.total_amount = grand_total
        order.save(update_fields=["subtotal", "tax_amount", "total_amount", "updated_at"])

        # Persist the exact 30/70 split before returning the checkout response so
        # the customer sees the due-now amount even before opening Razorpay.
        from decimal import ROUND_HALF_UP
        allocation_items = list(order.items.all())
        advance_percentage = Decimal(str(getattr(settings, "ORDER_ADVANCE_PERCENTAGE", 30)))
        advance_total = (order.total_amount * advance_percentage / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        balance_total = order.total_amount - advance_total
        advance_rows, balance_rows = [], []
        allocated_advance = Decimal("0.00")
        allocated_balance = Decimal("0.00")
        for index, item in enumerate(allocation_items):
            if index == len(allocation_items) - 1:
                advance_line = advance_total - allocated_advance
                balance_line = balance_total - allocated_balance
            else:
                ratio = item.line_total / order.total_amount if order.total_amount else Decimal("0")
                advance_line = (advance_total * ratio).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                balance_line = item.line_total - advance_line
                allocated_advance += advance_line
                allocated_balance += balance_line
            advance_rows.append({
                "order_item_id": item.id,
                "booking_id": item.booking_id,
                "amount": str(advance_line),
            })
            balance_rows.append({
                "order_item_id": item.id,
                "booking_id": item.booking_id,
                "amount": str(balance_line),
            })
        order.metadata = {
            **(order.metadata or {}),
            "payment_allocation_v1": {
                "percentage": str(advance_percentage),
                "advance_total": str(advance_total),
                "balance_total": str(balance_total),
                "advance": advance_rows,
                "balance": balance_rows,
            },
        }
        order.save(update_fields=["metadata", "updated_at"])

        # Worker dispatch is intentionally gated behind verified 30% advance.
        # Payment webhook/verification triggers DispatcherService.dispatch_order.

        cart.items.all().delete()
        return Response({
            "order_id": order.id,
            "status": order.status,
            "address_id": order.address_id,
            "currency": order.currency,
            "subtotal": str(order.subtotal),
            "tax_amount": str(order.tax_amount),
            "total_amount": str(order.total_amount),
            "items": [
                {
                    "order_item_id": row.id,
                    "booking_id": row.booking_id,
                    "service": row.service_snapshot,
                    "quantity": row.quantity,
                    "line_total": str(row.line_total),
                }
                for row in order.items.all()
            ],
            "dispatch": {"offers_sent": 0, "deferred_until_advance_payment": True},
            "next_step": "Pay the 30% advance to start worker matching. The remaining 70% is due after all services are completed and verified.",

        }, status=status.HTTP_201_CREATED)


class CustomerOrderDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, order_id):
        from apps.payments.models import Payment

        from apps.payments.models import PaymentRefund

        order = get_object_or_404(
            Order.objects.prefetch_related(
                "items__booking__assignment__worker__user",
                "items__booking__payment_refunds",
                "payments",
            ),
            pk=order_id,
            customer=request.user,
        )
        allocation = (order.metadata or {}).get("payment_allocation_v1", {})
        advance_rows = {row["order_item_id"]: row for row in allocation.get("advance", [])}
        balance_rows = {row["order_item_id"]: row for row in allocation.get("balance", [])}
        items = []
        for row in order.items.all():
            booking = row.booking
            assignment = getattr(booking, "assignment", None)
            completion_code = None
            completion_expires_at = None
            if booking.status == Booking.Status.IN_PROGRESS:
                from apps.bookings.models import BookingCompletionOTP
                from apps.notifications.models import Notification
                otp_record = BookingCompletionOTP.objects.filter(
                    booking=booking,
                    verified_at__isnull=True,
                    expires_at__gt=timezone.now(),
                ).first()
                if otp_record:
                    otp_notice = Notification.objects.filter(
                        user=request.user,
                        data__booking_id=booking.id,
                        data__purpose="service_completion_otp",
                    ).order_by("-created_at").first()
                    if otp_notice:
                        completion_code = (otp_notice.data or {}).get("completion_code")
                        if not completion_code:
                            import re
                            match = re.search(r"\\bis (\\d{6})\\.", otp_notice.body)
                            completion_code = match.group(1) if match else None
                        completion_expires_at = otp_record.expires_at.isoformat()
            items.append({
                "order_item_id": row.id,
                "booking_id": booking.id,
                "service": row.service_snapshot,
                "booking_status": booking.status,
                "scheduled_at": booking.scheduled_at,
                "worker": (
                    {
                        "id": assignment.worker_id,
                        "name": assignment.worker.user.name or assignment.worker.user.phone,
                    }
                    if assignment else None
                ),
                "quantity": row.quantity,
                "line_total": str(row.line_total),
                "advance_amount": advance_rows.get(row.id, {}).get("amount"),
                "balance_amount": balance_rows.get(row.id, {}).get("amount"),
                "completion_verified": booking.status == Booking.Status.COMPLETED,
                "completion_otp": (
                    {
                        "code": completion_code,
                        "expires_at": completion_expires_at,
                    }
                    if completion_code else None
                ),
                "refunds": [
                    {
                        "id": refund.pk,
                        "amount": str(refund.amount),
                        "wallet_amount": str(refund.wallet_amount),
                        "gateway_amount": str(refund.gateway_amount),
                        "status": refund.status,
                        "reason": refund.reason,
                        "failure_reason": refund.failure_reason,
                        "created_at": refund.created_at,
                        "processed_at": refund.processed_at,
                    }
                    for refund in booking.payment_refunds.all()
                ],
            })

        is_staged_payment = bool(allocation)
        advance_payment = order.payments.filter(stage=Payment.Stage.ADVANCE, status=Payment.Status.PAID).first()
        balance_payment = order.payments.filter(stage=Payment.Stage.BALANCE, status=Payment.Status.PAID).first()
        legacy_payment = order.payments.filter(stage=Payment.Stage.LEGACY, status=Payment.Status.PAID).first()
        legacy_ready = (
            not is_staged_payment
            and order.status == Order.Status.AWAITING_PAYMENT
            and all(row["booking_status"] == Booking.Status.ASSIGNED for row in items)
            and not legacy_payment
        )
        active_item_ids = {
            row["order_item_id"] for row in items
            if row["booking_status"] != Booking.Status.CANCELLED
        }
        active_advance_due = sum(
            (
                Decimal(str(entry.get("amount", "0")))
                for entry in allocation.get("advance", [])
                if entry.get("order_item_id") in active_item_ids
            ),
            Decimal("0.00"),
        )
        advance_due = active_advance_due if not advance_payment else Decimal("0")
        active_balance_due = sum(
            (
                Decimal(str(entry.get("amount", "0")))
                for entry in allocation.get("balance", [])
                if entry.get("order_item_id") in active_item_ids
            ),
            Decimal("0.00"),
        )
        balance_due = active_balance_due if not balance_payment else Decimal("0")
        active_rows = [
            row for row in items
            if row["booking_status"] != Booking.Status.CANCELLED
        ]
        all_services_verified = bool(active_rows) and all(
            row["completion_verified"] for row in active_rows
        )
        ready_for_balance = bool(advance_payment and all_services_verified and not balance_payment)

        return Response({
            "id": order.id,
            "status": order.status,
            "currency": order.currency,
            "subtotal": str(order.subtotal),
            "tax_amount": str(order.tax_amount),
            "total_amount": str(order.total_amount),
            "is_staged_payment": is_staged_payment,
            "advance_percentage": int(allocation.get("percentage", 30)),
            "advance_total": allocation.get("advance_total"),
            "balance_total": allocation.get("balance_total"),
            "advance_paid": bool(advance_payment),
            "balance_paid": bool(balance_payment),
            "legacy_paid": bool(legacy_payment),
            "advance_due": str(advance_due),
            "balance_due": str(balance_due),
            "legacy_payment_due": str(order.total_amount) if legacy_ready else "0.00",
            "amount_due": str(advance_due + balance_due) if is_staged_payment else (str(order.total_amount) if legacy_ready else "0.00"),
            "ready_for_advance": is_staged_payment and not advance_payment and order.status in (Order.Status.AWAITING_ASSIGNMENT, Order.Status.AWAITING_PAYMENT, Order.Status.PARTIALLY_CANCELLED),
            "ready_for_balance": ready_for_balance,
            "ready_for_legacy_payment": legacy_ready,
            "ready_for_payment": ready_for_balance or legacy_ready,
            "all_services_verified": all_services_verified,
            "items": items,
        })


class CustomerOrderListView(APIView):
    """List the authenticated customer's multi-service orders."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from apps.payments.models import Payment

        orders = Order.objects.filter(customer=request.user).prefetch_related(
            "items__booking", "payments"
        ).order_by("-created_at")
        results = []
        for order in orders:
            allocation = (order.metadata or {}).get("payment_allocation_v1", {})
            staged = bool(allocation)
            advance_paid = order.payments.filter(
                stage=Payment.Stage.ADVANCE, status=Payment.Status.PAID
            ).exists()
            balance_paid = order.payments.filter(
                stage=Payment.Stage.BALANCE, status=Payment.Status.PAID
            ).exists()
            legacy_paid = order.payments.filter(
                stage=Payment.Stage.LEGACY, status=Payment.Status.PAID
            ).exists()
            active_items = order.items.exclude(booking__status=Booking.Status.CANCELLED)
            all_completed = active_items.exists() and not active_items.exclude(
                booking__status=Booking.Status.COMPLETED
            ).exists()
            ready_for_advance = staged and not advance_paid and order.status in (
                Order.Status.AWAITING_ASSIGNMENT, Order.Status.AWAITING_PAYMENT,
                Order.Status.PARTIALLY_CANCELLED,
            )
            ready_for_balance = staged and advance_paid and all_completed and not balance_paid
            ready_for_legacy = (
                not staged and order.status == Order.Status.AWAITING_PAYMENT and not legacy_paid
            )
            # Order state is changed by payment/assignment actions, never by a read.
            results.append({
                "id": order.id,
                "status": order.status,
                "total_amount": str(order.total_amount),
                "created_at": order.created_at,
                "item_count": order.items.count(),
                "is_staged_payment": staged,
                "advance_paid": advance_paid,
                "balance_paid": balance_paid,
                "ready_for_advance": ready_for_advance,
                "ready_for_balance": ready_for_balance,
                "ready_for_payment": ready_for_balance or ready_for_legacy,
            })
        return Response(results)


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

        # Once an address is selected, only allow services available in that
        # address's city to be added to the cart.
        if cart.address:
            try:
                check_service_available(
                    service=serializer.validated_data["service"],
                    address=cart.address,
                    audience="all",
                )
            except ServiceUnavailableError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

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
                address = get_object_or_404(
                    Address.objects.select_related("zone__city"),
                    pk=address_id,
                    user=request.user,
                    deleted_at__isnull=True,
                )
                # Changing Jaipur to another city must not leave unavailable
                # services silently attached to the cart.
                for item in cart.items.select_related("service"):
                    try:
                        check_service_available(
                            service=item.service,
                            address=address,
                            audience="all",
                        )
                    except ServiceUnavailableError as exc:
                        return Response(
                            {
                                "detail": str(exc),
                                "unavailable_cart_item_id": item.id,
                                "service_id": item.service_id,
                            },
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                cart.address = address
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
        if item.cart.address:
            try:
                check_service_available(
                    service=serializer.validated_data.get("service", item.service),
                    address=item.cart.address,
                    audience="all",
                )
            except ServiceUnavailableError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(CustomerCartSerializer(item.cart, context={"request": request}).data)

    def delete(self, request, item_id):
        item = self.get_item(request, item_id)
        cart = item.cart
        item.delete()
        return Response(CustomerCartSerializer(cart, context={"request": request}).data)
