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
    def dispatch_offers(cls, booking, batch_size=BATCH_SIZE, expiry_minutes=OFFER_EXPIRY_MINUTES):
        """
        Create worker offers for a booking.

        Args:
            booking: Booking instance (must be PENDING or CONFIRMED status)
            batch_size: Number of workers per batch (default 5)
            expiry_minutes: Offer expiry time window in minutes (default 5)

        Returns:
            list: Created WorkerOffer instances

        Raises:
            ValueError: If booking has no address/zone or invalid status
        """
        from apps.workers.models import WorkerProfile, WorkerService, WorkerZone, WorkerSchedule
        from apps.availability.models import WorkerBlockedSlot
        from apps.notifications.models import Notification
        from apps.bookings.models import WorkerOffer

        # Validate booking status - can dispatch for PENDING or CONFIRMED
        if booking.status not in [booking.Status.PENDING, booking.Status.CONFIRMED]:
            logger.warning(f"Cannot dispatch for booking {booking.id} in status {booking.status}")
            return []

        # Get address and zone
        address = booking.address
        if not address or not address.zone:
            logger.warning(f"Booking {booking.id} has no address or zone for dispatch")
            return []

        service = booking.service
        scheduled_at = booking.scheduled_at
        duration_minutes = (booking.variant.duration_minutes if booking.variant else service.duration_minutes) or 60

        if not scheduled_at:
            logger.warning(f"Booking {booking.id} has no scheduled_at time")
            return []

        # Calculate booking time window
        from datetime import timedelta
        booking_end = scheduled_at + timedelta(minutes=duration_minutes)

        # Find eligible workers
        from apps.workers.eligibility import required_worker_gender_for_booking
        try:
            required_gender = required_worker_gender_for_booking(
                service, booking.customer_answers
            )
        except ValueError:
            logger.exception("Invalid worker preference on booking %s", booking.id)
            return []

        eligible_workers = cls._get_eligible_workers(
            service=service,
            zone=address.zone,
            scheduled_at=scheduled_at,
            duration_minutes=duration_minutes,
            drop_scheduled_at=booking.drop_scheduled_at if booking.booking_mode == booking.BookingMode.PICKUP_DROP else None,
            exclude_booking_id=booking.id,
            exclude_customer_id=booking.customer_id,
            required_gender=required_gender,
        )

        if not eligible_workers:
            logger.info(f"No eligible workers found for booking {booking.id}")
            return []

        # Create offers with notifications
        offers_created = []
        offer_expiry = timezone.now() + timedelta(minutes=expiry_minutes)

        for worker in eligible_workers[:batch_size]:
            # Check for duplicate offer
            if WorkerOffer.objects.filter(booking=booking, worker=worker).exists():
                continue

            # Create the offer
            offer = WorkerOffer.objects.create(
                booking=booking,
                worker=worker,
                expires_at=offer_expiry
            )
            offers_created.append(offer)

            # Create notification for worker
            Notification.objects.create(
                user=worker.user,
                type=Notification.Type.WORKER_OFFER,
                title="Job Offer",
                body=f"A new job request for {service.title} at {scheduled_at.strftime('%d %b, %H:%M')}",
                channel=Notification.Channel.IN_APP,
                data={
                    "offer_id": offer.id,
                    "booking_id": booking.id,
                    "service_id": service.id,
                    "scheduled_at": scheduled_at.isoformat(),
                }
            )
            logger.info(f"Created offer {offer.id} for worker {worker.user.phone} -> booking {booking.id}")

        logger.info(f"Dispatched {len(offers_created)} offers for booking {booking.id}")
        return offers_created

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
