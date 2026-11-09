"""Domain services for AIRway's versioned split-payment and OTP lifecycle.

These services are additive. Legacy bookings without BookingFinancialPlan continue
through the existing payment path until the checkout/dispatch rollout is switched.
"""
import secrets
from datetime import datetime, time, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.utils import timezone

from apps.bookings.models import (
    Booking,
    BookingAssignment,
    BookingStatusHistory,
    Order,
    OrderItem,
)
from .models import (
    BookingFinancialPlan,
    PaymentInstallment,
    RefundRecord,
    ServiceOTPChallenge,
)

INR = Decimal("0.01")
ZERO = Decimal("0.00")
CANCELLATION_FEE = Decimal("40.00")
BUSINESS_TIMEZONE = ZoneInfo("Asia/Kolkata")
OTP_TTL = timedelta(minutes=10)
OTP_MAX_ATTEMPTS = 5


class PaymentLifecycleError(Exception):
    """A safe, expected domain rejection in the payment/service lifecycle."""


def as_money(value):
    """Convert a trusted server-side value to INR precision without float math."""
    try:
        amount = Decimal(str(value)).quantize(INR, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        raise PaymentLifecycleError("The booking total is not a valid monetary amount.")
    if not amount.is_finite() or amount < ZERO:
        raise PaymentLifecycleError("The booking total cannot be negative or non-finite.")
    return amount


def split_total(total):
    """Return (50% advance, exact remainder) using paise rounding."""
    gross = as_money(total)
    advance = (gross / Decimal("2")).quantize(INR, rounding=ROUND_HALF_UP)
    balance = gross - advance
    return advance, balance


@transaction.atomic
def create_financial_plan(booking):
    """Create an immutable per-booking financial plan once; legacy rows are untouched."""
    locked = Booking.objects.select_for_update().get(pk=booking.pk)
    existing = BookingFinancialPlan.objects.filter(booking=locked).first()
    if existing:
        return existing

    snapshot = dict(locked.pricing_snapshot or {})
    if "total" not in snapshot:
        raise PaymentLifecycleError("A server-calculated booking total is required.")
    gross = as_money(snapshot["total"])
    advance, balance = split_total(gross)

    plan = BookingFinancialPlan.objects.create(
        booking=locked,
        currency="INR",
        gross_total=gross,
        advance_due=advance,
        balance_due=balance,
        pricing_snapshot=snapshot,
        calculation_version="split-50-50-v1",
    )
    PaymentInstallment.objects.bulk_create([
        PaymentInstallment(
            financial_plan=plan,
            kind=PaymentInstallment.Kind.ADVANCE,
            amount_due=advance,
            status=PaymentInstallment.Status.DUE,
            due_at=timezone.now(),
        ),
        PaymentInstallment(
            financial_plan=plan,
            kind=PaymentInstallment.Kind.FINAL_BALANCE,
            amount_due=balance,
            status=PaymentInstallment.Status.NOT_DUE,
        ),
    ])
    return plan


def cancellation_cutoff(scheduled_at):
    """10 PM IST on the calendar day before the scheduled service date."""
    if timezone.is_naive(scheduled_at):
        raise PaymentLifecycleError("The scheduled service time must be timezone-aware.")
    local_service_time = scheduled_at.astimezone(BUSINESS_TIMEZONE)
    cutoff_date = local_service_time.date() - timedelta(days=1)
    return datetime.combine(cutoff_date, time(hour=22), tzinfo=BUSINESS_TIMEZONE)


def customer_cancellation_is_refundable(scheduled_at, *, now=None):
    """Exactly 10:00 PM IST is still eligible."""
    current = now or timezone.now()
    if timezone.is_naive(current):
        raise PaymentLifecycleError("The current time must be timezone-aware.")
    return current.astimezone(BUSINESS_TIMEZONE) <= cancellation_cutoff(scheduled_at)


def calculate_customer_refund(collected_amount):
    """One ₹40 fee per cancelled booking line; never return a negative refund."""
    collected = as_money(collected_amount)
    return max(collected - CANCELLATION_FEE, ZERO)


def calculate_platform_refund(collected_amount):
    """Platform/worker inability before start is refunded in full."""
    return as_money(collected_amount)


def customer_cancellation_terms(scheduled_at, collected_amount, *, worker_accepted, now=None):
    """Return the authoritative refund decision for a customer cancellation.

    Same-day service: full refund until a worker accepts; no refund after acceptance.
    Future service: refund collected advance less the single ₹40 fee through 10 PM
    IST on the previous calendar day. The exact cutoff instant remains eligible.
    """
    current = now or timezone.now()
    if timezone.is_naive(current) or timezone.is_naive(scheduled_at):
        raise PaymentLifecycleError("Cancellation dates must be timezone-aware.")
    local_now = current.astimezone(BUSINESS_TIMEZONE)
    local_service = scheduled_at.astimezone(BUSINESS_TIMEZONE)
    collected = as_money(collected_amount)

    if local_now.date() == local_service.date():
        if worker_accepted:
            return {
                "policy": "same_day_after_worker_acceptance",
                "refund_amount": ZERO,
                "platform_fee": ZERO,
                "refundable": False,
            }
        return {
            "policy": "same_day_before_worker_acceptance",
            "refund_amount": collected,
            "platform_fee": ZERO,
            "refundable": collected > ZERO,
        }

    if customer_cancellation_is_refundable(scheduled_at, now=current):
        refund = calculate_customer_refund(collected)
        return {
            "policy": "future_before_cutoff",
            "refund_amount": refund,
            "platform_fee": min(collected, CANCELLATION_FEE),
            "refundable": refund > ZERO,
        }

    return {
        "policy": "future_after_cutoff",
        "refund_amount": ZERO,
        "platform_fee": ZERO,
        "refundable": False,
    }


def create_customer_cancellation_refund_record(*, booking, payment, terms):
    """Persist one idempotent line refund request against the captured payment."""
    if payment is None or payment.status != "paid":
        return None, False
    amount = as_money(terms["refund_amount"])
    collected = as_money(payment.amount)
    key = f"customer-cancel:booking:{booking.pk}:payment:{payment.pk}"
    record, created = RefundRecord.objects.get_or_create(
        idempotency_key=key,
        defaults={
            "booking": booking,
            "payment": payment,
            "reason": RefundRecord.Reason.CUSTOMER_CANCELLATION,
            "gross_amount": collected,
            "platform_fee": as_money(terms["platform_fee"]),
            "refund_amount": amount,
            "status": (
                RefundRecord.Status.REQUESTED
                if amount > ZERO else RefundRecord.Status.PROCESSED
            ),
            "requested_at": timezone.now(),
            "processed_at": timezone.now() if amount == ZERO else None,
            "provider_payload": {"policy": terms["policy"]},
        },
    )
    return record, created


def _new_otp():
    return f"{secrets.randbelow(1_000_000):06d}"


@transaction.atomic
def issue_service_otp(*, booking_id, purpose, requested_by):
    """Issue a hashed, short-lived OTP to the booking customer.

    The plaintext is returned exactly once to the trusted delivery layer. It must
    never be returned to the worker or included in logs/API payloads.
    """
    booking = Booking.objects.select_for_update().get(pk=booking_id)
    if booking.customer_id != requested_by.pk:
        raise PaymentLifecycleError("You cannot request an OTP for this booking.")

    if purpose == ServiceOTPChallenge.Purpose.START:
        if booking.status not in (Booking.Status.ASSIGNED, Booking.Status.CONFIRMED):
            raise PaymentLifecycleError("A start OTP is available only for an assigned booking.")
        if not BookingAssignment.objects.filter(booking=booking).exists():
            raise PaymentLifecycleError("A worker must be assigned before requesting a start OTP.")
        advance = PaymentInstallment.objects.filter(
            financial_plan__booking=booking,
            kind=PaymentInstallment.Kind.ADVANCE,
        ).first()
        if (
            advance is None
            or advance.status != PaymentInstallment.Status.PAID
            or advance.amount_captured < advance.amount_due
        ):
            raise PaymentLifecycleError("The booking advance must be fully captured before service can start.")
    elif purpose == ServiceOTPChallenge.Purpose.COMPLETION:
        if booking.status != Booking.Status.IN_PROGRESS:
            raise PaymentLifecycleError("A completion OTP is available only after service starts.")
    else:
        raise PaymentLifecycleError("Invalid service OTP purpose.")

    now = timezone.now()
    recent_count = ServiceOTPChallenge.objects.filter(
        booking=booking,
        purpose=purpose,
        created_at__gte=now - timedelta(minutes=15),
    ).count()
    if recent_count >= 3:
        raise PaymentLifecycleError("Too many OTP requests. Please try again later.")

    ServiceOTPChallenge.objects.filter(
        booking=booking,
        purpose=purpose,
        consumed_at__isnull=True,
        invalidated_at__isnull=True,
    ).update(invalidated_at=now)

    plaintext = _new_otp()
    challenge = ServiceOTPChallenge.objects.create(
        booking=booking,
        purpose=purpose,
        code_hash=make_password(plaintext),
        expires_at=now + OTP_TTL,
        max_attempts=OTP_MAX_ATTEMPTS,
    )
    return challenge, plaintext


def verify_service_otp(*, booking_id, purpose, code, worker_user):
    """Atomically verify OTP and persist failed-attempt counters on rejection."""
    error = None
    completed_booking = None
    with transaction.atomic():
        booking = Booking.objects.select_for_update().get(pk=booking_id)
        assignment = BookingAssignment.objects.select_for_update().filter(
            booking=booking,
        ).select_related("worker__user").first()
        if assignment is None or assignment.worker.user_id != worker_user.pk:
            error = "Only the currently assigned worker can verify this OTP."
        else:
            expected_states = (
                (Booking.Status.ASSIGNED, Booking.Status.CONFIRMED)
                if purpose == ServiceOTPChallenge.Purpose.START
                else (Booking.Status.IN_PROGRESS,)
            )
            target_state = (
                Booking.Status.IN_PROGRESS
                if purpose == ServiceOTPChallenge.Purpose.START
                else Booking.Status.COMPLETED
            )
            if purpose not in (
                ServiceOTPChallenge.Purpose.START,
                ServiceOTPChallenge.Purpose.COMPLETION,
            ):
                error = "Invalid service OTP purpose."
            elif booking.status not in expected_states:
                error = "This booking is not in the required state for this OTP."
            elif purpose == ServiceOTPChallenge.Purpose.START:
                advance = PaymentInstallment.objects.select_for_update().filter(
                    financial_plan__booking=booking,
                    kind=PaymentInstallment.Kind.ADVANCE,
                ).first()
                if (
                    advance is None
                    or advance.status != PaymentInstallment.Status.PAID
                    or advance.amount_captured < advance.amount_due
                ):
                    error = "The booking advance must be fully captured before service can start."
                else:
                    challenge = None
            else:
                challenge = None

            if error is None:
                challenge = ServiceOTPChallenge.objects.select_for_update().filter(
                    booking=booking,
                    purpose=purpose,
                    consumed_at__isnull=True,
                    invalidated_at__isnull=True,
                ).order_by("-created_at").first()
                now = timezone.now()
                if challenge is None:
                    error = "No active OTP exists. Ask the customer to request a new one."
                elif challenge.expires_at <= now:
                    challenge.invalidated_at = now
                    challenge.save(update_fields=["invalidated_at", "updated_at"])
                    error = "The OTP has expired. Ask the customer to request a new one."
                elif challenge.attempts >= challenge.max_attempts:
                    challenge.invalidated_at = now
                    challenge.save(update_fields=["invalidated_at", "updated_at"])
                    error = "Maximum OTP attempts exceeded."
                elif (
                    not isinstance(code, str)
                    or len(code) != 6
                    or not code.isdigit()
                    or not check_password(code, challenge.code_hash)
                ):
                    challenge.attempts += 1
                    if challenge.attempts >= challenge.max_attempts:
                        challenge.invalidated_at = now
                    challenge.save(update_fields=["attempts", "invalidated_at", "updated_at"])
                    error = "The OTP is incorrect."
                else:
                    old_status = booking.status
                    challenge.consumed_at = now
                    challenge.save(update_fields=["consumed_at", "updated_at"])
                    booking.status = target_state
                    update_fields = ["status", "updated_at"]
                    if purpose == ServiceOTPChallenge.Purpose.START:
                        assignment.started_at = now
                        assignment.save(update_fields=["started_at", "updated_at"])
                    else:
                        booking.completed_at = now
                        update_fields.append("completed_at")
                        assignment.completed_at = now
                        assignment.save(update_fields=["completed_at", "updated_at"])
                        final_installment = PaymentInstallment.objects.select_for_update().get(
                            financial_plan__booking=booking,
                            kind=PaymentInstallment.Kind.FINAL_BALANCE,
                        )
                        final_installment.status = PaymentInstallment.Status.DUE
                        final_installment.due_at = now
                        final_installment.save(update_fields=["status", "due_at", "updated_at"])
                    booking.save(update_fields=update_fields)
                    order_id = OrderItem.objects.filter(
                        booking_id=booking.pk
                    ).values_list("order_id", flat=True).first()
                    if order_id:
                        parent_order = Order.objects.select_for_update().get(pk=order_id)
                        if purpose == ServiceOTPChallenge.Purpose.START:
                            parent_order.status = Order.Status.IN_PROGRESS
                        else:
                            all_lines_completed = not parent_order.items.exclude(
                                booking__status=Booking.Status.COMPLETED
                            ).exists()
                            parent_order.status = (
                                Order.Status.AWAITING_FINAL_PAYMENT
                                if all_lines_completed
                                else Order.Status.IN_PROGRESS
                            )
                        parent_order.save(update_fields=["status", "updated_at"])
                    BookingStatusHistory.objects.create(
                        booking=booking,
                        from_status=old_status,
                        to_status=target_state,
                        changed_by=worker_user,
                        note=(
                            "Service started after successful start OTP verification."
                            if purpose == ServiceOTPChallenge.Purpose.START
                            else "Service completed after successful completion OTP verification."
                        ),
                    )
                    completed_booking = booking

    # Raise outside atomic so failed attempts and expiry invalidation are committed.
    if error:
        raise PaymentLifecycleError(error)
    return completed_booking
