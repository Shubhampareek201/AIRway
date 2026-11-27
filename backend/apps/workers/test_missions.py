from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Address, Referral, User
from apps.bookings.models import Booking, BookingAssignment, BookingCompletionOTP
from apps.catalog.models import Category, Service
from apps.workers.missions import award_mission_reward_for_completed_booking
from apps.workers.models import (
    WorkerProfile,
    WorkerRewardTransaction,
    WorkerRewardWallet,
    WorkerRewardWithdrawal,
    WorkerMonthlyMissionProgress,
    WorkerReferralSettings,
)


class WorkerRewardLedgerTests(TestCase):
    def setUp(self):
        self.referrer_user = User.objects.create_user(phone="+919800001001", name="Referring worker")
        self.referred_user = User.objects.create_user(phone="+919800001002", name="Invited worker")
        self.referrer = WorkerProfile.objects.create(
            user=self.referrer_user, status=WorkerProfile.Status.APPROVED,
        )
        self.referred = WorkerProfile.objects.create(
            user=self.referred_user, status=WorkerProfile.Status.APPROVED,
        )
        self.referral = Referral.objects.create(
            referral_type=Referral.ReferralType.WORKER,
            referrer=self.referrer_user, referred=self.referred_user,
        )
        self.category = Category.objects.create(title="Reward tests", slug="reward-tests")
        self.service = Service.objects.create(
            category=self.category, title="Reward test service", is_active=True,
        )
        self.address = Address.objects.create(
            user=self.referred_user, label="home", house_details="House 1",
            landmark="Near test park", full_address="Reward test address",
        )

    def _completed_eligible_booking(self, index, *, amount="501.00", completed_at=None, status=None, verified=True):
        completed_at = completed_at or timezone.now()
        booking = Booking.objects.create(
            customer=self.referred_user, address=self.address, service=self.service,
            booking_mode=Booking.BookingMode.SCHEDULED,
            scheduled_at=completed_at - timedelta(hours=1),
            status=status or Booking.Status.COMPLETED,
            pricing_snapshot={"subtotal": amount, "discount": "250.00", "total": "251.00"},
            completed_at=completed_at,
        )
        BookingAssignment.objects.create(booking=booking, worker=self.referred, completed_at=completed_at)
        if verified:
            BookingCompletionOTP.objects.create(
                booking=booking, code_hash="verified-test-code",
                expires_at=completed_at + timedelta(hours=1),
                last_sent_at=completed_at, verified_at=completed_at,
            )
        return booking

    def test_mission_and_worker_referral_rewards_are_separate_and_idempotent(self):
        bookings = [self._completed_eligible_booking(i) for i in range(5)]
        for booking in bookings:
            award_mission_reward_for_completed_booking(booking)
        award_mission_reward_for_completed_booking(bookings[-1])

        invited_wallet = WorkerRewardWallet.objects.get(worker=self.referred)
        referrer_wallet = WorkerRewardWallet.objects.get(worker=self.referrer)
        self.assertEqual(invited_wallet.balance, Decimal("300.00"))
        self.assertEqual(referrer_wallet.balance, Decimal("150.00"))
        self.assertEqual(
            WorkerRewardTransaction.objects.filter(
                worker=self.referred,
                type=WorkerRewardTransaction.Type.MISSION_REWARD,
            ).count(),
            1,
        )
        referral_rows = WorkerRewardTransaction.objects.filter(
            worker=self.referrer,
            type=WorkerRewardTransaction.Type.REFERRAL_REWARD,
            referral=self.referral,
        )
        self.assertEqual(referral_rows.count(), 1)
        self.assertEqual(referral_rows.get().reference_key, f"worker-referral:{self.referral.pk}:referrer")
        self.referral.refresh_from_db()
        self.assertTrue(self.referral.worker_rewarded)
        self.assertIsNotNone(self.referral.worker_rewarded_at)

    def test_worker_referral_reward_requires_five_jobs_strictly_over_500(self):
        exact_jobs = [self._completed_eligible_booking(i, amount="500.00") for i in range(5)]
        for booking in exact_jobs:
            award_mission_reward_for_completed_booking(booking)
        self.assertFalse(WorkerRewardWallet.objects.filter(worker=self.referrer).exists())

        over_jobs = [self._completed_eligible_booking(i + 10, amount="500.01") for i in range(5)]
        for booking in over_jobs:
            award_mission_reward_for_completed_booking(booking)
        self.assertEqual(WorkerRewardWallet.objects.get(worker=self.referrer).balance, Decimal("150.00"))

    def test_worker_referral_reward_uses_admin_configured_amount(self):
        WorkerReferralSettings.objects.create(reward_amount=Decimal("250.00"))
        for i in range(5):
            award_mission_reward_for_completed_booking(self._completed_eligible_booking(i))
        self.assertEqual(WorkerRewardWallet.objects.get(worker=self.referrer).balance, Decimal("250.00"))

    def test_worker_referral_reward_waits_for_approved_referrer(self):
        self.referrer.status = WorkerProfile.Status.SUSPENDED
        self.referrer.save(update_fields=["status", "updated_at"])
        for i in range(5):
            award_mission_reward_for_completed_booking(self._completed_eligible_booking(i))
        self.assertFalse(WorkerRewardWallet.objects.filter(worker=self.referrer).exists())
        self.referral.refresh_from_db()
        self.assertFalse(self.referral.worker_rewarded)

    def test_monthly_mission_uses_original_charge_and_requires_strictly_more_than_500(self):
        exactly_500 = self._completed_eligible_booking(1, amount="500.00")
        over_500 = self._completed_eligible_booking(2, amount="500.01")
        award_mission_reward_for_completed_booking(exactly_500)
        award_mission_reward_for_completed_booking(over_500)
        progress = WorkerMonthlyMissionProgress.objects.get(worker=self.referred)
        self.assertEqual(progress.eligible_jobs_count, 1)

    def test_monthly_milestones_are_repeatable_and_history_is_preserved(self):
        now = timezone.now()
        bookings = [self._completed_eligible_booking(i, completed_at=now) for i in range(25)]
        for booking in bookings:
            award_mission_reward_for_completed_booking(booking)
        month_start = timezone.localdate(now).replace(day=1)
        current = WorkerMonthlyMissionProgress.objects.get(worker=self.referred, month_start=month_start)
        self.assertEqual(current.eligible_jobs_count, 25)
        rewards = {
            row.milestone_jobs: row.amount
            for row in WorkerRewardTransaction.objects.filter(
                worker=self.referred, type=WorkerRewardTransaction.Type.MISSION_REWARD,
                reference_key__startswith=f"monthly-mission-reward:{self.referred.pk}:",
            )
        }
        self.assertEqual(rewards, {5: Decimal("300.00"), 15: Decimal("600.00"), 25: Decimal("1000.00")})
        self.assertEqual(sum(rewards.values()), Decimal("1900.00"))
        next_month_at = (now + timedelta(days=35)).replace(day=1)
        next_booking = self._completed_eligible_booking(26, completed_at=next_month_at)
        award_mission_reward_for_completed_booking(next_booking)
        next_month = WorkerMonthlyMissionProgress.objects.get(worker=self.referred, month_start=next_month_at.date().replace(day=1))
        current.refresh_from_db()
        self.assertEqual(current.eligible_jobs_count, 25)
        self.assertEqual(next_month.eligible_jobs_count, 1)
        self.assertEqual(WorkerRewardTransaction.objects.filter(worker=self.referred, type=WorkerRewardTransaction.Type.MISSION_REWARD).count(), 3)

    def test_unverified_cancelled_or_refunded_bookings_do_not_count(self):
        unverified = self._completed_eligible_booking(1, verified=False)
        cancelled = self._completed_eligible_booking(2, status=Booking.Status.CANCELLED)
        refunded = self._completed_eligible_booking(3)
        from apps.payments.models import Payment, PaymentRefund
        payment = Payment.objects.create(
            booking=refunded, customer=self.referred_user,
            amount=Decimal("501.00"), status=Payment.Status.PAID,
        )
        PaymentRefund.objects.create(
            payment=payment, booking=refunded, amount=Decimal("501.00"),
            reason=PaymentRefund.Reason.CUSTOMER_CANCELLATION,
            status=PaymentRefund.Status.PROCESSING,
        )
        for booking in (unverified, cancelled, refunded):
            award_mission_reward_for_completed_booking(booking)
        self.assertFalse(WorkerMonthlyMissionProgress.objects.filter(worker=self.referred).exists())

    def test_reward_wallet_withdrawal_retries_are_idempotent(self):
        wallet = WorkerRewardWallet.objects.create(
            worker=self.referred, balance=Decimal("200.00"),
            total_earned=Decimal("200.00"),
        )
        self.referred.upi_id = "worker@upi"
        self.referred.save(update_fields=["upi_id", "updated_at"])
        client = APIClient()
        client.force_authenticate(user=self.referred_user)
        first = client.post(
            "/api/v1/workers/mission-wallet/",
            {"amount": "200.00"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="worker-withdrawal-1",
        )
        second = client.post(
            "/api/v1/workers/mission-wallet/",
            {"amount": "200.00"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="worker-withdrawal-1",
        )
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(second.status_code, 200, second.data)
        self.assertEqual(first.data["id"], second.data["id"])
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, Decimal("0.00"))
        self.assertEqual(WorkerRewardWithdrawal.objects.filter(worker=self.referred).count(), 1)
        self.assertEqual(WorkerRewardTransaction.objects.filter(
            worker=self.referred,
            type=WorkerRewardTransaction.Type.WITHDRAWAL,
        ).count(), 1)

    def test_reward_withdrawal_requires_idempotency_key(self):
        wallet = WorkerRewardWallet.objects.create(
            worker=self.referred, balance=Decimal("100.00"),
            total_earned=Decimal("100.00"),
        )
        self.referred.upi_id = "worker@upi"
        self.referred.save(update_fields=["upi_id", "updated_at"])
        client = APIClient()
        client.force_authenticate(user=self.referred_user)

        response = client.post(
            "/api/v1/workers/mission-wallet/",
            {"amount": "50.00"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(wallet.__class__.objects.get(pk=wallet.pk).balance, Decimal("100.00"))
        self.assertFalse(WorkerRewardWithdrawal.objects.filter(worker=self.referred).exists())

    def test_reward_wallet_api_returns_auditable_transaction_references(self):
        wallet = WorkerRewardWallet.objects.create(worker=self.referred, balance=Decimal("150.00"))
        WorkerRewardTransaction.objects.create(
            wallet=wallet, worker=self.referred,
            type=WorkerRewardTransaction.Type.MISSION_REWARD,
            amount=Decimal("150.00"),
            reference_key="mission-reward:worker:5",
            description="Mission reward",
        )
        client = APIClient()
        client.force_authenticate(user=self.referred_user)
        response = client.get("/api/v1/workers/mission-wallet/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["transactions"][0]["reference_key"], "mission-reward:worker:5")
        self.assertEqual(response.data["transactions"][0]["type_display"], "Mission reward")
        self.assertEqual(response.data["monthly_eligible_jobs_count"], 0)
        self.assertEqual(response.data["minimum_original_service_charge"], "500.00")
        self.assertEqual(
            [(item["jobs"], item["reward"], item["achieved"]) for item in response.data["milestones"]],
            [(5, "300.00", False), (15, "600.00", False), (25, "1000.00", False)],
        )
        self.assertIsNone(response.data["transactions_next_offset"])
        self.assertIsNone(response.data["withdrawals_next_offset"])

    def test_reward_wallet_history_paginates_without_skipping_or_repeating_rows(self):
        wallet = WorkerRewardWallet.objects.create(worker=self.referred)
        for index in range(55):
            WorkerRewardTransaction.objects.create(
                wallet=wallet,
                worker=self.referred,
                type=WorkerRewardTransaction.Type.MISSION_REWARD,
                amount=Decimal("10.00"),
                reference_key=f"history-mission:{index}",
                description=f"Mission reward {index}",
            )
        for _ in range(22):
            WorkerRewardWithdrawal.objects.create(
                wallet=wallet,
                worker=self.referred,
                amount=Decimal("5.00"),
                payout_upi_id="worker@upi",
            )

        client = APIClient()
        client.force_authenticate(user=self.referred_user)
        first = client.get("/api/v1/workers/reward-wallet/")
        second = client.get(
            "/api/v1/workers/reward-wallet/?transaction_offset=50&withdrawal_offset=20"
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(len(first.data["transactions"]), 50)
        self.assertEqual(first.data["transactions_next_offset"], 50)
        self.assertEqual(len(first.data["withdrawals"]), 20)
        self.assertEqual(first.data["withdrawals_next_offset"], 20)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(len(second.data["transactions"]), 5)
        self.assertIsNone(second.data["transactions_next_offset"])
        self.assertEqual(len(second.data["withdrawals"]), 2)
        self.assertIsNone(second.data["withdrawals_next_offset"])
        first_ids = {row["id"] for row in first.data["transactions"]}
        second_ids = {row["id"] for row in second.data["transactions"]}
        self.assertFalse(first_ids & second_ids)
        self.assertEqual(len(first_ids | second_ids), 55)
        first_withdrawals = {row["id"] for row in first.data["withdrawals"]}
        second_withdrawals = {row["id"] for row in second.data["withdrawals"]}
        self.assertFalse(first_withdrawals & second_withdrawals)
        self.assertEqual(len(first_withdrawals | second_withdrawals), 22)
        self.assertTrue(all(row["reference_key"] for row in first.data["transactions"] + second.data["transactions"]))

    def test_reward_wallet_rejects_negative_history_offsets(self):
        client = APIClient()
        client.force_authenticate(user=self.referred_user)
        response = client.get("/api/v1/workers/reward-wallet/?transaction_offset=-1")
        self.assertEqual(response.status_code, 400)
