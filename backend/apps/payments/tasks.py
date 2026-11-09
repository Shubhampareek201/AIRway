""""Celery tasks for payment processing and provider reconciliation."""
import logging

from celery import shared_task
from .installment_service import reconcile_refund_record
from .models import RefundRecord

logger = logging.getLogger(__name__)


@shared_task
def reconcile_unresolved_refunds(batch_size=100):
    """Reconcile unresolved provider refunds without submitting new refunds.

    Safe to invoke manually or from an approved Celery Beat schedule. The
    provider lookup is read-only; unmatched records remain pending for dashboard
    review rather than being blindly resubmitted.
    """
    record_ids = list(
        RefundRecord.objects.filter(
            status__in=(RefundRecord.Status.REQUESTED, RefundRecord.Status.PENDING, RefundRecord.Status.FAILED),
            gateway_refund_amount__gt=0,
        ).order_by("requested_at", "pk").values_list("pk", flat=True)[:batch_size]
    )
    summary = {"checked": 0, "matched": 0, "unresolved": 0, "errors": 0}
    for record_id in record_ids:
        try:
            record = reconcile_refund_record(record_id=record_id)
            summary["checked"] += 1
            if record.status == RefundRecord.Status.PROCESSED:
                summary["matched"] += 1
            else:
                summary["unresolved"] += 1
        except Exception:
            summary["errors"] += 1
            logger.exception("Refund reconciliation failed for record %s", record_id)
    return summary
