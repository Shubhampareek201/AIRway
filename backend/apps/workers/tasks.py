import logging

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from apps.notifications.models import Notification

from .models import WorkerLeave, WorkerLeaveHistory

logger = logging.getLogger(__name__)


@shared_task
def expire_past_worker_leave_requests():
    """
    Close pending requests only after their requested period has fully elapsed.
    A request is never auto-approved, and approved leave is never modified here.
    """
    now = timezone.now()
    expired_ids = list(
        WorkerLeave.objects.filter(
            status=WorkerLeave.Status.PENDING,
            end_at__lte=now,
        ).values_list("pk", flat=True)[:500]
    )
    count = 0
    for leave_id in expired_ids:
        with transaction.atomic():
            leave = (
                WorkerLeave.objects.select_for_update()
                .select_related("worker__user")
                .filter(pk=leave_id, status=WorkerLeave.Status.PENDING, end_at__lte=now)
                .first()
            )
            if leave is None:
                continue
            leave.status = WorkerLeave.Status.CANCELLED
            leave.admin_note = "Automatically closed because the requested leave period ended before review."
            leave.save(update_fields=["status", "admin_note", "updated_at"])
            WorkerLeaveHistory.objects.create(
                leave=leave,
                from_status=WorkerLeave.Status.PENDING,
                to_status=WorkerLeave.Status.CANCELLED,
                changed_by=None,
                note=leave.admin_note,
            )
            Notification.objects.create(
                user=leave.worker.user,
                type=Notification.Type.WORKER_LEAVE_REJECTED,
                title="Leave request expired",
                body="Your leave request was closed because its requested period ended before Admin review.",
                channel=Notification.Channel.IN_APP,
                data={"worker_leave_id": leave.pk, "status": WorkerLeave.Status.CANCELLED, "reason": "expired_before_review"},
            )
            count += 1
    if count:
        logger.info("Expired %s past worker leave requests", count)
    return count
