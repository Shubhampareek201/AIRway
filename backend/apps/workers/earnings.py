import logging
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction

from apps.bookings.models import Booking, BookingAssignment, BookingExtraWork, OrderItem
from apps.payments.models import Payment, PaymentRefund
from .models import WorkerEarning

logger = logging.getLogger(__name__)


@transaction.atomic
def sync_worker_earning(booking_id, payment_id):
    """Create the worker's earning only after service completion and full customer settlement."""
    booking = Booking.objects.select_for_update().filter(pk=booking_id).first()
    payment = Payment.objects.select_for_update().filter(pk=payment_id, status=Payment.Status.PAID).first()
    if booking is None or payment is None or booking.status != Booking.Status.COMPLETED:
        return None

    assignment = BookingAssignment.objects.select_related("worker").filter(booking=booking).first()
    if assignment is None:
        return None
    worker = assignment.worker

    if payment.order_id:
        item = OrderItem.objects.filter(order_id=payment.order_id, booking=booking).first()
        if item is None:
            return None
        if payment.stage == Payment.Stage.BALANCE:
            if booking.appointment_group_id != payment.appointment_group_id:
                return None
        elif payment.stage != Payment.Stage.LEGACY:
            return None
        gross = Decimal(str(item.line_subtotal or "0.00"))
        paid_extra_work = BookingExtraWork.objects.filter(
            booking=booking,
            status=BookingExtraWork.Status.APPROVED,
            payment_status="paid",
        )
        gross += sum(
            paid_extra_work.values_list("total_amount", flat=True),
            Decimal("0.00"),
        )
    elif payment.booking_id == booking.pk and payment.stage == Payment.Stage.LEGACY:
        gross = Decimal(str((booking.pricing_snapshot or {}).get("subtotal", (booking.pricing_snapshot or {}).get("total", "0.00"))))
    else:
        return None

    existing = WorkerEarning.objects.select_for_update().filter(booking=booking).first()
    if existing and existing.status == WorkerEarning.Status.PAID:
        return existing

    # Once a commission rate is snapshotted, retries and later rate changes must not rewrite history.
    rate = (
        existing.commission_rate
        if existing and existing.commission_rate is not None
        else worker.commission_rate
    )
    refunds_exist = PaymentRefund.objects.filter(
        booking=booking,
        status__in=(
            PaymentRefund.Status.PENDING,
            PaymentRefund.Status.PROCESSING,
            PaymentRefund.Status.PROCESSED,
        ),
    ).exists()
    hold_reason = ""
    if rate is None:
        hold_reason = "Commission rate has not been configured by AIRway finance."
    elif refunds_exist:
        hold_reason = "A refund is pending or has been processed; finance reconciliation is required."

    commission = None
    net = None
    state = WorkerEarning.Status.AVAILABLE
    if hold_reason:
        state = WorkerEarning.Status.ON_HOLD
    elif existing and existing.commission_rate is not None:
        commission = existing.commission_amount
        net = existing.net_amount
        state = existing.status if existing.status == WorkerEarning.Status.PAID else WorkerEarning.Status.AVAILABLE
    else:
        commission = (gross * rate / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        net = gross - commission

    values = {
        "worker": worker,
        "payment": payment,
        "gross_amount": gross,
        "commission_rate": rate,
        "commission_amount": commission,
        "net_amount": net,
        "status": state,
        "hold_reason": hold_reason,
    }
    if existing:
        for field, value in values.items():
            setattr(existing, field, value)
        existing.save(update_fields=[*values.keys(), "updated_at"])
        return existing
    return WorkerEarning.objects.create(booking=booking, **values)


def refresh_worker_earnings_for_profile(worker_id):
    """Recalculate held records after Finance configures a worker's commission."""
    rows = WorkerEarning.objects.filter(
        worker_id=worker_id,
        status=WorkerEarning.Status.ON_HOLD,
        payment__isnull=False,
    ).values_list("booking_id", "payment_id")
    for booking_id, payment_id in rows.iterator():
        sync_worker_earning(booking_id, payment_id)
