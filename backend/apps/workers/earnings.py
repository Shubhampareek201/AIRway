from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Q

from apps.bookings.models import (
    Booking,
    BookingAssignment,
    BookingExtraWork,
    OrderItem,
)
from apps.payments.models import Payment, PaymentRefund
from .models import WorkerEarning


REFUND_HOLD_STATUSES = (
    PaymentRefund.Status.PENDING,
    PaymentRefund.Status.PROCESSING,
    PaymentRefund.Status.PROCESSED,
)


def _upsert_worker_earning(booking, worker, payment, gross_amount, extra_work=None):
    existing_query = WorkerEarning.objects.select_for_update().filter(
        booking=booking,
        extra_work=extra_work,
    )
    existing = existing_query.first()
    if existing and existing.status == WorkerEarning.Status.PAID:
        return existing

    refunds = PaymentRefund.objects.filter(
        booking=booking,
        status__in=REFUND_HOLD_STATUSES,
    )
    refunds = (
        refunds.filter(Q(extra_work=extra_work) | Q(extra_work__isnull=True))
        if extra_work
        else refunds.filter(extra_work__isnull=True)
    )
    refunds_exist = refunds.exists()

    rate = (
        existing.commission_rate
        if existing and existing.commission_rate is not None
        else worker.commission_rate
    )
    hold_reason = ""
    if rate is None:
        hold_reason = "Commission rate has not been configured by AIRway finance."
    elif refunds_exist:
        hold_reason = "A refund is pending or has been processed; finance reconciliation is required."

    commission = None
    net = None
    if (
        existing
        and existing.commission_rate is not None
        and existing.commission_amount is not None
    ):
        commission = existing.commission_amount
        net = gross_amount - commission + existing.adjustment_amount
    elif rate is not None:
        commission = (gross_amount * rate / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        net = gross_amount - commission + (
            existing.adjustment_amount if existing else Decimal("0.00")
        )

    state = (
        WorkerEarning.Status.ON_HOLD
        if hold_reason
        else WorkerEarning.Status.AVAILABLE
    )
    values = {
        "worker": worker,
        "payment": payment,
        "gross_amount": gross_amount,
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
    return WorkerEarning.objects.create(
        booking=booking,
        extra_work=extra_work,
        **values,
    )


def _get_paid_base_payment(booking):
    order_item = OrderItem.objects.filter(booking=booking).select_related("order").first()
    if order_item:
        group_filter = {"appointment_group_id": booking.appointment_group_id}
        balance = Payment.objects.filter(
            order=order_item.order,
            stage=Payment.Stage.BALANCE,
            status=Payment.Status.PAID,
            **group_filter,
        ).order_by("-paid_at", "-pk").first()
        if balance:
            return balance, order_item
        legacy = Payment.objects.filter(
            order=order_item.order,
            stage=Payment.Stage.LEGACY,
            appointment_group__isnull=True,
            status=Payment.Status.PAID,
        ).order_by("-paid_at", "-pk").first()
        return (legacy, order_item) if legacy else (None, order_item)

    legacy = Payment.objects.filter(
        booking=booking,
        stage=Payment.Stage.LEGACY,
        status=Payment.Status.PAID,
    ).first()
    return legacy, None


@transaction.atomic
def sync_worker_earning(booking_id, payment_id):
    """Create service and extra-work earnings only after completion and final settlement."""
    booking = Booking.objects.select_for_update().filter(pk=booking_id).first()
    payment = Payment.objects.select_for_update().filter(
        pk=payment_id,
        status=Payment.Status.PAID,
    ).first()
    if booking is None or payment is None or booking.status != Booking.Status.COMPLETED:
        return None

    assignment = BookingAssignment.objects.select_related("worker").filter(
        booking=booking
    ).first()
    if assignment is None:
        return None
    worker = assignment.worker

    base_payment, order_item = _get_paid_base_payment(booking)
    if base_payment is None:
        return None

    if payment.stage == Payment.Stage.EXTRA_WORK:
        if not payment.extra_work_id or payment.extra_work.booking_id != booking.pk:
            return None
        target_payment = payment
        target_extra_work = payment.extra_work
        if (
            target_extra_work.status != BookingExtraWork.Status.APPROVED
            or target_extra_work.payment_status != "paid"
        ):
            return None
        return _upsert_worker_earning(
            booking,
            worker,
            target_payment,
            Decimal(str(target_extra_work.subtotal)),
            extra_work=target_extra_work,
        )

    if payment.pk != base_payment.pk:
        # The settlement webhook may be retried with an older paid stage.
        # Always use the current final base payment as the service earning source.
        if payment.stage not in (Payment.Stage.BALANCE, Payment.Stage.LEGACY):
            return None
        payment = base_payment

    if order_item is not None:
        if payment.order_id != order_item.order_id:
            return None
        if payment.stage == Payment.Stage.BALANCE and (
            booking.appointment_group_id != payment.appointment_group_id
        ):
            return None
        gross = Decimal(str(order_item.line_subtotal or "0.00"))
    else:
        snapshot = booking.pricing_snapshot or {}
        gross = Decimal(str(snapshot.get("subtotal", snapshot.get("total", "0.00"))))

    service_earning = _upsert_worker_earning(
        booking,
        worker,
        payment,
        gross,
        extra_work=None,
    )

    paid_extra_work = BookingExtraWork.objects.filter(
        booking=booking,
        status=BookingExtraWork.Status.APPROVED,
        payment_status="paid",
    ).order_by("created_at", "pk")
    for proposal in paid_extra_work:
        separate_payment = Payment.objects.filter(
            extra_work=proposal,
            status=Payment.Status.PAID,
        ).first()
        earning_payment = separate_payment or payment
        _upsert_worker_earning(
            booking,
            worker,
            earning_payment,
            Decimal(str(proposal.subtotal)),
            extra_work=proposal,
        )

    return service_earning



@transaction.atomic
def sync_rework_worker_earning(booking_id):
    """Record AIRway-funded worker compensation for a completed no-charge recovery visit."""
    booking = Booking.objects.select_for_update(of=("self",)).select_related(
        "rework_source__dispute__booking"
    ).filter(pk=booking_id, status=Booking.Status.COMPLETED).first()
    if booking is None:
        return None
    proposal = getattr(booking, "rework_source", None)
    if proposal is None or proposal.status != "accepted":
        return None
    assignment = BookingAssignment.objects.select_related("worker").filter(
        booking=booking
    ).first()
    if assignment is None:
        return None
    original = proposal.dispute.booking
    original_item = OrderItem.objects.filter(booking=original).first()
    if original_item is not None:
        gross = Decimal(str(original_item.line_subtotal or "0.00"))
    else:
        snapshot = original.pricing_snapshot or {}
        gross = Decimal(str(snapshot.get("subtotal", snapshot.get("total", "0.00"))))
    if not gross.is_finite() or gross <= 0:
        return None
    return _upsert_worker_earning(
        booking,
        assignment.worker,
        None,
        gross,
        extra_work=None,
    )


def refresh_worker_earnings_for_profile(worker_id):
    """Recalculate held records after Finance configures a worker's commission."""
    rows = WorkerEarning.objects.filter(
        worker_id=worker_id,
        status=WorkerEarning.Status.ON_HOLD,
        payment__isnull=False,
    ).values_list("booking_id", "payment_id")
    for booking_id, payment_id in rows.iterator():
        sync_worker_earning(booking_id, payment_id)
    recovery_rows = WorkerEarning.objects.filter(
        worker_id=worker_id,
        status=WorkerEarning.Status.ON_HOLD,
        payment__isnull=True,
        booking__rework_source__isnull=False,
    ).values_list("booking_id", flat=True)
    for booking_id in recovery_rows.iterator():
        sync_rework_worker_earning(booking_id)
