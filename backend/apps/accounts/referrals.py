from decimal import Decimal, InvalidOperation

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.validators import validate_ipv46_address
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import Referral, User
from apps.wallet.models import Wallet, WalletTransaction

REFERRED_FIRST_SERVICE_CREDIT = Decimal("100.00")
REFERRER_FIRST_SERVICE_CREDIT = Decimal("200.00")
MINIMUM_ORIGINAL_SERVICE_CHARGE = Decimal("500.00")


def _request_ip(request):
    if request is None:
        return None
    value = request.META.get("REMOTE_ADDR")
    if not value:
        return None
    try:
        validate_ipv46_address(value)
    except ValidationError:
        return None
    return value


def _credit_wallet(user, amount, description, reference_id):
    wallet, _ = Wallet.objects.get_or_create(user=user)
    wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)
    existing = WalletTransaction.objects.filter(wallet=wallet, reference_id=reference_id).first()
    if existing:
        return existing
    entry = WalletTransaction.objects.create(
        wallet=wallet,
        type=WalletTransaction.Type.PROMOTIONAL_CREDIT,
        amount=amount,
        description=description,
        status=WalletTransaction.Status.COMPLETED,
        reference_id=reference_id,
    )
    wallet.balance += amount
    wallet.save(update_fields=["balance", "updated_at"])
    return entry


def _booking_has_refund(booking, order_id=None):
    """A refunded service line must never qualify for a referral credit."""
    from apps.payments.models import Payment, PaymentRefund

    if PaymentRefund.objects.filter(
        booking_id=booking.pk,
        status=PaymentRefund.Status.PROCESSED,
        extra_work__isnull=True,
    ).exists():
        return True
    payment_filter = Q(booking_id=booking.pk)
    if order_id:
        payment_filter |= Q(order_id=order_id)
    if Payment.objects.filter(payment_filter, status=Payment.Status.REFUNDED).exists():
        return True
    return WalletTransaction.objects.filter(
        wallet__user=booking.customer,
        type=WalletTransaction.Type.REFUND,
        status=WalletTransaction.Status.COMPLETED,
        reference_id=str(booking.pk),
    ).exists()


@transaction.atomic
def apply_referral_code(referred_user, code, request=None):
    """Attach one referrer to a customer before their first booking; never credit at application."""
    normalized = str(code or "").strip().upper()
    if not normalized:
        raise ValueError("Enter a referral code.")
    referred = User.objects.select_for_update().get(pk=referred_user.pk)
    if Referral.objects.filter(referred=referred).exists():
        raise ValueError("A referral code has already been applied to this account.")
    if referred.referral_code.upper() == normalized:
        raise ValueError("You cannot use your own referral code.")
    if referred.bookings.exists():
        raise ValueError("Referral codes can only be applied before your first booking.")
    referrer = User.objects.filter(referral_code__iexact=normalized, is_active=True).first()
    if referrer is None:
        raise ValueError("This referral code is invalid.")
    if referrer.pk == referred.pk:
        raise ValueError("You cannot use your own referral code.")

    same_phone = bool(
        referred.phone and referrer.phone
        and referred.phone.strip() == referrer.phone.strip()
    )
    referred_email = (referred.email or "").strip().casefold()
    referrer_email = (referrer.email or "").strip().casefold()
    same_email = bool(referred_email and referrer_email and referred_email == referrer_email)
    same_firebase_identity = bool(
        referred.firebase_uid and referrer.firebase_uid
        and referred.firebase_uid == referrer.firebase_uid
    )
    if same_phone or same_email or same_firebase_identity:
        raise ValueError("This referral cannot be applied between duplicate or matching account identities.")

    return Referral.objects.create(
        referral_type=Referral.ReferralType.CUSTOMER,
        referrer=referrer,
        referred=referred,
        applied_ip=_request_ip(request),
    )


@transaction.atomic
def reward_referral_for_first_completed_booking(booking):
    """
    Issue ₹200/₹100 AIRway-only promotional credits after the referred
    customer's first OTP-verified completed service line whose original
    pre-tax, pre-discount subtotal is strictly greater than ₹500.
    """
    if booking.status != "completed":
        return False
    try:
        order_item = booking.order_item
    except ObjectDoesNotExist:
        return False
    if order_item is None:
        return False
    try:
        original_service_charge = Decimal(str(order_item.line_subtotal))
    except (InvalidOperation, TypeError, ValueError):
        return False
    if not original_service_charge.is_finite() or original_service_charge <= MINIMUM_ORIGINAL_SERVICE_CHARGE:
        return False
    referral = (
        Referral.objects.select_for_update()
        .select_related("referrer", "referred")
        .filter(referred=booking.customer, referral_type=Referral.ReferralType.CUSTOMER, rewarded=False)
        .first()
    )
    if referral is None:
        return False

    if _booking_has_refund(booking, order_id=order_item.order_id):
        return False

    # Locking the referral row serializes competing completion attempts.
    # Earlier low-value or refunded services do not consume eligibility.
    from apps.bookings.models import OrderItem
    previous_eligible_items = OrderItem.objects.filter(
        booking__customer=booking.customer,
        booking__status="completed",
        line_subtotal__gt=MINIMUM_ORIGINAL_SERVICE_CHARGE,
    ).exclude(booking_id=booking.pk).select_related("booking")
    for previous_item in previous_eligible_items:
        if not _booking_has_refund(previous_item.booking, order_id=previous_item.order_id):
            return False

    _credit_wallet(
        referral.referrer,
        REFERRER_FIRST_SERVICE_CREDIT,
        "Referral promotional credit: your friend's first eligible AIRway service was completed",
        f"referral:{referral.pk}:referrer",
    )
    _credit_wallet(
        referral.referred,
        REFERRED_FIRST_SERVICE_CREDIT,
        "Welcome promotional credit: your first eligible AIRway service was completed",
        f"referral:{referral.pk}:referred:first-service",
    )

    from apps.notifications.models import Notification
    Notification.objects.bulk_create([
        Notification(
            user=referral.referrer,
            type=Notification.Type.REFERRAL_REWARD,
            title="Referral reward credited",
            body="₹200 promotional credit has been added to your AIRway wallet because your friend's eligible service was completed.",
            channel=Notification.Channel.IN_APP,
            data={"referral_id": referral.pk, "amount": "200.00", "reward_for": "referrer"},
        ),
        Notification(
            user=referral.referred,
            type=Notification.Type.REFERRAL_REWARD,
            title="Welcome reward credited",
            body="₹100 promotional credit has been added to your AIRway wallet after your eligible service was completed.",
            channel=Notification.Channel.IN_APP,
            data={"referral_id": referral.pk, "amount": "100.00", "reward_for": "referred"},
        ),
    ])
    referral.rewarded = True
    referral.reward_status = Referral.RewardStatus.REWARDED
    referral.reward_booking_id = booking.pk
    referral.reward_original_service_charge = original_service_charge.quantize(Decimal("0.01"))
    referral.rewarded_at = timezone.now()
    referral.save(update_fields=[
        "rewarded", "reward_status", "reward_booking_id",
        "reward_original_service_charge", "rewarded_at", "updated_at",
    ])
    return True
