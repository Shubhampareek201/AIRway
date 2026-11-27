from decimal import Decimal

from django.db import transaction

from apps.bookings.models import Booking, BookingAssignment, OrderItem
from apps.accounts.models import Referral

from .models import (
    WorkerRewardWallet,
    WorkerRewardTransaction,
    WorkerJobStreak,
    WorkerProfile,
)


MISSION_REWARDS = {
    5: Decimal("300.00"),
    15: Decimal("600.00"),
    25: Decimal("1000.00"),
}
MINIMUM_SERVICE_COST = Decimal("300.00")
WORKER_REFERRAL_MILESTONE = 5
WORKER_REFERRAL_REWARD = Decimal("150.00")


def _service_line_cost(booking):
    """Return this booking's own service-line subtotal, never the parent order total."""
    line_subtotal = OrderItem.objects.filter(
        booking_id=booking.pk
    ).values_list("line_subtotal", flat=True).first()
    if line_subtotal is not None:
        return Decimal(str(line_subtotal))

    snapshot = booking.pricing_snapshot or {}
    raw = snapshot.get("subtotal", snapshot.get("total", "0.00"))
    try:
        return Decimal(str(raw))
    except Exception:
        return Decimal("0.00")


@transaction.atomic
def award_worker_referral_reward_for_worker(worker, eligible_jobs_count):
    """Credit the referring worker once the invited worker completes five eligible jobs."""
    if eligible_jobs_count < WORKER_REFERRAL_MILESTONE:
        return False

    referral = (
        Referral.objects.select_for_update()
        .select_related("referrer")
        .filter(referred_id=worker.user_id, worker_rewarded=False)
        .first()
    )
    if referral is None:
        return False

    referrer_worker = WorkerProfile.objects.filter(user_id=referral.referrer_id).first()
    if referrer_worker is None:
        return False

    wallet, _ = WorkerRewardWallet.objects.get_or_create(worker=referrer_worker)
    wallet = WorkerRewardWallet.objects.select_for_update().get(pk=wallet.pk)
    transaction_row, created = WorkerRewardTransaction.objects.get_or_create(
        reference_key=f"worker-referral:{referral.pk}:referrer",
        defaults={
            "wallet": wallet,
            "worker": referrer_worker,
            "referral": referral,
            "type": WorkerRewardTransaction.Type.REFERRAL_REWARD,
            "amount": WORKER_REFERRAL_REWARD,
            "description": (
                f"Worker referral reward: invited worker #{worker.pk} "
                f"completed {WORKER_REFERRAL_MILESTONE} eligible jobs"
            ),
        },
    )
    if created:
        wallet.balance += WORKER_REFERRAL_REWARD
        wallet.total_earned += WORKER_REFERRAL_REWARD
        wallet.save(update_fields=["balance", "total_earned", "updated_at"])

    referral.worker_rewarded = True
    referral.worker_rewarded_at = timezone.now()
    referral.save(update_fields=["worker_rewarded", "worker_rewarded_at", "updated_at"])
    return created


@transaction.atomic
def award_mission_reward_for_completed_booking(booking):
    """
    Count one OTP-verified completed service when its own line cost is > ₹300.
    Cumulative rewards are credited exactly once at 5, 15 and 25 eligible jobs.
    """
    if booking.status != Booking.Status.COMPLETED:
        return None

    assignment = BookingAssignment.objects.select_related("worker").filter(
        booking_id=booking.pk
    ).first()
    if assignment is None:
        return None

    service_cost = _service_line_cost(booking)
    if service_cost <= MINIMUM_SERVICE_COST:
        return None

    worker = assignment.worker
    wallet, _ = WorkerRewardWallet.objects.get_or_create(worker=worker)
    wallet = WorkerRewardWallet.objects.select_for_update().get(pk=wallet.pk)

    job_reference = f"completed-booking:{booking.pk}"
    if WorkerRewardTransaction.objects.filter(reference_key=job_reference).exists():
        return wallet

    next_count = wallet.eligible_jobs_count + 1
    WorkerRewardTransaction.objects.create(
        wallet=wallet,
        worker=worker,
        booking=booking,
        type=WorkerRewardTransaction.Type.ELIGIBLE_JOB,
        amount=Decimal("0.00"),
        reference_key=job_reference,
        description=f"Eligible completed service #{booking.pk} (₹{service_cost})",
    )
    wallet.eligible_jobs_count = next_count

    reward = MISSION_REWARDS.get(next_count)
    if reward is not None:
        WorkerRewardTransaction.objects.create(
            wallet=wallet,
            worker=worker,
            type=WorkerRewardTransaction.Type.MISSION_REWARD,
            amount=reward,
            milestone_jobs=next_count,
            reference_key=f"mission-reward:{worker.pk}:{next_count}",
            description=f"{next_count}-job mission reward",
        )
        wallet.balance += reward
        wallet.total_earned += reward
        WorkerJobStreak.objects.get_or_create(
            worker=worker,
            jobs_completed=next_count,
            defaults={"bonus_amount": reward},
        )

    wallet.save(update_fields=[
        "eligible_jobs_count", "balance", "total_earned", "updated_at",
    ])
    award_worker_referral_reward_for_worker(worker, next_count)
    return wallet
