import logging
from decimal import Decimal, ROUND_HALF_UP

import razorpay
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.bookings.models import Booking, Order
from .models import Payment, PaymentInstallment, PaymentAttempt

logger = logging.getLogger(__name__)
CENT = Decimal("0.01")


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
    if wallet_amount not in (None, 0, "0", "0.00", Decimal("0.00")):
        raise ValueError("Wallet use is temporarily unavailable for split installments. Your wallet balance is unchanged.")
    payment = get_or_create_aggregate_payment(booking=booking, order=order, customer=customer)
    advance, balance = ensure_installments(payment)
    installment = advance if kind == PaymentInstallment.Kind.ADVANCE else balance
    if kind == PaymentInstallment.Kind.ADVANCE and (booking and booking.status not in (Booking.Status.PENDING, Booking.Status.CONFIRMED)):
        raise ValueError("Advance payment is no longer available for this booking.")
    if kind == PaymentInstallment.Kind.ADVANCE and order and order.status not in (Order.Status.AWAITING_PAYMENT, Order.Status.AWAITING_ASSIGNMENT):
        raise ValueError("Advance payment is no longer available for this order.")
    if kind == PaymentInstallment.Kind.BALANCE:
        if booking and booking.status != Booking.Status.COMPLETED:
            raise ValueError("The balance is payable only after the service is completed.")
        if order and any(row.booking.status != Booking.Status.COMPLETED for row in order.items.select_related("booking")):
            raise ValueError("The balance is payable only after every service in the order is completed.")
    if installment.status == PaymentInstallment.Status.PAID:
        return payment, installment, None, True
    latest = installment.attempts.order_by("-attempt_number").first()
    if latest and latest.status == PaymentAttempt.Status.PENDING and latest.razorpay_order_id:
        return payment, installment, latest, True
    with transaction.atomic():
        installment = PaymentInstallment.objects.select_for_update().get(pk=installment.pk)
        if installment.status == PaymentInstallment.Status.PAID:
            return payment, installment, None, True
        latest = installment.attempts.select_for_update().order_by("-attempt_number").first()
        if latest and latest.status == PaymentAttempt.Status.PENDING and latest.razorpay_order_id:
            return payment, installment, latest, True
        attempt_number = (latest.attempt_number if latest else 0) + 1
        attempt = PaymentAttempt.objects.create(
            installment=installment,
            attempt_number=attempt_number,
            amount=installment.amount,
            method=Payment.Method.RAZORPAY,
            status=PaymentAttempt.Status.PENDING,
        )
    try:
        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
        target = f"order_{order.pk}" if order else f"booking_{booking.pk}"
        gateway_order = client.order.create(data={
            "amount": int(attempt.amount * 100),
            "currency": "INR",
            "receipt": f"airway_{target}_{kind}_{attempt.pk}",
            "notes": {
                "airway_payment_id": str(payment.pk),
                "airway_installment_id": str(installment.pk),
                "airway_attempt_id": str(attempt.pk),
                "installment": kind,
            },
        })
    except Exception:
        attempt.status = PaymentAttempt.Status.FAILED
        attempt.failed_at = timezone.now()
        attempt.save(update_fields=["status", "failed_at", "updated_at"])
        raise
    attempt.razorpay_order_id = gateway_order["id"]
    attempt.save(update_fields=["razorpay_order_id", "updated_at"])
    return payment, installment, attempt, False
