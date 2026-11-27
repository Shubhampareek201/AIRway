from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Address, Referral, User
from apps.bookings.models import Booking, BookingAssignment
from apps.catalog.models import Category, Service
from apps.workers.missions import award_mission_reward_for_completed_booking
from apps.workers.models import (
    WorkerProfile,
    WorkerRewardTransaction,
    WorkerRewardWallet,
    WorkerRewardWithdrawal,
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

    def _completed_eligible_booking(self, index):
        booking = Booking.objects.create(
            customer=self.referred_user,
            address=self.address,
            service=self.service,
            booking_mode=Booking.BookingMode.SCHEDULED,
            scheduled_at=timezone.now() - timedelta(hours=1),
            status=Booking.Status.COMPLETED,
            pricing_snapshot={"subtotal": "400.00"},
            completed_at=timezone.now(),
        )
        BookingAssignment.objects.create(
            booking=booking, worker=self.referred, completed_at=timezone.now(),
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
