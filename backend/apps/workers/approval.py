from django.db import transaction
from django.utils import timezone

from apps.accounts.models import UserRole
from .models import WorkerDocument, WorkerProfile


APPROVAL_REQUIREMENTS = {
    "has_verified_id": "Verified ID (Aadhaar or other ID)",
    "has_verified_photo": "Verified profile photograph",
    "has_service": "At least one active service in an active category",
    "has_zone": "At least one active zone in an active city",
    "has_schedule": "At least one active working schedule",
}


def get_approval_requirements(worker):
    """Return authoritative approval checks using fresh database queries."""
    checks = {
        "has_verified_id": worker.documents.filter(
            doc_type__in=[
                WorkerDocument.DocumentType.AADHAAR,
                WorkerDocument.DocumentType.ID,
            ],
            status=WorkerDocument.Status.VERIFIED,
        ).exists(),
        "has_verified_photo": worker.documents.filter(
            doc_type=WorkerDocument.DocumentType.PHOTO,
            status=WorkerDocument.Status.VERIFIED,
        ).exists(),
        "has_service": worker.worker_services.filter(
            service__is_active=True,
            service__category__is_active=True,
        ).exists(),
        "has_zone": worker.worker_zones.filter(
            zone__is_active=True,
            zone__city__is_active=True,
        ).exists(),
        "has_schedule": worker.schedules.filter(is_active=True).exists(),
    }
    missing = [
        label
        for key, label in APPROVAL_REQUIREMENTS.items()
        if not checks[key]
    ]
    return {
        **checks,
        "eligible": not missing,
        "missing": missing,
    }


def approve_worker(worker_id, approved_by):
    """Approve a pending worker and create the worker role atomically."""
    with transaction.atomic():
        try:
            worker = (
                WorkerProfile.objects
                .select_for_update()
                .select_related("user")
                .get(pk=worker_id)
            )
        except WorkerProfile.DoesNotExist:
            return {
                "status": "not_found",
                "worker": None,
                "requirements": None,
            }

        if worker.status != WorkerProfile.Status.PENDING:
            return {
                "status": "already_processed",
                "worker": worker,
                "requirements": get_approval_requirements(worker),
            }

        requirements = get_approval_requirements(worker)
        if not requirements["eligible"]:
            return {
                "status": "ineligible",
                "worker": worker,
                "requirements": requirements,
            }

        worker.status = WorkerProfile.Status.APPROVED
        worker.approved_by = approved_by
        worker.approved_at = timezone.now()
        worker.rejection_reason = ""
        # Approval must never silently put a worker online.
        worker.is_online = False
        worker.save(update_fields=[
            "status",
            "approved_by",
            "approved_at",
            "rejection_reason",
            "is_online",
            "updated_at",
        ])

        UserRole.objects.get_or_create(
            user=worker.user,
            role=UserRole.Role.WORKER,
        )

        return {
            "status": "approved",
            "worker": worker,
            "requirements": requirements,
        }
