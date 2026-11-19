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
        if order_id and parent_order is None:
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
            if not (parent_order.metadata or {}).get("payment_allocation_v1") or not Payment.objects.filter(
                order=parent_order, stage=Payment.Stage.ADVANCE,
                status=Payment.Status.PAID,
            ).exists():
                return []
        elif not prepaid_recurring and not Payment.objects.filter(
            booking=booking, stage=Payment.Stage.ADVANCE,
            status=Payment.Status.PAID,
        ).exists():
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
        candidates = cls._rank_by_service_scope(candidates, booking.service)
        # The launch default offers every eligible worker simultaneously. Keep
        # the explicit batch_size argument meaningful for controlled dispatches
        # and callers that intentionally request a smaller batch.
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
    def dispatch_order(cls, order):
        """Dispatch one worker offer per appointment group, then legacy standalone lines."""
        from apps.bookings.models import (
            Booking, BookingAssignment, WorkerOffer, DispatchConfiguration,
            Order, AppointmentGroup,
        )
        from apps.payments.models import Payment

        with transaction.atomic():
            order = Order.objects.select_for_update().get(pk=order.pk)
            config = DispatchConfiguration.get_solo()
            if not config.is_enabled or order.status not in (
                Order.Status.AWAITING_ASSIGNMENT, Order.Status.PARTIALLY_CANCELLED
            ):
                return []
            if not (order.metadata or {}).get("payment_allocation_v1") or not Payment.objects.filter(
                order=order, stage=Payment.Stage.ADVANCE, status=Payment.Status.PAID
            ).exists():
                return []
            # Legacy whole-order offers are allowed to finish before the
            # appointment-group dispatch path takes ownership of the order.
            if WorkerOffer.objects.filter(
                order=order,
                status__in=(WorkerOffer.Status.PENDING, WorkerOffer.Status.ACCEPTED),
            ).exists():
                return []

            created = []
            grouped_booking_ids = set()
            groups = AppointmentGroup.objects.filter(order=order).order_by("scheduled_at", "id")
            for group in groups:
                group_bookings = list(
                    group.bookings.exclude(status=Booking.Status.CANCELLED)
                    .select_related("service__category__parent", "variant", "address__zone__city")
                    .order_by("created_at")
                )
                grouped_booking_ids.update(row.pk for row in group_bookings)
                if not group_bookings:
                    continue
                # A group is one worker visit. If any active line is already
                # assigned, never split the remaining lines across workers.
                if any(BookingAssignment.objects.filter(booking=row).exists() for row in group_bookings):
                    continue
                if any(row.status not in (Booking.Status.PENDING, Booking.Status.CONFIRMED) for row in group_bookings):
                    continue
                if WorkerOffer.objects.filter(
                    appointment_group=group,
                    status__in=(WorkerOffer.Status.PENDING, WorkerOffer.Status.ACCEPTED),
                ).exists():
                    continue
                created.extend(cls.dispatch_appointment_group(group, order, group_bookings))

            bookings = list(
                Booking.objects.filter(order_item__order=order)
                .exclude(status=Booking.Status.CANCELLED)
                .exclude(pk__in=grouped_booking_ids)
                .select_related("service__category", "variant", "address__zone__city")
                .order_by("created_at")
            )
            for booking in bookings:
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

    @classmethod
    def dispatch_appointment_group(cls, group, order, bookings=None):
        """Offer the complete appointment group only to workers qualified for every service."""
        from django.db.models import Max
        from apps.bookings.models import Booking, BookingAssignment, WorkerOffer, DispatchConfiguration
        from apps.workers.eligibility import required_worker_gender_for_booking

        config = DispatchConfiguration.get_solo()
        if not config.is_enabled or not bookings:
            return []
        bookings = list(bookings)
        if len({row.scheduled_at for row in bookings}) != 1:
            logger.error("Appointment group %s contains inconsistent service times", group.pk)
            return []
        if any(BookingAssignment.objects.filter(booking=row).exists() for row in bookings):
            return []
        if WorkerOffer.objects.filter(
            appointment_group=group,
            status__in=(WorkerOffer.Status.PENDING, WorkerOffer.Status.ACCEPTED),
        ).exists():
            return []

        total_duration = 0
        required_gender = None
        eligible_ids = None
        service_titles = []
        required_tasks_by_service = {}
        for booking in bookings:
            duration = (
                booking.variant.duration_minutes
                if booking.variant_id and booking.variant.duration_minutes
                else booking.service.duration_minutes
            ) or 60
            quantity = max(int((booking.pricing_snapshot or {}).get("quantity", 1) or 1), 1)
            duration *= 1 if booking.service.pricing_type == "per_unit" else quantity
            total_duration += duration
            service_titles.append(booking.service.title)
            try:
                gender = required_worker_gender_for_booking(booking.service, booking.customer_answers)
            except ValueError:
                logger.exception("Invalid worker preference in appointment group %s", group.pk)
                return []
            if gender:
                if required_gender and required_gender != gender:
                    logger.warning("Conflicting worker gender requirements in appointment group %s", group.pk)
                    return []
                required_gender = gender
            tasks = booking.variant.included_tasks if booking.variant_id else []
            required_tasks_by_service[booking.service_id] = tasks or []

            zone = booking.address.zone if booking.address_id else None
            candidates = cls._get_eligible_workers(
                service=booking.service,
                zone=zone,
                scheduled_at=booking.scheduled_at,
                duration_minutes=duration,
                drop_scheduled_at=(
                    booking.drop_scheduled_at
                    if booking.booking_mode == Booking.BookingMode.PICKUP_DROP else None
                ),
                exclude_booking_id=booking.pk,
                exclude_customer_id=booking.customer_id,
                required_gender=gender,
                priority_order=config.priority_order,
                required_tasks=tasks,
            )
            current_ids = set(candidates.values_list("pk", flat=True))
            eligible_ids = current_ids if eligible_ids is None else eligible_ids.intersection(current_ids)
            if not eligible_ids:
                break

        if not eligible_ids:
            cls._notify_dispatch_exhausted(bookings[0], order=order)
            return []

        anchor = bookings[0]
        combined_candidates = cls._get_eligible_workers(
            service=anchor.service,
            zone=anchor.address.zone if anchor.address_id else None,
            scheduled_at=anchor.scheduled_at,
            duration_minutes=total_duration,
            drop_scheduled_at=(
                anchor.drop_scheduled_at
                if anchor.booking_mode == Booking.BookingMode.PICKUP_DROP else None
            ),
            exclude_booking_id=anchor.pk,
            exclude_customer_id=anchor.customer_id,
            required_gender=required_gender,
            priority_order=config.priority_order,
            required_tasks=required_tasks_by_service.get(anchor.service_id, []),
        ).filter(pk__in=eligible_ids)
        candidates = cls._rank_by_appointment_group(list(combined_candidates), bookings)
        existing = WorkerOffer.objects.filter(appointment_group=group)
        already_offered = set(existing.filter(
            status__in=(WorkerOffer.Status.DECLINED, WorkerOffer.Status.EXPIRED)
        ).values_list("worker_id", flat=True))
        candidates = [worker for worker in candidates if worker.pk not in already_offered]
        if not candidates:
            cls._notify_dispatch_exhausted(anchor, order=order)
            return []
        batch_number = (existing.aggregate(value=Max("batch_number"))["value"] or 0) + 1
        return cls._create_offers(
            booking=anchor,
            order=None,
            appointment_group=group,
            workers=candidates,
            batch_number=batch_number,
            expiry_minutes=config.offer_expiry_minutes,
            service_titles=service_titles,
            payment_order=order,
        )

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
        from apps.bookings.models import WorkerOffer
        from apps.notifications.models import Notification
        expiry = timezone.now() + timedelta(minutes=max(int(expiry_minutes), 1))
        created = []
        summary = ", ".join(service_titles)
        group_bookings = (
            list(appointment_group.bookings.select_related(
                "service", "variant", "order_item"
            ).order_by("created_at"))
            if appointment_group else []
        )
        for worker in workers:
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
            notification_title = (
                "New Service Order" if order
                else "New Appointment Group" if appointment_group
                else "Job Offer"
            )
            notification_body = (
                f"New order ({len(service_titles)} services): {summary}"
                if order else
                f"New appointment ({len(service_titles)} services): {summary}"
                if appointment_group else
                f"New job request for {summary} at {booking.scheduled_at.strftime('%d %b, %H:%M')}"
            )
            from apps.payments.models import Payment
            if recurring_visit:
                from decimal import Decimal
                customer_total = str(recurring_visit.prepaid_amount)
                advance_received = str(recurring_visit.prepaid_amount)
                remaining_balance = "0.00"
                address_text = booking.address.full_address
            elif appointment_group:
                from decimal import Decimal
                payment_context = payment_order
                allocation = (payment_context.metadata or {}).get("payment_allocation_v1", {})
                group_order_item_ids = {row.order_item.pk for row in group_bookings if hasattr(row, "order_item")}
                customer_total_value = sum(
                    (row.order_item.line_total for row in group_bookings if hasattr(row, "order_item")),
                    Decimal("0.00"),
                )
                advance_received_value = sum(
                    (
                        Decimal(str(entry.get("amount", "0")))
                        for entry in allocation.get("advance", [])
                        if entry.get("order_item_id") in group_order_item_ids
                    ),
                    Decimal("0.00"),
                )
                customer_total = str(customer_total_value)
                advance_received = str(advance_received_value)
                remaining_balance = str(max(
                    customer_total_value - advance_received_value, Decimal("0.00")
                ))
                address_text = payment_context.address.full_address
            elif order or payment_order:
                from decimal import Decimal
                payment_context = order or payment_order
                allocation = (payment_context.metadata or {}).get("payment_allocation_v1", {})
                order_item = getattr(booking, "order_item", None)
                advance_row = next(
                    (row for row in allocation.get("advance", [])
                     if order_item and row.get("order_item_id") == order_item.id),
                    {},
                )
                customer_total = str(order_item.line_total if order_item else payment_context.total_amount)
                advance_received = str(advance_row.get("amount", "0.00")) if order_item else str(allocation.get("advance_total", "0"))
                remaining_balance = str(max(
                    Decimal(customer_total) - Decimal(advance_received), Decimal("0.00")
                ))
                address_text = payment_context.address.full_address
            else:
                from decimal import Decimal
                snapshot = booking.pricing_snapshot or {}
                customer_total = str(snapshot.get("total", booking.total_amount))
                advance_received = str(Payment.objects.filter(
                    booking=booking, stage=Payment.Stage.ADVANCE,
                    status=Payment.Status.PAID,
                ).values_list("amount", flat=True).first() or "0")
                remaining_balance = str(max(Decimal(customer_total) - Decimal(advance_received), Decimal("0")))
                address_text = booking.address.full_address
            if appointment_group:
                duration_minutes = 0
                for group_booking in group_bookings:
                    row_duration = (
                        group_booking.variant.duration_minutes
                        if group_booking.variant_id and group_booking.variant.duration_minutes
                        else group_booking.service.duration_minutes
                    ) or 60
                    row_quantity = (
                        group_booking.order_item.quantity
                        if hasattr(group_booking, "order_item")
                        else max(int((group_booking.pricing_snapshot or {}).get("quantity", 1) or 1), 1)
                    )
                    duration_minutes += row_duration * (
                        1 if group_booking.service.pricing_type == "per_unit" else row_quantity
                    )
                service_quantity = len(group_bookings)
                service_unit_label = "services"
                quantity_preview = f"{service_quantity} services"
            else:
                duration_minutes = (
                    booking.variant.duration_minutes
                    if booking.variant_id and booking.variant.duration_minutes
                    else booking.service.duration_minutes
                ) or 60
                duration_minutes *= (
                    1 if booking.service.pricing_type == "per_unit"
                    else max(int((booking.pricing_snapshot or {}).get("quantity", 1) or 1), 1)
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
            notification_data = {
                "offer_id": offer.pk,
                "booking_id": booking.pk,
                "quantity": service_quantity,
                "service_unit_label": service_unit_label,
                "order_id": (
                    (order or payment_order).pk if (order or payment_order)
                    else recurring_visit.plan.order_id if recurring_visit else None
                ),
                "service_ids": (
                    [row.service_id for row in group_bookings]
                    if appointment_group else
                    list((order or payment_order).items.values_list("booking__service_id", flat=True))
                    if (order or payment_order) else [booking.service_id]
                ),
                "appointment_group_id": appointment_group.pk if appointment_group else None,
                "appointment_group_title": appointment_group.category_title_snapshot if appointment_group else None,
                "appointment_group_message": appointment_group.customer_message if appointment_group else "",
                "recurring_plan_id": recurring_visit.plan_id if recurring_visit else None,
                "recurring_visit_id": recurring_visit.pk if recurring_visit else None,
                "recurring_visit_number": recurring_visit.visit_number if recurring_visit else None,
                "service_title": summary,
                "scheduled_at": booking.scheduled_at.isoformat(),
                "address": address_text,
                "customer_instructions": "\\n".join(
                    value for value in [
                        appointment_group.customer_message if appointment_group else "",
                        booking.notes or "",
                    ] if value
                ),
                "expected_duration_minutes": duration_minutes,
                "customer_total": customer_total,
                "advance_received": advance_received,
                "remaining_balance": remaining_balance,
                "notification_kind": "worker_offer",
            }
            # Put actionable facts in the visible push body as well as its data
            # payload; workers should not need to open the app just to see the
            # location, appointment, and payment split.
            location_preview = (address_text or "").strip()[:90]
            notification_body = (
                f"{summary} • {booking.scheduled_at.strftime('%d %b, %I:%M %p')} "
                f"• {location_preview} "
                f"{('• ' + quantity_preview + ' ') if quantity_preview else ''}"
                f"• Advance ₹{advance_received} • Balance ₹{remaining_balance}"
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

    @classmethod
    def _rank_by_appointment_group(cls, workers, bookings):
        """Rank workers dedicated to this exact service set before related and multi-category workers."""
        if not workers:
            return workers
        from apps.workers.models import WorkerService

        worker_ids = [worker.pk for worker in workers]
        target_service_ids = {booking.service_id for booking in bookings}
        category = bookings[0].service.category
        while category.parent_id:
            category = category.parent
        target_root_id = category.pk
        scopes = {worker_id: {"services": set(), "roots": set()} for worker_id in worker_ids}

        rows = WorkerService.objects.filter(
            worker_id__in=worker_ids,
            service__is_active=True,
            service__category__is_active=True,
        ).select_related("service__category__parent")
        for row in rows:
            service_category = row.service.category
            while service_category.parent_id:
                service_category = service_category.parent
            scopes[row.worker_id]["services"].add(row.service_id)
            scopes[row.worker_id]["roots"].add(service_category.pk)

        def tier(worker):
            scope = scopes.get(worker.pk, {"services": set(), "roots": set()})
            if scope["services"] == target_service_ids:
                return 0
            if scope["roots"] == {target_root_id}:
                return 1
            return 2

        return sorted(workers, key=tier)

    @classmethod
    def _rank_by_service_scope(cls, workers, requested_service):
        """Prefer dedicated service professionals, then same-category specialists, then multi-category workers.

        Every candidate has already passed exact-service enrollment, approval,
        zone, schedule, leave, gender, task and conflict checks. This method
        changes ranking only; it never broadens worker eligibility.
        """
        if not workers:
            return workers

        from apps.workers.models import WorkerService

        worker_ids = [worker.pk for worker in workers]
        service_rows = WorkerService.objects.filter(
            worker_id__in=worker_ids,
            service__is_active=True,
            service__category__is_active=True,
        ).select_related("service__category__parent")
        scopes = {worker_id: {"services": set(), "roots": set()} for worker_id in worker_ids}

        def root_category(category):
            while category.parent_id:
                category = category.parent
            return category.pk

        requested_root = root_category(requested_service.category)
        for row in service_rows:
            scopes[row.worker_id]["services"].add(row.service_id)
            scopes[row.worker_id]["roots"].add(root_category(row.service.category))

        def tier(worker):
            scope = scopes.get(worker.pk, {"services": set(), "roots": set()})
            service_count = len(scope["services"])
            root_ids = scope["roots"]
            if service_count <= 1:
                return 0
            if root_ids == {requested_root}:
                return 1
            return 2

        # Python's sort is stable, so the existing Admin-configured rating /
        # acceptance / cancellation ordering remains the tie-breaker.
        return sorted(workers, key=tier)

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
                existing_duration = (
                    existing.variant.duration_minutes
                    if existing.variant_id and existing.variant.duration_minutes
                    else existing.service.duration_minutes
                ) or 60
                occupied = _booking_intervals(
                    existing.scheduled_at,
                    existing_duration,
                    existing.service.buffer_minutes,
                    existing.drop_scheduled_at
                    if existing.booking_mode == Booking.BookingMode.PICKUP_DROP
                    else None,
                )
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
