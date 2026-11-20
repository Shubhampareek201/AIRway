from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Address, User
from apps.catalog.models import Category, Service
from apps.bookings.models import Booking, BookingAssignment
from apps.payments.models import Payment, PaymentRefund
from apps.workers.earnings import sync_worker_earning
from apps.workers.models import WorkerEarning, WorkerProfile
from apps.wallet.models import Wallet, WalletTransaction


class WorkerEarningLedgerTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(phone="+919800000101", name="Customer")
        self.worker_user = User.objects.create_user(phone="+919800000102", name="Worker")
        self.worker = WorkerProfile.objects.create(
            user=self.worker_user,
            status=WorkerProfile.Status.APPROVED,
            commission_rate=Decimal("20.00"),
        )
        category = Category.objects.create(title="Earning tests", slug="earning-tests")
        service = Service.objects.create(category=category, title="Test service", is_active=True)
        address = Address.objects.create(
            user=self.customer,
            label="home",
            house_details="House 1",
            landmark="Near test park",
            full_address="Test address",
        )
        self.booking = Booking.objects.create(
            customer=self.customer,
            address=address,
            service=service,
            booking_mode=Booking.BookingMode.SCHEDULED,
            scheduled_at=timezone.now() + timedelta(days=1),
            status=Booking.Status.COMPLETED,
            pricing_snapshot={"total": "100.00"},
            completed_at=timezone.now(),
        )
        BookingAssignment.objects.create(
            booking=self.booking,
            worker=self.worker,
            completed_at=timezone.now(),
        )
        self.payment = Payment.objects.create(
            booking=self.booking,
            customer=self.customer,
            stage=Payment.Stage.LEGACY,
            amount=Decimal("100.00"),
            status=Payment.Status.PAID,
            paid_at=timezone.now(),
        )

    def test_verified_settlement_creates_net_worker_earning_once(self):
        first = sync_worker_earning(self.booking.pk, self.payment.pk)
        second = sync_worker_earning(self.booking.pk, self.payment.pk)

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(WorkerEarning.objects.filter(booking=self.booking).count(), 1)
        self.assertEqual(first.gross_amount, Decimal("100.00"))
        self.assertEqual(first.commission_rate, Decimal("20.00"))
        self.assertEqual(first.commission_amount, Decimal("20.00"))
        self.assertEqual(first.net_amount, Decimal("80.00"))
        self.assertEqual(first.status, WorkerEarning.Status.AVAILABLE)

    def test_worker_api_returns_calculated_ledger_not_customer_gross(self):
        earning = sync_worker_earning(self.booking.pk, self.payment.pk)
        client = APIClient()
        client.force_authenticate(user=self.worker_user)

        response = client.get("/api/v1/workers/earnings/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["gross_amount"], "100.00")
        self.assertEqual(response.data[0]["commission_amount"], "20.00")
        self.assertEqual(response.data[0]["net_amount"], "80.00")
        self.assertEqual(response.data[0]["status"], WorkerEarning.Status.AVAILABLE)

    def test_commission_snapshot_is_not_rewritten_after_rate_change(self):
        earning = sync_worker_earning(self.booking.pk, self.payment.pk)
        self.worker.commission_rate = Decimal("30.00")
        self.worker.save(update_fields=["commission_rate", "updated_at"])

        retried = sync_worker_earning(self.booking.pk, self.payment.pk)

        self.assertEqual(retried.commission_rate, Decimal("20.00"))
        self.assertEqual(retried.commission_amount, Decimal("20.00"))
        self.assertEqual(retried.net_amount, Decimal("80.00"))

    def test_manual_adjustment_is_preserved_on_idempotent_sync(self):
        earning = sync_worker_earning(self.booking.pk, self.payment.pk)
        earning.adjustment_amount = Decimal("-5.00")
        earning.adjustment_note = "Finance refund reconciliation"
        earning.save(update_fields=["adjustment_amount", "adjustment_note", "updated_at"])

        retried = sync_worker_earning(self.booking.pk, self.payment.pk)

        self.assertEqual(retried.net_amount, Decimal("75.00"))
        self.assertEqual(retried.adjustment_amount, Decimal("-5.00"))

    def test_missing_commission_rate_holds_earning_without_guessing_net(self):
        self.worker.commission_rate = None
        self.worker.save(update_fields=["commission_rate", "updated_at"])

        earning = sync_worker_earning(self.booking.pk, self.payment.pk)

        self.assertEqual(earning.status, WorkerEarning.Status.ON_HOLD)
        self.assertIsNone(earning.net_amount)
        self.assertIn("Commission rate", earning.hold_reason)

    def test_refund_in_progress_holds_worker_earning(self):
        PaymentRefund.objects.create(
            payment=self.payment,
            booking=self.booking,
            amount=Decimal("10.00"),
            wallet_amount=Decimal("10.00"),
            gateway_amount=Decimal("0.00"),
            reason=PaymentRefund.Reason.ADMIN_ADJUSTMENT,
            status=PaymentRefund.Status.PENDING,
        )

        earning = sync_worker_earning(self.booking.pk, self.payment.pk)

        self.assertEqual(earning.status, WorkerEarning.Status.ON_HOLD)
        self.assertEqual(earning.net_amount, Decimal("80.00"))
        self.assertIn("refund", earning.hold_reason.lower())

    def test_commission_is_snapshotted_while_refund_hold_is_active(self):
        self.worker.commission_rate = None
        self.worker.save(update_fields=["commission_rate", "updated_at"])
        refund = PaymentRefund.objects.create(
            payment=self.payment,
            booking=self.booking,
            amount=Decimal("10.00"),
            wallet_amount=Decimal("10.00"),
            gateway_amount=Decimal("0.00"),
            reason=PaymentRefund.Reason.ADMIN_ADJUSTMENT,
            status=PaymentRefund.Status.PENDING,
        )
        earning = sync_worker_earning(self.booking.pk, self.payment.pk)
        self.assertEqual(earning.status, WorkerEarning.Status.ON_HOLD)
        self.assertIsNone(earning.commission_amount)

        self.worker.commission_rate = Decimal("20.00")
        self.worker.save(update_fields=["commission_rate", "updated_at"])
        earning = sync_worker_earning(self.booking.pk, self.payment.pk)
        self.assertEqual(earning.status, WorkerEarning.Status.ON_HOLD)
        self.assertEqual(earning.commission_amount, Decimal("20.00"))
        self.assertEqual(earning.net_amount, Decimal("80.00"))

        refund.status = PaymentRefund.Status.FAILED
        refund.save(update_fields=["status", "updated_at"])
        earning = sync_worker_earning(self.booking.pk, self.payment.pk)
        self.assertEqual(earning.status, WorkerEarning.Status.AVAILABLE)
        self.assertEqual(earning.net_amount, Decimal("80.00"))

    def test_unpaid_or_incomplete_booking_does_not_create_earning(self):
        self.payment.status = Payment.Status.PENDING
        self.payment.save(update_fields=["status", "updated_at"])

        self.assertIsNone(sync_worker_earning(self.booking.pk, self.payment.pk))
        self.assertFalse(WorkerEarning.objects.filter(booking=self.booking).exists())

    def test_worker_earnings_api_does_not_count_unrelated_wallet_credits(self):
        wallet, _ = Wallet.objects.get_or_create(user=self.worker_user)
        WalletTransaction.objects.create(
            wallet=wallet,
            type=WalletTransaction.Type.CREDIT,
            amount=Decimal("500.00"),
            description="Unrelated wallet credit",
            status=WalletTransaction.Status.COMPLETED,
        )
        client = APIClient()
        client.force_authenticate(user=self.worker_user)

        response = client.get("/api/v1/workers/earnings/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])
