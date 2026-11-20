import logging
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import razorpay
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.bookings.models import Booking, OrderItem
from apps.notifications.models import Notification
from apps.wallet.models import Wallet, WalletTransaction
from .models import Payment, PaymentRefund

logger = logging.getLogger(__name__)
CENT = Decimal("0.01")


def _line_stage_amount(payment, booking):
    """Return the immutable per-service captured split for this payment."""
    if payment.extra_work_id and payment.extra_work.booking_id == booking.id:
        return (
            payment.extra_work.total_amount,
            payment.wallet_amount,
            payment.amount,
            None,
        )
    rows = (payment.raw_response or {}).get("service_allocation_v1", [])
    matching_rows = [
        entry for entry in rows
        if entry.get("booking_id") == booking.id
    ]
    if matching_rows:
        item_id = next(
            (entry.get("order_item_id") for entry in matching_rows if entry.get("order_item_id")),
            None,
        )
        item = OrderItem.objects.filter(pk=item_id).first() if item_id else None
        return (
            sum((Decimal(str(entry.get("total", "0"))) for entry in matching_rows), Decimal("0.00")),
            sum((Decimal(str(entry.get("wallet_amount", "0"))) for entry in matching_rows), Decimal("0.00")),
            sum((Decimal(str(entry.get("gateway_amount", "0"))) for entry in matching_rows), Decimal("0.00")),
            item,
        )
    if not payment.order_id and payment.booking_id == booking.id:
        return (
            payment.amount + payment.wallet_amount,
            payment.wallet_amount,
            payment.amount,
            None,
        )
    return Decimal("0.00"), Decimal("0.00"), Decimal("0.00"), None


def _component_allocation(payment, line_total, stage_total):
    if stage_total <= 0 or line_total <= 0:
        return Decimal("0.00"), Decimal("0.00")
    ratio = line_total / stage_total
    wallet_part = min(
        payment.wallet_amount,
        (payment.wallet_amount * ratio).quantize(CENT, rounding=ROUND_HALF_UP),
    )
    gateway_part = (line_total - wallet_part).quantize(CENT)
    # Keep the two components bounded by the payment's captured components.
    if gateway_part > payment.amount:
        gateway_part = payment.amount
        wallet_part = line_total - gateway_part
    return wallet_part, gateway_part


def _existing_refund_components(payment, booking):
    refunds = PaymentRefund.objects.filter(payment=payment, booking=booking)
    return (
        sum(refunds.values_list("amount", flat=True), Decimal("0.00")),
        sum(refunds.values_list("wallet_amount", flat=True), Decimal("0.00")),
        sum(refunds.values_list("gateway_amount", flat=True), Decimal("0.00")),
    )


def issue_admin_partial_refund(
    payment,
    booking,
    amount,
    requested_by,
    admin_note,
    idempotency_key,
    reason=PaymentRefund.Reason.ADMIN_ADJUSTMENT,
):
    """Create an audited, source-proportional partial refund under a unique request key."""
    try:
        requested_amount = Decimal(str(amount))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Enter a valid refund amount.")
    if (
        not requested_amount.is_finite()
        or requested_amount <= 0
        or requested_amount.quantize(CENT) != requested_amount
    ):
        raise ValueError("Refund amount must be positive and have at most two decimal places.")
    if not idempotency_key or len(idempotency_key) > 100:
        raise ValueError("A valid refund request key is required.")
    if not admin_note or not admin_note.strip():
        raise ValueError("An audit note is required for an admin-issued refund.")
    if reason not in (
        PaymentRefund.Reason.ADMIN_ADJUSTMENT,
        PaymentRefund.Reason.DISPUTE_RESOLUTION,
    ):
        raise ValueError("Unsupported admin refund reason.")

    with transaction.atomic():
        existing = PaymentRefund.objects.filter(idempotency_key=idempotency_key).first()
        if existing:
            if (
                existing.payment_id != payment.pk
                or existing.booking_id != booking.pk
                or existing.amount != requested_amount
            ):
                raise ValueError("This refund request key was already used for a different request.")
            refund = existing
            created = False
        else:
            locked_payment = Payment.objects.select_for_update().select_related("extra_work").get(
                pk=payment.pk
            )
            locked_booking = Booking.objects.select_for_update().get(pk=booking.pk)
            if locked_payment.status != Payment.Status.PAID:
                raise ValueError("Only captured payments can be partially refunded.")
            line_total, wallet_captured, gateway_captured, order_item = _line_stage_amount(
                locked_payment, locked_booking
            )
            if line_total <= 0:
                raise ValueError("This payment has no captured allocation for the selected service.")
            refunded_total, refunded_wallet, refunded_gateway = _existing_refund_components(
                locked_payment, locked_booking
            )
            remaining_wallet = wallet_captured - refunded_wallet
            remaining_gateway = gateway_captured - refunded_gateway
            remaining_total = remaining_wallet + remaining_gateway
            if remaining_wallet < 0 or remaining_gateway < 0:
                raise ValueError("Existing refunds exceed the captured payment allocation. Reconciliation is required.")
            if requested_amount > remaining_total:
                raise ValueError(
                    f"Refund exceeds the remaining refundable amount of ₹{remaining_total:.2f}."
                )
            wallet_refund = (
                requested_amount * remaining_wallet / remaining_total
            ).quantize(CENT, rounding=ROUND_HALF_UP) if remaining_total else Decimal("0.00")
            wallet_refund = min(wallet_refund, remaining_wallet)
            gateway_refund = requested_amount - wallet_refund
            if gateway_refund > remaining_gateway:
                gateway_refund = remaining_gateway
                wallet_refund = requested_amount - gateway_refund
            if wallet_refund < 0 or gateway_refund < 0:
                raise ValueError("The requested refund cannot be allocated to the original payment sources.")

            refund = PaymentRefund.objects.create(
                payment=locked_payment,
                booking=locked_booking,
                order_item=order_item,
                amount=requested_amount,
                wallet_amount=wallet_refund,
                gateway_amount=gateway_refund,
                reason=reason,
                status=PaymentRefund.Status.PENDING,
                requested_by=requested_by,
                admin_note=admin_note.strip(),
                idempotency_key=idempotency_key,
            )
            created = True

    if refund.status == PaymentRefund.Status.PENDING:
        return process_payment_refund(refund.pk)
    return refund


def request_booking_refunds(booking, reason=PaymentRefund.Reason.CUSTOMER_CANCELLATION):
    """
    Create an idempotent refund for the remaining captured amount per payment/service.
    Existing partial refunds are deducted before a cancellation refund is created.
    """
    booking = Booking.objects.select_related("customer").get(pk=booking.pk)
    if booking.status != Booking.Status.CANCELLED:
        raise ValueError("Only cancelled bookings can be refunded.")

    if hasattr(booking, "order_item"):
        from apps.wallet.services import release_wallet_reservation

        pending_attempts = Payment.objects.filter(
            order_id=booking.order_item.order_id,
            status=Payment.Status.PENDING,
        )
        for pending_payment in pending_attempts:
            release_wallet_reservation(
                pending_payment,
                reason="Wallet hold released because a service in this order was cancelled.",
            )

    payments = Payment.objects.filter(status=Payment.Status.PAID).filter(
        order__items__booking=booking
    ) if hasattr(booking, "order_item") else Payment.objects.filter(
        booking=booking, status=Payment.Status.PAID
    )
    created_ids = []
    for payment in payments.distinct():
        with transaction.atomic():
            locked = Payment.objects.select_for_update().select_related("extra_work").get(pk=payment.pk)
            line_total, wallet_captured, gateway_captured, item = _line_stage_amount(locked, booking)
            if line_total <= 0:
                continue
            _, refunded_wallet, refunded_gateway = _existing_refund_components(locked, booking)
            wallet_part = wallet_captured - refunded_wallet
            gateway_part = gateway_captured - refunded_gateway
            if wallet_part < 0 or gateway_part < 0:
                raise ValueError("Existing refunds exceed the captured service allocation. Manual reconciliation is required.")
            amount = wallet_part + gateway_part
            if amount <= 0:
                continue
            key = f"booking-cancel:{locked.pk}:{booking.pk}"
            refund, was_created = PaymentRefund.objects.get_or_create(
                idempotency_key=key,
                defaults={
                    "payment": locked,
                    "booking": booking,
                    "order_item": item,
                    "amount": amount,
                    "wallet_amount": wallet_part,
                    "gateway_amount": gateway_part,
                    "reason": reason,
                    "status": PaymentRefund.Status.PENDING,
                },
            )
            if was_created:
                created_ids.append(refund.pk)
            elif (
                refund.amount != amount
                or refund.wallet_amount != wallet_part
                or refund.gateway_amount != gateway_part
            ):
                raise ValueError("The cancellation refund allocation changed after it was first created. Manual reconciliation is required.")

    for refund_id in created_ids:
        process_payment_refund(refund_id)
    return PaymentRefund.objects.filter(booking=booking).order_by("created_at")


def process_payment_refund(refund_id):
    """Idempotently credit wallet funds and submit the gateway portion."""
    with transaction.atomic():
        refund = PaymentRefund.objects.select_for_update().select_related(
            "payment", "booking", "payment__customer"
        ).get(pk=refund_id)
        if refund.status in (PaymentRefund.Status.PROCESSED, PaymentRefund.Status.PROCESSING):
            return refund
        if refund.status == PaymentRefund.Status.PENDING and refund.gateway_refund_id:
            return refund
        if refund.status == PaymentRefund.Status.FAILED and refund.gateway_refund_id:
            # A failed gateway refund must be reconciled before another request
            # is issued; blindly retrying could double-refund a late success.
            return refund
        refund.status = PaymentRefund.Status.PROCESSING
        refund.save(update_fields=["status", "updated_at"])
        payment = Payment.objects.select_for_update().get(pk=refund.payment_id)

        if refund.wallet_amount > 0:
            wallet, _ = Wallet.objects.get_or_create(user=payment.customer)
            wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)
            reference = f"payment-refund:{refund.pk}:wallet"
            existing = WalletTransaction.objects.filter(
                reference_id=reference,
                type=WalletTransaction.Type.REFUND,
                status=WalletTransaction.Status.COMPLETED,
            ).first()
            if not existing:
                wallet.balance += refund.wallet_amount
                wallet.save(update_fields=["balance", "updated_at"])
                WalletTransaction.objects.create(
                    wallet=wallet,
                    type=WalletTransaction.Type.REFUND,
                    amount=refund.wallet_amount,
                    description=f"Refund for cancelled AIRway booking #{refund.booking_id}",
                    status=WalletTransaction.Status.COMPLETED,
                    reference_id=reference,
                )

        if refund.gateway_amount <= 0:
            refund.status = PaymentRefund.Status.PROCESSED
            refund.processed_at = timezone.now()
            refund.save(update_fields=["status", "processed_at", "updated_at"])
            _notify_refund(refund)
            return refund

        if not payment.razorpay_payment_id:
            refund.status = PaymentRefund.Status.FAILED
            refund.failure_reason = "Captured Razorpay payment ID is unavailable."
            refund.save(update_fields=["status", "failure_reason", "updated_at"])
            return refund

    try:
        gateway = razorpay.Client(
            auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
        )
        response = gateway.payment.refund(
            payment.razorpay_payment_id,
            {
                "amount": int(refund.gateway_amount * 100),
                "notes": {
                    "airway_refund_id": str(refund.pk),
                    "airway_booking_id": str(refund.booking_id),
                    "reason": refund.reason,
                },
            },
        )
        with transaction.atomic():
            locked = PaymentRefund.objects.select_for_update().get(pk=refund_id)
            locked.gateway_refund_id = response.get("id", "")
            gateway_status = response.get("status", "").lower()
            locked.status = (
                PaymentRefund.Status.PROCESSED
                if gateway_status == "processed"
                else PaymentRefund.Status.PENDING
            )
            if gateway_status == "processed":
                locked.processed_at = timezone.now()
            locked.save(update_fields=[
                "gateway_refund_id", "status", "processed_at", "updated_at"
            ])
            if gateway_status == "processed":
                _notify_refund(locked)
            return locked
    except Exception as exc:
        logger.exception("Razorpay refund request outcome is uncertain for refund %s", refund_id)
        # A timeout can occur after Razorpay accepted the refund but before AIRway
        # received its response. Keep the ledger non-retryable until reconciliation;
        # blindly issuing another refund could pay the customer twice.
        failure_reason = (
            "Gateway outcome is unconfirmed. Manual reconciliation is required "
            "before retrying. " + str(exc)
        )[:500]
        PaymentRefund.objects.filter(pk=refund_id).update(
            status=PaymentRefund.Status.PROCESSING,
            failure_reason=failure_reason,
            updated_at=timezone.now(),
        )
        refund = PaymentRefund.objects.select_related(
            "payment", "booking", "payment__customer"
        ).get(pk=refund_id)
        _notify_refund_attention(
            refund,
            "Razorpay did not return a conclusive refund result. AIRway support must reconcile it before another refund attempt.",
        )
        return refund


def reconcile_gateway_refund(refund_id, event_type, gateway_status, gateway_amount=None, refund_pk=None):
    """Apply signed Razorpay refund webhook events idempotently."""
    with transaction.atomic():
        refund_query = PaymentRefund.objects.select_for_update().select_related(
            "payment", "booking"
        )
        refund = (
            refund_query.filter(gateway_refund_id=refund_id).first()
            if refund_id else None
        )
        if refund is None and refund_pk:
            refund = refund_query.filter(pk=refund_pk).first()
        if refund is None:
            return None
        if gateway_amount is not None and int(gateway_amount) != int(refund.gateway_amount * 100):
            logger.error(
                "Razorpay refund amount mismatch for refund %s: expected %s, received %s",
                refund.pk, int(refund.gateway_amount * 100), gateway_amount,
            )
            return None
        if refund.status == PaymentRefund.Status.PROCESSED:
            return refund
        if refund_id and not refund.gateway_refund_id:
            refund.gateway_refund_id = refund_id
        if event_type == "refund.processed" or gateway_status == "processed":
            refund.status = PaymentRefund.Status.PROCESSED
            refund.processed_at = timezone.now()
            refund.failure_reason = ""
        elif event_type == "refund.failed" or gateway_status == "failed":
            refund.status = PaymentRefund.Status.FAILED
            refund.failure_reason = "Razorpay reported that this refund failed."
        refund.save(update_fields=[
            "gateway_refund_id", "status", "processed_at",
            "failure_reason", "updated_at",
        ])
        if refund.status == PaymentRefund.Status.PROCESSED:
            _notify_refund(refund)
        else:
            _notify_refund_attention(
                refund,
                "Razorpay could not complete a refund. AIRway support has been alerted to reconcile it.",
            )
        return refund


def _notify_refund(refund):
    Notification.objects.get_or_create(
        user=refund.payment.customer,
        type=Notification.Type.SYSTEM_ANNOUNCEMENT,
        title="Refund processed",
        body=f"Your refund of ₹{refund.amount} for booking #{refund.booking_id} has been processed.",
        channel=Notification.Channel.IN_APP,
        data={"refund_id": refund.pk, "booking_id": refund.booking_id},
    )


def _notify_refund_attention(refund, customer_message):
    payload = {"refund_id": refund.pk, "booking_id": refund.booking_id}
    Notification.objects.get_or_create(
        user=refund.payment.customer,
        type=Notification.Type.SYSTEM_ANNOUNCEMENT,
        title="Refund needs attention",
        data__refund_id=refund.pk,
        defaults={
            "body": customer_message,
            "channel": Notification.Channel.IN_APP,
            "data": payload,
        },
    )

    User = get_user_model()
    staff_message = (
        f"Refund #{refund.pk} for booking #{refund.booking_id} has an unresolved "
        "gateway result. Verify the Razorpay refund status before any retry."
    )
    for staff_user in User.objects.filter(is_staff=True, is_active=True).only("id"):
        Notification.objects.get_or_create(
            user=staff_user,
            type=Notification.Type.SYSTEM_ANNOUNCEMENT,
            title="Refund requires reconciliation",
            data__refund_id=refund.pk,
            defaults={
                "body": staff_message,
                "channel": Notification.Channel.IN_APP,
                "data": payload,
            },
        )



def request_recurring_plan_refund(plan):
    """Refund unused prepaid visits without exceeding any prior refund allocation."""
    from apps.bookings.models import RecurringWashVisit, RecurringWashPlan

    locked_plan = RecurringWashPlan.objects.get(pk=plan.pk)
    unused_total = sum(
        (
            visit.prepaid_amount
            for visit in locked_plan.visits.exclude(
                status__in=(
                    RecurringWashVisit.Status.COMPLETED,
                    RecurringWashVisit.Status.IN_PROGRESS,
                )
            )
        ),
        Decimal("0.00"),
    )
    unused_total = min(Decimal(locked_plan.quoted_total), unused_total).quantize(CENT)
    if unused_total <= 0:
        return PaymentRefund.objects.none()

    payments = list(
        Payment.objects.filter(
            order_id=locked_plan.order_id,
            status=Payment.Status.PAID,
        ).order_by("created_at")
    )
    allocations = []
    already_refunded = Decimal("0.00")
    for payment in payments:
        line_total, wallet_captured, gateway_captured, item = _line_stage_amount(
            payment, locked_plan.source_booking
        )
        if line_total <= 0:
            continue
        refunded_total, refunded_wallet, refunded_gateway = _existing_refund_components(
            payment, locked_plan.source_booking
        )
        already_refunded += refunded_total
        remaining_wallet = wallet_captured - refunded_wallet
        remaining_gateway = gateway_captured - refunded_gateway
        if remaining_wallet < 0 or remaining_gateway < 0:
            raise ValueError(
                "Existing refunds exceed the recurring payment allocation. "
                "Manual reconciliation is required."
            )
        remaining_total = remaining_wallet + remaining_gateway
        if remaining_total > 0:
            allocations.append(
                (payment, remaining_total, remaining_wallet, remaining_gateway, item)
            )

    refund_target = max(unused_total - already_refunded, Decimal("0.00")).quantize(CENT)
    if refund_target <= 0:
        return PaymentRefund.objects.filter(
            payment__order_id=locked_plan.order_id,
            booking=locked_plan.source_booking,
            reason=PaymentRefund.Reason.RECURRING_PLAN_CANCELLATION,
        ).order_by("created_at")

    captured_remaining = sum((row[1] for row in allocations), Decimal("0.00"))
    if captured_remaining < refund_target:
        raise ValueError(
            "Remaining captured payment allocations are lower than the unused prepaid visit balance. "
            "Manual payment reconciliation is required before refunding."
        )

    to_process = []
    allocated = Decimal("0.00")
    for index, (payment, remaining_total, wallet_available, gateway_available, item) in enumerate(allocations):
        refund_amount = (
            refund_target - allocated
            if index == len(allocations) - 1
            else (refund_target * remaining_total / captured_remaining).quantize(
                CENT, rounding=ROUND_HALF_UP
            )
        )
        refund_amount = min(refund_amount, remaining_total)
        wallet_refund = (
            refund_amount * wallet_available / remaining_total
        ).quantize(CENT, rounding=ROUND_HALF_UP)
        wallet_refund = min(wallet_refund, wallet_available)
        gateway_refund = refund_amount - wallet_refund
        if gateway_refund > gateway_available:
            gateway_refund = gateway_available
            wallet_refund = refund_amount - gateway_refund
        amount = wallet_refund + gateway_refund
        if amount <= 0:
            continue

        with transaction.atomic():
            locked_payment = Payment.objects.select_for_update().get(pk=payment.pk)
            existing = PaymentRefund.objects.filter(
                payment=locked_payment,
                booking=locked_plan.source_booking,
                reason=PaymentRefund.Reason.RECURRING_PLAN_CANCELLATION,
            ).order_by("created_at").first()
            if existing and existing.idempotency_key.startswith(
                f"recurring-plan:{locked_plan.pk}:"
            ):
                refund = existing
                if (
                    refund.amount != amount
                    or refund.wallet_amount != wallet_refund
                    or refund.gateway_amount != gateway_refund
                ):
                    raise ValueError(
                        "The recurring plan refund allocation changed after it was first created. "
                        "Manual reconciliation is required."
                    )
            else:
                key = f"recurring-plan:{locked_plan.pk}:payment:{locked_payment.pk}"
                refund, was_created = PaymentRefund.objects.get_or_create(
                    idempotency_key=key,
                    defaults={
                        "payment": locked_payment,
                        "booking": locked_plan.source_booking,
                        "order_item": item,
                        "amount": amount,
                        "wallet_amount": wallet_refund,
                        "gateway_amount": gateway_refund,
                        "reason": PaymentRefund.Reason.RECURRING_PLAN_CANCELLATION,
                        "status": PaymentRefund.Status.PENDING,
                    },
                )
                if (
                    refund.payment_id != locked_payment.pk
                    or refund.booking_id != locked_plan.source_booking.pk
                    or refund.amount != amount
                    or refund.wallet_amount != wallet_refund
                    or refund.gateway_amount != gateway_refund
                ):
                    raise ValueError(
                        "The recurring plan already has a different refund allocation for this payment. "
                        "Manual refund reconciliation is required."
                    )
            allocated += amount
            if refund.status == PaymentRefund.Status.PENDING:
                to_process.append(refund.pk)

    if allocated < refund_target:
        raise ValueError("The captured recurring payment could not cover the unused visit refund.")

    for refund_id in to_process:
        process_payment_refund(refund_id)
    return PaymentRefund.objects.filter(
        payment__order_id=locked_plan.order_id,
        booking=locked_plan.source_booking,
        reason=PaymentRefund.Reason.RECURRING_PLAN_CANCELLATION,
    ).order_by("created_at")
