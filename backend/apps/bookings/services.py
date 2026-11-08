"""
Booking availability and slot management services.
Ensures no overlapping bookings and handles hold logic.
"""
from django.db import transaction
from django.utils import timezone
from datetime import timedelta

from apps.bookings.models import Booking
from apps.catalog.models import Service


class SlotConflictError(Exception):
    """Raised when a slot conflicts with existing bookings."""
    pass


class ServiceUnavailableError(Exception):
    """Raised when service is not available for booking."""
    pass


def _booking_intervals(
    start_at,
    duration_minutes: int,
    buffer_minutes: int,
    drop_at=None,
):
    """Return the service's occupied intervals, including configured buffer time."""
    duration = timedelta(minutes=max(int(duration_minutes or 0), 1))
    buffer = timedelta(minutes=max(int(buffer_minutes or 0), 0))
    intervals = [(start_at, start_at + duration + buffer)]
    if drop_at is not None:
        intervals.append((drop_at, drop_at + duration + buffer))
    return intervals


def _intervals_overlap(first, second) -> bool:
    """Half-open interval overlap: adjacent jobs are allowed when buffers permit."""
    return first[0] < second[1] and second[0] < first[1]


def check_slot_availability(
    service: Service,
    scheduled_at: timezone.datetime,
    duration_minutes: int,
    booking_mode: str,
    drop_scheduled_at: timezone.datetime = None,
    exclude_booking_id: int = None,
) -> bool:
    """
    Check whether a service slot overlaps an active booking.

    The current data model has service-level capacity (not per-worker slot
    inventory), so all active bookings for the same service are considered.
    Both start and end bounds are checked, and each existing booking uses its
    own variant duration plus the service buffer.
    """
    active_statuses = [
        Booking.Status.PENDING,
        Booking.Status.CONFIRMED,
        Booking.Status.ASSIGNED,
        Booking.Status.IN_PROGRESS,
    ]
    requested = _booking_intervals(
        scheduled_at,
        duration_minutes or service.duration_minutes or 60,
        service.buffer_minutes,
        drop_scheduled_at if booking_mode == Booking.BookingMode.PICKUP_DROP else None,
    )

    existing_bookings = (
        Booking.objects.filter(service=service, status__in=active_statuses)
        .exclude(pk=exclude_booking_id)
        .select_related("variant")
        .only(
            "id", "scheduled_at", "drop_scheduled_at", "booking_mode",
            "service__duration_minutes", "service__buffer_minutes",
            "variant__duration_minutes",
        )
    )

    for existing in existing_bookings:
        existing_duration = (
            existing.variant.duration_minutes
            if existing.variant_id and existing.variant.duration_minutes
            else existing.service.duration_minutes
        ) or 60
        existing_intervals = _booking_intervals(
            existing.scheduled_at,
            existing_duration,
            existing.service.buffer_minutes,
            existing.drop_scheduled_at
            if existing.booking_mode == Booking.BookingMode.PICKUP_DROP
            else None,
        )
        if any(
            _intervals_overlap(candidate, occupied)
            for candidate in requested
            for occupied in existing_intervals
        ):
            raise SlotConflictError("Slot is already booked. Please choose another time.")

    return True


def check_service_available(
    service: Service,
    address=None,
    audience: str = "all",
) -> bool:
    """
    Check if service is available for the given address.
    TODO: Implement pincode-based serviceability when CityService integration is ready.
    """
    if not service.is_active:
        raise ServiceUnavailableError(f"Service '{service.title}' is not active.")

    if not service.category.is_active:
        raise ServiceUnavailableError(
            f"Service '{service.title}' is not available."
        )

    # Booking serviceability follows the same area configuration as the
    # catalogue: either an active CityService row or an approved worker's
    # explicit service + zone assignment makes the service serviceable.
    # Online status and exact slot fit are handled by dispatch/availability.
    if address:
        if not address.zone_id or not address.zone.is_active:
            raise ServiceUnavailableError(
                "This address is outside an active AIRway service zone."
            )

        city = address.zone.city
        if not city.is_active:
            raise ServiceUnavailableError(
                f"Services are not active in {city.name}."
            )

        from apps.catalog.models import CityService
        from apps.workers.models import WorkerProfile

        city_configured = CityService.objects.filter(
            city=city,
            service=service,
            is_active=True,
        ).exists()
        worker_assigned = WorkerProfile.objects.filter(
            status=WorkerProfile.Status.APPROVED,
            worker_zones__zone=address.zone,
            worker_services__service=service,
        ).exists()

        if not city_configured and not worker_assigned:
            raise ServiceUnavailableError(
                f"Service '{service.title}' is not configured for {city.name}."
            )

    return True


def get_available_slots(
    service: Service,
    date,
    count: int = 5,
) -> list:
    """
    Return standard local-hour slots that pass the same interval validation
    used by booking creation and the availability endpoint.
    """
    from datetime import time

    start_of_day = timezone.make_aware(
        timezone.datetime.combine(date, time(0, 0))
    )
    available_slots = []

    for hour in range(10, 22):
        slot_time = start_of_day.replace(hour=hour)
        try:
            check_slot_availability(
                service=service,
                scheduled_at=slot_time,
                duration_minutes=service.duration_minutes or 60,
                booking_mode=Booking.BookingMode.SCHEDULED,
            )
        except SlotConflictError:
            continue
        available_slots.append(hour)
        if len(available_slots) >= count:
            break

    return available_slots


def has_eligible_worker_for_slot(
    service,
    address,
    scheduled_at,
    duration_minutes,
    required_gender=None,
    drop_scheduled_at=None,
    exclude_customer_id=None,
):
    """Check whether at least one eligible worker can cover this exact slot."""
    if not address or not address.zone_id:
        return False

    from apps.bookings.dispatcher import DispatcherService

    return DispatcherService._get_eligible_workers(
        service=service,
        zone=address.zone,
        scheduled_at=scheduled_at,
        duration_minutes=duration_minutes,
        drop_scheduled_at=drop_scheduled_at,
        exclude_customer_id=exclude_customer_id,
        required_gender=required_gender,
    ).exists()


def create_worker_offers_for_booking(booking: Booking) -> list:
    """
    Create worker offers for eligible workers for a given booking.

    Delegates to DispatcherService for the actual dispatch logic.

    Eligibility criteria:
    - Worker profile is approved
    - Worker is online
    - Worker offers the required service
    - Worker is in the same zone as the booking address
    - Worker doesn't have blocking leave for the scheduled time
    - Worker schedule covers the scheduled time

    Uses DispatcherService which supports batch dispatch:
    - Max 5 workers per batch
    - Max 3 batches (15 total offers)
    - 5-minute offer expiry

    Works with PENDING and CONFIRMED booking statuses to support
    auto-dispatch on booking creation.

    Returns list of created WorkerOffer instances.
    """
    from apps.bookings.dispatcher import DispatcherService

    return DispatcherService.dispatch_offers(booking)