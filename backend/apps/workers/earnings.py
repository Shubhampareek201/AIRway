from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.db.models import Q
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.bookings.models import (
    Booking,
    BookingAssignment,
    BookingExtraWork,
    OrderItem,
)
from apps.payments.models import Payment, PaymentRefund
from .models import WorkerEarning, WorkerPayoutSettlement, WorkerProfile


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

    payout_snapshot = booking.worker_payout_snapshot or {}
    fixed_model = payout_snapshot.get("pricing_model") in (
        "fixed_service_payout_v1",
        "admin_approved_quote_payout_v1",
    )
    fixed_payout_raw = payout_snapshot.get("total") if fixed_model else None
    if extra_work is not None:
        if extra_work.worker_payout_amount is not None:
            fixed_model = True
            fixed_payout_raw = extra_work.worker_payout_amount
        elif fixed_model:
            # Do not reuse the base-job payout for a legacy extra-work proposal.
            if existing is not None and not refunds_exist:
                return existing
            fixed_payout_raw = None
    fixed_payout = None
    if fixed_payout_raw not in (None, ""):
        fixed_payout = Decimal(str(fixed_payout_raw))
        if not fixed_payout.is_finite() or fixed_payout < 0:
            fixed_payout = None

    rate = None if fixed_model else (
        existing.commission_rate
        if existing and existing.commission_rate is not None
        else worker.commission_rate
    )
    hold_reason = ""
    if fixed_model and fixed_payout is None:
        hold_reason = (
            "Additional-scope worker payout was not snapshotted."
            if extra_work is not None
            else "Fixed service payout is not configured by AIRway finance."
        )
    elif not fixed_model and rate is None:
        hold_reason = "Commission rate / worker earning rate has not been configured for this legacy booking."
    elif refunds_exist:
        hold_reason = "A refund is pending or has been processed; finance reconciliation is required."

    commission = None
    net = None
    if fixed_payout is not None:
        commission = max(gross_amount - fixed_payout, Decimal("0.00"))
        net = fixed_payout + (existing.adjustment_amount if existing else Decimal("0.00"))
        rate = None
    elif not fixed_model and existing and existing.commission_rate is not None and existing.commission_amount is not None:
        commission = existing.commission_amount
        net = gross_amount - commission + existing.adjustment_amount
    elif not fixed_model and rate is not None:
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
    if state == WorkerEarning.Status.AVAILABLE and (
        existing is None or existing.status != WorkerEarning.Status.AVAILABLE
    ):
        values["available_at"] = timezone.now()
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


def calculate_worker_earning_net(earning):
    """Rebuild a held earning without replacing fixed catalogue payouts with commission math."""
    extra_work = getattr(earning, "extra_work", None)
    if getattr(earning, "extra_work_id", None):
        if extra_work is not None and extra_work.worker_payout_amount is not None:
            payout = Decimal(str(extra_work.worker_payout_amount))
            if not payout.is_finite() or payout < 0:
                return None
            return payout + earning.adjustment_amount
        payout_snapshot = earning.booking.worker_payout_snapshot or {}
        if payout_snapshot.get("pricing_model") in (
            "fixed_service_payout_v1",
            "admin_approved_quote_payout_v1",
        ):
            return None
    else:
        payout_snapshot = earning.booking.worker_payout_snapshot or {}
    if payout_snapshot.get("pricing_model") in (
        "fixed_service_payout_v1",
        "admin_approved_quote_payout_v1",
    ):
        raw_payout = payout_snapshot.get("total")
        if raw_payout in (None, ""):
            return None
        payout = Decimal(str(raw_payout))
        if not payout.is_finite() or payout < 0:
            return None
        return payout + earning.adjustment_amount
    if earning.commission_amount is None:
        return None
    return earning.gross_amount - earning.commission_amount + earning.adjustment_amount


@transaction.atomic
def snapshot_worker_earning_for_assignment(booking, worker):
    """Lock the worker's net service earning when they accept the job."""
    payout_snapshot = booking.worker_payout_snapshot or {}
    fixed_model = payout_snapshot.get("pricing_model") in (
        "fixed_service_payout_v1",
        "admin_approved_quote_payout_v1",
    )
    fixed_payout_raw = payout_snapshot.get("total") if fixed_model else None
    fixed_payout = Decimal(str(fixed_payout_raw)) if fixed_payout_raw not in (None, "") else None
    rate = None if fixed_model else worker.commission_rate
    if (fixed_model and fixed_payout is None) or (not fixed_model and rate is None):
        return None
    order_item = OrderItem.objects.filter(booking=booking).first()
    if order_item is not None:
        gross = Decimal(str(order_item.line_subtotal or "0.00"))
    else:
        snapshot = booking.pricing_snapshot or {}
        gross = Decimal(str(snapshot.get("subtotal", snapshot.get("total", "0.00"))))
    if not gross.is_finite() or gross <= 0:
        return None
    commission = (
        max(gross - fixed_payout, Decimal("0.00"))
        if fixed_payout is not None
        else (gross * rate / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    )
    existing = WorkerEarning.objects.select_for_update().filter(
        booking=booking, extra_work__isnull=True
    ).first()
    if existing and existing.status == WorkerEarning.Status.PAID:
        return existing
    net = (
        fixed_payout if fixed_payout is not None else gross - commission
    ) + (existing.adjustment_amount if existing else Decimal("0.00"))
    if net <= 0:
        return None
    values = {
        "worker": worker,
        "gross_amount": gross,
        "commission_rate": rate,
        "commission_amount": commission,
        "net_amount": net,
        "status": WorkerEarning.Status.PENDING,
        "hold_reason": "Worker earning locked at acceptance; pending service completion and final settlement.",
    }
    if existing:
        for field, value in values.items():
            setattr(existing, field, value)
        existing.save(update_fields=[*values.keys(), "updated_at"])
        return existing
    return WorkerEarning.objects.create(
        booking=booking,
        extra_work=None,
        payment=None,
        **values,
    )



@transaction.atomic
def create_weekly_worker_settlements(earning_ids, created_by=None):
    """Group unassigned available earnings into worker-specific Monday–Sunday batches."""
    ids = sorted({int(value) for value in earning_ids})
    if not ids:
        return []

    candidates = list(
        WorkerEarning.objects.filter(
            pk__in=ids,
            status=WorkerEarning.Status.AVAILABLE,
            settlement_batch__isnull=True,
            net_amount__gt=0,
        )
        .select_related("worker")
        .order_by("worker_id", "created_at", "pk")
    )
    groups = {}
    for earning in candidates:
        settlement_date = timezone.localtime(
            earning.available_at or earning.updated_at or earning.created_at
        ).date()
        period_start = settlement_date - timedelta(days=settlement_date.weekday())
        period_end = period_start + timedelta(days=6)
        key = (earning.worker_id, period_start, period_end)
        groups.setdefault(key, []).append(earning.pk)

    batches = []
    for (worker_id, period_start, period_end), candidate_ids in groups.items():
        # Lock order is worker -> batch -> earnings in both creation and payment paths.
        WorkerProfile.objects.select_for_update().get(pk=worker_id)
        batch = WorkerPayoutSettlement.objects.select_for_update().filter(
            worker_id=worker_id,
            period_start=period_start,
            status=WorkerPayoutSettlement.Status.PENDING,
        ).first()
        rows = list(
            WorkerEarning.objects.select_for_update()
            .filter(
                pk__in=candidate_ids,
                worker_id=worker_id,
                status=WorkerEarning.Status.AVAILABLE,
                settlement_batch__isnull=True,
                net_amount__gt=0,
            )
            .order_by("pk")
        )
        if not rows:
            continue

        if batch is None:
            batch = WorkerPayoutSettlement.objects.create(
                worker_id=worker_id,
                period_start=period_start,
                period_end=period_end,
                total_amount=sum((row.net_amount for row in rows), Decimal("0.00")),
                created_by=created_by,
            )
        for earning in rows:
            earning.settlement_batch = batch
            earning.save(update_fields=["settlement_batch", "updated_at"])

        batch_rows = list(
            WorkerEarning.objects.filter(settlement_batch=batch).values_list("net_amount", flat=True)
        )
        if any(amount is None or amount <= 0 for amount in batch_rows):
            raise ValidationError("A weekly settlement contains an earning without a valid positive payout.")
        batch.total_amount = sum(batch_rows, Decimal("0.00"))
        batch.period_end = max(batch.period_end, period_end)
        batch.save(update_fields=["total_amount", "period_end", "updated_at"])
        batches.append(batch)

    return batches


@transaction.atomic
def mark_worker_payout_settlement_paid(settlement_id, payout_reference, paid_by):
    """Settle every earning in a weekly batch atomically; retries with the same ref are safe."""
    reference = str(payout_reference or "").strip()
    if not reference:
        raise ValidationError("A bank/UPI payout reference is required.")

    worker_id = WorkerPayoutSettlement.objects.filter(
        pk=settlement_id
    ).values_list("worker_id", flat=True).get()
    WorkerProfile.objects.select_for_update().get(pk=worker_id)
    batch = WorkerPayoutSettlement.objects.select_for_update().get(pk=settlement_id)
    if batch.status == WorkerPayoutSettlement.Status.PAID:
        if batch.payout_reference == reference:
            return batch
        raise ValidationError("This weekly settlement was already paid with a different reference.")
    if batch.status != WorkerPayoutSettlement.Status.PENDING:
        raise ValidationError("This weekly settlement cannot be paid from its current status.")

    earnings = list(
        WorkerEarning.objects.select_for_update()
        .filter(settlement_batch=batch)
        .order_by("pk")
    )
    if not earnings:
        raise ValidationError("This weekly settlement has no linked job earnings.")
    if any(
        earning.status != WorkerEarning.Status.AVAILABLE
        or earning.net_amount is None
        or earning.net_amount <= 0
        for earning in earnings
    ):
        raise ValidationError("Every linked job earning must be available with a positive payout.")
    actual_total = sum((earning.net_amount for earning in earnings), Decimal("0.00"))
    if actual_total != batch.total_amount:
        raise ValidationError("The batch total no longer matches its linked worker earnings.")

    paid_at = timezone.now()
    for earning in earnings:
        earning.status = WorkerEarning.Status.PAID
        earning.payout_reference = reference[:120]
        earning.paid_at = paid_at
        earning.paid_by = paid_by
        earning.save(update_fields=[
            "status", "payout_reference", "paid_at", "paid_by", "updated_at",
        ])

    batch.status = WorkerPayoutSettlement.Status.PAID
    batch.payout_reference = reference[:120]
    batch.paid_at = paid_at
    batch.paid_by = paid_by
    batch.save(update_fields=[
        "status", "payout_reference", "paid_at", "paid_by", "updated_at",
    ])
    return batch


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
    """Finalize the locked worker earning after completion and final settlement."""
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
