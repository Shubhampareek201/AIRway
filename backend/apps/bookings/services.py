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

    # Address stores its service city through Address.zone.city.
    if address and address.zone_id:
        from apps.catalog.models import CityService
        city = address.zone.city
        if not city.is_active or not CityService.objects.filter(
            city=city, service=service, is_active=True
        ).exists():
            raise ServiceUnavailableError(
                f"Service '{service.title}' is not available in {city.name}."
            )

    return True


def get_available_slots(
    service: Service,
    date,
    count: int = 5,
) -> list:
    """
    Get available time slots for a given date.
    Returns list of available hour slots (e.g., [10, 11, 12, 13, 14]).
    """
    from django.db.models import Q
    from datetime import time

    # Get existing bookings for the date
    start_of_day = timezone.make_aware(
        timezone.datetime.combine(date, time(0, 0))
    )
    end_of_day = start_of_day + timedelta(days=1)

    existing_bookings = Booking.objects.filter(
        service=service,
        scheduled_at__gte=start_of_day,
        scheduled_at__lt=end_of_day,
        status__in=[Booking.Status.PENDING, Booking.Status.CONFIRMED, Booking.Status.ASSIGNED, Booking.Status.IN_PROGRESS]
    ).values_list('scheduled_at', flat=True)

    # Define standard slots (10:00 - 21:00)
    slots = []
    available_slots = []

    for hour in range(10, 22):
        slot_time = start_of_day.replace(hour=hour)

        # Check if this slot conflicts
        slot_end = slot_time + timedelta(minutes=service.duration_minutes or 60) + timedelta(minutes=service.buffer_minutes)

        conflicts = False
        for booking_time in existing_bookings:
            booking_end = booking_time + timedelta(minutes=service.duration_minutes or 60) + timedelta(minutes=service.buffer_minutes)
            if slot_time < booking_end and booking_time < slot_end:
                conflicts = True
                break

        if not conflicts:
            available_slots.append(hour)

    return available_slots[:count]


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