from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils import timezone
from django.db import transaction
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
        serializer = self.get_serializer(
            data=request.data,
            context={"request": request, "defer_worker_dispatch": True},
        )
        serializer.is_valid(raise_exception=True)
        booking = serializer.save()

        from apps.payments.lifecycle import create_financial_plan
        financial_plan = create_financial_plan(booking)
        detail = BookingDetailSerializer(booking, context={"request": request}).data
        detail.update({
            "payment_required": True,
            "advance_due": str(financial_plan.advance_due),
            "balance_due": str(financial_plan.balance_due),
            "dispatch": [],
            "next_step": "Pay the booking advance. Worker offers will be created only after capture is verified.",
        })
        return Response(detail, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        from apps.payments.lifecycle import (
            PaymentLifecycleError,
            create_customer_cancellation_refund_record,
            customer_cancellation_terms,
        )
        from apps.payments.models import Payment, RefundRecord
        from apps.bookings.models import BookingAssignment, OrderItem

        visible_booking = self.get_object()
        refund_record = None
        refund_created = False
        terms = None

        with transaction.atomic():
            booking = Booking.objects.select_for_update().get(
                pk=visible_booking.pk, customer=request.user,
            )
            # A parent-order line cannot be cancelled independently until the
            # order-level partial-cancellation/refund workflow is implemented.
            if OrderItem.objects.filter(booking=booking).exists():
                return Response(
                    {"detail": "This service belongs to a multi-service order. Contact AIRway support to change the order safely."},
                    status=status.HTTP_409_CONFLICT,
                )

            serializer = BookingCancelSerializer(
                data=request.data, context={"booking": booking},
            )
            serializer.is_valid(raise_exception=True)
            assignment = BookingAssignment.objects.select_for_update().filter(
                booking=booking,
            ).first()
            if (
                booking.status in (Booking.Status.IN_PROGRESS, Booking.Status.COMPLETED)
                or (assignment and assignment.started_at)
            ):
                return Response(
                    {"detail": "A service cannot be cancelled after its start OTP has been verified. You can raise a support or dispute request."},
                    status=status.HTTP_409_CONFLICT,
                )

            reason = serializer.validated_data.get("reason", "")
            payment = Payment.objects.select_for_update().filter(
                booking=booking, status=Payment.Status.PAID,
            ).first()
            collected_amount = payment.amount if payment else Decimal("0.00")
            try:
                terms = customer_cancellation_terms(
                    booking.scheduled_at,
                    collected_amount,
                    worker_accepted=bool(assignment and assignment.accepted_at),
                    now=timezone.now(),
                )
            except PaymentLifecycleError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

            if payment and collected_amount > 0:
                refund_record, refund_created = create_customer_cancellation_refund_record(
                    booking=booking, payment=payment, terms=terms,
                )

            old_status = booking.status
            now = timezone.now()
            booking.status = Booking.Status.CANCELLED
            booking.cancelled_at = now
            booking.cancellation_reason = reason
            booking.cancelled_by = request.user
            booking.save(update_fields=[
                "status", "cancelled_at", "cancellation_reason",
                "cancelled_by", "updated_at",
            ])
            BookingStatusHistory.objects.create(
                booking=booking,
                from_status=old_status,
                to_status=Booking.Status.CANCELLED,
                changed_by=request.user,
                note=(
                    f"Cancelled by customer. Reason: {reason}. "
                    f"Refund policy: {terms['policy']}; "
                    f"collected: {collected_amount}; "
                    f"refund: {terms['refund_amount']}; "
                    f"platform fee: {terms['platform_fee']}."
                ),
            )
            WorkerOffer.objects.select_for_update().filter(
                booking=booking, status=WorkerOffer.Status.PENDING,
            ).update(
                status=WorkerOffer.Status.EXPIRED, responded_at=now,
            )
            Notification.objects.create(
                user=request.user,
                type=Notification.Type.BOOKING_CANCELLED,
                title="Booking Cancelled",
                body="Your service booking has been cancelled.",
                channel=Notification.Channel.IN_APP,
                data={"booking_id": booking.id},
            )

        # Network I/O must happen after the database transaction. The refund
        # record is durable first, so a provider timeout can be reconciled.
        provider_error = None
        if refund_record and refund_record.refund_amount > 0 and refund_created:
            if not payment.razorpay_payment_id:
                provider_error = "Captured payment has no Razorpay payment ID; manual reconciliation is required."
                refund_record.status = RefundRecord.Status.FAILED
                refund_record.provider_payload = {
                    **(refund_record.provider_payload or {}),
                    "submission_error": provider_error,
                }
                refund_record.save(update_fields=["status", "provider_payload", "updated_at"])
            else:
                try:
                    import razorpay
                    from django.conf import settings
                    gateway = razorpay.Client(
                        auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
                    )
                    provider_refund = gateway.payment.refund(
                        payment.razorpay_payment_id,
                        {
                            "amount": int(refund_record.refund_amount * 100),
                            "notes": {
                                "airway_refund_record_id": str(refund_record.pk),
                                "airway_booking_id": str(booking.pk),
                                "airway_policy": terms["policy"],
                            },
                        },
                    )
                    refund_record.provider_refund_id = provider_refund.get("id")
                    refund_record.status = (
                        RefundRecord.Status.PROCESSED
                        if provider_refund.get("status") == "processed"
                        else RefundRecord.Status.PENDING
                    )
                    if refund_record.status == RefundRecord.Status.PROCESSED:
                        refund_record.processed_at = timezone.now()
                    refund_record.provider_payload = provider_refund
                    refund_record.save(update_fields=[
                        "provider_refund_id", "status", "processed_at",
                        "provider_payload", "updated_at",
                    ])
                except Exception:
                    logger.exception(
                        "Razorpay refund submission failed for booking %s / refund %s",
                        booking.pk, refund_record.pk,
                    )
                    provider_error = (
                        "Cancellation succeeded, but refund submission needs AIRway support reconciliation."
                    )
                    refund_record.status = RefundRecord.Status.FAILED
                    refund_record.provider_payload = {
                        **(refund_record.provider_payload or {}),
                        "submission_error": provider_error,
                    }
                    refund_record.save(update_fields=["status", "provider_payload", "updated_at"])

        booking.refresh_from_db()
        refund_status = refund_record.status if refund_record else "not_applicable"
        response_data = {
            "detail": "Booking cancelled successfully.",
            "status": booking.status,
            "refund_policy": terms["policy"],
            "refund_amount": str(terms["refund_amount"]),
            "platform_fee": str(terms["platform_fee"]),
            "refund_status": refund_status,
        }
        if refund_record:
            response_data["refund_id"] = refund_record.pk
        if provider_error:
            response_data["refund_message"] = provider_error
        elif refund_record and refund_record.refund_amount > 0:
            response_data["refund_message"] = "Refund request submitted to Razorpay; final settlement is pending provider confirmation."
        return Response(response_data)
 
    @action(detail=True, methods=["post"], url_path="service-otp")
    def service_otp(self, request, pk=None):
        """Allow only the booking customer to retrieve a short-lived service OTP."""
        from apps.payments.lifecycle import PaymentLifecycleError, issue_service_otp
        from apps.payments.models import BookingFinancialPlan, ServiceOTPChallenge

        booking = self.get_object()
        if not BookingFinancialPlan.objects.filter(booking=booking).exists():
            return Response(
                {"detail": "This booking is not enrolled in the split-payment service lifecycle."},
                status=status.HTTP_409_CONFLICT,
            )

        purpose = request.data.get("purpose")
        if purpose not in (ServiceOTPChallenge.Purpose.START, ServiceOTPChallenge.Purpose.COMPLETION):
            return Response(
                {"purpose": ["Choose 'start' or 'completion'."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            challenge, otp = issue_service_otp(
                booking_id=booking.pk,
                purpose=purpose,
                requested_by=request.user,
            )
        except PaymentLifecycleError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        # This response is customer-authenticated and is the one-time handoff
        # for the customer to share with the assigned professional in person.
        return Response({
            "booking_id": booking.pk,
            "purpose": purpose,
            "otp": otp,
            "expires_at": challenge.expires_at.isoformat(),
            "message": "Share this OTP with your assigned professional only at the relevant service milestone.",
        })

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

        # New checkouts are payment-gated: no worker offers exist until
        # every booking-line advance is captured and allocated.
        order = Order.objects.create(
            customer=request.user,
            address=cart.address,
            status=Order.Status.AWAITING_PAYMENT,
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

            from apps.payments.lifecycle import create_financial_plan
            create_financial_plan(booking)

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

        advance_due_total = sum(
            (item.booking.financial_plan.advance_due for item in order.items.select_related("booking")),
            Decimal("0.00"),
        )
        cart.items.all().delete()
        return Response({
            "order_id": order.id,
            "status": order.status,
            "address_id": order.address_id,
            "currency": order.currency,
            "subtotal": str(order.subtotal),
            "tax_amount": str(order.tax_amount),
            "total_amount": str(order.total_amount),
            "advance_due_total": str(advance_due_total),
            "payment_required": True,
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
            "dispatch": [],
            "next_step": "Pay the booking advance. Worker offers will be created only after the complete advance is captured and reconciled.",
        }, status=status.HTTP_201_CREATED)


class CustomerOrderDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, order_id):
        order = get_object_or_404(
            Order.objects.prefetch_related("items__booking__assignment__worker__user"),
            pk=order_id,
            customer=request.user,
        )
        items = []
        for row in order.items.all():
            booking = row.booking
            assignment = getattr(booking, "assignment", None)
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
            })
        # GET endpoints must not advance order lifecycle state. Worker offer
        # acceptance performs the AWAITING_PAYMENT transition atomically.
        return Response({
            "id": order.id,
            "status": order.status,
            "currency": order.currency,
            "subtotal": str(order.subtotal),
            "tax_amount": str(order.tax_amount),
            "total_amount": str(order.total_amount),
            "items": items,
            "ready_for_payment": order.status == Order.Status.AWAITING_PAYMENT,
        })


class CustomerOrderListView(APIView):
    """List the authenticated customer's multi-service orders."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        orders = Order.objects.filter(customer=request.user).prefetch_related(
            "items__booking"
        ).order_by("-created_at")
        results = []
        for order in orders:
            # Order state is changed by the assignment workflow, never by a read.
            results.append({
                "id": order.id,
                "status": order.status,
                "total_amount": str(order.total_amount),
                "created_at": order.created_at,
                "item_count": order.items.count(),
                "ready_for_payment": order.status == Order.Status.AWAITING_PAYMENT,
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
