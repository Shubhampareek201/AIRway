from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.bookings.models import Booking, BookingAssignment
from apps.notifications.models import Notification

from .models import WorkerLeave, WorkerLeaveHistory, WorkerProfile


ACTIVE_BOOKING_STATUSES = (
    Booking.Status.CONFIRMED,
    Booking.Status.ASSIGNED,
    Booking.Status.IN_PROGRESS,
)


def _notify(user, kind, title, body, data):
    Notification.objects.create(
        user=user, type=kind, title=title, body=body,
        channel=Notification.Channel.IN_APP, data=data,
    )


def request_worker_leave(*, worker, start_at, end_at, reason=""):
    now = timezone.now()
    if start_at <= now:
        raise ValidationError({"start_at": "Leave must start in the future."})
    if end_at <= start_at:
        raise ValidationError({"end_at": "End time must be after start time."})
    if (end_at - start_at).total_seconds() > 60 * 60 * 24 * 90:
        raise ValidationError({"end_at": "A leave request cannot exceed 90 days."})

    with transaction.atomic():
        locked_worker = WorkerProfile.objects.select_for_update().get(pk=worker.pk)
        overlap = WorkerLeave.objects.filter(
            worker=locked_worker,
            status__in=(WorkerLeave.Status.PENDING, WorkerLeave.Status.APPROVED),
            start_at__lt=end_at,
            end_at__gt=start_at,
        ).exists()
        if overlap:
            raise ValidationError({"start_at": "This period overlaps an existing pending or approved leave request."})

        leave = WorkerLeave.objects.create(
            worker=locked_worker, start_at=start_at, end_at=end_at,
            reason=reason.strip(), status=WorkerLeave.Status.PENDING,
        )
        WorkerLeaveHistory.objects.create(
            leave=leave, from_status="", to_status=WorkerLeave.Status.PENDING,
            changed_by=worker.user, note="Leave requested by worker.",
        )
        staff_users = WorkerProfile._meta.get_field("user").remote_field.model.objects.filter(
            is_staff=True, is_active=True,
        )
        for user in staff_users.iterator():
            _notify(
                user, Notification.Type.WORKER_LEAVE_REQUEST,
                "Worker leave request",
                f"{locked_worker.user.name or locked_worker.user.phone} requested leave from {start_at:%d %b %Y %H:%M} to {end_at:%d %b %Y %H:%M}.",
                {"worker_leave_id": leave.pk, "worker_id": locked_worker.pk},
            )
        return leave


def _assigned_booking_conflicts(worker, start_at, end_at):
    from apps.bookings.dispatcher import DispatcherService

    # Lock only assignment rows. Joining nullable booking relations into
    # SELECT FOR UPDATE makes PostgreSQL reject the query unless the lock
    # target is explicitly limited to the non-nullable base table.
    assignments = BookingAssignment.objects.select_for_update(of=("self",)).filter(
        worker=worker, booking__status__in=ACTIVE_BOOKING_STATUSES,
    ).select_related("booking__service", "booking__variant", "booking__appointment_group")
    conflicts = []
    for assignment in assignments:
        booking = assignment.booking
        intervals = DispatcherService._assigned_booking_intervals(booking)
        if any(left < end_at and right > start_at for left, right in intervals):
            conflicts.append(booking.pk)
    return conflicts


def review_worker_leave(*, leave_id, reviewer, decision, note=""):
    if decision not in (WorkerLeave.Status.APPROVED, WorkerLeave.Status.REJECTED):
        raise ValidationError({"decision": "Choose approve or reject."})
    with transaction.atomic():
        leave = WorkerLeave.objects.select_for_update().select_related("worker__user").get(pk=leave_id)
        worker = WorkerProfile.objects.select_for_update().get(pk=leave.worker_id)
        if leave.status != WorkerLeave.Status.PENDING:
            raise ValidationError({"detail": "Only pending leave requests can be reviewed."})
        if decision == WorkerLeave.Status.APPROVED:
            if leave.end_at <= timezone.now():
                raise ValidationError({"detail": "Expired leave requests cannot be approved."})
            overlaps = WorkerLeave.objects.filter(
                worker=worker, status=WorkerLeave.Status.APPROVED,
                start_at__lt=leave.end_at, end_at__gt=leave.start_at,
            ).exclude(pk=leave.pk).exists()
            if overlaps:
                raise ValidationError({"detail": "This request overlaps another approved leave."})
            conflicts = _assigned_booking_conflicts(worker, leave.start_at, leave.end_at)
            if conflicts:
                raise ValidationError({
                    "detail": "Approval blocked: the worker has active assigned appointments in this period.",
                    "conflicting_booking_ids": conflicts,
                    "next_step": "Resolve or safely reassign the complete affected appointment groups before approving this leave.",
                })
        old_status = leave.status
        leave.status = decision
        leave.reviewed_by = reviewer
        leave.reviewed_at = timezone.now()
        leave.admin_note = note.strip()
        leave.save(update_fields=["status", "reviewed_by", "reviewed_at", "admin_note", "updated_at"])
        WorkerLeaveHistory.objects.create(
            leave=leave, from_status=old_status, to_status=decision,
            changed_by=reviewer, note=note.strip(),
        )
        approved = decision == WorkerLeave.Status.APPROVED
        _notify(
            worker.user,
            Notification.Type.WORKER_LEAVE_APPROVED if approved else Notification.Type.WORKER_LEAVE_REJECTED,
            "Leave request approved" if approved else "Leave request declined",
            note.strip() or ("Your leave request has been approved." if approved else "Your leave request was not approved."),
            {"worker_leave_id": leave.pk, "status": decision},
        )
        return leave


def cancel_worker_leave(*, leave, worker):
    with transaction.atomic():
        locked = WorkerLeave.objects.select_for_update().get(pk=leave.pk, worker=worker)
        if locked.status == WorkerLeave.Status.PENDING:
            pass
        elif locked.status == WorkerLeave.Status.APPROVED and locked.start_at > timezone.now():
            pass
        else:
            raise ValidationError({"detail": "Only pending or future approved leave can be cancelled."})
        old_status = locked.status
        locked.status = WorkerLeave.Status.CANCELLED
        locked.save(update_fields=["status", "updated_at"])
        WorkerLeaveHistory.objects.create(
            leave=locked, from_status=old_status,
            to_status=WorkerLeave.Status.CANCELLED, changed_by=worker.user,
            note="Cancelled by worker.",
        )
        staff_users = WorkerProfile._meta.get_field("user").remote_field.model.objects.filter(
            is_staff=True, is_active=True,
        )
        for user in staff_users.iterator():
            _notify(
                user, Notification.Type.WORKER_LEAVE_REQUEST,
                "Worker leave request cancelled",
                f"{worker.user.name or worker.user.phone} cancelled leave request #{locked.pk}.",
                {"worker_leave_id": locked.pk, "worker_id": worker.pk, "status": WorkerLeave.Status.CANCELLED},
            )
        return locked
