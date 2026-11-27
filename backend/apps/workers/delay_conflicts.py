"""Customer alerts when a late job is likely to overlap a worker's next booking."""

from django.db.models import Q
from django.utils import timezone

from apps.bookings.models import Booking, BookingAssignment
from apps.notifications.models import Notification


ACTIVE_BOOKING_STATUSES = (
    Booking.Status.ASSIGNED,
    Booking.Status.CONFIRMED,
    Booking.Status.IN_PROGRESS,
)


def notify_upcoming_booking_conflicts(*, worker, current_booking, now=None):
    """Notify affected customers without cancelling or changing any booking.

    The current appointment's planned occupied interval already includes its
    service duration and configured buffers. Starting late shifts its expected
    finish by the observed delay; appointments in the same group are counted
    only once.
    """
    now = now or timezone.now()
    from apps.bookings.dispatcher import DispatcherService

    current_intervals = DispatcherService._assigned_booking_intervals(current_booking)
    if not current_intervals:
        return 0
    planned_start = min(start for start, _ in current_intervals)
    planned_end = max(end for _, end in current_intervals)
    delay = now - planned_start
    if delay.total_seconds() <= 0:
        return 0
    expected_finish = planned_end + delay

    assignments = BookingAssignment.objects.filter(
        worker=worker,
        accepted_at__isnull=False,
        booking__status__in=ACTIVE_BOOKING_STATUSES,
        booking__scheduled_at__gt=planned_start,
    ).select_related("booking", "booking__customer", "booking__appointment_group")

    current_group_id = current_booking.appointment_group_id
    current_ids = {current_booking.pk}
    if current_group_id:
        current_ids.update(
            Booking.objects.filter(appointment_group_id=current_group_id)
            .values_list("pk", flat=True)
        )

    affected = {}
    for assignment in assignments:
        upcoming = assignment.booking
        if upcoming.pk in current_ids:
            continue
        if upcoming.appointment_group_id and upcoming.appointment_group_id == current_group_id:
            continue
        intervals = DispatcherService._assigned_booking_intervals(upcoming)
        if not intervals:
            continue
        next_start = min(start for start, _ in intervals)
        if next_start >= expected_finish:
            continue
        group_key = upcoming.appointment_group_id or f"booking-{upcoming.pk}"
        affected.setdefault(group_key, upcoming)

    created = 0
    delay_minutes = max(1, int(delay.total_seconds() // 60))
    for upcoming in affected.values():
        group_key = upcoming.appointment_group_id or f"booking-{upcoming.pk}"
        conflict_key = f"worker-delay:{worker.pk}:{current_group_id or current_booking.pk}:{group_key}"
        if Notification.objects.filter(
            user=upcoming.customer,
            type=Notification.Type.SYSTEM_ANNOUNCEMENT,
            data__delay_conflict_key=conflict_key,
        ).exists():
            continue
        Notification.objects.create(
            user=upcoming.customer,
            type=Notification.Type.SYSTEM_ANNOUNCEMENT,
            title="Your appointment may be delayed",
            body=(
                "Your professional's previous appointment started later than scheduled. "
                "Your booking may be affected; AIRway will keep your appointment active "
                "and share any confirmed update."
            ),
            channel=Notification.Channel.IN_APP,
            data={
                "delay_conflict_key": conflict_key,
                "booking_id": upcoming.pk,
                "appointment_group_id": upcoming.appointment_group_id,
                "previous_booking_id": current_booking.pk,
                "previous_appointment_group_id": current_group_id,
                "worker_id": worker.pk,
                "estimated_delay_minutes": delay_minutes,
                "conflict_type": "late_previous_job",
            },
        )
        created += 1
    return created
