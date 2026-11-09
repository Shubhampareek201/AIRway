import logging
from decimal import Decimal, ROUND_HALF_UP

import razorpay
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.bookings.models import Booking, Order
from apps.wallet.models import Wallet, WalletTransaction
from .models import Payment, PaymentInstallment, PaymentAttempt

logger = logging.getLogger(__name__)
CENT = Decimal("0.01")



def reserve_installment_wallet(attempt, customer):
    amount = Decimal(attempt.wallet_amount).quantize(CENT)
    if amount <= 0:
        return
    with transaction.atomic():
        wallet, _ = Wallet.objects.get_or_create(user=customer)
        wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)
        if wallet.balance < amount:
            raise ValueError("Insufficient AIRway wallet balance.")
        wallet.balance -= amount
        wallet.pending_balance += amount
        wallet.save(update_fields=["balance", "pending_balance", "updated_at"])
        WalletTransaction.objects.create(
            wallet=wallet,
            type=WalletTransaction.Type.DEBIT,
            amount=amount,
            description=f"Wallet reserved for payment installment #{attempt.installment_id}",
            status=WalletTransaction.Status.PENDING,
            reference_id=f"installment_attempt:{attempt.pk}",
        )


def capture_installment_wallet(attempt, razorpay_payment_id=""):
    amount = Decimal(attempt.wallet_amount).quantize(CENT)
    if amount <= 0:
        return
    with transaction.atomic():
        tx = WalletTransaction.objects.select_for_update().filter(
            reference_id=f"installment_attempt:{attempt.pk}",
            type=WalletTransaction.Type.DEBIT,
            status=WalletTransaction.Status.PENDING,
        ).first()
        if tx is None:
            if WalletTransaction.objects.filter(
                reference_id=f"installment_attempt:{attempt.pk}",
                type=WalletTransaction.Type.DEBIT,
                status=WalletTransaction.Status.COMPLETED,
            ).exists():
                return
            raise ValueError("The reserved wallet contribution is missing.")
        wallet = Wallet.objects.select_for_update().get(pk=tx.wallet_id)
        if wallet.pending_balance < amount:
            raise ValueError("Wallet pending balance is inconsistent.")
        wallet.pending_balance -= amount
        wallet.save(update_fields=["pending_balance", "updated_at"])
        tx.status = WalletTransaction.Status.COMPLETED
        tx.razorpay_payment_id = razorpay_payment_id or ""
        tx.save(update_fields=["status", "razorpay_payment_id", "updated_at"])


def release_installment_wallet(attempt, reason="Payment attempt failed"):
    amount = Decimal(attempt.wallet_amount).quantize(CENT)
    if amount <= 0:
        return
    with transaction.atomic():
        tx = WalletTransaction.objects.select_for_update().filter(
            reference_id=f"installment_attempt:{attempt.pk}",
            type=WalletTransaction.Type.DEBIT,
            status=WalletTransaction.Status.PENDING,
        ).first()
        if tx is None:
            return
        wallet = Wallet.objects.select_for_update().get(pk=tx.wallet_id)
        if wallet.pending_balance < amount:
            raise ValueError("Wallet pending balance is inconsistent.")
        wallet.balance += amount
        wallet.pending_balance -= amount
        wallet.save(update_fields=["balance", "pending_balance", "updated_at"])
        tx.status = WalletTransaction.Status.FAILED
        tx.description = reason[:255]
        tx.save(update_fields=["status", "description", "updated_at"])


def payment_total(payment):
    if payment.order_id:
        return Decimal(payment.order.total_amount).quantize(CENT)
    return Decimal(str(payment.booking.total_amount)).quantize(CENT)


def ensure_installments(payment):
    total = payment_total(payment)
    if total <= 0:
        raise ValueError("Payment total must be greater than zero.")
    advance_amount = (total / Decimal("2")).quantize(CENT, rounding=ROUND_HALF_UP)
    balance_amount = total - advance_amount
    advance, _ = PaymentInstallment.objects.get_or_create(
        payment=payment,
        kind=PaymentInstallment.Kind.ADVANCE,
        defaults={"amount": advance_amount},
    )
    balance, _ = PaymentInstallment.objects.get_or_create(
        payment=payment,
        kind=PaymentInstallment.Kind.BALANCE,
        defaults={"amount": balance_amount},
    )
    if advance.amount + balance.amount != total:
        raise ValueError("The stored payment installments do not match the locked booking total.")
    return advance, balance


def get_or_create_aggregate_payment(*, booking=None, order=None, customer):
    if bool(booking) == bool(order):
        raise ValueError("Exactly one booking or order is required.")
    if booking:
        if booking.customer_id != customer.id:
            raise ValueError("Booking not found or access denied.")
        payment, _ = Payment.objects.get_or_create(
            booking=booking,
            defaults={
                "customer": customer,
                "amount": Decimal(str(booking.total_amount)).quantize(CENT),
                "method": Payment.Method.RAZORPAY,
                "status": Payment.Status.PENDING,
            },
        )
    else:
        if order.customer_id != customer.id:
            raise ValueError("Order not found or access denied.")
        payment, _ = Payment.objects.get_or_create(
            order=order,
            defaults={
                "customer": customer,
                "amount": Decimal(order.total_amount).quantize(CENT),
                "method": Payment.Method.RAZORPAY,
                "status": Payment.Status.PENDING,
            },
        )
    if payment.customer_id != customer.id:
        raise ValueError("Payment owner mismatch.")
    payment.amount = payment_total(payment)
    payment.save(update_fields=["amount", "updated_at"])
    return payment


def create_installment_gateway_order(*, booking=None, order=None, customer, kind, wallet_amount=Decimal("0.00")):
    try:
        requested_wallet = Decimal(str(wallet_amount or "0.00"))
    except Exception as exc:
        raise ValueError("Provide a valid wallet amount.") from exc
    if not requested_wallet.is_finite() or requested_wallet < 0:
        raise ValueError("Wallet amount must be finite and non-negative.")
    if requested_wallet.quantize(CENT) != requested_wallet:
        raise ValueError("Wallet amount must have at most two decimal places.")

    payment = get_or_create_aggregate_payment(booking=booking, order=order, customer=customer)
    advance, balance = ensure_installments(payment)
    installment = advance if kind == PaymentInstallment.Kind.ADVANCE else balance
    if kind == PaymentInstallment.Kind.ADVANCE and booking and booking.status not in (Booking.Status.PENDING, Booking.Status.CONFIRMED):
        raise ValueError("Advance payment is no longer available for this booking.")
    if kind == PaymentInstallment.Kind.ADVANCE and order and order.status not in (Order.Status.AWAITING_PAYMENT, Order.Status.AWAITING_ASSIGNMENT):
        raise ValueError("Advance payment is no longer available for this order.")
    if kind == PaymentInstallment.Kind.BALANCE:
        if booking and booking.status != Booking.Status.COMPLETED:
            raise ValueError("The balance is payable only after the service is completed.")
        if order and any(row.booking.status != Booking.Status.COMPLETED for row in order.items.select_related("booking")):
            raise ValueError("The balance is payable only after every service in the order is completed.")
    if requested_wallet > installment.amount:
        raise ValueError("Wallet amount cannot exceed the current installment.")
    if installment.status == PaymentInstallment.Status.PAID:
        return payment, installment, None, True

    with transaction.atomic():
        installment = PaymentInstallment.objects.select_for_update().get(pk=installment.pk)
        if installment.status == PaymentInstallment.Status.PAID:
            return payment, installment, None, True
        latest = installment.attempts.select_for_update().order_by("-attempt_number").first()
        if latest and latest.status == PaymentAttempt.Status.PENDING:
            if latest.wallet_amount != requested_wallet:
                raise ValueError("A payment attempt is already pending with a different wallet contribution.")
            if latest.razorpay_order_id or latest.amount == 0:
                return payment, installment, latest, True
        attempt_number = (latest.attempt_number if latest else 0) + 1
        gateway_amount = installment.amount - requested_wallet
        attempt = PaymentAttempt.objects.create(
            installment=installment,
            attempt_number=attempt_number,
            amount=gateway_amount,
            wallet_amount=requested_wallet,
            method=Payment.Method.WALLET if gateway_amount == 0 else Payment.Method.RAZORPAY,
            status=PaymentAttempt.Status.PENDING,
        )
        reserve_installment_wallet(attempt, customer)

    if attempt.amount == 0:
        from .verify_view import _process_verified_attempt
        result = _process_verified_attempt(
            attempt=attempt, razorpay_payment_id="", razorpay_order_id="",
            customer=customer, source="wallet",
        )
        if getattr(result, "status_code", 500) >= 400:
            release_installment_wallet(attempt, "Wallet-only installment settlement failed")
            raise ValueError("Wallet payment could not be completed. Please retry.")
        attempt.refresh_from_db()
        return payment, installment, attempt, False

    try:
        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
        target = f"order_{order.pk}" if order else f"booking_{booking.pk}"
        gateway_order = client.order.create(data={
            "amount": int((attempt.amount * 100).to_integral_value(rounding=ROUND_HALF_UP)),
            "currency": "INR",
            "receipt": f"airway_{target}_{kind}_{attempt.pk}",
            "notes": {
                "airway_payment_id": str(payment.pk),
                "airway_installment_id": str(installment.pk),
                "airway_attempt_id": str(attempt.pk),
                "installment": kind,
                "wallet_amount": str(attempt.wallet_amount),
            },
        })
    except Exception:
        attempt.status = PaymentAttempt.Status.FAILED
        attempt.failed_at = timezone.now()
        attempt.save(update_fields=["status", "failed_at", "updated_at"])
        release_installment_wallet(attempt, "Razorpay order creation failed")
        raise
    attempt.razorpay_order_id = gateway_order["id"]
    attempt.save(update_fields=["razorpay_order_id", "updated_at"])
    return payment, installment, attempt, False
