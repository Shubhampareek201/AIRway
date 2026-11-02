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


def check_slot_availability(
    service: Service,
    scheduled_at: timezone.datetime,
    duration_minutes: int,
    booking_mode: str,
    drop_scheduled_at: timezone.datetime = None,
    exclude_booking_id: int = None,
) -> bool:
    """
    Check if a slot is available for booking.

    Returns True if available, raises SlotConflictError if not.
    Uses database query to check for overlapping confirmed/pending bookings.
    """
    buffer = timedelta(minutes=service.buffer_minutes)
    end_at = scheduled_at + timedelta(minutes=duration_minutes) + buffer

    # Check for overlapping bookings
    overlapping = Booking.objects.filter(
        service=service,
        status__in=[Booking.Status.PENDING, Booking.Status.CONFIRMED, Booking.Status.ASSIGNED, Booking.Status.IN_PROGRESS]
    ).exists()

    # For proper overlap detection, check:
    # A booking [start1, end1] overlaps with [start2, end2] if:
    # start1 < end2 AND start2 < end1
    from django.db.models import Q

    queryset = Booking.objects.filter(
        service=service,
        status__in=[Booking.Status.PENDING, Booking.Status.CONFIRMED, Booking.Status.ASSIGNED, Booking.Status.IN_PROGRESS]
    )

    # Check pickup slot overlap
    if queryset.filter(
        Q(scheduled_at__lt=end_at) &
        (Q(scheduled_at__gt=scheduled_at - buffer) | Q(scheduled_at__gte=scheduled_at))
    ).exclude(pk=exclude_booking_id).exists():
        raise SlotConflictError("Slot is already booked. Please choose another time.")

    # For pickup-drop mode, check drop slot overlap
    if booking_mode == 'pickup_drop' and drop_scheduled_at and drop_scheduled_at > scheduled_at:
        drop_duration = duration_minutes or service.duration_minutes or 60
        drop_end = drop_scheduled_at + timedelta(minutes=drop_duration) + buffer

        if queryset.filter(
            Q(drop_scheduled_at__lt=drop_end) &
            (Q(drop_scheduled_at__gt=drop_scheduled_at - buffer) | Q(drop_scheduled_at__gte=drop_scheduled_at))
        ).exclude(pk=exclude_booking_id).exists():
            raise SlotConflictError("Drop slot conflicts with existing booking.")

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

    # Check if service is available in user's city (when address is provided)
    # This requires CityService model to be linked to address
    if address and hasattr(address, 'city') and address.city:
        from apps.catalog.models import CityService
        if not CityService.objects.filter(city=address.city, service=service, is_active=True).exists():
            raise ServiceUnavailableError(
                f"Service '{service.title}' is not available in your area."
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