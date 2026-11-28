"""
DispatcherService - Sends each booking to all currently eligible workers.
"""
import logging
from datetime import timedelta
from django.utils import timezone
from django.db import transaction

logger = logging.getLogger(__name__)

# Default time window for workers to accept an offer.
OFFER_EXPIRY_MINUTES = 5


class DispatcherService:
    """
    Dispatches worker offers for bookings based on eligibility criteria.

    Eligibility:
    - Worker profile is APPROVED
    - Worker is ONLINE
    - Worker offers the required service
    - Worker is in the same zone as booking address
    - Worker schedule covers the booking time
    - Worker has no blocking leave for the time
    - Worker doesn't have overlapping bookings

    Dispatch Flow:
    1. Find every worker who passes service, zone, approval, online, schedule,
       leave, gender, skill and booking-conflict checks.
    2. Create an offer for every matching worker in one dispatch pass.
    3. Notify all offered workers; the first valid acceptance wins atomically.
    """

    @staticmethod
    def has_verified_worker_payment(*, order=None, booking=None):
        """Authorize dispatch for current 30% advances or fully paid legacy bookings.

        New-format orders must have a captured advance and allocation snapshot.
        Legacy orders without that snapshot are eligible only with a captured
        LEGACY payment; failed, pending, and refunded-only rows never qualify.
        """
        from apps.payments.models import Payment

        if order is not None:
            if (order.metadata or {}).get("payment_allocation_v1"):
                return Payment.objects.filter(
                    order=order, stage=Payment.Stage.ADVANCE,
                    status=Payment.Status.PAID,
                ).exists()
            return Payment.objects.filter(
                order=order, stage=Payment.Stage.LEGACY,
                status=Payment.Status.PAID,
            ).exists()

        if booking is not None:
            return Payment.objects.filter(
                booking=booking,
                stage__in=(Payment.Stage.ADVANCE, Payment.Stage.LEGACY),
                status=Payment.Status.PAID,
            ).exists()
        return False

    @classmethod
    @transaction.atomic
    def dispatch_offers(cls, booking, batch_size=None, expiry_minutes=None, parent_order=None):
        """Dispatch one service line; parent orders may use different workers per line."""
        from apps.bookings.models import Booking, OrderItem, WorkerOffer, DispatchConfiguration
        # Resolve the parent before taking a booking lock. Order acceptance
        # consistently locks order first, then bookings.
        order_id = OrderItem.objects.filter(
            booking_id=booking.pk
        ).values_list("order_id", flat=True).first()
        if order_id and (parent_order is None or booking.appointment_group_id):
            # Grouped bookings must never fall back to independent line offers.
            # Route every trigger through the parent-order dispatcher.
            from apps.bookings.models import Order
            return cls.dispatch_order(Order.objects.get(pk=order_id))
        booking = Booking.objects.select_for_update(of=("self",)).select_related(
            "service__category", "variant", "address__zone__city"
        ).get(pk=booking.pk)
        config = DispatchConfiguration.get_solo()
        if not config.is_enabled or booking.status not in (booking.Status.PENDING, booking.Status.CONFIRMED):
            return []
        recurring_visit = getattr(booking, "recurring_wash_visit", None)
        prepaid_recurring = bool(
            recurring_visit
            and recurring_visit.status == recurring_visit.Status.BOOKED
            and recurring_visit.plan.status in (
                recurring_visit.plan.Status.PAID_PENDING_SETUP,
                recurring_visit.plan.Status.ACTIVE,
            )
        )
        # Parent-order and standalone bookings require their own verified
        # advance. A recurring visit is authorized by its already-paid plan;
        # do not create a synthetic Payment row for it.
        from apps.payments.models import Payment
        if parent_order is not None:
            if not cls.has_verified_worker_payment(order=parent_order):
                return []
        elif not prepaid_recurring and not cls.has_verified_worker_payment(booking=booking):
            return []
        expiry_minutes = max(int(expiry_minutes or config.offer_expiry_minutes), 1)
        existing = WorkerOffer.objects.filter(booking=booking, order__isnull=True)
        if existing.filter(status__in=[WorkerOffer.Status.PENDING, WorkerOffer.Status.ACCEPTED]).exists():
            return []
        from django.db.models import Max
        batch_number = (existing.aggregate(value=Max("batch_number"))["value"] or 0) + 1
        duration = (booking.variant.duration_minutes if booking.variant_id and booking.variant.duration_minutes else booking.service.duration_minutes) or 60
        quantity = max(int((booking.pricing_snapshot or {}).get("quantity", 1) or 1), 1)
        duration_multiplier = 1 if booking.service.pricing_type == "per_unit" else quantity
        from apps.workers.eligibility import required_worker_gender_for_booking
        try:
            gender = required_worker_gender_for_booking(booking.service, booking.customer_answers)
        except ValueError:
            logger.exception("Invalid worker preference for booking %s", booking.pk)
            return []
        candidates = cls._get_eligible_workers(
            service=booking.service,
            zone=booking.address.zone if booking.address_id else None,
            scheduled_at=booking.scheduled_at,
            duration_minutes=duration * duration_multiplier,
            drop_scheduled_at=booking.drop_scheduled_at if booking.booking_mode == booking.BookingMode.PICKUP_DROP else None,
            exclude_booking_id=booking.pk,
            exclude_customer_id=booking.customer_id,
            required_gender=gender,
            priority_order=config.priority_order,
            required_tasks=(booking.variant.included_tasks if booking.variant_id else []),
        )
        already_offered = set(existing.filter(
            status__in=(WorkerOffer.Status.DECLINED, WorkerOffer.Status.EXPIRED)
        ).values_list("worker_id", flat=True))
        candidates = [worker for worker in candidates if worker.pk not in already_offered]
        # Launch policy: offer every currently eligible professional at once.
        # Eligibility already enforces the exact requested service, zone, schedule,
        # worker approval/online state, leave and booking-conflict constraints.
        # Skill breadth is not a reason to hide an otherwise qualified worker.
        # Keep explicit batch_size support for controlled internal dispatches.
        if batch_size is not None:
            candidates = candidates[:max(int(batch_size), 0)]
        if not candidates:
            cls._notify_dispatch_exhausted(booking)
            return []
        return cls._create_offers(
            booking=booking, order=None, workers=candidates,
            batch_number=batch_number, expiry_minutes=expiry_minutes,
            service_titles=[booking.service.title],
            payment_order=parent_order,
            recurring_visit=recurring_visit if prepaid_recurring else None,
        )

    @classmethod
    @transaction.atomic
    def dispatch_appointment_group(cls, group, parent_order):
        """Offer one appointment to workers qualified and available for every service in it."""
        from django.db.models import Max
        from apps.bookings.models import (
            AppointmentGroup, Booking, BookingAssignment, WorkerOffer,
            DispatchConfiguration,
        )
        from apps.workers.models import WorkerProfile
        from apps.workers.eligibility import required_worker_gender_for_booking
        from apps.availability.models import WorkerBlockedSlot
        from apps.bookings.services import _booking_intervals, _intervals_overlap
        from apps.payments.models import Payment

        group = AppointmentGroup.objects.select_for_update().get(pk=group.pk)
        if not DispatcherService.has_verified_worker_payment(order=parent_order):
            return []

        bookings = list(
            group.bookings.exclude(status=Booking.Status.CANCELLED)
            .select_related("service__category", "variant", "address__zone__city")
            .order_by("pk")
        )
        if not bookings or any(
            booking.status not in (Booking.Status.PENDING, Booking.Status.CONFIRMED)
            or BookingAssignment.objects.filter(booking=booking).exists()
            or booking.scheduled_at != group.scheduled_at
            for booking in bookings
        ):
            return []

        active_offers = WorkerOffer.objects.filter(
            appointment_group=group,
            status__in=(WorkerOffer.Status.PENDING, WorkerOffer.Status.ACCEPTED),
        )
        if active_offers.exists():
            return []

        now = timezone.now()
        # Retire any pre-migration line offers so a worker can receive one
        # coherent group offer rather than competing offers for individual lines.
        WorkerOffer.objects.filter(
            booking__in=bookings,
            order__isnull=True,
            appointment_group__isnull=True,
            status__in=(WorkerOffer.Status.PENDING, WorkerOffer.Status.ACCEPTED),
        ).update(status=WorkerOffer.Status.WITHDRAWN, responded_at=now)

        config = DispatchConfiguration.get_solo()
        if not config.is_enabled:
            return []

        common_worker_ids = None
        group_duration = 0
        for booking in bookings:
            zone = booking.address.zone if booking.address_id else None
            duration = (
                booking.variant.duration_minutes
                if booking.variant_id and booking.variant.duration_minutes
                else booking.service.duration_minutes
            ) or 60
            quantity = max(int((booking.pricing_snapshot or {}).get("quantity", 1) or 1), 1)
            duration *= 1 if booking.service.pricing_type == "per_unit" else quantity
            group_duration += duration + max(int(booking.service.buffer_minutes or 0), 0)
            try:
                gender = required_worker_gender_for_booking(
                    booking.service, booking.customer_answers
                )
            except ValueError:
                logger.exception("Invalid worker preference for booking %s", booking.pk)
                return []
            candidates = cls._get_eligible_workers(
                service=booking.service,
                zone=zone,
                scheduled_at=group.scheduled_at,
                duration_minutes=duration,
                drop_scheduled_at=(
                    booking.drop_scheduled_at
                    if booking.booking_mode == Booking.BookingMode.PICKUP_DROP else None
                ),
                exclude_booking_id=booking.pk,
                exclude_customer_id=booking.customer_id,
                required_gender=gender,
                priority_order=config.priority_order,
                required_tasks=(booking.variant.included_tasks if booking.variant_id else []),
            )
            candidate_ids = set(candidates.values_list("pk", flat=True))
            common_worker_ids = (
                candidate_ids if common_worker_ids is None
                else common_worker_ids.intersection(candidate_ids)
            )
            if not common_worker_ids:
                break

        if not common_worker_ids:
            cls._notify_dispatch_exhausted(bookings[0], order=parent_order)
            return []

        # The combined appointment must fit inside one worker shift and must
        # not overlap blocked time or another assigned job.
        start_at = group.scheduled_at
        end_at = start_at + timedelta(minutes=max(group_duration, 1))
        local_start = timezone.localtime(start_at)
        local_end = timezone.localtime(end_at)
        if local_start.date() != local_end.date():
            cls._notify_dispatch_exhausted(bookings[0], order=parent_order)
            return []

        eligible_ids = []
        active_statuses = (
            Booking.Status.ASSIGNED, Booking.Status.CONFIRMED,
            Booking.Status.IN_PROGRESS,
        )
        for worker in WorkerProfile.objects.filter(pk__in=common_worker_ids).prefetch_related("schedules", "leaves"):
            if not worker.schedules.filter(
                weekday=local_start.weekday(),
                is_active=True,
                start_time__lte=local_start.time(),
                end_time__gte=local_end.time(),
            ).exists():
                continue
            if WorkerBlockedSlot.objects.filter(
                worker=worker.user, start_at__lt=end_at, end_at__gt=start_at
            ).exists() or worker.leaves.filter(
                status="approved", start_at__lt=end_at, end_at__gt=start_at
            ).exists():
                continue

            conflict = False
            assignments = BookingAssignment.objects.filter(
                worker=worker, booking__status__in=active_statuses,
            ).exclude(booking__appointment_group=group).select_related(
                "booking__service", "booking__variant",
            )
            for assignment in assignments:
                existing = assignment.booking
                occupied = cls._assigned_booking_intervals(existing)
                if any(
                    _intervals_overlap((start_at, end_at), current)
                    for current in occupied
                ):
                    conflict = True
                    break
            if not conflict:
                eligible_ids.append(worker.pk)

        candidates = list(
            WorkerProfile.objects.filter(pk__in=eligible_ids)
            .order_by(*cls._priority_ordering(config.priority_order))
            .select_related("user")
        )
        already_responded = set(
            WorkerOffer.objects.filter(
                appointment_group=group,
                status__in=(WorkerOffer.Status.DECLINED, WorkerOffer.Status.EXPIRED),
            ).values_list("worker_id", flat=True)
        )
        candidates = [
            worker for worker in candidates
            if worker.pk not in already_responded
        ]
        # Launch policy: every worker who passed every service's exact
        # qualification and shared-appointment availability checks receives
        # the offer. Do not suppress qualified workers by skill-breadth tier.
        if not candidates:
            cls._notify_dispatch_exhausted(bookings[0], order=parent_order)
            return []

        existing = WorkerOffer.objects.filter(appointment_group=group)
        batch_number = (existing.aggregate(value=Max("batch_number"))["value"] or 0) + 1
        return cls._create_offers(
            booking=bookings[0],
            order=None,
            appointment_group=group,
            workers=candidates,
            batch_number=batch_number,
            expiry_minutes=config.offer_expiry_minutes,
            service_titles=[booking.service.title for booking in bookings],
            payment_order=parent_order,
        )

    @classmethod
    def dispatch_order(cls, order):
        """Dispatch each unassigned service line independently within one paid order."""
        from apps.bookings.models import Booking, BookingAssignment, WorkerOffer, DispatchConfiguration, Order
        from apps.payments.models import Payment

        with transaction.atomic():
            order = Order.objects.select_for_update().get(pk=order.pk)
            config = DispatchConfiguration.get_solo()
            if not config.is_enabled or order.status not in (
                Order.Status.AWAITING_ASSIGNMENT, Order.Status.PARTIALLY_CANCELLED
            ):
                return []
            if not cls.has_verified_worker_payment(order=order):
                return []
            # Let any legacy whole-order offer finish before creating line offers.
            if WorkerOffer.objects.filter(
                order=order,
                status__in=(WorkerOffer.Status.PENDING, WorkerOffer.Status.ACCEPTED),
            ).exists():
                return []

            bookings = list(
                Booking.objects.filter(order_item__order=order)
                .exclude(status=Booking.Status.CANCELLED)
                .select_related("service__category", "variant", "address__zone__city")
                .order_by("created_at")
            )
            created = []
            grouped_booking_ids = set()
            for group in order.appointment_groups.order_by("group_number"):
                group_bookings = list(
                    group.bookings.exclude(status=Booking.Status.CANCELLED)
                    .order_by("pk").values_list("pk", flat=True)
                )
                grouped_booking_ids.update(group_bookings)
                if group_bookings and not BookingAssignment.objects.filter(
                    booking_id__in=group_bookings
                ).exists():
                    created.extend(cls.dispatch_appointment_group(group, parent_order=order))

            for booking in bookings:
                if booking.pk in grouped_booking_ids:
                    continue
                if booking.status not in (Booking.Status.PENDING, Booking.Status.CONFIRMED):
                    continue
                if BookingAssignment.objects.filter(booking=booking).exists():
                    continue
                if WorkerOffer.objects.filter(
                    booking=booking, order__isnull=True,
                    status__in=(WorkerOffer.Status.PENDING, WorkerOffer.Status.ACCEPTED),
                ).exists():
                    continue
                created.extend(cls.dispatch_offers(booking, parent_order=order))
            return created

    @staticmethod
    def _notify_dispatch_exhausted(booking, order=None):
        """Alert operations once; customer booking screens own dispatch progress."""
        from apps.notifications.models import Notification
        from django.contrib.auth import get_user_model

        identity = {"booking_id": booking.pk, "order_id": order.pk if order else None}
        User = get_user_model()
        for staff_user in User.objects.filter(is_staff=True, is_active=True).only("id"):
            Notification.objects.get_or_create(
                user=staff_user,
                type=Notification.Type.SYSTEM_ANNOUNCEMENT,
                title="Worker dispatch needs attention",
                data__booking_id=booking.pk,
                defaults={
                    "body": f"No eligible worker accepted booking #{booking.pk}. Please review coverage and dispatch.",
                    "channel": Notification.Channel.IN_APP,
                    "data": {**identity, "dispatch_exhausted": True},
                },
            )

    @classmethod
    def order_schedule_is_compatible(cls, bookings):
        """A single worker must not be scheduled for overlapping order lines."""
        from apps.bookings.services import _booking_intervals, _intervals_overlap

        occupied = []
        for booking in bookings:
            duration = (
                booking.variant.duration_minutes
                if booking.variant_id and booking.variant.duration_minutes
                else booking.service.duration_minutes
            ) or 60
            quantity = max(int((booking.pricing_snapshot or {}).get("quantity", 1) or 1), 1)
            duration_multiplier = 1 if booking.service.pricing_type == "per_unit" else quantity
            intervals = _booking_intervals(
                booking.scheduled_at,
                duration * duration_multiplier,
                booking.service.buffer_minutes,
                booking.drop_scheduled_at
                if booking.booking_mode == booking.BookingMode.PICKUP_DROP else None,
            )
            if any(
                _intervals_overlap(candidate, previous)
                for candidate in intervals for previous in occupied
            ):
                return False
            occupied.extend(intervals)
        return True

    @classmethod
    def _create_offers(cls, *, booking, order, workers, batch_number, expiry_minutes, service_titles, payment_order=None, recurring_visit=None, appointment_group=None):
        from datetime import timedelta
        from decimal import Decimal
        from apps.bookings.models import WorkerOffer
        from apps.notifications.models import Notification
        # A pending request remains available until the scheduled service start.
        # Grouped appointments use their shared scheduled time; individual service
        # bookings use the booking's own scheduled_at value.
        expiry = appointment_group.scheduled_at if appointment_group else booking.scheduled_at
        if expiry <= timezone.now():
            logger.info("Skip dispatch for booking %s: scheduled service time has passed.", booking.pk)
            return []
        created = []
        summary = ", ".join(service_titles)
        for worker in workers:
            offer = None
            if appointment_group:
                offer = WorkerOffer.objects.filter(
                    appointment_group=appointment_group, worker=worker
                ).first()
            if offer is None:
                offer = WorkerOffer.objects.filter(
                    booking=booking, worker=worker
                ).first()
            if offer is not None and offer.status == WorkerOffer.Status.WITHDRAWN:
                # Reuse the unique booking/worker offer row when a previous
                # assignment was withdrawn before work started (for example,
                # because the accepted worker was suspended).
                offer.order = order
                offer.appointment_group = appointment_group
                offer.batch_number = batch_number
                offer.status = WorkerOffer.Status.PENDING
                offer.offered_at = timezone.now()
                offer.expires_at = expiry
                offer.responded_at = None
                offer.accepted_at = None
                offer.save(update_fields=[
                    "order", "appointment_group", "batch_number", "status", "offered_at",
                    "expires_at", "responded_at", "accepted_at", "updated_at",
                ])
            elif offer is None:
                offer = WorkerOffer.objects.create(
                    booking=booking, order=order, appointment_group=appointment_group,
                    worker=worker, batch_number=batch_number, expires_at=expiry,
                )
            else:
                continue
            created.append(offer)
            notification_title = "New Appointment" if appointment_group else ("New Service Order" if order else "Job Offer")
            notification_body = (
                f"New appointment ({len(service_titles)} services): {summary}"
                if appointment_group else (f"New order ({len(service_titles)} services): {summary}" if order else
                f"New job request for {summary} at {booking.scheduled_at.strftime('%d %b, %H:%M')}"))
            if recurring_visit:
                address_text = booking.address.full_address
            elif appointment_group or order or payment_order:
                payment_context = order or payment_order
                address_text = payment_context.address.full_address
            else:
                address_text = booking.address.full_address
            duration_minutes = (
                booking.variant.duration_minutes
                if booking.variant_id and booking.variant.duration_minutes
                else booking.service.duration_minutes
            ) or 60
            duration_minutes *= (
                1 if booking.service.pricing_type == "per_unit"
                else max(int((booking.pricing_snapshot or {}).get("quantity", 1) or 1), 1)
            )
            if appointment_group:
                duration_minutes = sum(
                    (
                        (item.variant.duration_minutes if item.variant_id and item.variant.duration_minutes else item.service.duration_minutes or 60)
                        * (1 if item.service.pricing_type == "per_unit" else max(int((item.pricing_snapshot or {}).get("quantity", 1) or 1), 1))
                    )
                    + max(int(item.service.buffer_minutes or 0), 0)
                    for item in appointment_group.bookings.exclude(status="cancelled").select_related("service", "variant").all()
                )
            service_quantity = (
                booking.order_item.quantity
                if hasattr(booking, "order_item")
                else max(int((booking.pricing_snapshot or {}).get("quantity", 1) or 1), 1)
            )
            service_unit_label = booking.service.unit_label or ""
            quantity_preview = (
                f"{service_quantity} {service_unit_label}"
                if service_unit_label
                else (f"Qty {service_quantity}" if service_quantity > 1 else "")
            )
            worker_payout = None
            if appointment_group:
                from decimal import Decimal
                payout_bookings = list(appointment_group.bookings.exclude(status="cancelled").all())
            elif order:
                from decimal import Decimal
                payout_bookings = [
                    item.booking
                    for item in order.items.exclude(booking__status="cancelled").select_related("booking")
                ]
            else:
                payout_bookings = [booking]
            payout_values = [
                (row.worker_payout_snapshot or {}).get("total")
                if (row.worker_payout_snapshot or {}).get("pricing_model") == "fixed_service_payout_v1"
                else None
                for row in payout_bookings
            ]
            if payout_values and all(value not in (None, "") for value in payout_values):
                worker_payout = str(sum((Decimal(str(value)) for value in payout_values), Decimal("0.00")))
            fixed_pricing_missing = (
                any(
                    (row.worker_payout_snapshot or {}).get("pricing_model") == "fixed_service_payout_v1"
                    for row in payout_bookings
                )
                and worker_payout is None
            )
            if worker_payout is None and not fixed_pricing_missing and worker.commission_rate is not None:
                from decimal import Decimal, ROUND_HALF_UP
                if appointment_group:
                    payout_gross = sum(
                        (Decimal(str(item.order_item.line_subtotal or "0.00"))
                         for item in appointment_group.bookings.exclude(status="cancelled").select_related("order_item")
                         if hasattr(item, "order_item")),
                        Decimal("0.00"),
                    )
                elif order:
                    payout_gross = sum(
                        (Decimal(str(item.line_subtotal or "0.00")) for item in order.items.all()),
                        Decimal("0.00"),
                    )
                else:
                    order_item = getattr(booking, "order_item", None)
                    snapshot = booking.pricing_snapshot or {}
                    payout_gross = Decimal(str(
                        order_item.line_subtotal if order_item
                        else snapshot.get("subtotal", snapshot.get("total", "0.00"))
                    ))
                commission = (payout_gross * worker.commission_rate / Decimal("100")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                net_payout = payout_gross - commission
                worker_payout = str(net_payout) if net_payout > 0 else None

            notification_data = {
                "offer_id": offer.pk,
                "booking_id": booking.pk,
                "appointment_group_id": appointment_group.pk if appointment_group else None,
                "appointment_group_message": appointment_group.customer_message if appointment_group else "",
                "quantity": service_quantity,
                "service_unit_label": service_unit_label,
                "order_id": (
                    (order or payment_order).pk if (order or payment_order)
                    else recurring_visit.plan.order_id if recurring_visit else None
                ),
                "service_ids": (
                    list(appointment_group.bookings.exclude(status="cancelled").values_list("service_id", flat=True))
                    if appointment_group else (
                        list((order or payment_order).items.values_list("booking__service_id", flat=True))
                        if (order or payment_order) else [booking.service_id]
                    )
                ),
                "recurring_plan_id": recurring_visit.plan_id if recurring_visit else None,
                "recurring_visit_id": recurring_visit.pk if recurring_visit else None,
                "recurring_visit_number": recurring_visit.visit_number if recurring_visit else None,
                "service_title": summary,
                "scheduled_at": booking.scheduled_at.isoformat(),
                "address": address_text,
                "customer_instructions": (appointment_group.customer_message if appointment_group else booking.notes) or "",
                "expected_duration_minutes": duration_minutes,
                "worker_payout": worker_payout,
                "notification_kind": "worker_offer",
            }
            # Keep the lock-screen alert focused on the job and the worker's
            # own earning; customer payment totals are intentionally not shown.
            location_preview = (address_text or "").strip()[:90]
            notification_body = (
                f"New AIRway service request: {summary} • "
                f"{booking.scheduled_at.strftime('%d %b, %I:%M %p')} • {location_preview} "
                f"{('• ' + quantity_preview + ' ') if quantity_preview else ''}"
                + (f"• Your earning: ₹{worker_payout}" if worker_payout is not None
                   else "• Your earning is not configured yet; open AIRway for details.")
            )
            Notification.objects.create(
                user=worker.user,
                type=Notification.Type.WORKER_OFFER,
                title=notification_title,
                body=notification_body,
                channel=Notification.Channel.IN_APP,
                data=notification_data,
            )
            from apps.notifications.service import send_push_notification
            transaction.on_commit(
                lambda user=worker.user, title=notification_title, body=notification_body, payload=notification_data:
                    send_push_notification(
                        user,
                        title,
                        body,
                        data=payload,
                        channel_id="airway_job_alerts",
                    )
            )
        logger.info("Dispatched %s offers for %s %s in batch %s", len(created), "order" if order else "booking", order.pk if order else booking.pk, batch_number)
        return created

    @staticmethod
    def _assigned_booking_intervals(booking):
        """Return occupied time for a booking, expanding multi-service groups once."""
        from apps.bookings.models import Booking
        from apps.bookings.services import _booking_intervals

        if booking.appointment_group_id:
            group = booking.appointment_group
            group_bookings = list(
                group.bookings.exclude(status=Booking.Status.CANCELLED)
                .select_related("service", "variant")
            )
            total_minutes = 0
            for item in group_bookings:
                duration = (
                    item.variant.duration_minutes
                    if item.variant_id and item.variant.duration_minutes
                    else item.service.duration_minutes
                ) or 60
                quantity = max(int((item.pricing_snapshot or {}).get("quantity", 1) or 1), 1)
                duration *= 1 if item.service.pricing_type == "per_unit" else quantity
                total_minutes += duration + max(int(item.service.buffer_minutes or 0), 0)
            return [(
                group.scheduled_at,
                group.scheduled_at + timedelta(minutes=max(total_minutes, 1)),
            )]

        duration = (
            booking.variant.duration_minutes
            if booking.variant_id and booking.variant.duration_minutes
            else booking.service.duration_minutes
        ) or 60
        quantity = max(int((booking.pricing_snapshot or {}).get("quantity", 1) or 1), 1)
        duration *= 1 if booking.service.pricing_type == "per_unit" else quantity
        return _booking_intervals(
            booking.scheduled_at,
            duration,
            booking.service.buffer_minutes,
            booking.drop_scheduled_at
            if booking.booking_mode == Booking.BookingMode.PICKUP_DROP else None,
        )

    @staticmethod
    def _root_category_id(category):
        while category.parent_id:
            category = category.parent
        return category.pk

    @classmethod
    def _service_scope_tiers(cls, workers, requested_service):
        """Return skill-priority tiers for already eligible exact-service workers."""
        if not workers:
            return {}

        from apps.workers.models import WorkerService

        worker_ids = [worker.pk for worker in workers]
        scopes = {worker_id: {"services": set(), "roots": set()} for worker_id in worker_ids}
        rows = WorkerService.objects.filter(
            worker_id__in=worker_ids,
            service__is_active=True,
            service__category__is_active=True,
        ).select_related("service__category__parent")
        for row in rows:
            scopes[row.worker_id]["services"].add(row.service_id)
            scopes[row.worker_id]["roots"].add(
                cls._root_category_id(row.service.category)
            )

        requested_root = cls._root_category_id(requested_service.category)
        tiers = {}
        for worker in workers:
            scope = scopes.get(worker.pk, {"services": set(), "roots": set()})
            if len(scope["services"]) <= 1:
                tiers[worker.pk] = 0
            elif scope["roots"] == {requested_root}:
                tiers[worker.pk] = 1
            else:
                tiers[worker.pk] = 2
        return tiers

    @classmethod
    def _appointment_group_tiers(cls, workers, bookings):
        """Return exact-service-set, same-root, and multi-category worker tiers."""
        if not workers:
            return {}

        from apps.workers.models import WorkerService

        worker_ids = [worker.pk for worker in workers]
        target_service_ids = {booking.service_id for booking in bookings}
        target_root_ids = {
            cls._root_category_id(booking.service.category)
            for booking in bookings
        }
        scopes = {worker_id: {"services": set(), "roots": set()} for worker_id in worker_ids}
        rows = WorkerService.objects.filter(
            worker_id__in=worker_ids,
            service__is_active=True,
            service__category__is_active=True,
        ).select_related("service__category__parent")
        for row in rows:
            scopes[row.worker_id]["services"].add(row.service_id)
            scopes[row.worker_id]["roots"].add(
                cls._root_category_id(row.service.category)
            )

        tiers = {}
        for worker in workers:
            scope = scopes.get(worker.pk, {"services": set(), "roots": set()})
            if scope["services"] == target_service_ids:
                tiers[worker.pk] = 0
            elif scope["roots"].issubset(target_root_ids):
                tiers[worker.pk] = 1
            else:
                tiers[worker.pk] = 2
        return tiers

    @staticmethod
    def _priority_ordering(priority_order):
        """Translate the Admin-selected priority strategy into stable DB ordering."""
        from apps.bookings.models import DispatchConfiguration

        if priority_order == DispatchConfiguration.PRIORITY_ACCEPTANCE:
            return ("-acceptance_rate", "-rating_avg", "pk")
        if priority_order == DispatchConfiguration.PRIORITY_RATING_ACCEPTANCE:
            return ("-rating_avg", "-acceptance_rate", "pk")
        if priority_order == DispatchConfiguration.PRIORITY_CANCELLATIONS:
            return ("cancellation_count", "-rating_avg", "pk")
        return ("-rating_avg", "pk")

    @classmethod
    def _get_eligible_workers(
        cls, service, zone, scheduled_at, duration_minutes,
        drop_scheduled_at=None, exclude_booking_id=None,
        exclude_customer_id=None, required_gender=None, priority_order=None,
        required_tasks=None,
    ):
        """Return workers who can cover every visit without a schedule or job conflict."""
        from apps.workers.models import WorkerProfile
        from apps.workers.eligibility import eligible_workers_for_service
        from apps.availability.models import WorkerBlockedSlot
        from apps.bookings.models import Booking, BookingAssignment
        from apps.bookings.services import _booking_intervals, _intervals_overlap

        if not scheduled_at or not zone or not zone.is_active or not zone.city.is_active:
            return WorkerProfile.objects.none()

        eligible_workers = eligible_workers_for_service(
            service, zone=zone, required_tasks=required_tasks,
        )
        if required_gender:
            eligible_workers = eligible_workers.filter(gender=required_gender)
        if exclude_customer_id is not None:
            eligible_workers = eligible_workers.exclude(user_id=exclude_customer_id)
        eligible_workers = eligible_workers.prefetch_related("schedules", "leaves")

        duration_minutes = max(int(duration_minutes or service.duration_minutes or 60), 1)
        duration = timedelta(minutes=duration_minutes)
        requested_intervals = _booking_intervals(
            scheduled_at, duration_minutes, service.buffer_minutes, drop_scheduled_at,
        )
        # Worker shift must cover the visit plus configured turnaround buffer.
        visit_windows = requested_intervals

        active_statuses = [
            Booking.Status.ASSIGNED,
            Booking.Status.CONFIRMED,
            Booking.Status.IN_PROGRESS,
        ]
        eligible_ids = []
        for worker in eligible_workers:
            schedule_ok = True
            for visit_start, visit_end in visit_windows:
                local_start = timezone.localtime(visit_start)
                local_end = timezone.localtime(visit_end)
                if local_start.date() != local_end.date() or not worker.schedules.filter(
                    weekday=local_start.weekday(),
                    is_active=True,
                    start_time__lte=local_start.time(),
                    end_time__gte=local_end.time(),
                ).exists():
                    schedule_ok = False
                    break
            if not schedule_ok:
                continue

            blocked = any(
                WorkerBlockedSlot.objects.filter(
                    worker=worker.user,
                    start_at__lt=end_at,
                    end_at__gt=start_at,
                ).exists()
                or worker.leaves.filter(
                    status="approved",
                    start_at__lt=end_at,
                    end_at__gt=start_at,
                ).exists()
                for start_at, end_at in requested_intervals
            )
            if blocked:
                continue

            assignments = BookingAssignment.objects.filter(
                worker=worker,
                booking__status__in=active_statuses,
            ).exclude(booking_id=exclude_booking_id).select_related(
                "booking__service", "booking__variant",
            )
            conflict = False
            for assignment in assignments:
                existing = assignment.booking
                if not existing.scheduled_at:
                    continue
                occupied = cls._assigned_booking_intervals(existing)
                if any(
                    _intervals_overlap(requested, current)
                    for requested in requested_intervals
                    for current in occupied
                ):
                    conflict = True
                    break
            if conflict:
                continue

            eligible_ids.append(worker.id)

        return WorkerProfile.objects.filter(id__in=eligible_ids).order_by(
            *cls._priority_ordering(priority_order)
        ).select_related("user")
