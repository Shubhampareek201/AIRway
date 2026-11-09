import logging
from decimal import Decimal, ROUND_HALF_UP

import razorpay
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from apps.wallet.models import Wallet, WalletTransaction

from .models import Payment, PaymentAttempt, PaymentInstallment, PaymentRefund

logger = logging.getLogger(__name__)
CENT = Decimal("0.01")
CANCELLATION_FEE = Decimal("40.00")


def request_installment_refund(*, attempt, idempotency_key, reason, deduct_platform_fee=False):
    """Create one auditable refund request and submit only the gateway refund amount."""
    with transaction.atomic():
        locked = PaymentAttempt.objects.select_for_update().select_related(
            "installment__payment"
        ).get(pk=attempt.pk)
        existing = PaymentRefund.objects.filter(idempotency_key=idempotency_key).first()
        if existing:
            return existing
        if locked.status != PaymentAttempt.Status.PAID or not locked.razorpay_payment_id:
            raise ValueError("Only a captured Razorpay installment can be refunded.")
        paid_total = (Decimal(locked.amount) + Decimal(locked.wallet_amount)).quantize(CENT)
        fee = min(CANCELLATION_FEE, paid_total) if deduct_platform_fee else Decimal("0.00")
        total_refund = max(paid_total - fee, Decimal("0.00")).quantize(CENT)
        gateway_refund = min(Decimal(locked.amount), total_refund).quantize(CENT)
        wallet_refund = (total_refund - gateway_refund).quantize(CENT)
        refund = PaymentRefund.objects.create(
            attempt=locked,
            idempotency_key=idempotency_key,
            gateway_amount=gateway_refund,
            wallet_amount=wallet_refund,
            platform_fee=fee,
            reason=reason[:255],
            status=PaymentRefund.Status.PENDING,
        )
        payment = Payment.objects.select_for_update().get(pk=locked.installment.payment_id)
        payment.status = Payment.Status.REFUND_PENDING
        payment.save(update_fields=["status", "updated_at"])

    if refund.gateway_amount == 0:
        refund.status = PaymentRefund.Status.PROCESSED
        refund.processed_at = timezone.now()
        refund.save(update_fields=["status", "processed_at", "updated_at"])
        _finalize_refunded_attempt(refund)
        return refund

    try:
        gateway = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
        result = gateway.payment.refund(
            locked.razorpay_payment_id,
            {
                "amount": int((refund.gateway_amount * 100).to_integral_value(rounding=ROUND_HALF_UP)),
                "notes": {
                    "airway_refund_key": idempotency_key,
                    "airway_attempt_id": str(locked.pk),
                    "reason": reason[:200],
                },
            },
        )
    except Exception:
        logger.exception("Razorpay refund request failed for payment attempt %s", locked.pk)
        refund.status = PaymentRefund.Status.FAILED
        refund.raw_response = {"error": "Gateway refund request failed; manual reconciliation required."}
        refund.save(update_fields=["status", "raw_response", "updated_at"])
        raise

    refund.gateway_refund_id = result.get("id", "")
    refund.raw_response = result
    if result.get("status") == "processed":
        refund.status = PaymentRefund.Status.PROCESSED
        refund.processed_at = timezone.now()
    else:
        refund.status = PaymentRefund.Status.PENDING
    refund.save(update_fields=[
        "gateway_refund_id", "raw_response", "status", "processed_at", "updated_at"
    ])
    if refund.status == PaymentRefund.Status.PROCESSED:
        _finalize_refunded_attempt(refund)
    return refund


def _finalize_refunded_attempt(refund):
    with transaction.atomic():
        refund = PaymentRefund.objects.select_for_update().select_related(
            "attempt__installment__payment"
        ).get(pk=refund.pk)
        if refund.status != PaymentRefund.Status.PROCESSED:
            return
        attempt = PaymentAttempt.objects.select_for_update().get(pk=refund.attempt_id)
        payment = Payment.objects.select_for_update().get(pk=attempt.installment.payment_id)
        if attempt.status != PaymentAttempt.Status.REFUNDED and refund.wallet_amount > 0:
            wallet, _ = Wallet.objects.get_or_create(user=payment.customer)
            wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)
            wallet.balance += refund.wallet_amount
            wallet.save(update_fields=["balance", "updated_at"])
            WalletTransaction.objects.get_or_create(
                wallet=wallet,
                reference_id=f"payment_refund:{refund.pk}",
                type=WalletTransaction.Type.CREDIT,
                defaults={
                    "amount": refund.wallet_amount,
                    "description": f"Wallet refund for AIRway payment #{payment.pk}",
                    "status": WalletTransaction.Status.COMPLETED,
                },
            )
        attempt.status = PaymentAttempt.Status.REFUNDED
        attempt.save(update_fields=["status", "updated_at"])
        payment.status = Payment.Status.REFUNDED
        payment.save(update_fields=["status", "updated_at"])
