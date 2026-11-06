"""
Shared worker eligibility filters used by the catalogue and booking dispatcher.

This module deliberately contains only the stable, location-independent
eligibility gates. Booking-time checks (weekday hours, leave, blocked slots,
and overlapping assignments) remain in the dispatcher.
"""
from apps.workers.models import WorkerProfile


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
