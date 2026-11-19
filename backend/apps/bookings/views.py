from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils import timezone
from django.db import transaction
from django.conf import settings
from decimal import Decimal
from datetime import date, timedelta
from django.shortcuts import get_object_or_404
from django.core.exceptions import ObjectDoesNotExist
from django.core.files.storage import FileSystemStorage
from django.http import FileResponse
from rest_framework.parsers import MultiPartParser, FormParser
import mimetypes
import uuid

from .models import Booking, BookingStatusHistory, BookingAssignment, CustomerCart, CartItem, Order, AppointmentGroup, OrderItem, BookingAddOn, WorkerOffer, BookingQuote, BookingWorkEvidence, RecurringWashPlan, RecurringWashVisit
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
from apps.catalog.models import FormField


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


def _schedule_recurring_plan_refund(plan_id):
    import logging
    from apps.payments.refunds import request_recurring_plan_refund

    try:
        plan = RecurringWashPlan.objects.get(pk=plan_id)
        request_recurring_plan_refund(plan)
    except Exception:
        logging.getLogger(__name__).exception(
            "Could not schedule unused recurring plan refund for plan %s", plan_id
        )


class CustomerRecurringWashPlanCancelView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request, plan_id):
        plan = get_object_or_404(
            RecurringWashPlan.objects.select_for_update(),
            pk=plan_id,
            customer=request.user,
        )
        if plan.status not in (
            RecurringWashPlan.Status.PAID_PENDING_SETUP,
            RecurringWashPlan.Status.ACTIVE,
            RecurringWashPlan.Status.PAUSED,
        ):
            return Response(
                {"detail": "This recurring plan cannot be cancelled in its current state."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        reason = str(request.data.get("reason", "")).strip()
        if len(reason) > 500:
            return Response({"reason": "Keep the cancellation reason under 500 characters."}, status=status.HTTP_400_BAD_REQUEST)

        now = timezone.now()
        for visit in plan.visits.select_for_update(of=("self",)).select_related("booking").order_by("visit_number"):
            if visit.status in (
                RecurringWashVisit.Status.COMPLETED,
                RecurringWashVisit.Status.IN_PROGRESS,
            ):
                continue
            booking = visit.booking if visit.booking_id else None
            if booking and booking.status in (
                Booking.Status.PENDING,
                Booking.Status.CONFIRMED,
                Booking.Status.ASSIGNED,
            ):
                old_status = booking.status
                assignment = getattr(booking, "assignment", None)
                if assignment:
                    Notification.objects.create(
                        user=assignment.worker.user,
                        type=Notification.Type.WORKER_OFFER_WITHDRAWN,
                        title="Recurring visit cancelled",
                        body=f"Recurring Car Wash visit #{visit.visit_number} for plan #{plan.pk} was cancelled by the customer.",
                        channel=Notification.Channel.IN_APP,
                        data={"booking_id": booking.pk, "recurring_visit_id": visit.pk},
                    )
                    assignment.delete()
                WorkerOffer.objects.filter(
                    booking=booking,
                    status__in=(
                    WorkerOffer.Status.PENDING,
                    WorkerOffer.Status.ACCEPTED,
                    WorkerOffer.Status.DECLINED,
                    WorkerOffer.Status.EXPIRED,
                ),
                ).update(status=WorkerOffer.Status.WITHDRAWN, responded_at=now)
                booking.status = Booking.Status.CANCELLED
                booking.cancelled_at = now
                booking.cancelled_by = request.user
                booking.cancellation_reason = reason or "Recurring Car Wash plan cancelled."
                booking.save(update_fields=[
                    "status", "cancelled_at", "cancelled_by",
                    "cancellation_reason", "updated_at",
                ])
                BookingStatusHistory.objects.create(
                    booking=booking,
                    from_status=old_status,
                    to_status=Booking.Status.CANCELLED,
                    changed_by=request.user,
                    note=f"Recurring plan #{plan.pk} cancelled. {reason}".strip(),
                )
            visit.status = RecurringWashVisit.Status.CANCELLED
            visit.admin_notes = "Cancelled with recurring plan by customer."
            visit.save(update_fields=["status", "admin_notes", "updated_at"])

        plan.status = RecurringWashPlan.Status.CANCELLED
        plan.cancelled_at = now
        if reason:
            plan.admin_notes = (plan.admin_notes + "\nCustomer cancellation: " + reason).strip()
        plan.save(update_fields=["status", "cancelled_at", "admin_notes", "updated_at"])
        Notification.objects.create(
            user=request.user,
            type=Notification.Type.BOOKING_CANCELLED,
            title="Recurring Car Wash plan cancelled",
            body="Your remaining recurring visits have been cancelled. Any unused prepaid amount is being reviewed for refund.",
            channel=Notification.Channel.IN_APP,
            data={"recurring_plan_id": plan.pk},
        )
        transaction.on_commit(lambda plan_id=plan.pk: _schedule_recurring_plan_refund(plan_id))
        return Response({
            "detail": "Recurring plan cancelled. Refund processing for undelivered prepaid visits will be handled separately.",
            "status": plan.status,
        })


class CustomerRecurringWashVisitRescheduleView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request, visit_id):
        visit = get_object_or_404(
            RecurringWashVisit.objects.select_for_update(of=("self",)).select_related(
                "plan__service", "plan__variant", "plan__address", "booking"
            ),
            pk=visit_id,
            plan__customer=request.user,
        )
        plan = visit.plan
        if plan.status not in (
            RecurringWashPlan.Status.PAID_PENDING_SETUP,
            RecurringWashPlan.Status.ACTIVE,
        ):
            return Response({"detail": "Only an active recurring plan can be rescheduled."}, status=status.HTTP_400_BAD_REQUEST)
        if visit.status not in (
            RecurringWashVisit.Status.PENDING_SETUP,
            RecurringWashVisit.Status.BOOKED,
        ):
            return Response({"detail": "This visit can no longer be rescheduled."}, status=status.HTTP_400_BAD_REQUEST)

        from django.utils.dateparse import parse_datetime
        raw_value = request.data.get("scheduled_at")
        new_time = parse_datetime(str(raw_value)) if raw_value else None
        if new_time is None or timezone.is_naive(new_time):
            return Response({"scheduled_at": "Provide a valid timezone-aware ISO 8601 date and time."}, status=status.HTTP_400_BAD_REQUEST)
        if new_time <= timezone.now():
            return Response({"scheduled_at": "Choose a future date and time."}, status=status.HTTP_400_BAD_REQUEST)
        if plan.visits.exclude(pk=visit.pk).filter(scheduled_at=new_time).exists():
            return Response(
                {"scheduled_at": "Another visit in this plan already uses that date and time."},
                status=status.HTTP_409_CONFLICT,
            )

        booking = visit.booking if visit.booking_id else None
        if booking and (
            booking.status not in (Booking.Status.PENDING, Booking.Status.CONFIRMED)
            or hasattr(booking, "assignment")
        ):
            return Response({"detail": "A visit already assigned to a worker or already started cannot be rescheduled online. Contact AIRway support."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            check_service_available(plan.service, address=plan.address)
            duration = (
                plan.variant.duration_minutes
                if plan.variant_id and plan.variant.duration_minutes
                else plan.service.duration_minutes
            ) or 60
            quantity = max(int(plan.vehicle_quantity or 1), 1)
            check_slot_availability(
                service=plan.service,
                scheduled_at=new_time,
                duration_minutes=duration * (
                    1 if plan.service.pricing_type == "per_unit" else quantity
                ),
                booking_mode=Booking.BookingMode.SCHEDULED,
            )
        except (SlotConflictError, ServiceUnavailableError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

        old_time = visit.scheduled_at
        visit.scheduled_at = new_time
        visit.admin_notes = ""
        visit.save(update_fields=["scheduled_at", "admin_notes", "updated_at"])
        if booking:
            WorkerOffer.objects.filter(
                booking=booking,
                status__in=(
                    WorkerOffer.Status.PENDING,
                    WorkerOffer.Status.ACCEPTED,
                    WorkerOffer.Status.DECLINED,
                    WorkerOffer.Status.EXPIRED,
                ),
            ).update(status=WorkerOffer.Status.WITHDRAWN, responded_at=timezone.now())
            booking.scheduled_at = new_time
            booking.save(update_fields=["scheduled_at", "updated_at"])
            BookingStatusHistory.objects.create(
                booking=booking,
                from_status=booking.status,
                to_status=booking.status,
                changed_by=request.user,
                note=f"Recurring visit rescheduled from {old_time.isoformat()} to {new_time.isoformat()} by customer.",
            )
        Notification.objects.create(
            user=request.user,
            type=Notification.Type.SYSTEM_ANNOUNCEMENT,
            title="Recurring visit rescheduled",
            body=f"Visit #{visit.visit_number} is now scheduled for {timezone.localtime(new_time).strftime('%d %b %Y, %I:%M %p')}.",
            channel=Notification.Channel.IN_APP,
            data={"recurring_plan_id": plan.pk, "recurring_visit_id": visit.pk},
        )
        return Response({
            "detail": "Recurring visit rescheduled successfully.",
            "visit_id": visit.pk,
            "scheduled_at": visit.scheduled_at.isoformat(),
            "status": visit.status,
        })


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

        # Keep the same parent-order -> child-booking lock order used by
        # dispatch and reschedule. Locking the booking first can deadlock when
        # dispatch holds the order row and is waiting for this booking.
        booking = self.get_object()
        order_item_ref = OrderItem.objects.filter(
            booking_id=booking.pk
        ).values("order_id").first()
        order = None
        if order_item_ref:
            order = get_object_or_404(
                Order.objects.select_for_update(),
                pk=order_item_ref["order_id"],
                customer=request.user,
            )
        booking = get_object_or_404(
            Booking.objects.select_for_update(of=("self",)).filter(
                customer=request.user
            ),
            pk=booking.pk,
        )
        recurring_plan = getattr(booking, "recurring_wash_plan", None)
        if recurring_plan and recurring_plan.status in (
            RecurringWashPlan.Status.PAID_PENDING_SETUP,
            RecurringWashPlan.Status.ACTIVE,
            RecurringWashPlan.Status.PAUSED,
        ):
            return Response(
                {"detail": "This booking belongs to a prepaid recurring plan. Cancel the recurring plan from its plan controls so all remaining visits and refunds are handled together."},
                status=status.HTTP_400_BAD_REQUEST,
            )
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
        if order is not None:
            active_remaining = order.items.exclude(
                booking__status=Booking.Status.CANCELLED
            ).exists()
            order.status = (
                Order.Status.PARTIALLY_CANCELLED
                if active_remaining else Order.Status.CANCELLED
            )
            order.save(update_fields=["status", "updated_at"])
            WorkerOffer.objects.filter(
                booking=booking, order__isnull=True,
                status__in=(WorkerOffer.Status.PENDING, WorkerOffer.Status.ACCEPTED),
            ).update(
                status=WorkerOffer.Status.WITHDRAWN,
                responded_at=timezone.now(),
            )
            if booking.appointment_group_id:
                # A pending group offer includes every active service in the
                # appointment. Withdraw it and let dispatch rebuild the offer
                # for the remaining services only.
                WorkerOffer.objects.filter(
                    appointment_group_id=booking.appointment_group_id,
                    status=WorkerOffer.Status.PENDING,
                ).update(
                    status=WorkerOffer.Status.WITHDRAWN,
                    responded_at=timezone.now(),
                )
            # Also close any pre-transition whole-order offer still pending.
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
                booking=booking,
                status__in=(WorkerOffer.Status.PENDING, WorkerOffer.Status.ACCEPTED),
            ).update(
                status=WorkerOffer.Status.WITHDRAWN,
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

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def reschedule(self, request, pk=None):
        """Reschedule an eligible booking, preserving shared-order appointment rules."""
        from django.utils.dateparse import parse_datetime

        # Lock the parent order before its child bookings, matching dispatcher
        # lock order and avoiding order/booking deadlocks.
        booking = get_object_or_404(
            Booking.objects.filter(customer=request.user).select_related(
                "service__category", "variant", "address__zone__city"
            ),
            pk=pk,
        )
        order_item_ref = OrderItem.objects.filter(
            booking_id=booking.pk
        ).values("order_id").first()
        order = None
        if order_item_ref:
            order = get_object_or_404(
                Order.objects.select_for_update(),
                pk=order_item_ref["order_id"],
                customer=request.user,
            )
        booking = get_object_or_404(
            Booking.objects.select_for_update(of=("self",)).select_related(
                "service__category", "variant", "address__zone__city"
            ),
            pk=booking.pk,
            customer=request.user,
        )
        if booking.status not in (Booking.Status.PENDING, Booking.Status.CONFIRMED) or BookingAssignment.objects.filter(booking=booking).exists():
            return Response(
                {"detail": "This booking is already assigned, started, completed or cancelled and cannot be rescheduled online."},
                status=status.HTTP_409_CONFLICT,
            )
        recurring_plan = getattr(booking, "recurring_wash_plan", None)
        if recurring_plan and recurring_plan.status in (
            RecurringWashPlan.Status.PAID_PENDING_SETUP,
            RecurringWashPlan.Status.ACTIVE,
            RecurringWashPlan.Status.PAUSED,
        ):
            return Response(
                {"detail": "Reschedule this visit from the recurring plan controls."},
                status=status.HTTP_409_CONFLICT,
            )

        raw_time = request.data.get("scheduled_at")
        new_time = parse_datetime(str(raw_time)) if raw_time else None
        if new_time is None or timezone.is_naive(new_time):
            return Response(
                {"scheduled_at": "Provide a valid timezone-aware ISO 8601 date and time."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if new_time <= timezone.now():
            return Response(
                {"scheduled_at": "Choose a future date and time."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        raw_drop = request.data.get("drop_scheduled_at")
        new_drop = parse_datetime(str(raw_drop)) if raw_drop else None
        if raw_drop and (new_drop is None or timezone.is_naive(new_drop)):
            return Response(
                {"drop_scheduled_at": "Provide a valid timezone-aware ISO 8601 date and time."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if booking.booking_mode == Booking.BookingMode.PICKUP_DROP:
            if new_drop is None or new_drop <= new_time:
                return Response(
                    {"drop_scheduled_at": "Choose a drop-off time after pickup."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        elif new_drop is not None:
            return Response(
                {"drop_scheduled_at": "Drop-off time is only valid for Pickup & Drop bookings."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        targets = [booking]
        shared_appointment = False
        appointment_group = getattr(booking, "appointment_group", None)
        if appointment_group is not None:
            # A customer reschedules the complete service-type appointment,
            # without moving other appointment groups in the same checkout.
            targets = list(
                Booking.objects.select_for_update(of=("self",)).filter(
                    appointment_group=appointment_group
                ).exclude(status=Booking.Status.CANCELLED).select_related(
                    "service__category", "variant", "address__zone__city"
                ).order_by("id")
            )
            shared_appointment = True
        elif order is not None:
            scheduling = (order.metadata or {}).get("scheduling_v1", {})
            shared_appointment = scheduling.get("mode") == "same_appointment"
            if shared_appointment:
                targets = list(
                    Booking.objects.select_for_update(of=("self",)).filter(
                        order_item__order=order
                    ).exclude(status=Booking.Status.CANCELLED).select_related(
                        "service__category", "variant", "address__zone__city"
                    ).order_by("id")
                )

        for target in targets:
            if target.status not in (Booking.Status.PENDING, Booking.Status.CONFIRMED):
                return Response(
                    {"detail": "This service or a service in its shared appointment is already assigned, started, completed or cancelled. Contact AIRway support to change it."},
                    status=status.HTTP_409_CONFLICT,
                )
            if BookingAssignment.objects.filter(booking=target).exists():
                return Response(
                    {"detail": "A professional is already assigned to this service. Contact AIRway support to reschedule."},
                    status=status.HTTP_409_CONFLICT,
                )
            if (
                appointment_group is None
                and target.booking_mode != booking.booking_mode
            ):
                return Response(
                    {"detail": "Services with different booking modes cannot be moved as one shared appointment."},
                    status=status.HTTP_409_CONFLICT,
                )

        target_ids = [target.pk for target in targets]
        try:
            for target in targets:
                check_service_available(target.service, address=target.address)
                duration = (
                    target.variant.duration_minutes
                    if target.variant_id and target.variant.duration_minutes
                    else target.service.duration_minutes
                ) or 60
                quantity = max(
                    int((target.pricing_snapshot or {}).get("quantity", 1) or 1), 1
                )
                duration *= (
                    1 if target.service.pricing_type == "per_unit" else quantity
                )
                if target.booking_mode == Booking.BookingMode.PICKUP_DROP:
                    # Preserve each service's pickup-to-drop interval when the
                    # shared appointment is moved together.
                    if shared_appointment:
                        old_drop = target.drop_scheduled_at
                        drop_time = (
                            new_drop if target.pk == booking.pk else
                            (new_time + (old_drop - target.scheduled_at) if old_drop else None)
                        )
                    else:
                        drop_time = new_drop
                else:
                    drop_time = None
                check_slot_availability(
                    service=target.service,
                    scheduled_at=new_time,
                    duration_minutes=duration,
                    booking_mode=target.booking_mode,
                    drop_scheduled_at=drop_time,
                    exclude_booking_ids=target_ids,
                )
        except (SlotConflictError, ServiceUnavailableError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

        now = timezone.now()
        old_times = {target.pk: target.scheduled_at for target in targets}
        for target in targets:
            old_status = target.status
            if target.booking_mode == Booking.BookingMode.PICKUP_DROP:
                if shared_appointment:
                    old_drop = target.drop_scheduled_at
                    target.drop_scheduled_at = (
                        new_drop if target.pk == booking.pk else
                        (new_time + (old_drop - target.scheduled_at) if old_drop else None)
                    )
                else:
                    target.drop_scheduled_at = new_drop
            target.scheduled_at = new_time
            target.save(update_fields=["scheduled_at", "drop_scheduled_at", "updated_at"])
            WorkerOffer.objects.filter(
                booking=target,
                status__in=(WorkerOffer.Status.PENDING, WorkerOffer.Status.ACCEPTED),
            ).update(
                status=WorkerOffer.Status.WITHDRAWN,
                responded_at=now,
            )
            BookingStatusHistory.objects.create(
                booking=target,
                from_status=old_status,
                to_status=old_status,
                changed_by=request.user,
                note=(
                    f"Customer rescheduled from {old_times[target.pk].isoformat()} "
                    f"to {new_time.isoformat()}."
                ),
            )

        if appointment_group is not None:
            import secrets
            from datetime import timedelta
            appointment_group.scheduled_at = new_time
            appointment_group.arrival_otp = f"{secrets.randbelow(1_000_000):06d}"
            appointment_group.arrival_otp_expires_at = new_time + timedelta(hours=6)
            appointment_group.arrival_otp_verified_at = None
            appointment_group.arrival_otp_attempts = 0
            appointment_group.arrival_otp_locked_until = None
            appointment_group.save(update_fields=[
                "scheduled_at", "arrival_otp", "arrival_otp_expires_at",
                "arrival_otp_verified_at", "arrival_otp_attempts",
                "arrival_otp_locked_until", "updated_at",
            ])
            WorkerOffer.objects.filter(
                appointment_group=appointment_group,
                status__in=(WorkerOffer.Status.PENDING, WorkerOffer.Status.ACCEPTED),
            ).update(status=WorkerOffer.Status.WITHDRAWN, responded_at=now)

        if order and shared_appointment and appointment_group is None:
            metadata = dict(order.metadata or {})
            scheduling = dict(metadata.get("scheduling_v1", {}))
            scheduling["shared_appointment_at"] = new_time.isoformat()
            metadata["scheduling_v1"] = scheduling
            order.metadata = metadata
            order.save(update_fields=["metadata", "updated_at"])

        Notification.objects.create(
            user=request.user,
            type=Notification.Type.SYSTEM_ANNOUNCEMENT,
            title="Service rescheduled",
            body=(
                f"{len(targets)} services in your shared appointment are now scheduled for "
                if shared_appointment and len(targets) > 1
                else "Your service is now scheduled for "
            ) + f"{timezone.localtime(new_time).strftime('%d %b %Y, %I:%M %p')}.",
            channel=Notification.Channel.IN_APP,
            data={
                "booking_id": booking.pk,
                "order_id": order.pk if order else None,
                "rescheduled_booking_ids": target_ids,
            },
        )

        if order:
            from apps.bookings.dispatcher import DispatcherService
            transaction.on_commit(
                lambda order_id=order.pk: DispatcherService.dispatch_order(
                    Order.objects.get(pk=order_id)
                )
            )
        elif booking.status in (Booking.Status.PENDING, Booking.Status.CONFIRMED):
            from apps.bookings.dispatcher import DispatcherService
            transaction.on_commit(
                lambda booking_id=booking.pk: DispatcherService.dispatch_offers(
                    Booking.objects.get(pk=booking_id)
                )
            )

        return Response({
            "detail": "Booking rescheduled successfully.",
            "booking_id": booking.pk,
            "scheduled_at": new_time.isoformat(),
            "rescheduled_booking_ids": target_ids,
            "shared_appointment": shared_appointment,
            "appointment_group_id": appointment_group.pk if appointment_group else None,
        })

    @action(detail=True, methods=["post"], url_path="quote/respond")
    @transaction.atomic
    def respond_to_quote(self, request, pk=None):
        booking = self.get_object()
        decision = str(request.data.get("decision", "")).strip().lower()
        note = str(request.data.get("note", "")).strip()
        if decision not in ("accept", "reject"):
            return Response({"decision": "Choose accept or reject."}, status=status.HTTP_400_BAD_REQUEST)
        if len(note) > 1000:
            return Response({"note": "Note must not exceed 1000 characters."}, status=status.HTTP_400_BAD_REQUEST)
        if booking.status != Booking.Status.IN_PROGRESS:
            return Response({"detail": "A quote can be approved only while the inspection job is in progress."}, status=status.HTTP_400_BAD_REQUEST)

        quote = BookingQuote.objects.select_for_update().filter(
            booking=booking, status=BookingQuote.Status.PENDING_CUSTOMER
        ).order_by("-version").first()
        if quote is None:
            return Response({"detail": "There is no quote waiting for your response."}, status=status.HTTP_404_NOT_FOUND)
        if quote.expires_at and quote.expires_at <= timezone.now():
            quote.status = BookingQuote.Status.REJECTED
            quote.customer_response_note = "Quote expired before customer response."
            quote.responded_at = timezone.now()
            quote.save(update_fields=["status", "customer_response_note", "responded_at", "updated_at"])
            return Response({"detail": "This quote has expired. Ask the worker to submit a revised estimate."}, status=status.HTTP_400_BAD_REQUEST)

        quote.customer_response_note = note
        quote.responded_at = timezone.now()
        if decision == "reject":
            quote.status = BookingQuote.Status.REJECTED
            quote.save(update_fields=["status", "customer_response_note", "responded_at", "updated_at"])
            Notification.objects.create(
                user=quote.worker.user,
                type=Notification.Type.SYSTEM_ANNOUNCEMENT,
                title="Customer requested a quote revision",
                body=f"The customer declined quote v{quote.version} for booking #{booking.id}. Review their note and submit a revised estimate.",
                channel=Notification.Channel.IN_APP,
                data={"booking_id": booking.id, "quote_id": quote.id, "purpose": "booking_quote_rejected"},
            )
            return Response({"detail": "Quote declined. The worker can review your note and submit a revised estimate.", "quote_status": quote.status})

        order_item = OrderItem.objects.select_for_update().filter(
            booking=booking
        ).select_related("order").first()
        if order_item is None and hasattr(booking, "payment"):
            return Response(
                {"detail": "This legacy booking already has a payment attempt. Contact AIRway support before approving an additional estimate."},
                status=status.HTTP_409_CONFLICT,
            )

        quote_subtotal = (
            quote.labour_amount + quote.material_amount + quote.other_amount
        )
        quote_total = quote_subtotal + quote.tax_amount
        snapshot = dict(booking.pricing_snapshot or {})
        visit_fee = Decimal(str(snapshot.get("visit_fee", "0") or "0"))
        visit_tax = Decimal(str(snapshot.get("tax", "0") or "0"))
        updated_subtotal = visit_fee + quote_subtotal
        updated_tax = visit_tax + quote.tax_amount
        updated_total = updated_subtotal + updated_tax
        snapshot.update({
            "inspection_quote_id": quote.id,
            "inspection_quote_version": quote.version,
            "inspection_quote_subtotal": str(quote_subtotal),
            "inspection_quote_tax": str(quote.tax_amount),
            "inspection_quote_total": str(quote_total),
            "inspection_quote_items": quote.line_items,
            "inspection_quote_notes": quote.notes,
            "subtotal": str(updated_subtotal),
            "tax": str(updated_tax),
            "total": str(updated_total),
        })
        booking.pricing_snapshot = snapshot
        booking.save(update_fields=["pricing_snapshot", "updated_at"])

        if order_item:
            order = Order.objects.select_for_update().get(pk=order_item.order_id)
            order_item.pricing_snapshot = snapshot
            order_item.line_subtotal = updated_subtotal
            order_item.tax_amount = updated_tax
            order_item.line_total = updated_total
            order_item.save(update_fields=[
                "pricing_snapshot", "line_subtotal", "tax_amount", "line_total", "updated_at",
            ])

            active_items = list(order.items.exclude(
                booking__status=Booking.Status.CANCELLED
            ))
            order.subtotal = sum((row.line_subtotal for row in active_items), Decimal("0.00"))
            order.tax_amount = sum((row.tax_amount for row in active_items), Decimal("0.00"))
            order.total_amount = order.subtotal + order.tax_amount - order.discount_amount

            metadata = dict(order.metadata or {})
            allocation = metadata.get("payment_allocation_v1")
            if isinstance(allocation, dict):
                balance_rows = list(allocation.get("balance", []))
                balance_row = next(
                    (row for row in balance_rows if row.get("order_item_id") == order_item.id),
                    None,
                )
                if balance_row is None:
                    balance_rows.append({
                        "order_item_id": order_item.id,
                        "booking_id": booking.id,
                        "amount": str(quote_total),
                    })
                else:
                    balance_row["amount"] = str(
                        Decimal(str(balance_row.get("amount", "0"))) + quote_total
                    )
                allocation["balance"] = balance_rows
                allocation["balance_total"] = str(
                    Decimal(str(allocation.get("balance_total", "0"))) + quote_total
                )
                advance_total = Decimal(str(allocation.get("advance_total", "0")))
                allocation["percentage"] = str(
                    (advance_total * Decimal("100") / order.total_amount).quantize(Decimal("0.01"))
                    if order.total_amount > 0 else Decimal("0.00")
                )
                metadata["payment_allocation_v1"] = allocation
            order.metadata = metadata
            order.save(update_fields=[
                "subtotal", "tax_amount", "total_amount", "metadata", "updated_at",
            ])

        quote.status = BookingQuote.Status.ACCEPTED
        quote.save(update_fields=["status", "customer_response_note", "responded_at", "updated_at"])

        from apps.bookings.models import RecurringWashPlan
        recurring_plan = RecurringWashPlan.objects.select_for_update().filter(
            source_booking=booking,
            status=RecurringWashPlan.Status.AWAITING_QUOTE,
        ).first()
        if recurring_plan:
            recurring_plan.quoted_total = quote_total
            recurring_plan.status = RecurringWashPlan.Status.AWAITING_PAYMENT
            recurring_plan.quote_accepted_at = timezone.now()
            recurring_plan.save(update_fields=[
                "quoted_total", "status", "quote_accepted_at", "updated_at",
            ])
        Notification.objects.create(
            user=quote.worker.user,
            type=Notification.Type.SYSTEM_ANNOUNCEMENT,
            title="Customer approved the estimate",
            body=f"The customer approved quote v{quote.version} for booking #{booking.id}. You can proceed with the work.",
            channel=Notification.Channel.IN_APP,
            data={"booking_id": booking.id, "quote_id": quote.id, "purpose": "booking_quote_accepted"},
        )
        return Response({
            "detail": "Estimate approved. The final payable amount has been updated.",
            "quote_status": quote.status,
            "pricing_snapshot": snapshot,
            "order_total": str(order_item.order.total_amount) if order_item else str(updated_total),
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
        exclude_booking_ids = []
        if data.get("exclude_booking_id"):
            existing_booking = Booking.objects.filter(
                pk=data["exclude_booking_id"], customer=request.user,
                service=service,
            ).first()
            if existing_booking is None:
                return Response(
                    {"detail": "Booking cannot be excluded from this availability check."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            exclude_booking_ids.append(existing_booking.pk)

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
            duration = (duration or 60) * (
                1 if service.pricing_type == "per_unit" else data.get("quantity", 1)
            )

            check_slot_availability(
                service=service,
                scheduled_at=scheduled_at,
                duration_minutes=duration,
                booking_mode=booking_mode,
                drop_scheduled_at=drop_scheduled_at,
                exclude_booking_ids=exclude_booking_ids,
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
        worker_is_approved = worker.status == worker.Status.APPROVED

        # Expose only admin-approved public professional information. Never return
        # personal phone, email, home address, ID documents or unverified photos.
        from apps.workers.models import WorkerDocument
        photo = worker.documents.filter(
            doc_type=WorkerDocument.DocumentType.PHOTO,
            status=WorkerDocument.Status.VERIFIED,
        ).order_by("-created_at", "-id").first() if worker_is_approved else None
        try:
            photo_url = request.build_absolute_uri(photo.file.url) if photo else None
        except Exception:
            photo_url = None
        verified_services = worker.worker_services.filter(
            capabilities_verified=True,
            service__is_active=True,
            service__category__is_active=True,
        ).select_related("service", "service__category").order_by("service__title") if worker_is_approved else worker.worker_services.none()
        scheduled_at = (
            booking.appointment_group.scheduled_at
            if booking.appointment_group_id else booking.scheduled_at
        )
        now = timezone.now()
        location_available_at = (
            scheduled_at - timedelta(minutes=30) if scheduled_at else None
        )
        location_visibility_window_open = bool(
            location_available_at and now >= location_available_at
        )
        location_is_fresh = bool(
            worker_is_approved
            and location_visibility_window_open
            and assignment.accepted_at
            and booking.status in (Booking.Status.ASSIGNED, Booking.Status.IN_PROGRESS)
            and assignment.live_location_updated_at
            and assignment.live_location_updated_at >= timezone.now() - timedelta(minutes=2)
            and assignment.live_latitude is not None
            and assignment.live_longitude is not None
            and (assignment.live_accuracy_m is None or assignment.live_accuracy_m <= 150)
        )
        return Response({
            "is_assigned": True,
            "worker_id": worker.id,
            "worker_name": (worker.user.name or "AIRway Professional") if worker_is_approved else "AIRway Professional",
            "worker_photo": photo_url,
            "worker_bio": worker.bio if worker_is_approved else None,
            "worker_experience_years": worker.experience_years if worker_is_approved else None,
            "worker_qualification": worker.qualification if worker_is_approved else None,
            "worker_rating": (float(worker.rating_avg) if worker.rating_avg else None) if worker_is_approved else None,
            "worker_rating_count": worker.rating_count if worker_is_approved else 0,
            "worker_completed_jobs": BookingAssignment.objects.filter(
                worker=worker, booking__status=Booking.Status.COMPLETED
            ).count() if worker_is_approved else 0,
            "worker_unavailable": not worker_is_approved,
            "worker_verified_services": [{
                "service": row.service.title,
                "category": row.service.category.title,
                "experience_years": row.experience_years,
                "verified_skills": row.capabilities or [],
            } for row in verified_services],
            "status": booking.status,
            "assigned_at": assignment.assigned_at,
            "started_at": assignment.started_at,
            "worker_latitude": float(assignment.live_latitude) if location_is_fresh else None,
            "worker_longitude": float(assignment.live_longitude) if location_is_fresh else None,
            "worker_location_accuracy_m": float(assignment.live_accuracy_m) if location_is_fresh and assignment.live_accuracy_m is not None else None,
            "worker_location_updated_at": assignment.live_location_updated_at.isoformat() if location_is_fresh else None,
            "location_is_fresh": location_is_fresh,
            "location_visibility_window_open": location_visibility_window_open,
            "location_available_at": location_available_at.isoformat() if location_available_at else None,
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
        from apps.bookings.models import RecurringWashVisit
        RecurringWashVisit.objects.filter(
            booking=booking,
            status=RecurringWashVisit.Status.BOOKED,
        ).update(status=RecurringWashVisit.Status.IN_PROGRESS, updated_at=timezone.now())

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
        if booking.booking_mode == Booking.BookingMode.INSPECTION or booking.service.pricing_type == "quote":
            accepted_quote = booking.quotes.filter(status=BookingQuote.Status.ACCEPTED).exists()
            if not accepted_quote:
                return Response(
                    {"detail": "The customer must approve the inspection estimate before the job can be completed."},
                    status=status.HTTP_409_CONFLICT,
                )

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

                notification_title = "Your service completion code is ready"
                notification_body = (
                    f"Your AIRway completion code for booking #{locked_booking.id} is {code}. "
                    "Share it with your assigned professional only after the service is finished. "
                    "It expires in 10 minutes."
                )
                Notification.objects.create(
                    user=locked_booking.customer,
                    type=Notification.Type.SYSTEM_ANNOUNCEMENT,
                    title="Share your service completion code",
                    body=notification_body,
                    channel=Notification.Channel.IN_APP,
                    data={
                        "booking_id": locked_booking.id,
                        "purpose": "service_completion_otp",
                        "completion_code": code,
                        "expires_at": expires_at.isoformat(),
                    },
                )
                order_item = getattr(locked_booking, "order_item", None)
                push_data = {
                    "notification_kind": "customer_completion_otp",
                    "booking_id": locked_booking.id,
                    "order_id": order_item.order_id if order_item else "",
                }
                from apps.notifications.service import send_push_notification
                transaction.on_commit(
                    lambda customer=locked_booking.customer, title=notification_title, payload=push_data:
                        send_push_notification(
                            customer,
                            title,
                            "Your professional requested the completion code. Open your AIRway order to view it.",
                            data=payload,
                            channel_id="airway_general",
                        )
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
            from apps.ratings.models import BookingCompletionFeedback
            completion_feedback = BookingCompletionFeedback.objects.select_for_update().filter(
                booking=locked_booking,
                customer=locked_booking.customer,
            ).first()
            if locked_booking.appointment_group_id and completion_feedback is None:
                return Response(
                    {"detail": "Customer feedback or the explicit skip action is required before completion verification."},
                    status=status.HTTP_409_CONFLICT,
                )
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
            BookingAssignment.objects.filter(booking=locked_booking).update(
                live_latitude=None,
                live_longitude=None,
                live_accuracy_m=None,
                live_location_updated_at=None,
            )
            from apps.bookings.models import RecurringWashVisit, RecurringWashPlan
            recurring_visit = RecurringWashVisit.objects.select_for_update().filter(
                booking=locked_booking
            ).select_related("plan").first()
            if recurring_visit:
                recurring_visit.status = RecurringWashVisit.Status.COMPLETED
                recurring_visit.save(update_fields=["status", "updated_at"])
                unfinished = recurring_visit.plan.visits.exclude(
                    status__in=(
                        RecurringWashVisit.Status.COMPLETED,
                        RecurringWashVisit.Status.CANCELLED,
                        RecurringWashVisit.Status.SKIPPED,
                    )
                ).exists()
                if not unfinished:
                    RecurringWashPlan.objects.filter(
                        pk=recurring_visit.plan_id,
                        status__in=(
                            RecurringWashPlan.Status.ACTIVE,
                            RecurringWashPlan.Status.PAID_PENDING_SETUP,
                        ),
                    ).update(
                        status=RecurringWashPlan.Status.COMPLETED,
                        updated_at=now,
                    )
            assignment.completed_at = now
            assignment.save(update_fields=["completed_at", "updated_at"])
            BookingStatusHistory.objects.create(
                booking=locked_booking,
                from_status=old_status,
                to_status=Booking.Status.COMPLETED,
                changed_by=request.user,
                note="Service completion verified with customer-shared OTP.",
            )
            if not completion_feedback.skipped:
                from apps.ratings.models import BookingRating, RatingSummary
                overall_rating = (
                    completion_feedback.service_quality
                    + completion_feedback.worker_behaviour
                    + 1
                ) // 2
                BookingRating.objects.get_or_create(
                    booking=locked_booking,
                    rater=locked_booking.customer,
                    defaults={
                        "rated": assignment.worker.user,
                        "rating_type": "customer",
                        "rating": overall_rating,
                        "comment": completion_feedback.comment,
                    },
                )
                summary, _ = RatingSummary.objects.get_or_create(
                    user=assignment.worker.user
                )
                summary.update_stats()

            # Referral reward is earned only on the referred customer's first
            # successfully OTP-verified completed service.
            from apps.accounts.referrals import reward_referral_for_first_completed_booking
            reward_referral_for_first_completed_booking(locked_booking)

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

        schedule_mode = str(request.data.get("schedule_mode", "separate")).strip().lower()
        if schedule_mode not in ("separate", "same_appointment"):
            return Response(
                {"schedule_mode": "Choose separate or same_appointment."},
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
                context={
                    "request": request,
                    "defer_worker_dispatch": True,
                    "allow_issue_photo_metadata": True,
                },
            )
            serializer.is_valid(raise_exception=True)
            prepared.append((item, serializer))

        # Services below the same root catalogue category form one appointment.
        # Each group has one shared start time; different root categories remain
        # independently schedulable inside the same parent checkout.
        grouped_by_root = {}
        for item, serializer in prepared:
            root_category = item.service.category
            while root_category.parent_id:
                root_category = root_category.parent
            group = grouped_by_root.setdefault(root_category.pk, {
                "category": root_category,
                "items": [],
            })
            group["items"].append((item, serializer))

        for group in grouped_by_root.values():
            group_times = {
                serializer.validated_data.get("scheduled_at")
                for _, serializer in group["items"]
            }
            if None in group_times or len(group_times) != 1:
                return Response(
                    {
                        "detail": (
                            f"All services in {group['category'].title} must use "
                            "the same date and time for one appointment. Other service "
                            "categories can have their own schedule."
                        ),
                        "category_root": group["category"].slug,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            group["scheduled_at"] = next(iter(group_times))
            group_modes = {item.service.booking_mode for item, _ in group["items"]}
            if len(group_modes) != 1:
                return Response(
                    {
                        "detail": (
                            f"Services in {group['category'].title} use different "
                            "appointment modes and cannot share one appointment."
                        ),
                        "category_root": group["category"].slug,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if next(iter(group_modes)) == Booking.BookingMode.PICKUP_DROP:
                group_drop_times = {
                    serializer.validated_data.get("drop_scheduled_at")
                    for _, serializer in group["items"]
                }
                if None in group_drop_times or len(group_drop_times) != 1:
                    return Response(
                        {
                            "detail": (
                                f"Pickup & Drop services in {group['category'].title} "
                                "must share the same drop-off time."
                            ),
                            "category_root": group["category"].slug,
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

        raw_group_messages = request.data.get("group_messages", cart.group_messages or {})
        if not isinstance(raw_group_messages, dict):
            return Response(
                {"group_messages": "Provide one optional message per appointment group."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        valid_group_slugs = {group["category"].slug for group in grouped_by_root.values()}
        group_messages = {}
        for slug, raw_message in raw_group_messages.items():
            if slug not in valid_group_slugs:
                return Response(
                    {"group_messages": f"Unknown appointment group: {slug}."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if not isinstance(raw_message, str) or len(raw_message.strip()) > 500:
                return Response(
                    {"group_messages": "Each appointment message must be text up to 500 characters."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            group_messages[slug] = raw_message.strip()

        # A shared appointment means every service starts at the same instant.
        # Each service is still validated independently for its own duration,
        # booking mode, zone and worker eligibility. Worker assignment remains
        # independent; a shared start time never promises one common worker.
        shared_appointment_at = None
        if schedule_mode == "same_appointment":
            scheduled_values = [
                serializer.validated_data.get("scheduled_at")
                for _, serializer in prepared
            ]
            if any(value is None for value in scheduled_values) or len(set(scheduled_values)) != 1:
                return Response(
                    {"detail": "For one shared appointment, choose the exact same date and time for every service."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            shared_appointment_at = scheduled_values[0]

        order = Order.objects.create(
            customer=request.user,
            address=cart.address,
            status=Order.Status.AWAITING_ASSIGNMENT,
        )
        appointment_groups = {}
        for root_id, group_data in grouped_by_root.items():
            category = group_data["category"]
            import secrets
            from datetime import timedelta
            appointment_groups[root_id] = AppointmentGroup.objects.create(
                order=order,
                root_category=category,
                category_slug_snapshot=category.slug,
                category_title_snapshot=category.title,
                scheduled_at=group_data["scheduled_at"],
                customer_message=group_messages.get(category.slug, ""),
                arrival_otp=f"{secrets.randbelow(1_000_000):06d}",
                arrival_otp_expires_at=group_data["scheduled_at"] + timedelta(hours=6),
            )

        subtotal = Decimal("0")
        tax_total = Decimal("0")
        grand_total = Decimal("0")
        dispatch_results = []

        for item, serializer in prepared:
            booking = serializer.save()
            root_category = item.service.category
            while root_category.parent_id:
                root_category = root_category.parent
            booking.appointment_group = appointment_groups[root_category.pk]
            booking.save(update_fields=["appointment_group", "updated_at"])
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
            # Package and add-ons apply per selected service unit. The
            # inspection/visit fee is charged once for the booking line.
            variant_base = Decimal(str(base_snapshot.get("variant_price", "0")))
            visit_fee = Decimal(str(base_snapshot.get("visit_fee", "0")))
            unit_subtotal = variant_base + adjusted_addons_total
            line_subtotal = (unit_subtotal * quantity) + visit_fee
            line_tax = line_subtotal * Decimal("0.18")
            line_total = line_subtotal + line_tax

            base_snapshot.update({
                "cart_item_id": item.id,
                "quantity": quantity,
                "unit_subtotal": str(unit_subtotal),
                "visit_fee": str(visit_fee),
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
                    "unit_label": item.service.unit_label,
                    "variant_id": item.variant_id,
                    "variant_title": item.variant.title if item.variant else None,
                    "cart_item_id": item.id,
                    "appointment_group_id": booking.appointment_group_id,
                    "appointment_group_slug": booking.appointment_group.category_slug_snapshot,
                    "appointment_group_title": booking.appointment_group.category_title_snapshot,
                    "form_answers": item.form_answers,
                    "category_answers": item.category_answers,
                    "notes": item.notes,
                },
                pricing_snapshot=base_snapshot,
                line_subtotal=line_subtotal,
                tax_amount=line_tax,
                line_total=line_total,
            )

            if item.service.category.slug == "monthly-car-wash-plans":
                from datetime import timedelta
                from apps.bookings.models import RecurringWashPlan

                answers = item.form_answers or {}
                category_answers = item.category_answers or {}
                duration_days = {
                    "15 days": 15, "1 month": 30,
                    "3 months": 90, "6 months": 180,
                }.get(answers.get("subscription_duration"))
                frequency = {
                    "Daily": RecurringWashPlan.Frequency.DAILY,
                    "Alternate day": RecurringWashPlan.Frequency.ALTERNATE_DAY,
                    "Twice a week": RecurringWashPlan.Frequency.TWICE_WEEKLY,
                    "Weekly": RecurringWashPlan.Frequency.WEEKLY,
                    "Fortnightly": RecurringWashPlan.Frequency.FORTNIGHTLY,
                }.get(answers.get("wash_frequency"))
                try:
                    vehicle_quantity = int(answers.get("vehicle_quantity", 0))
                    starts_on = timezone.localtime(booking.scheduled_at).date()
                except (TypeError, ValueError):
                    raise serializers.ValidationError({
                        "items": "The recurring wash plan needs a valid first-visit date and vehicle quantity."
                    })
                vehicle_type = category_answers.get("vehicle_type") or answers.get("vehicle_type")
                time_window = answers.get("preferred_time_window", "")
                if (
                    not duration_days or not frequency or vehicle_quantity < 1
                    or not vehicle_type
                    or time_window not in ("", "Morning", "Afternoon", "Evening")
                ):
                    raise serializers.ValidationError({
                        "items": "Complete the recurring wash plan details with a valid start date, vehicle and frequency."
                    })
                RecurringWashPlan.objects.create(
                    order=order,
                    source_booking=booking,
                    customer=request.user,
                    address=cart.address,
                    service=item.service,
                    variant=item.variant,
                    frequency=frequency,
                    duration_days=duration_days,
                    starts_on=starts_on,
                    ends_on=starts_on + timedelta(days=duration_days - 1),
                    preferred_time_window=time_window,
                    vehicle_type=str(vehicle_type),
                    vehicle_quantity=vehicle_quantity,
                    plan_snapshot={
                        "form_answers": answers,
                        "category_answers": {
                            key: value for key, value in category_answers.items()
                            if not key.startswith("_airway_")
                        },
                        "notes": item.notes,
                    },
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
            "scheduling_v1": {
                "mode": schedule_mode,
                "shared_appointment_at": (
                    shared_appointment_at.isoformat()
                    if shared_appointment_at is not None else None
                ),
            },
            "appointment_groups_v1": [
                {
                    "id": group.pk,
                    "category_root_id": group.root_category_id,
                    "category_slug": group.category_slug_snapshot,
                    "category_title": group.category_title_snapshot,
                    "scheduled_at": group.scheduled_at.isoformat(),
                    "customer_message": group.customer_message,
                }
                for group in appointment_groups.values()
            ],
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
        cart.group_messages = {}
        update_fields = ["group_messages", "updated_at"]
        if cart.schedule_mode != "separate":
            cart.schedule_mode = "separate"
            update_fields.append("schedule_mode")
        cart.save(update_fields=update_fields)
        return Response({
            "order_id": order.id,
            "status": order.status,
            "address_id": order.address_id,
            "currency": order.currency,
            "subtotal": str(order.subtotal),
            "tax_amount": str(order.tax_amount),
            "total_amount": str(order.total_amount),
            "appointment_groups": [
                {
                    "id": group.pk,
                    "category_root_id": group.root_category_id,
                    "category_slug": group.category_slug_snapshot,
                    "category_title": group.category_title_snapshot,
                    "scheduled_at": group.scheduled_at.isoformat(),
                    "customer_message": group.customer_message,
                    "arrival_otp": group.arrival_otp,
                    "arrival_otp_expires_at": (
                        group.arrival_otp_expires_at.isoformat()
                        if group.arrival_otp_expires_at else None
                    ),
                    "booking_ids": list(group.bookings.order_by("id").values_list("id", flat=True)),
                }
                for group in order.appointment_groups.select_related("root_category").all()
            ],
            "items": [
                {
                    "order_item_id": row.id,
                    "booking_id": row.booking_id,
                    "appointment_group_id": row.booking.appointment_group_id,
                    "service": row.service_snapshot,
                    "quantity": row.quantity,
                    "line_total": str(row.line_total),
                }
                for row in order.items.select_related("booking").all()
            ],
            "dispatch": {"offers_sent": 0, "deferred_until_advance_payment": True},
            "next_step": "Pay the 30% advance to start worker matching. The remaining 70% is due after all services are completed and verified.",

        }, status=status.HTTP_201_CREATED)


class CustomerOrderDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, order_id):
        from apps.payments.models import Payment

        from apps.payments.models import PaymentRefund
        from apps.ratings.models import BookingRating

        order = get_object_or_404(
            Order.objects.prefetch_related(
                "items__booking__assignment__worker__user",
                "items__booking__payment_refunds",
                "appointment_groups__bookings",
                "payments",
            ),
            pk=order_id,
            customer=request.user,
        )
        allocation = (order.metadata or {}).get("payment_allocation_v1", {})
        advance_rows = {row["order_item_id"]: row for row in allocation.get("advance", [])}
        balance_rows = {row["order_item_id"]: row for row in allocation.get("balance", [])}
        order_items = list(order.items.all())
        scheduling = (order.metadata or {}).get("scheduling_v1", {})
        shared_appointment = scheduling.get("mode") == "same_appointment"
        recurring_order = RecurringWashPlan.objects.filter(order=order).exists()
        active_order_items = [
            row for row in order_items
            if row.booking.status != Booking.Status.CANCELLED
        ]
        shared_reschedule_eligible = (
            bool(active_order_items)
            and not recurring_order
            and all(
                row.booking.status in (Booking.Status.PENDING, Booking.Status.CONFIRMED)
                and not hasattr(row.booking, "assignment")
                for row in active_order_items
            )
        )
        rated_booking_ids = set(BookingRating.objects.filter(
            booking_id__in=[row.booking_id for row in order_items],
            rater=request.user,
        ).values_list("booking_id", flat=True))
        items = []
        for row in order_items:
            booking = row.booking
            assignment = getattr(booking, "assignment", None)
            completion_code = None
            completion_expires_at = None
            completion_otp_requested = False
            from apps.ratings.models import BookingCompletionFeedback
            completion_feedback = BookingCompletionFeedback.objects.filter(
                booking=booking,
                customer=request.user,
            ).first()
            if booking.status == Booking.Status.IN_PROGRESS:
                from apps.bookings.models import BookingCompletionOTP
                from apps.notifications.models import Notification
                otp_record = BookingCompletionOTP.objects.filter(
                    booking=booking,
                    verified_at__isnull=True,
                    expires_at__gt=timezone.now(),
                ).first()
                completion_otp_requested = otp_record is not None
                if otp_record and (
                    completion_feedback is not None or not booking.appointment_group_id
                ):
                    otp_notice = Notification.objects.filter(
                        user=request.user,
                        data__booking_id=booking.id,
                        data__purpose="service_completion_otp",
                    ).order_by("-created_at").first()
                    if otp_notice:
                        completion_code = (otp_notice.data or {}).get("completion_code")
                        if not completion_code:
                            import re
                            match = re.search(r"\bis (\d{6})\.", otp_notice.body)
                            completion_code = match.group(1) if match else None
                        completion_expires_at = otp_record.expires_at.isoformat()
            service_snapshot = dict(row.service_snapshot or {})
            service_snapshot.setdefault("unit_label", booking.service.unit_label)
            service_snapshot.setdefault("category_answers", booking.customer_answers or {})
            latest_quote = booking.quotes.order_by("-version").first()
            quote_data = None
            if latest_quote:
                quote_data = {
                    "id": latest_quote.id,
                    "version": latest_quote.version,
                    "status": (
                        "expired"
                        if latest_quote.status == BookingQuote.Status.PENDING_CUSTOMER
                        and latest_quote.expires_at and latest_quote.expires_at <= timezone.now()
                        else latest_quote.status
                    ),
                    "line_items": latest_quote.line_items,
                    "labour_amount": str(latest_quote.labour_amount),
                    "material_amount": str(latest_quote.material_amount),
                    "other_amount": str(latest_quote.other_amount),
                    "tax_amount": str(latest_quote.tax_amount),
                    "total_amount": str(latest_quote.total_amount),
                    "notes": latest_quote.notes,
                    "customer_response_note": latest_quote.customer_response_note,
                    "expires_at": latest_quote.expires_at.isoformat() if latest_quote.expires_at else None,
                    "responded_at": latest_quote.responded_at.isoformat() if latest_quote.responded_at else None,
                }
            items.append({
                "order_item_id": row.id,
                "booking_id": booking.id,
                "appointment_group_id": booking.appointment_group_id,
                "appointment_group_title": (
                    booking.appointment_group.category_title_snapshot
                    if booking.appointment_group_id else None
                ),
                "service": service_snapshot,
                "booking_status": booking.status,
                "booking_mode": booking.booking_mode,
                "can_cancel": booking.can_cancel,
                "can_reschedule": (
                    shared_reschedule_eligible
                    and booking.status in (Booking.Status.PENDING, Booking.Status.CONFIRMED)
                    and not assignment
                    if shared_appointment
                    else (
                        not recurring_order
                        and booking.status in (Booking.Status.PENDING, Booking.Status.CONFIRMED)
                        and not assignment
                    )
                ),
                "scheduled_at": booking.scheduled_at,
                "drop_scheduled_at": booking.drop_scheduled_at,
                "quote": quote_data,
                "work_evidence": [
                    {
                        "id": evidence.id,
                        "stage": evidence.stage,
                        "note": evidence.note,
                        "photo_url": request.build_absolute_uri(
                            f"/api/v1/bookings/work-evidence/{evidence.id}/photo/"
                        ),
                        "created_at": evidence.created_at.isoformat(),
                    }
                    for evidence in booking.work_evidence.select_related("worker").all()
                ],
                "form_responses": [
                    {
                        "key": response.form_field.key,
                        "label": response.form_field.label,
                        "field_type": response.form_field.field_type,
                        "value": (
                            "Photo attached"
                            if response.form_field.field_type == FormField.FieldType.PHOTO
                            and (booking.customer_answers or {}).get("_airway_form_photos", {}).get(response.form_field.key)
                            else response.value
                        ),
                        "photo_url": (
                            request.build_absolute_uri(
                                f"/api/v1/bookings/issue-photos/{booking.id}/?field_key={response.form_field.key}"
                            )
                            if response.form_field.field_type == FormField.FieldType.PHOTO
                            and (booking.customer_answers or {}).get("_airway_form_photos", {}).get(response.form_field.key)
                            else None
                        ),
                    }
                    for response in booking.form_responses.select_related("form_field").all()
                ],
                "worker": (
                    {
                        "id": assignment.worker_id,
                        "name": assignment.worker.user.name or "AIRway Professional",
                    }
                    if assignment else None
                ),
                "quantity": row.quantity,
                "line_total": str(row.line_total),
                "advance_amount": advance_rows.get(row.id, {}).get("amount"),
                "balance_amount": balance_rows.get(row.id, {}).get("amount"),
                "completion_verified": booking.status == Booking.Status.COMPLETED,
                "completion_otp_requested": completion_otp_requested,
                "completion_feedback_submitted": completion_feedback is not None,
                "completion_feedback_skipped": (
                    completion_feedback.skipped if completion_feedback else False
                ),
                "customer_has_rated": (
                    booking.id in rated_booking_ids
                    or bool(completion_feedback and completion_feedback.skipped)
                ),
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
        recurring_plan = RecurringWashPlan.objects.filter(order=order).first()

        return Response({
            "id": order.id,
            "address_id": order.address_id,
            "status": order.status,
            "scheduling": (order.metadata or {}).get(
                "scheduling_v1",
                {"mode": "separate", "shared_appointment_at": None},
            ),
            "appointment_groups": [
                {
                    "id": group.pk,
                    "category_root_id": group.root_category_id,
                    "category_slug": group.category_slug_snapshot,
                    "category_title": group.category_title_snapshot,
                    "scheduled_at": group.scheduled_at.isoformat(),
                    "customer_message": group.customer_message,
                    "arrival_otp": (
                        group.arrival_otp
                        if not group.arrival_otp_verified_at
                        and group.arrival_otp_expires_at
                        and group.arrival_otp_expires_at > timezone.now()
                        else None
                    ),
                    "arrival_otp_expires_at": (
                        group.arrival_otp_expires_at.isoformat()
                        if group.arrival_otp_expires_at else None
                    ),
                    "arrival_otp_verified_at": (
                        group.arrival_otp_verified_at.isoformat()
                        if group.arrival_otp_verified_at else None
                    ),
                    "booking_ids": list(group.bookings.order_by("id").values_list("id", flat=True)),
                }
                for group in order.appointment_groups.select_related("root_category").all()
            ],
            "currency": order.currency,
            "subtotal": str(order.subtotal),
            "tax_amount": str(order.tax_amount),
            "total_amount": str(order.total_amount),
            "is_staged_payment": is_staged_payment,
            "advance_percentage": float(allocation.get("percentage", 30)),
            "advance_total": allocation.get("advance_total"),
            "balance_total": allocation.get("balance_total"),
            "advance_paid": bool(advance_payment),
            "balance_paid": bool(balance_payment),
            "legacy_paid": bool(legacy_payment),
            "advance_due": str(advance_due),
            "balance_due": str(balance_due),
            "legacy_payment_due": str(order.total_amount) if legacy_ready else "0.00",
            "amount_due": str(advance_due + balance_due) if is_staged_payment else (str(order.total_amount) if legacy_ready else "0.00"),
            "ready_for_advance": is_staged_payment and not advance_payment and order.status in (
                Order.Status.AWAITING_ASSIGNMENT,
                Order.Status.PARTIALLY_ASSIGNED,
                Order.Status.AWAITING_PAYMENT,
                Order.Status.PARTIALLY_CANCELLED,
            ),
            "ready_for_balance": ready_for_balance,
            "ready_for_legacy_payment": legacy_ready,
            "ready_for_payment": ready_for_balance or legacy_ready,
            "all_services_verified": all_services_verified,
            "recurring_wash_plan": (
                {
                    "id": recurring_plan.id,
                    "service_title": recurring_plan.service.title,
                    "status": recurring_plan.status,
                    "frequency": recurring_plan.frequency,
                    "duration_days": recurring_plan.duration_days,
                    "starts_on": recurring_plan.starts_on.isoformat(),
                    "ends_on": recurring_plan.ends_on.isoformat(),
                    "preferred_time_window": recurring_plan.preferred_time_window,
                    "vehicle_type": recurring_plan.vehicle_type,
                    "vehicle_quantity": recurring_plan.vehicle_quantity,
                    "quoted_total": str(recurring_plan.quoted_total),
                    "refunds": [
                        {
                            "id": refund.pk,
                            "amount": str(refund.amount),
                            "status": refund.status,
                            "failure_reason": refund.failure_reason,
                            "created_at": refund.created_at.isoformat(),
                        }
                        for refund in recurring_plan.source_booking.payment_refunds.filter(
                            reason="recurring_plan_cancellation"
                        ).order_by("-created_at")
                    ],
                    "can_cancel": recurring_plan.status in (
                        RecurringWashPlan.Status.PAID_PENDING_SETUP,
                        RecurringWashPlan.Status.ACTIVE,
                        RecurringWashPlan.Status.PAUSED,
                    ),
                    "visits": [
                        {
                            "id": visit.pk,
                            "visit_number": visit.visit_number,
                            "scheduled_at": visit.scheduled_at.isoformat(),
                            "status": visit.status,
                            "prepaid_amount": str(visit.prepaid_amount),
                            "booking_id": visit.booking_id,
                            "booking_status": visit.booking.status if visit.booking_id else None,
                            "can_reschedule": (
                                recurring_plan.status in (
                                    RecurringWashPlan.Status.PAID_PENDING_SETUP,
                                    RecurringWashPlan.Status.ACTIVE,
                                )
                                and visit.status in (
                                    RecurringWashVisit.Status.PENDING_SETUP,
                                    RecurringWashVisit.Status.BOOKED,
                                )
                                and (
                                    not visit.booking_id
                                    or visit.booking.status in (
                                        Booking.Status.PENDING,
                                        Booking.Status.CONFIRMED,
                                    )
                                )
                            ),
                        }
                        for visit in recurring_plan.visits.select_related("booking").order_by("visit_number")
                    ],
                }
                if recurring_plan else None
            ),
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
                "scheduling": (order.metadata or {}).get(
                    "scheduling_v1",
                    {"mode": "separate", "shared_appointment_at": None},
                ),
                "appointment_groups": [
                    {
                        "id": group.pk,
                        "category_root_id": group.root_category_id,
                        "category_slug": group.category_slug_snapshot,
                        "category_title": group.category_title_snapshot,
                        "scheduled_at": group.scheduled_at.isoformat(),
                        "customer_message": group.customer_message,
                        "booking_ids": list(group.bookings.order_by("id").values_list("id", flat=True)),
                    }
                    for group in order.appointment_groups.select_related("root_category").all()
                ],
                "items": [
                    {
                        "booking_id": item.booking_id,
                        "appointment_group_id": item.booking.appointment_group_id,
                        "service_title": item.booking.service.title,
                        "variant_title": item.booking.variant.title if item.booking.variant_id else "",
                        "scheduled_at": item.booking.scheduled_at,
                        "status": item.booking.status,
                        "line_total": str(item.line_total),
                    }
                    for item in order.items.select_related("booking__service", "booking__variant").all()
                ],
                "is_staged_payment": staged,
                "advance_paid": advance_paid,
                "balance_paid": balance_paid,
                "ready_for_advance": ready_for_advance,
                "ready_for_balance": ready_for_balance,
                "ready_for_payment": ready_for_balance or ready_for_legacy,
            })
        return Response(results)


class CustomerCartIssuePhotoView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request, item_id):
        storage = FileSystemStorage(location=settings.PRIVATE_UPLOAD_ROOT)
        item = get_object_or_404(
            CartItem.objects.select_related("cart"),
            pk=item_id,
            cart__customer=request.user,
        )
        stored_path = (item.category_answers or {}).get("_airway_issue_photo")
        if not stored_path or not storage.exists(stored_path):
            return Response({"detail": "Photo not found."}, status=status.HTTP_404_NOT_FOUND)
        content_type = mimetypes.guess_type(stored_path)[0] or "application/octet-stream"
        response = FileResponse(storage.open(stored_path, "rb"), content_type=content_type)
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response

    def post(self, request, item_id):
        storage = FileSystemStorage(location=settings.PRIVATE_UPLOAD_ROOT)
        item = get_object_or_404(
            CartItem.objects.select_related("cart"),
            pk=item_id,
            cart__customer=request.user,
        )
        photo = request.FILES.get("photo")
        if photo is None:
            return Response({"detail": "Choose a photo to upload."}, status=status.HTTP_400_BAD_REQUEST)
        if photo.size > 5 * 1024 * 1024:
            return Response({"detail": "Photo must be 5 MB or smaller."}, status=status.HTTP_400_BAD_REQUEST)
        if photo.content_type not in ("image/jpeg", "image/png", "image/webp"):
            return Response({"detail": "Upload a JPG, PNG or WEBP image."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            from PIL import Image
            image = Image.open(photo)
            image_width, image_height = image.size
            image_format = image.format
            image.verify()
            if image_format not in ("JPEG", "PNG", "WEBP"):
                raise ValueError("Unsupported image format")
        except Exception:
            return Response({"detail": "The uploaded file is not a valid supported image."}, status=status.HTTP_400_BAD_REQUEST)
        finally:
            photo.seek(0)

        extension = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}[image_format]
        if image_width > 6000 or image_height > 6000:
            return Response({"detail": "Image dimensions must not exceed 6000 × 6000 pixels."}, status=status.HTTP_400_BAD_REQUEST)
        stored_path = storage.save(
            f"booking_issue_photos/customer_{request.user.pk}/{uuid.uuid4().hex}{extension}",
            photo,
        )
        answers = dict(item.category_answers or {})
        previous_path = answers.get("_airway_issue_photo")
        answers["_airway_issue_photo"] = stored_path
        item.category_answers = answers
        item.save(update_fields=["category_answers", "updated_at"])
        if previous_path and previous_path != stored_path:
            storage.delete(previous_path)
        return Response({"has_issue_photo": True}, status=status.HTTP_200_OK)

    def delete(self, request, item_id):
        storage = FileSystemStorage(location=settings.PRIVATE_UPLOAD_ROOT)
        item = get_object_or_404(
            CartItem.objects.select_related("cart"),
            pk=item_id,
            cart__customer=request.user,
        )
        answers = dict(item.category_answers or {})
        stored_path = answers.pop("_airway_issue_photo", None)
        item.category_answers = answers
        item.save(update_fields=["category_answers", "updated_at"])
        if stored_path:
            storage.delete(stored_path)
        return Response({"has_issue_photo": False}, status=status.HTTP_200_OK)


class CustomerCartFormPhotoView(APIView):
    """Secure upload/delete for Admin-configured service photo questions."""

    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def _get_item_and_field(self, request, item_id, field_key):
        item = get_object_or_404(
            CartItem.objects.select_related("cart", "service"),
            pk=item_id,
            cart__customer=request.user,
        )
        field = get_object_or_404(
            FormField,
            service=item.service,
            key=field_key,
            field_type=FormField.FieldType.PHOTO,
            is_active=True,
        )
        return item, field

    def get(self, request, item_id, field_key):
        item, field = self._get_item_and_field(request, item_id, field_key)
        storage = FileSystemStorage(location=settings.PRIVATE_UPLOAD_ROOT)
        photo_map = (item.category_answers or {}).get("_airway_form_photos", {})
        stored_path = photo_map.get(field.key) if isinstance(photo_map, dict) else None
        if not stored_path or not storage.exists(stored_path):
            return Response({"detail": "Photo not found."}, status=status.HTTP_404_NOT_FOUND)
        content_type = mimetypes.guess_type(stored_path)[0] or "application/octet-stream"
        response = FileResponse(storage.open(stored_path, "rb"), content_type=content_type)
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response

    def post(self, request, item_id, field_key):
        item, field = self._get_item_and_field(request, item_id, field_key)
        storage = FileSystemStorage(location=settings.PRIVATE_UPLOAD_ROOT)
        photo = request.FILES.get("photo")
        if photo is None:
            return Response({"detail": "Choose a photo to upload."}, status=status.HTTP_400_BAD_REQUEST)
        if photo.size > 5 * 1024 * 1024:
            return Response({"detail": "Photo must be 5 MB or smaller."}, status=status.HTTP_400_BAD_REQUEST)
        if photo.content_type not in ("image/jpeg", "image/png", "image/webp"):
            return Response({"detail": "Upload a JPG, PNG or WEBP image."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            from PIL import Image
            image = Image.open(photo)
            image_width, image_height = image.size
            image_format = image.format
            image.verify()
            if image_format not in ("JPEG", "PNG", "WEBP"):
                raise ValueError("Unsupported image format")
        except Exception:
            return Response({"detail": "The uploaded file is not a valid supported image."}, status=status.HTTP_400_BAD_REQUEST)
        finally:
            photo.seek(0)
        if image_width > 6000 or image_height > 6000:
            return Response({"detail": "Image dimensions must not exceed 6000 × 6000 pixels."}, status=status.HTTP_400_BAD_REQUEST)

        extension = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}[image_format]
        stored_path = storage.save(
            f"booking_form_photos/customer_{request.user.pk}/cart_item_{item.pk}/{field.key}/{uuid.uuid4().hex}{extension}",
            photo,
        )
        answers = dict(item.category_answers or {})
        photo_map = dict(answers.get("_airway_form_photos") or {})
        previous_path = photo_map.get(field.key)
        photo_map[field.key] = stored_path
        answers["_airway_form_photos"] = photo_map
        form_answers = dict(item.form_answers or {})
        form_answers[field.key] = "uploaded"
        item.category_answers = answers
        item.form_answers = form_answers
        item.save(update_fields=["category_answers", "form_answers", "updated_at"])
        if previous_path and previous_path != stored_path:
            storage.delete(previous_path)
        return Response({"field_key": field.key, "uploaded": True}, status=status.HTTP_200_OK)

    def delete(self, request, item_id, field_key):
        item, field = self._get_item_and_field(request, item_id, field_key)
        storage = FileSystemStorage(location=settings.PRIVATE_UPLOAD_ROOT)
        answers = dict(item.category_answers or {})
        photo_map = dict(answers.get("_airway_form_photos") or {})
        stored_path = photo_map.pop(field.key, None)
        if photo_map:
            answers["_airway_form_photos"] = photo_map
        else:
            answers.pop("_airway_form_photos", None)
        form_answers = dict(item.form_answers or {})
        form_answers.pop(field.key, None)
        item.category_answers = answers
        item.form_answers = form_answers
        item.save(update_fields=["category_answers", "form_answers", "updated_at"])
        if stored_path:
            storage.delete(stored_path)
        return Response({"field_key": field.key, "uploaded": False}, status=status.HTTP_200_OK)


class BookingIssuePhotoView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, booking_id):
        storage = FileSystemStorage(location=settings.PRIVATE_UPLOAD_ROOT)
        booking = get_object_or_404(
            Booking.objects.select_related("customer", "assignment__worker"),
            pk=booking_id,
        )
        allowed = booking.customer_id == request.user.pk or BookingAssignment.objects.filter(
            booking=booking, worker__user=request.user
        ).exists()
        if not allowed:
            return Response({"detail": "Photo not found."}, status=status.HTTP_404_NOT_FOUND)

        field_key = str(request.query_params.get("field_key", "")).strip()
        if field_key:
            photo_map = (booking.customer_answers or {}).get("_airway_form_photos", {})
            stored_path = photo_map.get(field_key) if isinstance(photo_map, dict) else None
            field_exists = FormField.objects.filter(
                service=booking.service,
                key=field_key,
                field_type=FormField.FieldType.PHOTO,
                is_active=True,
            ).exists()
            if not field_exists:
                return Response({"detail": "Photo not found."}, status=status.HTTP_404_NOT_FOUND)
        else:
            stored_path = (booking.customer_answers or {}).get("_airway_issue_photo")
        if not stored_path or not storage.exists(stored_path):
            return Response({"detail": "Photo not found."}, status=status.HTTP_404_NOT_FOUND)
        content_type = mimetypes.guess_type(stored_path)[0] or "application/octet-stream"
        response = FileResponse(storage.open(stored_path, "rb"), content_type=content_type)
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response


class BookingWorkEvidencePhotoView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, evidence_id):
        evidence = get_object_or_404(
            BookingWorkEvidence.objects.select_related(
                "booking__customer", "worker__user"
            ),
            pk=evidence_id,
        )
        if request.user.pk not in (evidence.booking.customer_id, evidence.worker.user_id):
            return Response({"detail": "Photo not found."}, status=status.HTTP_404_NOT_FOUND)
        storage = FileSystemStorage(location=settings.PRIVATE_UPLOAD_ROOT)
        if not storage.exists(evidence.image_path):
            return Response({"detail": "Photo not found."}, status=status.HTTP_404_NOT_FOUND)
        content_type = mimetypes.guess_type(evidence.image_path)[0] or "application/octet-stream"
        response = FileResponse(storage.open(evidence.image_path, "rb"), content_type=content_type)
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response


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
        serializer = CartItemSerializer(data=request.data, context={"request": request, "allow_incomplete": True})
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

        created_item = serializer.save(cart=cart)
        response_data = CustomerCartSerializer(cart, context={"request": request}).data
        response_data["added_item_id"] = created_item.pk
        return Response(response_data, status=status.HTTP_201_CREATED)

    def patch(self, request):
        cart = self.get_cart(request.user)
        update_fields = []
        if "address_id" in request.data:
            address_id = request.data.get("address_id")
            previous_address_id = cart.address_id
            if address_id in (None, ""):
                cart.address = None
            else:
                address = get_object_or_404(
                    Address.objects.select_related("zone__city"),
                    pk=address_id,
                    user=request.user,
                    deleted_at__isnull=True,
                )
                # Changing the service address invalidates every previously
                # selected slot; availability must be checked for the new area.
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
            if cart.address_id != previous_address_id:
                cart.items.update(schedule_data={})
            update_fields.append("address")

        if "schedule_mode" in request.data:
            schedule_mode = str(request.data.get("schedule_mode", "")).strip().lower()
            if schedule_mode not in ("separate", "same_appointment"):
                return Response(
                    {"schedule_mode": "Choose separate or same_appointment."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            cart.schedule_mode = schedule_mode
            update_fields.append("schedule_mode")

        if "group_messages" in request.data:
            raw_messages = request.data.get("group_messages")
            if not isinstance(raw_messages, dict):
                return Response(
                    {"group_messages": "Provide an object keyed by service category slug."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            allowed_slugs = set()
            for item in cart.items.select_related("service__category__parent"):
                root_category = item.service.category
                while root_category.parent_id:
                    root_category = root_category.parent
                allowed_slugs.add(root_category.slug)
            cleaned_messages = {}
            for slug, message in raw_messages.items():
                if slug not in allowed_slugs:
                    return Response(
                        {"group_messages": f"Unknown appointment group: {slug}."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if not isinstance(message, str) or len(message.strip()) > 500:
                    return Response(
                        {"group_messages": "Each message must be text up to 500 characters."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if message.strip():
                    cleaned_messages[slug] = message.strip()
            cart.group_messages = cleaned_messages
            update_fields.append("group_messages")

        if update_fields:
            cart.save(update_fields=[*update_fields, "updated_at"])
        return Response(CustomerCartSerializer(cart, context={"request": request}).data)


class CustomerCartItemView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_item(self, request, item_id):
        cart = get_object_or_404(CustomerCart, customer=request.user)
        return get_object_or_404(CartItem, cart=cart, pk=item_id)

    @transaction.atomic
    def patch(self, request, item_id):
        item = self.get_item(request, item_id)
        old_photo_map = (item.category_answers or {}).get("_airway_form_photos", {})
        old_photo_paths = set(old_photo_map.values()) if isinstance(old_photo_map, dict) else set()
        serializer = CartItemSerializer(
            item, data=request.data, partial=True, context={"request": request, "allow_incomplete": True}
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
        requested_schedule = serializer.validated_data.get("schedule_data") if "schedule_data" in request.data else None
        if requested_schedule is not None:
            if not item.cart.address_id:
                return Response(
                    {"detail": "Select a service address before choosing an appointment time."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            from django.utils.dateparse import parse_datetime
            if not isinstance(requested_schedule, dict):
                return Response(
                    {"schedule_data": "Provide a valid appointment schedule object."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            scheduled_at = parse_datetime(str(requested_schedule.get("scheduled_at", "")))
            if scheduled_at is None or timezone.is_naive(scheduled_at) or scheduled_at <= timezone.now():
                return Response(
                    {"schedule_data": "Choose a valid future date and time."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            root_category = item.service.category
            while root_category.parent_id:
                root_category = root_category.parent
            group_items = []
            for candidate in item.cart.items.select_related(
                "service__category__parent", "variant"
            ).order_by("id"):
                candidate_root = candidate.service.category
                while candidate_root.parent_id:
                    candidate_root = candidate_root.parent
                if candidate_root.pk == root_category.pk:
                    group_items.append(candidate)

            modes = {candidate.service.booking_mode for candidate in group_items}
            if len(modes) != 1:
                return Response(
                    {"schedule_data": "Services with different appointment modes cannot share one appointment group."},
                    status=status.HTTP_409_CONFLICT,
                )
            booking_mode = item.service.booking_mode
            drop_scheduled_at = None
            if booking_mode == Booking.BookingMode.PICKUP_DROP:
                drop_scheduled_at = parse_datetime(
                    str(requested_schedule.get("drop_scheduled_at", ""))
                )
                if (
                    drop_scheduled_at is None
                    or timezone.is_naive(drop_scheduled_at)
                    or drop_scheduled_at <= scheduled_at
                ):
                    return Response(
                        {"schedule_data": "Choose a drop-off time after pickup."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            elif requested_schedule.get("drop_scheduled_at"):
                return Response(
                    {"schedule_data": "Drop-off time is only valid for Pickup & Drop services."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            for candidate in group_items:
                try:
                    check_service_available(
                        service=candidate.service,
                        address=item.cart.address,
                        audience="all",
                    )
                    duration = (
                        candidate.variant.duration_minutes
                        if candidate.variant_id and candidate.variant.duration_minutes
                        else candidate.service.duration_minutes
                    ) or 60
                    quantity = max(int(candidate.quantity or 1), 1)
                    duration *= (
                        1 if candidate.service.pricing_type == "per_unit" else quantity
                    )
                    check_slot_availability(
                        service=candidate.service,
                        scheduled_at=scheduled_at,
                        duration_minutes=duration,
                        booking_mode=candidate.service.booking_mode,
                        drop_scheduled_at=drop_scheduled_at,
                    )
                except (SlotConflictError, ServiceUnavailableError) as exc:
                    return Response(
                        {"detail": str(exc), "cart_item_id": candidate.pk},
                        status=status.HTTP_409_CONFLICT,
                    )

            updated_schedule = {
                "scheduled_at": scheduled_at.isoformat(),
            }
            if drop_scheduled_at:
                updated_schedule["drop_scheduled_at"] = drop_scheduled_at.isoformat()
            for candidate in group_items:
                candidate.schedule_data = dict(updated_schedule)
                candidate.save(update_fields=["schedule_data", "updated_at"])

        updated_item = serializer.save()
        new_photo_map = (updated_item.category_answers or {}).get("_airway_form_photos", {})
        new_photo_paths = set(new_photo_map.values()) if isinstance(new_photo_map, dict) else set()
        storage = FileSystemStorage(location=settings.PRIVATE_UPLOAD_ROOT)
        for stored_path in old_photo_paths - new_photo_paths:
            storage.delete(stored_path)
        return Response(CustomerCartSerializer(item.cart, context={"request": request}).data)

    def delete(self, request, item_id):
        item = self.get_item(request, item_id)
        cart = item.cart
        root_category = item.service.category
        while root_category.parent_id:
            root_category = root_category.parent
        removed_group_slug = root_category.slug
        answers = dict(item.category_answers or {})
        stored_paths = []
        issue_photo = answers.get("_airway_issue_photo")
        if issue_photo:
            stored_paths.append(issue_photo)
        form_photos = answers.get("_airway_form_photos", {})
        if isinstance(form_photos, dict):
            stored_paths.extend(path for path in form_photos.values() if path)
        item.delete()
        remaining_group = False
        for candidate in cart.items.select_related("service__category__parent"):
            candidate_root = candidate.service.category
            while candidate_root.parent_id:
                candidate_root = candidate_root.parent
            if candidate_root.slug == removed_group_slug:
                remaining_group = True
                break
        if not remaining_group and removed_group_slug in (cart.group_messages or {}):
            cart.group_messages = dict(cart.group_messages or {})
            cart.group_messages.pop(removed_group_slug, None)
            cart.save(update_fields=["group_messages", "updated_at"])
        if cart.items.count() < 2 and cart.schedule_mode != "separate":
            cart.schedule_mode = "separate"
            cart.save(update_fields=["schedule_mode", "updated_at"])
        storage = FileSystemStorage(location=settings.PRIVATE_UPLOAD_ROOT)
        for stored_path in stored_paths:
            storage.delete(stored_path)
        return Response(CustomerCartSerializer(cart, context={"request": request}).data)
