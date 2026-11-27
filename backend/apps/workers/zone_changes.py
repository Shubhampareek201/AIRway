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
    return change
