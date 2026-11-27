from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.bookings.models import Booking, BookingAssignment, BookingCompletionOTP, BookingDispute, OrderItem
from apps.accounts.models import Referral
from apps.payments.models import Payment, PaymentRefund

from .models import WorkerRewardWallet, WorkerRewardTransaction, WorkerMonthlyMissionProgress, WorkerProfile

MISSION_REWARDS = {
    5: Decimal("300.00"),
    15: Decimal("600.00"),
    25: Decimal("1000.00"),
}
MINIMUM_SERVICE_COST = Decimal("500.00")
WORKER_REFERRAL_MILESTONE = 5
WORKER_REFERRAL_REWARD = Decimal("150.00")


def _service_line_cost(booking):
    """Original service-line charge before discounts and tax, excluding other order lines."""
    line_subtotal = OrderItem.objects.filter(booking_id=booking.pk).values_list("line_subtotal", flat=True).first()
    if line_subtotal is not None:
        return Decimal(str(line_subtotal))
    snapshot = booking.pricing_snapshot or {}
    try:
        return Decimal(str(snapshot.get("subtotal", snapshot.get("total", "0.00"))))
    except Exception:
        return Decimal("0.00")


def _mission_month(completed_at):
    return timezone.localtime(completed_at).date().replace(day=1)


def _booking_is_verified_completed(booking):
    if booking.status != Booking.Status.COMPLETED or booking.completed_at is None or booking.cancelled_at is not None:
        return False
    otp = BookingCompletionOTP.objects.filter(booking_id=booking.pk).only("verified_at").first()
    if otp is None or otp.verified_at is None:
        return False
    if booking.disputes.filter(status__in=(BookingDispute.Status.OPEN, BookingDispute.Status.IN_REVIEW)).exists():
        return False
    if PaymentRefund.objects.filter(booking_id=booking.pk).exclude(status=PaymentRefund.Status.FAILED).exists():
        return False
    if Payment.objects.filter(status=Payment.Status.REFUNDED).filter(
        Q(booking_id=booking.pk) | Q(order__items__booking_id=booking.pk)
    ).exists():
        return False
    return True


@transaction.atomic
def award_worker_referral_reward_for_worker(worker, eligible_jobs_count, *, booking=None):
    if eligible_jobs_count < WORKER_REFERRAL_MILESTONE:
        return False
    referral = Referral.objects.select_for_update().select_related("referrer").filter(
        referred_id=worker.user_id, worker_rewarded=False
    ).first()
    if referral is None:
        return False
    referrer_worker = WorkerProfile.objects.filter(user_id=referral.referrer_id).first()
    if referrer_worker is None:
        return False
    wallet, _ = WorkerRewardWallet.objects.get_or_create(worker=referrer_worker)
    wallet = WorkerRewardWallet.objects.select_for_update().get(pk=wallet.pk)
    _, created = WorkerRewardTransaction.objects.get_or_create(
        reference_key=f"worker-referral:{referral.pk}:referrer",
        defaults={
            "wallet": wallet, "worker": referrer_worker, "referral": referral, "booking": booking,
            "type": WorkerRewardTransaction.Type.REFERRAL_REWARD, "amount": WORKER_REFERRAL_REWARD,
            "description": f"Worker referral reward: invited worker #{worker.pk} completed {WORKER_REFERRAL_MILESTONE} eligible jobs",
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
    """Award repeatable calendar-month milestones for OTP-verified completed jobs."""
    if not _booking_is_verified_completed(booking):
        return None
    assignment = BookingAssignment.objects.filter(booking_id=booking.pk).first()
    if assignment is None:
        return None
    service_cost = _service_line_cost(booking)
    # Keep the pre-existing worker-referral eligibility (>₹300) independent
    # from the newly approved monthly mission threshold (>₹500).
    if service_cost <= Decimal("300.00"):
        return None

    worker = WorkerProfile.objects.select_for_update().get(pk=assignment.worker_id)
    wallet, _ = WorkerRewardWallet.objects.get_or_create(worker=worker)
    wallet = WorkerRewardWallet.objects.select_for_update().get(pk=wallet.pk)
    monthly_eligible = service_cost > MINIMUM_SERVICE_COST
    month_start = _mission_month(booking.completed_at) if monthly_eligible else None
    month_key = month_start.strftime("%Y-%m") if month_start else None
    job_reference = (
        f"monthly-eligible-job:{worker.pk}:{month_key}:{booking.pk}"
        if monthly_eligible else f"completed-booking:{booking.pk}"
    )
    if WorkerRewardTransaction.objects.filter(reference_key=job_reference).exists():
        return WorkerMonthlyMissionProgress.objects.filter(
            worker=worker, month_start=month_start
        ).first() if monthly_eligible else None

    if monthly_eligible:
        progress, _ = WorkerMonthlyMissionProgress.objects.get_or_create(worker=worker, month_start=month_start)
        progress = WorkerMonthlyMissionProgress.objects.select_for_update().get(pk=progress.pk)
        next_count = progress.eligible_jobs_count + 1
        description = f"Eligible service for {month_key} mission · booking #{booking.pk} · original charge ₹{service_cost}"
        progress.eligible_jobs_count = next_count
        progress.save(update_fields=["eligible_jobs_count", "updated_at"])
    else:
        progress = None
        next_count = None
        description = f"Lifetime referral-eligible completed service #{booking.pk} (₹{service_cost})"

    WorkerRewardTransaction.objects.create(
        wallet=wallet, worker=worker, booking=booking,
        type=WorkerRewardTransaction.Type.ELIGIBLE_JOB, amount=Decimal("0.00"),
        reference_key=job_reference, description=description,
    )
    # This remains a lifetime counter for the existing worker-referral programme.
    wallet.eligible_jobs_count += 1

    reward = MISSION_REWARDS.get(next_count) if monthly_eligible else None
    if reward is not None:
        _, created = WorkerRewardTransaction.objects.get_or_create(
            reference_key=f"monthly-mission-reward:{worker.pk}:{month_key}:{next_count}",
            defaults={
                "wallet": wallet, "worker": worker, "booking": booking,
                "type": WorkerRewardTransaction.Type.MISSION_REWARD, "amount": reward,
                "milestone_jobs": next_count,
                "description": f"{month_key} monthly mission · {next_count} eligible jobs · additional reward ₹{reward}",
            },
        )
        if created:
            wallet.balance += reward
            wallet.total_earned += reward
    wallet.save(update_fields=["eligible_jobs_count", "balance", "total_earned", "updated_at"])
    award_worker_referral_reward_for_worker(worker, wallet.eligible_jobs_count, booking=booking)
    return progress
