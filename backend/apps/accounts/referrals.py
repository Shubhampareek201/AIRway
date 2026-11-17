from decimal import Decimal
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import Referral, User
from apps.wallet.models import Wallet, WalletTransaction

REFERRED_FIRST_SERVICE_CREDIT = Decimal("100.00")
REFERRER_FIRST_SERVICE_CREDIT = Decimal("200.00")


def _credit_wallet(user, amount, description, reference_id):
    wallet, _ = Wallet.objects.get_or_create(user=user)
    wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)
    existing = WalletTransaction.objects.filter(reference_id=reference_id).first()
    if existing:
        return existing
    entry = WalletTransaction.objects.create(
        wallet=wallet,
        type=WalletTransaction.Type.CASHBACK,
        amount=amount,
        description=description,
        status=WalletTransaction.Status.COMPLETED,
        reference_id=reference_id,
    )
    wallet.balance += amount
    wallet.save(update_fields=["balance", "updated_at"])
    return entry


@transaction.atomic
def apply_referral_code(referred_user, code):
    """Attach one valid referrer to a new customer; do not credit either wallet yet."""
    normalized = str(code or "").strip().upper()
    if not normalized:
        raise ValueError("Enter a referral code.")

    referred = User.objects.select_for_update().get(pk=referred_user.pk)
    if Referral.objects.filter(referred=referred).exists():
        raise ValueError("A referral code has already been applied to this account.")
    if referred.referral_code.upper() == normalized:
        raise ValueError("You cannot use your own referral code.")
    if timezone.now() - referred.created_at > timedelta(hours=24):
        raise ValueError("Referral codes must be applied within 24 hours of creating your AIRway account.")
    if referred.bookings.exists():
        raise ValueError("Referral codes can only be applied before your first booking.")

    referrer = User.objects.filter(
        referral_code__iexact=normalized,
        is_active=True,
    ).first()
    if referrer is None:
        raise ValueError("This referral code is invalid.")
    if referrer.pk == referred.pk:
        raise ValueError("You cannot use your own referral code.")

    return Referral.objects.create(referrer=referrer, referred=referred)


@transaction.atomic
def reward_referral_for_first_completed_booking(booking):
    """
    Credit both customers only after the referred customer's first service
    has reached the OTP-verified COMPLETED state. Referral row locking and
    stable transaction references make the reward idempotent.
    """
    if booking.status != "completed":
        return False

    referral = (
        Referral.objects.select_for_update()
        .select_related("referrer", "referred")
        .filter(referred=booking.customer, rewarded=False)
        .first()
    )
    if referral is None:
        return False

    # Check after acquiring the referral lock so concurrent completion requests
    # cannot reward two different bookings for the same referred customer.
    if booking.customer.bookings.filter(status="completed").exclude(pk=booking.pk).exists():
        return False

    _credit_wallet(
        referral.referrer,
        REFERRER_FIRST_SERVICE_CREDIT,
        "Referral reward: your friend's first AIRway service was completed",
        f"referral:{referral.pk}:referrer",
    )
    _credit_wallet(
        referral.referred,
        REFERRED_FIRST_SERVICE_CREDIT,
        "Welcome reward: your first AIRway service was completed",
        f"referral:{referral.pk}:referred:first-service",
    )
    referral.rewarded = True
    referral.rewarded_at = timezone.now()
    referral.save(update_fields=["rewarded", "rewarded_at", "updated_at"])
    return True
