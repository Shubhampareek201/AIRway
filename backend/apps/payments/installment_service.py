"""Final-installment collection and settlement services.

All monetary values are Decimal INR amounts. Provider network calls are made
outside database transactions; captured funds are applied under row locks.
"""
import uuid
import logging
from decimal import Decimal, InvalidOperation

import razorpay
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.bookings.models import Booking, Order, OrderItem
from apps.notifications.models import Notification
from apps.wallet.models import Wallet, WalletReservation, WalletTransaction
from .models import (
    BookingFinancialPlan, PaymentAllocation, PaymentAttempt,
    PaymentInstallment,
)


logger = logging.getLogger(__name__)

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


class InstallmentPaymentError(Exception):
    pass


def _money(value):
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount < ZERO or amount.quantize(CENT) != amount:
            raise InvalidOperation
        return amount.quantize(CENT)
    except (InvalidOperation, TypeError, ValueError):
        raise InstallmentPaymentError("Enter a valid amount with at most two decimal places.")


def _reserve_wallet(attempt, amount):
    if amount <= ZERO:
        return None
    wallet, _ = Wallet.objects.get_or_create(user=attempt.installment.financial_plan.booking.customer)
    wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)
    if wallet.balance < amount:
        raise InstallmentPaymentError("Insufficient AIRway wallet balance.")
    wallet.balance -= amount
    wallet.pending_balance += amount
    wallet.save(update_fields=["balance", "pending_balance", "updated_at"])
    WalletTransaction.objects.create(
        wallet=wallet,
        type=WalletTransaction.Type.DEBIT,
        amount=amount,
        description=f"Wallet reserved for final balance of booking #{attempt.installment.financial_plan.booking_id}",
        status=WalletTransaction.Status.PENDING,
        reference_id=f"payment_attempt:{attempt.pk}",
    )
    return WalletReservation.objects.create(
        wallet=wallet, payment_attempt=attempt, amount=amount,
        status=WalletReservation.Status.RESERVED,
    )


@transaction.atomic
def _capture_wallet(attempt, razorpay_payment_id=""):
    reservation = WalletReservation.objects.select_for_update().filter(
        payment_attempt=attempt, status=WalletReservation.Status.RESERVED,
    ).first()
    if attempt.wallet_amount == ZERO:
        if reservation:
            raise InstallmentPaymentError("Unexpected wallet reservation for this attempt.")
        return
    if reservation is None:
        latest = WalletReservation.objects.select_for_update().filter(
            payment_attempt=attempt,
        ).order_by("-created_at").first()
        if latest and latest.status == WalletReservation.Status.CAPTURED:
            return
        raise InstallmentPaymentError("The wallet reservation is missing; payment needs reconciliation.")
    wallet = Wallet.objects.select_for_update().get(pk=reservation.wallet_id)
    if wallet.pending_balance < reservation.amount:
        raise InstallmentPaymentError("Wallet pending balance does not match its reservation.")
    wallet.pending_balance -= reservation.amount
    wallet.save(update_fields=["pending_balance", "updated_at"])
    WalletTransaction.objects.filter(
        wallet=wallet, reference_id=f"payment_attempt:{attempt.pk}",
        type=WalletTransaction.Type.DEBIT, status=WalletTransaction.Status.PENDING,
    ).update(status=WalletTransaction.Status.COMPLETED, razorpay_payment_id=razorpay_payment_id)
    reservation.status = WalletReservation.Status.CAPTURED
    reservation.captured_at = timezone.now()
    reservation.save(update_fields=["status", "captured_at", "updated_at"])


@transaction.atomic
def _release_wallet(attempt, reason):
    reservation = WalletReservation.objects.select_for_update().filter(
        payment_attempt=attempt, status=WalletReservation.Status.RESERVED,
    ).first()
    if reservation is None:
        return
    wallet = Wallet.objects.select_for_update().get(pk=reservation.wallet_id)
    if wallet.pending_balance < reservation.amount:
        raise InstallmentPaymentError("Wallet pending balance does not match its reservation.")
    wallet.balance += reservation.amount
    wallet.pending_balance -= reservation.amount
    wallet.save(update_fields=["balance", "pending_balance", "updated_at"])
    WalletTransaction.objects.filter(
        wallet=wallet, reference_id=f"payment_attempt:{attempt.pk}",
        type=WalletTransaction.Type.DEBIT, status=WalletTransaction.Status.PENDING,
    ).update(status=WalletTransaction.Status.FAILED, description=reason[:255])
    reservation.status = WalletReservation.Status.RELEASED
    reservation.released_at = timezone.now()
    reservation.save(update_fields=["status", "released_at", "updated_at"])


def create_final_balance_attempt(*, booking_id, customer, wallet_amount="0.00"):
    """Create one immutable Razorpay attempt for a completed booking line."""
    wallet_requested = _money(wallet_amount)
    with transaction.atomic():
        try:
            booking = Booking.objects.select_for_update().get(pk=booking_id, customer=customer)
        except Booking.DoesNotExist:
            raise InstallmentPaymentError("Booking not found or access denied.")
        if booking.status != Booking.Status.COMPLETED:
            raise InstallmentPaymentError("Final payment is available only after service completion.")
        plan = BookingFinancialPlan.objects.select_for_update().filter(booking=booking).first()
        if plan is None:
            raise InstallmentPaymentError("This booking uses the legacy payment flow.")
        installment = PaymentInstallment.objects.select_for_update().get(
            financial_plan=plan, kind=PaymentInstallment.Kind.FINAL_BALANCE,
        )
        if installment.status == PaymentInstallment.Status.PAID:
            raise InstallmentPaymentError("The final balance is already paid.")
        if installment.status not in (
            PaymentInstallment.Status.DUE, PaymentInstallment.Status.PARTIALLY_PAID,
            PaymentInstallment.Status.FAILED,
        ):
            raise InstallmentPaymentError("The final balance is not due yet.")
        outstanding = installment.amount_due - installment.amount_captured
        if outstanding <= ZERO:
            raise InstallmentPaymentError("No final balance remains outstanding.")
        if wallet_requested > outstanding:
            raise InstallmentPaymentError("Wallet amount cannot exceed the outstanding final balance.")
        if wallet_requested > ZERO and plan.currency != "INR":
            raise InstallmentPaymentError("AIRway wallet can only be used for INR payments.")

        active = PaymentAttempt.objects.select_for_update().filter(
            installment=installment,
            status__in=(PaymentAttempt.Status.CREATED, PaymentAttempt.Status.AUTHORIZED),
        ).order_by("-created_at").first()
        if active:
            if active.amount != outstanding or active.wallet_amount != wallet_requested:
                raise InstallmentPaymentError(
                    "A payment attempt is already active with different payment details. Complete or wait for it before changing the wallet amount."
                )
            return active, True

        gateway_amount = outstanding - wallet_requested
        attempt = PaymentAttempt.objects.create(
            installment=installment,
            provider=PaymentAttempt.Provider.RAZORPAY if gateway_amount > ZERO else PaymentAttempt.Provider.WALLET,
            idempotency_key=f"final:{installment.pk}:{uuid.uuid4().hex}",
            amount=outstanding,
            gateway_amount=gateway_amount,
            wallet_amount=wallet_requested,
            currency=plan.currency,
            status=PaymentAttempt.Status.CREATED,
        )
        _reserve_wallet(attempt, wallet_requested)
        installment.status = PaymentInstallment.Status.PROCESSING
        installment.save(update_fields=["status", "updated_at"])

    if gateway_amount == ZERO:
        settle_final_balance_attempt(
            attempt_id=attempt.pk, razorpay_payment_id="",
            provider_order_id="", amount_paise=0, currency=plan.currency,
            source="wallet",
        )
        attempt.refresh_from_db()
        return attempt, False

    gateway = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
    try:
        order_data = gateway.order.create(data={
            "amount": int(gateway_amount * 100),
            "currency": plan.currency,
            "receipt": f"airway_final_{attempt.pk}",
            "notes": {
                "airway_attempt_id": str(attempt.pk),
                "airway_booking_id": str(booking.pk),
                "airway_installment": "final_balance",
            },
        })
        provider_order_id = order_data.get("id")
        if not provider_order_id:
            raise ValueError("Razorpay did not return an order ID.")
    except Exception:
        _release_wallet(attempt, "Razorpay final-balance order creation failed")
        with transaction.atomic():
            locked = PaymentAttempt.objects.select_for_update().get(pk=attempt.pk)
            locked.status = PaymentAttempt.Status.FAILED
            locked.failed_at = timezone.now()
            locked.provider_payload = {"error": "Razorpay order creation failed"}
            locked.save(update_fields=["status", "failed_at", "provider_payload", "updated_at"])
            installment = PaymentInstallment.objects.select_for_update().get(pk=installment.pk)
            installment.status = (
                PaymentInstallment.Status.PARTIALLY_PAID
                if installment.amount_captured > ZERO else PaymentInstallment.Status.DUE
            )
            installment.save(update_fields=["status", "updated_at"])
        raise
    with transaction.atomic():
        locked = PaymentAttempt.objects.select_for_update().get(pk=attempt.pk)
        locked.provider_order_id = provider_order_id
        locked.save(update_fields=["provider_order_id", "updated_at"])
    attempt.refresh_from_db()
    return attempt, False


def settle_final_balance_attempt(
    *, attempt_id, razorpay_payment_id, provider_order_id,
    amount_paise, currency, source,
):
    """Apply an authenticated/captured final tender exactly once."""
    with transaction.atomic():
        attempt = PaymentAttempt.objects.select_for_update().select_related(
            "installment__financial_plan__booking",
        ).get(pk=attempt_id)
        installment = PaymentInstallment.objects.select_for_update().get(pk=attempt.installment_id)
        plan = BookingFinancialPlan.objects.select_for_update().get(pk=installment.financial_plan_id)
        booking = Booking.objects.select_for_update().get(pk=plan.booking_id)

        if attempt.status == PaymentAttempt.Status.CAPTURED:
            if attempt.provider_payment_id and attempt.provider_payment_id != razorpay_payment_id:
                raise InstallmentPaymentError("This attempt was already captured by a different payment.")
            return attempt

        if attempt.provider == PaymentAttempt.Provider.RAZORPAY:
            expected_paise = int(attempt.gateway_amount * 100)
            if not provider_order_id or provider_order_id != attempt.provider_order_id:
                raise InstallmentPaymentError("Razorpay order ID does not match this attempt.")
            if not razorpay_payment_id:
                raise InstallmentPaymentError("Razorpay payment ID is required.")
            if amount_paise != expected_paise:
                raise InstallmentPaymentError("Captured amount does not match the final-payment attempt.")
            if (currency or "").upper() != attempt.currency:
                raise InstallmentPaymentError("Captured currency does not match the installment.")
        elif source != "wallet" or amount_paise != 0:
            raise InstallmentPaymentError("Invalid wallet-only settlement.")

        if booking.status != Booking.Status.COMPLETED:
            raise InstallmentPaymentError("Final balance cannot settle before completion OTP.")
        if installment.status == PaymentInstallment.Status.PAID:
            raise InstallmentPaymentError("The installment was already settled by another attempt.")
        if attempt.amount != attempt.gateway_amount + attempt.wallet_amount:
            raise InstallmentPaymentError("Attempt tender does not reconcile.")

        _capture_wallet(attempt, razorpay_payment_id)
        PaymentAllocation.objects.create(
            payment_attempt=attempt,
            installment=installment,
            amount=attempt.amount,
            gateway_amount=attempt.gateway_amount,
            wallet_amount=attempt.wallet_amount,
        )
        installment.amount_captured += attempt.amount
        if installment.amount_captured > installment.amount_due:
            raise InstallmentPaymentError("Captured final balance exceeds the amount due.")
        installment.status = (
            PaymentInstallment.Status.PAID
            if installment.amount_captured == installment.amount_due
            else PaymentInstallment.Status.PARTIALLY_PAID
        )
        if installment.status == PaymentInstallment.Status.PAID:
            installment.settled_at = timezone.now()
        installment.save(update_fields=["amount_captured", "status", "settled_at", "updated_at"])

        plan.balance_captured = installment.amount_captured
        plan.save(update_fields=["balance_captured", "updated_at"])
        attempt.status = PaymentAttempt.Status.CAPTURED
        attempt.provider_payment_id = razorpay_payment_id or None
        attempt.captured_at = timezone.now()
        attempt.provider_payload = {
            **(attempt.provider_payload or {}),
            "source": source,
            "captured_at": attempt.captured_at.isoformat(),
        }
        attempt.save(update_fields=[
            "status", "provider_payment_id", "captured_at", "provider_payload", "updated_at",
        ])

        order_id = OrderItem.objects.filter(booking_id=booking.pk).values_list(
            "order_id", flat=True,
        ).first()
        if order_id:
            parent_order = Order.objects.select_for_update().get(pk=order_id)
            all_completed = not parent_order.items.exclude(
                booking__status=Booking.Status.COMPLETED,
            ).exists()
            all_balances_paid = not PaymentInstallment.objects.filter(
                financial_plan__booking__order_item__order=parent_order,
                kind=PaymentInstallment.Kind.FINAL_BALANCE,
            ).exclude(status=PaymentInstallment.Status.PAID).exists()
            if all_completed and all_balances_paid:
                parent_order.status = Order.Status.COMPLETED
            elif all_completed:
                parent_order.status = Order.Status.AWAITING_FINAL_PAYMENT
            parent_order.save(update_fields=["status", "updated_at"])

        Notification.objects.create(
            user=booking.customer,
            type=Notification.Type.PAYMENT_SUCCESS,
            title="Final payment received",
            body=f"Your final payment for booking #{booking.pk} was received.",
            channel=Notification.Channel.IN_APP,
            data={
                "booking_id": booking.pk,
                "payment_attempt_id": attempt.pk,
                "installment_status": installment.status,
                "remaining_balance": str(installment.amount_due - installment.amount_captured),
            },
        )
        return attempt


def refund_late_final_capture(*, attempt_id, razorpay_payment_id, provider_order_id, payload):
    """Refund a capture that arrives after its attempt was failed and wallet released."""
    import razorpay
    from django.conf import settings
    from .models import RefundRecord

    with transaction.atomic():
        attempt = PaymentAttempt.objects.select_for_update().select_related(
            "installment__financial_plan__booking",
        ).get(pk=attempt_id)
        if attempt.provider_order_id != provider_order_id:
            raise InstallmentPaymentError("Razorpay order ID does not match this attempt.")
        if attempt.status == PaymentAttempt.Status.CAPTURED:
            return None
        if attempt.status == PaymentAttempt.Status.REFUNDED:
            return RefundRecord.objects.filter(payment_attempt=attempt).first()
        if attempt.status != PaymentAttempt.Status.FAILED:
            raise InstallmentPaymentError("Attempt is not in a failed state.")
        booking = attempt.installment.financial_plan.booking
        refund_amount = attempt.gateway_amount
        record, created = RefundRecord.objects.get_or_create(
            idempotency_key=f"late-final-capture:attempt:{attempt.pk}:{razorpay_payment_id}",
            defaults={
                "booking": booking,
                "payment_attempt": attempt,
                "reason": RefundRecord.Reason.PAYMENT_RECONCILIATION,
                "gross_amount": refund_amount,
                "platform_fee": ZERO,
                "refund_amount": refund_amount,
                "status": (
                    RefundRecord.Status.REQUESTED if refund_amount > ZERO
                    else RefundRecord.Status.PROCESSED
                ),
                "requested_at": timezone.now(),
                "processed_at": timezone.now() if refund_amount == ZERO else None,
                "provider_payload": {"reason": "Capture arrived after failed attempt and wallet release."},
            },
        )
        attempt.provider_payment_id = razorpay_payment_id
        attempt.status = (
            PaymentAttempt.Status.REFUND_PENDING
            if refund_amount > ZERO else PaymentAttempt.Status.REFUNDED
        )
        attempt.provider_payload = payload or {}
        attempt.save(update_fields=["provider_payment_id", "status", "provider_payload", "updated_at"])

    if not created or refund_amount <= ZERO:
        return record
    try:
        gateway = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
        provider_refund = gateway.payment.refund(
            razorpay_payment_id,
            {
                "amount": int(refund_amount * 100),
                "notes": {
                    "airway_refund_record_id": str(record.pk),
                    "airway_attempt_id": str(attempt.pk),
                    "reason": "Late capture after failed final-balance attempt",
                },
            },
        )
        provider_id = provider_refund.get("id")
        if not provider_id:
            raise ValueError("Razorpay did not return a refund ID.")
        record.provider_refund_id = provider_id
        if provider_refund.get("status") == "processed":
            record.status = RefundRecord.Status.PROCESSED
            record.processed_at = timezone.now()
            attempt.status = PaymentAttempt.Status.REFUNDED
        elif provider_refund.get("status") == "failed":
            record.status = RefundRecord.Status.FAILED
            attempt.status = PaymentAttempt.Status.FAILED
        else:
            record.status = RefundRecord.Status.PENDING
        record.provider_payload = provider_refund
    except Exception as exc:
        logger.exception("Late final-payment refund failed for attempt %s", attempt.pk)
        record.status = RefundRecord.Status.FAILED
        record.provider_payload = {
            **(record.provider_payload or {}),
            "submission_error": str(exc)[:500],
        }
        attempt.status = PaymentAttempt.Status.FAILED
    record.save(update_fields=[
        "provider_refund_id", "status", "processed_at", "provider_payload", "updated_at",
    ])
    attempt.save(update_fields=["status", "updated_at"])
    return record


def mark_final_balance_attempt_failed(*, attempt_id, provider_order_id, payload=None):
    """Record a failed gateway attempt without changing service completion."""
    with transaction.atomic():
        attempt = PaymentAttempt.objects.select_for_update().select_related("installment").get(pk=attempt_id)
        if attempt.provider_order_id != provider_order_id:
            raise InstallmentPaymentError("Razorpay order ID does not match this attempt.")
        if attempt.status == PaymentAttempt.Status.CAPTURED:
            return attempt
        if attempt.status == PaymentAttempt.Status.FAILED:
            return attempt
        attempt.status = PaymentAttempt.Status.FAILED
        attempt.failed_at = timezone.now()
        attempt.provider_payload = payload or {}
        attempt.save(update_fields=["status", "failed_at", "provider_payload", "updated_at"])
        installment = PaymentInstallment.objects.select_for_update().get(pk=attempt.installment_id)
        installment.status = (
            PaymentInstallment.Status.PARTIALLY_PAID
            if installment.amount_captured > ZERO else PaymentInstallment.Status.DUE
        )
        installment.save(update_fields=["status", "updated_at"])
    _release_wallet(attempt, "Final payment attempt failed")
    return attempt
