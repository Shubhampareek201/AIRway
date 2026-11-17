from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .models import Referral, User
from apps.wallet.models import Wallet, WalletTransaction

REFERRED_SIGNUP_CREDIT = Decimal("149.00")
REFERRER_COMPLETION_CREDIT = Decimal("200.00")


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
    normalized = str(code or "").strip().upper()
    if not normalized:
        raise ValueError("Enter a referral code.")
    referred = User.objects.select_for_update().get(pk=referred_user.pk)
    if Referral.objects.filter(referred=referred).exists():
        raise ValueError("A referral code has already been applied to this account.")
    if referred.referral_code.upper() == normalized:
        raise ValueError("You cannot use your own referral code.")
    if referred.bookings.filter(status="completed").exists():
        raise ValueError("Referral codes can only be applied before your first completed service.")
    referrer = User.objects.filter(referral_code__iexact=normalized, is_active=True).first()
    if referrer is None:
        raise ValueError("This referral code is invalid.")
    if referrer.pk == referred.pk:
        raise ValueError("You cannot use your own referral code.")

    referral = Referral.objects.create(referrer=referrer, referred=referred)
    _credit_wallet(
        referred,
        REFERRED_SIGNUP_CREDIT,
        "AIRway referral welcome credit",
        f"referral:{referral.pk}:referred",
    )
    return referral


@transaction.atomic
def reward_referrer_for_first_completed_booking(booking):
    if booking.status != "completed":
        return False
    if booking.customer.bookings.filter(status="completed").exclude(pk=booking.pk).exists():
        return False
    referral = (
        Referral.objects.select_for_update()
        .select_related("referrer")
        .filter(referred=booking.customer, rewarded=False)
        .first()
    )
    if referral is None:
        return False

    _credit_wallet(
        referral.referrer,
        REFERRER_COMPLETION_CREDIT,
        "Referral reward: friend's first service was completed",
        f"referral:{referral.pk}:referrer",
    )
    referral.rewarded = True
    referral.rewarded_at = timezone.now()
    referral.save(update_fields=["rewarded", "rewarded_at", "updated_at"])
    return True
