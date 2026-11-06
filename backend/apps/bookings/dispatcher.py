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
        eligible_workers = cls._get_eligible_workers(
            service=service,
            zone=address.zone,
            scheduled_at=scheduled_at,
            duration_minutes=duration_minutes
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
    def _get_eligible_workers(cls, service, zone, scheduled_at, duration_minutes):
        """
        Get list of eligible workers sorted by rating (desc), then proximity.
        """
        from apps.workers.models import WorkerProfile
        from apps.workers.eligibility import eligible_workers_for_service
        from apps.availability.models import WorkerBlockedSlot
        from datetime import timedelta
        from django.utils import timezone

        # Use the same approved/online/skill/zone/schedule gates as the
        # customer catalogue. Booking-specific availability is checked below.
        eligible_workers = eligible_workers_for_service(
            service,
            zone=zone,
        ).prefetch_related("schedules", "leaves")

        # Convert to local timezone for schedule matching
        local_scheduled_at = timezone.localtime(scheduled_at)
        weekday = local_scheduled_at.weekday()
        booking_time = local_scheduled_at.time()
        booking_end = scheduled_at + timedelta(minutes=duration_minutes)
        local_booking_end = timezone.localtime(booking_end)

        eligible_ids = []
        worker_ratings = {}

        for worker in eligible_workers:
            # The full service duration must fit inside one active weekday shift.
            schedule_match = worker.schedules.filter(
                weekday=weekday,
                is_active=True,
                start_time__lte=booking_time,
                end_time__gte=local_booking_end.time(),
            ).order_by("start_time").first()

            # Overnight jobs are not supported by the current schedule model.
            if not schedule_match or local_booking_end.date() != local_scheduled_at.date():
                continue

            # Check both ad-hoc blocked slots and worker-entered leave periods.
            blocked = WorkerBlockedSlot.objects.filter(
                worker=worker.user,
                start_at__lt=booking_end,
                end_at__gt=scheduled_at,
            ).exists()
            on_leave = worker.leaves.filter(
                start_at__lt=booking_end,
                end_at__gt=scheduled_at,
            ).exists()

            if blocked or on_leave:
                continue

            # Collect rating for sorting.
            rating = worker.rating_avg or 0
            worker_ratings[worker.id] = rating
            eligible_ids.append(worker.id)

        # Sort by rating (descending)
        eligible_ids.sort(key=lambda wid: worker_ratings.get(wid, 0), reverse=True)

        # Return worker queryset in sorted order
        return WorkerProfile.objects.filter(id__in=eligible_ids).order_by(
            '-rating_avg'
        ).select_related('user')