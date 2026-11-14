import logging
from decimal import Decimal, ROUND_HALF_UP

import razorpay
from django.conf import settings
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
    rows = (payment.raw_response or {}).get("service_allocation_v1", [])
    row = next((entry for entry in rows if entry.get("booking_id") == booking.id), None)
    if row:
        item = OrderItem.objects.filter(pk=row.get("order_item_id")).first()
        return (
            Decimal(str(row.get("total", "0"))),
            Decimal(str(row.get("wallet_amount", "0"))),
            Decimal(str(row.get("gateway_amount", "0"))),
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


def request_booking_refunds(booking, reason=PaymentRefund.Reason.CUSTOMER_CANCELLATION):
    """
    Create one idempotent refund per paid payment/service line, then process
    wallet credits and Razorpay refunds. Call only after the booking is cancelled.
    """
    booking = Booking.objects.select_related("customer").get(pk=booking.pk)
    if booking.status != Booking.Status.CANCELLED:
        raise ValueError("Only cancelled bookings can be refunded.")

    if hasattr(booking, "order_item"):
        # Invalidate the wallet hold for any in-flight parent-order attempt.
        # A late Razorpay capture is still recognised by its order ID and the
        # staged-payment guard reverses it against the changed active allocation.
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
            locked = Payment.objects.select_for_update().get(pk=payment.pk)
            line_total, wallet_part, gateway_part, item = _line_stage_amount(locked, booking)
            if line_total <= 0 or wallet_part + gateway_part <= 0:
                continue
            refund, was_created = PaymentRefund.objects.get_or_create(
                payment=locked,
                booking=booking,
                defaults={
                    "order_item": item,
                    "amount": wallet_part + gateway_part,
                    "wallet_amount": wallet_part,
                    "gateway_amount": gateway_part,
                    "reason": reason,
                    "status": PaymentRefund.Status.PENDING,
                },
            )
            if was_created:
                created_ids.append(refund.pk)

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
        logger.exception("Razorpay refund request failed for refund %s", refund_id)
        PaymentRefund.objects.filter(pk=refund_id).update(
            status=PaymentRefund.Status.FAILED,
            failure_reason=str(exc)[:500],
        )
        return PaymentRefund.objects.get(pk=refund_id)


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
            Notification.objects.create(
                user=refund.payment.customer,
                type=Notification.Type.SYSTEM_ANNOUNCEMENT,
                title="Refund needs attention",
                body="Razorpay could not complete a refund. AIRway support has been alerted to reconcile it.",
                channel=Notification.Channel.IN_APP,
                data={"refund_id": refund.pk, "booking_id": refund.booking_id},
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
