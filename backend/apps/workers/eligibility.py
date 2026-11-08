"""
Shared worker eligibility filters used by the catalogue and booking dispatcher.

This module deliberately contains only the stable, location-independent
eligibility gates. Booking-time checks (weekday hours, leave, blocked slots,
and overlapping assignments) remain in the dispatcher.
"""
from apps.workers.models import WorkerProfile


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


def eligible_workers_for_service(service, *, zone=None, city=None):
    """Return the shared eligible worker pool for one active service."""
    if not service.is_active or not service.category.is_active:
        return WorkerProfile.objects.none()

    return eligible_worker_profiles(
        city=city,
        zone=zone,
    ).filter(
        worker_services__service=service,
    ).distinct().select_related("user")
