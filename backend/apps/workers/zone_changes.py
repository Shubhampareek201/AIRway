from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import WorkerZone, WorkerZoneChangeRequest


@transaction.atomic
def review_worker_zone_change(*, request_id, reviewer, decision, note=""):
    if decision not in (WorkerZoneChangeRequest.Status.APPROVED, WorkerZoneChangeRequest.Status.REJECTED):
        raise ValidationError("Invalid zone-change decision.")
    change = WorkerZoneChangeRequest.objects.select_for_update().select_related("worker", "zone").get(pk=request_id)
    if change.status != WorkerZoneChangeRequest.Status.PENDING:
        raise ValidationError("This zone request has already been reviewed.")
    note = (note or "").strip()
    if decision == WorkerZoneChangeRequest.Status.REJECTED and not note:
        raise ValidationError("A reason is required when rejecting a worker zone request.")

    worker = change.worker.__class__.objects.select_for_update().get(pk=change.worker_id)
    if decision == WorkerZoneChangeRequest.Status.APPROVED:
        if worker.status != worker.Status.APPROVED:
            raise ValidationError("Only approved workers can change service zones.")
        if not change.zone.is_active:
            raise ValidationError("This zone is inactive and cannot be assigned.")
        if change.action == WorkerZoneChangeRequest.Action.ADD:
            WorkerZone.objects.get_or_create(worker=worker, zone=change.zone)
        else:
            WorkerZone.objects.filter(worker=worker, zone=change.zone).delete()

    change.status = decision
    change.admin_note = note
    change.reviewed_by = reviewer
    change.reviewed_at = timezone.now()
    change.save(update_fields=["status", "admin_note", "reviewed_by", "reviewed_at", "updated_at"])

    from apps.notifications.models import Notification
    approved = decision == WorkerZoneChangeRequest.Status.APPROVED
    action_label = "added to" if change.action == WorkerZoneChangeRequest.Action.ADD else "removed from"
    Notification.objects.create(
        user=worker.user,
        type=(Notification.Type.WORKER_ZONE_APPROVED if approved else Notification.Type.WORKER_ZONE_REJECTED),
        title=("Service zone request approved" if approved else "Service zone request declined"),
        body=(
            f"Your request to be {action_label} {change.zone.name} has been approved."
            if approved else
            f"Your request to be {action_label} {change.zone.name} was declined. {note}"
        ).strip(),
        data={
            "worker_zone_request_id": change.pk,
            "zone_id": change.zone_id,
            "action": change.action,
            "status": change.status,
        },
    )
    return change
