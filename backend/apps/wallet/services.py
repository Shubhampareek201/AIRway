from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .models import Wallet, WalletReservation, WalletTransaction


CENT = Decimal("0.01")


def reserve_wallet_amount(payment, amount):
    """Hold wallet funds for a parent-order payment exactly once."""
    amount = Decimal(str(amount)).quantize(CENT)
    if amount < 0 or amount != Decimal(str(amount)):
        raise ValueError("Wallet amount must be a non-negative amount with at most two decimals.")
    if amount == 0:
        return None

    with transaction.atomic():
        locked_payment = payment.__class__.objects.select_for_update().get(pk=payment.pk)
        existing = WalletReservation.objects.select_for_update().filter(payment=locked_payment).first()
        if existing:
            if existing.amount != amount:
                raise ValueError("A different wallet amount is already reserved for this order.")
            if existing.status == WalletReservation.Status.RELEASED:
                raise ValueError("The previous wallet reservation was released. Start a new payment attempt.")
            return existing

        wallet, _ = Wallet.objects.get_or_create(user=locked_payment.customer)
        wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)
        if amount > wallet.balance:
            raise ValueError("Insufficient wallet balance.")

        wallet.balance -= amount
        wallet.pending_balance += amount
        wallet.save(update_fields=["balance", "pending_balance", "updated_at"])

        wallet_tx = WalletTransaction.objects.create(
            wallet=wallet,
            type=WalletTransaction.Type.DEBIT,
            amount=amount,
            description=f"Wallet amount reserved for AIRway order #{locked_payment.order_id}",
            status=WalletTransaction.Status.PENDING,
            reference_id=f"payment:{locked_payment.pk}",
        )
        reservation = WalletReservation.objects.create(
            wallet=wallet,
            payment=locked_payment,
            amount=amount,
            status=WalletReservation.Status.RESERVED,
        )
        return reservation


def capture_wallet_reservation(payment, razorpay_payment_id=""):
    """Finalize a held wallet debit after the order payment succeeds."""
    with transaction.atomic():
        reservation = WalletReservation.objects.select_for_update().filter(
            payment=payment
        ).first()
        if reservation is None or reservation.status == WalletReservation.Status.CAPTURED:
            return reservation
        if reservation.status == WalletReservation.Status.RELEASED:
            raise ValueError("Wallet reservation was already released and cannot be captured.")

        wallet = Wallet.objects.select_for_update().get(pk=reservation.wallet_id)
        wallet.pending_balance = max(Decimal("0.00"), wallet.pending_balance - reservation.amount)
        wallet.save(update_fields=["pending_balance", "updated_at"])

        WalletTransaction.objects.filter(
            wallet=wallet,
            reference_id=f"payment:{payment.pk}",
            type=WalletTransaction.Type.DEBIT,
            status=WalletTransaction.Status.PENDING,
        ).update(
            status=WalletTransaction.Status.COMPLETED,
            razorpay_payment_id=razorpay_payment_id,
        )
        reservation.status = WalletReservation.Status.CAPTURED
        reservation.captured_at = timezone.now()
        reservation.save(update_fields=["status", "captured_at", "updated_at"])
        return reservation


def release_wallet_reservation(payment, reason="Payment attempt expired"):
    """Release held funds once when the parent-order payment is abandoned."""
    with transaction.atomic():
        reservation = WalletReservation.objects.select_for_update().filter(
            payment=payment
        ).first()
        if reservation is None or reservation.status != WalletReservation.Status.RESERVED:
            return reservation

        wallet = Wallet.objects.select_for_update().get(pk=reservation.wallet_id)
        wallet.balance += reservation.amount
        wallet.pending_balance = max(Decimal("0.00"), wallet.pending_balance - reservation.amount)
        wallet.save(update_fields=["balance", "pending_balance", "updated_at"])

        WalletTransaction.objects.filter(
            wallet=wallet,
            reference_id=f"payment:{payment.pk}",
            type=WalletTransaction.Type.DEBIT,
            status=WalletTransaction.Status.PENDING,
        ).update(
            status=WalletTransaction.Status.FAILED,
            description=reason[:255],
        )
        reservation.status = WalletReservation.Status.RELEASED
        reservation.released_at = timezone.now()
        reservation.save(update_fields=["status", "released_at", "updated_at"])
        return reservation
