"""
DispatcherService - Handles multi-worker offer dispatch for bookings.
"""
import logging
from datetime import timedelta
from django.utils import timezone
from django.db import transaction

logger = logging.getLogger(__name__)

# Configuration constants
BATCH_SIZE = 5  # Max workers per batch
MAX_BATCHES = 3  # Max batches (5 workers × 3 batches = 15 max total offers)
OFFER_EXPIRY_MINUTES = 5  # Time window for workers to accept


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
    1. Find eligible workers sorted by rating (desc), then proximity
    2. Split into batches of 5 workers max
    3. Create WorkerOffer records with 5-minute expiry
    4. Send notifications to each offered worker
    """

    @classmethod
    def dispatch_offers(cls, booking, batch_size=None, expiry_minutes=None):
        """Dispatch a standalone booking through configured priority batches."""
        from apps.bookings.models import WorkerOffer, DispatchConfiguration
        config = DispatchConfiguration.get_solo()
        if not config.is_enabled or booking.status not in (booking.Status.PENDING, booking.Status.CONFIRMED):
            return []
        batch_size = max(int(batch_size or config.batch_size), 1)
        expiry_minutes = max(int(expiry_minutes or config.offer_expiry_minutes), 1)
        existing = WorkerOffer.objects.filter(booking=booking, order__isnull=True)
        if existing.filter(status__in=[WorkerOffer.Status.PENDING, WorkerOffer.Status.ACCEPTED]).exists():
            return []
        from django.db.models import Max
        batch_number = (existing.aggregate(value=Max("batch_number"))["value"] or 0) + 1
        if batch_number > config.max_batches:
            return []
        duration = (booking.variant.duration_minutes if booking.variant_id and booking.variant.duration_minutes else booking.service.duration_minutes) or 60
        quantity = max(int((booking.pricing_snapshot or {}).get("quantity", 1) or 1), 1)
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
            duration_minutes=duration * quantity,
            drop_scheduled_at=booking.drop_scheduled_at if booking.booking_mode == booking.BookingMode.PICKUP_DROP else None,
            exclude_booking_id=booking.pk,
            exclude_customer_id=booking.customer_id,
            required_gender=gender,
        )
        already_offered = set(existing.values_list("worker_id", flat=True))
        candidates = [worker for worker in candidates if worker.pk not in already_offered][:batch_size]
        return cls._create_offers(
            booking=booking, order=None, workers=candidates,
            batch_number=batch_number, expiry_minutes=expiry_minutes,
            service_titles=[booking.service.title],
        )

    @classmethod
    def dispatch_order(cls, order):
        """Offer a parent order only to workers eligible for every service line."""
        from apps.bookings.models import Booking, BookingAssignment, WorkerOffer, DispatchConfiguration, Order
        from apps.workers.models import WorkerProfile
        from django.db.models import Max

        with transaction.atomic():
            order = Order.objects.select_for_update().get(pk=order.pk)
            config = DispatchConfiguration.get_solo()
            if not config.is_enabled or order.status != Order.Status.AWAITING_ASSIGNMENT:
                return []
            items = list(order.items.select_related(
                "booking__service__category", "booking__variant", "booking__address__zone__city"
            ).order_by("created_at"))
            if not items:
                return []
            bookings = [item.booking for item in items]
            if any(
                booking.status not in (Booking.Status.PENDING, Booking.Status.CONFIRMED)
                or BookingAssignment.objects.filter(booking=booking).exists()
                for booking in bookings
            ):
                return []
            anchor = bookings[0]
            zone_id = anchor.address.zone_id if anchor.address_id else None
            if not zone_id or any(
                booking.address_id != anchor.address_id or booking.address.zone_id != zone_id
                for booking in bookings
            ):
                logger.warning("Order %s has inconsistent service addresses; dispatch skipped", order.pk)
                return []

            # One worker cannot perform two separate service lines at the
            # same time. Each line must have a non-overlapping reserved window.
            from apps.bookings.services import _booking_intervals, _intervals_overlap
            occupied_order_intervals = []
            for line in bookings:
                line_duration = (
                    line.variant.duration_minutes
                    if line.variant_id and line.variant.duration_minutes
                    else line.service.duration_minutes
                ) or 60
                line_quantity = max(int((line.pricing_snapshot or {}).get("quantity", 1) or 1), 1)
                line_intervals = _booking_intervals(
                    line.scheduled_at,
                    line_duration * line_quantity,
                    line.service.buffer_minutes,
                    line.drop_scheduled_at if line.booking_mode == line.BookingMode.PICKUP_DROP else None,
                )
                if any(
                    _intervals_overlap(current, previous)
                    for current in line_intervals
                    for previous in occupied_order_intervals
                ):
                    logger.info("Order %s has overlapping service times; dispatch skipped", order.pk)
                    return []
                occupied_order_intervals.extend(line_intervals)

            eligible_ids = None
            for booking in bookings:
                duration = (
                    booking.variant.duration_minutes
                    if booking.variant_id and booking.variant.duration_minutes
                    else booking.service.duration_minutes
                ) or 60
                quantity = max(int((booking.pricing_snapshot or {}).get("quantity", 1) or 1), 1)
                from apps.workers.eligibility import required_worker_gender_for_booking
                try:
                    gender = required_worker_gender_for_booking(booking.service, booking.customer_answers)
                except ValueError:
                    logger.exception("Invalid worker preference on booking %s", booking.pk)
                    return []
                line_workers = cls._get_eligible_workers(
                    service=booking.service,
                    zone=booking.address.zone,
                    scheduled_at=booking.scheduled_at,
                    duration_minutes=duration * quantity,
                    drop_scheduled_at=booking.drop_scheduled_at if booking.booking_mode == booking.BookingMode.PICKUP_DROP else None,
                    exclude_booking_id=booking.pk,
                    exclude_customer_id=booking.customer_id,
                    required_gender=gender,
                )
                line_ids = set(line_workers.values_list("pk", flat=True))
                eligible_ids = line_ids if eligible_ids is None else eligible_ids.intersection(line_ids)
                if not eligible_ids:
                    return []

            existing = WorkerOffer.objects.filter(order=order)
            if existing.filter(status__in=[WorkerOffer.Status.PENDING, WorkerOffer.Status.ACCEPTED]).exists():
                return []
            batch_number = (existing.aggregate(value=Max("batch_number"))["value"] or 0) + 1
            if batch_number > config.max_batches:
                return []
            already_offered = set(existing.values_list("worker_id", flat=True))
            workers = list(
                WorkerProfile.objects.filter(pk__in=eligible_ids)
                .exclude(pk__in=already_offered)
                .select_related("user")
                .order_by("-rating_avg", "pk")[:config.batch_size]
            )
            return cls._create_offers(
                booking=anchor, order=order, workers=workers,
                batch_number=batch_number, expiry_minutes=config.offer_expiry_minutes,
                service_titles=[booking.service.title for booking in bookings],
            )

    @classmethod
    def _create_offers(cls, *, booking, order, workers, batch_number, expiry_minutes, service_titles):
        from datetime import timedelta
        from apps.bookings.models import WorkerOffer
        from apps.notifications.models import Notification
        expiry = timezone.now() + timedelta(minutes=max(int(expiry_minutes), 1))
        created = []
        summary = ", ".join(service_titles)
        for worker in workers:
            offer = WorkerOffer.objects.create(
                booking=booking, order=order, worker=worker,
                batch_number=batch_number, expires_at=expiry,
            )
            created.append(offer)
            Notification.objects.create(
                user=worker.user,
                type=Notification.Type.WORKER_OFFER,
                title="New Service Order" if order else "Job Offer",
                body=(f"New order ({len(service_titles)} services): {summary}" if order else f"New job request for {summary} at {booking.scheduled_at.strftime('%d %b, %H:%M')}"),
                channel=Notification.Channel.IN_APP,
                data={
                    "offer_id": offer.pk, "booking_id": booking.pk,
                    "order_id": order.pk if order else None,
                    "service_ids": list(order.items.values_list("booking__service_id", flat=True)) if order else [booking.service_id],
                    "scheduled_at": booking.scheduled_at.isoformat(),
                },
            )
        logger.info("Dispatched %s offers for %s %s in batch %s", len(created), "order" if order else "booking", order.pk if order else booking.pk, batch_number)
        return created

    @classmethod
    def _get_eligible_workers(
        cls, service, zone, scheduled_at, duration_minutes,
        drop_scheduled_at=None, exclude_booking_id=None,
        exclude_customer_id=None, required_gender=None,
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
            service, zone=zone,
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
        worker_ratings = {}

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

            worker_ratings[worker.id] = worker.rating_avg or 0
            eligible_ids.append(worker.id)

        eligible_ids.sort(key=lambda worker_id: worker_ratings.get(worker_id, 0), reverse=True)
        return WorkerProfile.objects.filter(id__in=eligible_ids).order_by(
            "-rating_avg"
        ).select_related("user")
