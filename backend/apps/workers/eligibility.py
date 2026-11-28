"""
Shared worker eligibility filters used by the catalogue and booking dispatcher.

This module deliberately contains only the stable, location-independent
eligibility gates. Booking-time checks (weekday hours, leave, blocked slots,
and overlapping assignments) remain in the dispatcher.
"""
import re

from apps.workers.models import WorkerProfile



_CONTACT_PHONE_RE = re.compile(r"(?<!\d)(?:\+?91[\s.-]?)?[6-9]\d{4}[\s.-]?\d{5}(?!\d)")
_CONTACT_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)


def mask_personal_contact_details(value):
    """Mask phone numbers and email addresses embedded in customer-provided text."""
    if isinstance(value, str):
        value = _CONTACT_EMAIL_RE.sub("[contact hidden]", value)
        return _CONTACT_PHONE_RE.sub("[contact hidden]", value)
    if isinstance(value, dict):
        return {key: mask_personal_contact_details(item) for key, item in value.items()}
    if isinstance(value, list):
        return [mask_personal_contact_details(item) for item in value]
    if isinstance(value, tuple):
        return tuple(mask_personal_contact_details(item) for item in value)
    return value

def required_worker_gender_for_booking(service, category_answers=None):
    """Resolve the required worker gender from service policy and customer choice.

    The customer preference is optional and currently supported only for the
    Beauty launch category. A service-level female-worker requirement always
    takes precedence over a customer's 'any professional' preference.
    """
    answers = category_answers if isinstance(category_answers, dict) else {}
    preference = answers.get("professional_preference", "any")
    if preference not in ("any", "female"):
        raise ValueError("Choose a valid professional preference.")

    category = service.category
    while category.parent_id:
        category = category.parent

    is_beauty = (
        "beauty" in (category.slug or "").lower()
        or "beauty" in (category.title or "").lower()
    )
    if preference == "female" and not is_beauty:
        raise ValueError("Female professional preference is only available for Beauty services.")

    if service.requires_female_worker or preference == "female":
        return WorkerProfile.Gender.FEMALE
    return None


def eligible_worker_profiles(*, city=None, zone=None):
    """
    Base pool of workers who can currently serve at least one configured
    service in the requested area.

    A worker must be approved, online, linked to an active service and an
    active zone in an active city, and have at least one active schedule.
    """
    queryset = WorkerProfile.objects.filter(
        status=WorkerProfile.Status.APPROVED,
        is_online=True,
        worker_services__service__is_active=True,
        worker_services__service__category__is_active=True,
        worker_zones__zone__is_active=True,
        worker_zones__zone__city__is_active=True,
        schedules__is_active=True,
    )

    if city is not None:
        queryset = queryset.filter(worker_zones__zone__city=city)
    if zone is not None:
        queryset = queryset.filter(worker_zones__zone=zone)

    return queryset.distinct()


def eligible_workers_for_service(service, *, zone=None, city=None, required_tasks=None):
    """Return the shared eligible worker pool for one active service."""
    if not service.is_active or not service.category.is_active:
        return WorkerProfile.objects.none()

    queryset = eligible_worker_profiles(city=city, zone=zone).filter(
        worker_services__service=service,
    )
    required = [str(task).strip() for task in (required_tasks or []) if str(task).strip()]
    if required:
        # Task-specific packages require an explicit, admin-verified skill claim.
        queryset = queryset.filter(
            worker_services__service=service,
            worker_services__capabilities_verified=True,
            worker_services__capabilities__contains=required,
        )
    # Backward compatibility: approved workers enrolled before capability
    # capture may still receive task-neutral service variants. Empty task lists
    # never qualify for a variant that declares required tasks.
    return queryset.distinct().select_related("user")


def worker_contact_access(assignment, *, at=None):
    """Return the server-enforced privacy window for an assigned worker.

    Exact address is available only after the worker accepts the assignment.
    Customer phone access additionally opens one hour before the current
    scheduled start. Re-reading the booking time on every request makes
    reschedules and timezone-aware datetimes apply immediately.
    """
    from datetime import timedelta
    from django.utils import timezone
    from apps.bookings.models import Booking

    booking = assignment.booking
    now = at or timezone.now()
    accepted = bool(assignment.accepted_at)
    active = booking.status in (Booking.Status.ASSIGNED, Booking.Status.IN_PROGRESS)
    worker_approved = assignment.worker.status == WorkerProfile.Status.APPROVED
    contact_available_at = (
        booking.scheduled_at - timedelta(hours=1)
        if accepted and active and worker_approved and booking.scheduled_at else None
    )
    address_available = accepted and active and worker_approved
    phone_available = bool(
        address_available
        and contact_available_at
        and now >= contact_available_at
    )
    return {
        "address_available": address_available,
        "contact_available_at": contact_available_at,
        "phone_available": phone_available,
    }
