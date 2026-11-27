from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Address, User
from apps.catalog.models import Category, Service
from apps.bookings.models import Booking, BookingAssignment, BookingExtraWork, Order, OrderItem
from apps.payments.models import Payment, PaymentRefund
from apps.workers.earnings import (
    calculate_worker_earning_net,
    create_weekly_worker_settlements,
    mark_worker_payout_settlement_paid,
    sync_worker_earning,
)
from apps.workers.models import WorkerEarning, WorkerPayoutSettlement, WorkerProfile
from apps.wallet.models import Wallet, WalletTransaction


class WorkerEarningNetCalculationTests(TestCase):
    def test_fixed_payout_above_customer_gross_is_preserved_on_release(self):
        earning = type("Earning", (), {
            "booking": type("BookingSnapshot", (), {
                "worker_payout_snapshot": {
                    "pricing_model": "fixed_service_payout_v1",
                    "total": "120.00",
                }
            })(),
            "adjustment_amount": Decimal("0.00"),
            "gross_amount": Decimal("100.00"),
            "commission_amount": Decimal("0.00"),
        })()
        self.assertEqual(calculate_worker_earning_net(earning), Decimal("120.00"))

    def test_fixed_payout_release_keeps_audited_adjustment(self):
        earning = type("Earning", (), {
            "booking": type("BookingSnapshot", (), {
                "worker_payout_snapshot": {
                    "pricing_model": "admin_approved_quote_payout_v1",
                    "total": "120.00",
                }
            })(),
            "adjustment_amount": Decimal("-10.00"),
            "gross_amount": Decimal("100.00"),
            "commission_amount": Decimal("0.00"),
        })()
        self.assertEqual(calculate_worker_earning_net(earning), Decimal("110.00"))

    def test_legacy_commission_earning_keeps_existing_calculation(self):
        earning = type("Earning", (), {
            "booking": type("BookingSnapshot", (), {"worker_payout_snapshot": {}})(),
            "adjustment_amount": Decimal("-5.00"),
            "gross_amount": Decimal("100.00"),
            "commission_amount": Decimal("20.00"),
        })()
        self.assertEqual(calculate_worker_earning_net(earning), Decimal("75.00"))


class WorkerEarningLedgerTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(phone="+919800000101", name="Customer")
        self.worker_user = User.objects.create_user(phone="+919800000102", name="Worker")
        self.admin_user = User.objects.create_user(phone="+919800000103", name="Finance admin", is_staff=True)
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
        self.assertIsNotNone(first.available_at)


    def test_weekly_settlement_groups_earnings_and_pays_them_once(self):
        first_earning = sync_worker_earning(self.booking.pk, self.payment.pk)
        second_booking = Booking.objects.create(
            customer=self.customer,
            address=self.booking.address,
            service=self.booking.service,
            booking_mode=Booking.BookingMode.SCHEDULED,
            scheduled_at=timezone.now() + timedelta(days=1),
            status=Booking.Status.COMPLETED,
            pricing_snapshot={"total": "200.00"},
            completed_at=timezone.now(),
        )
        BookingAssignment.objects.create(
            booking=second_booking, worker=self.worker, completed_at=timezone.now(),
        )
        second_payment = Payment.objects.create(
            booking=second_booking, customer=self.customer,
            stage=Payment.Stage.LEGACY, amount=Decimal("200.00"),
            status=Payment.Status.PAID, paid_at=timezone.now(),
        )
        second_earning = sync_worker_earning(second_booking.pk, second_payment.pk)

        batches = create_weekly_worker_settlements(
            [first_earning.pk, second_earning.pk], created_by=self.admin_user,
        )
        self.assertEqual(len(batches), 1)
        batch = batches[0]
        self.assertEqual(batch.worker, self.worker)
        self.assertEqual(batch.total_amount, first_earning.net_amount + second_earning.net_amount)
        self.assertEqual(batch.earnings.count(), 2)
        self.assertEqual(create_weekly_worker_settlements(
            [first_earning.pk, second_earning.pk], created_by=self.admin_user,
        ), [])

        mark_worker_payout_settlement_paid(batch.pk, "UPI-WEEK-001", self.admin_user)
        batch.refresh_from_db()
        first_earning.refresh_from_db()
        second_earning.refresh_from_db()
        self.assertEqual(batch.status, WorkerPayoutSettlement.Status.PAID)
        self.assertEqual(batch.payout_reference, "UPI-WEEK-001")
        self.assertEqual(first_earning.status, WorkerEarning.Status.PAID)
        self.assertEqual(second_earning.status, WorkerEarning.Status.PAID)
        self.assertEqual(first_earning.payout_reference, "UPI-WEEK-001")
        self.assertEqual(second_earning.payout_reference, "UPI-WEEK-001")
        retried = mark_worker_payout_settlement_paid(batch.pk, "UPI-WEEK-001", self.admin_user)
        self.assertEqual(retried.pk, batch.pk)


    def test_weekly_settlement_is_visible_in_worker_api_and_admin_report(self):
        earning = sync_worker_earning(self.booking.pk, self.payment.pk)
        batch = create_weekly_worker_settlements(
            [earning.pk], created_by=self.admin_user,
        )[0]

        worker_client = APIClient()
        worker_client.force_authenticate(user=self.worker_user)
        response = worker_client.get("/api/v1/workers/earnings/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"][0]["settlement_batch_id"], batch.pk)
        self.assertEqual(
            response.data["results"][0]["settlement_period_start"],
            batch.period_start.isoformat(),
        )

        from django.contrib.auth.models import Permission
        from django.test import Client
        from django.urls import reverse

        permission = Permission.objects.get(
            content_type__app_label="workers",
            codename="manage_worker_payouts",
        )
        self.admin_user.user_permissions.add(permission)
        admin_client = Client()
        admin_client.force_login(self.admin_user)
        admin_response = admin_client.get(
            reverse("admin:workers_workerpayoutsettlement_change", args=[batch.pk])
        )
        self.assertEqual(admin_response.status_code, 200)
        self.assertContains(admin_response, str(self.booking.pk))

    def test_worker_api_returns_calculated_ledger_not_customer_gross(self):
        earning = sync_worker_earning(self.booking.pk, self.payment.pk)
        client = APIClient()
        client.force_authenticate(user=self.worker_user)

        response = client.get("/api/v1/workers/earnings/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertIsNone(response.data["next_offset"])
        self.assertEqual(response.data["results"][0]["gross_amount"], "100.00")
        self.assertEqual(response.data["results"][0]["commission_amount"], "20.00")
        self.assertEqual(response.data["results"][0]["net_amount"], "80.00")
        self.assertEqual(response.data["results"][0]["status"], WorkerEarning.Status.AVAILABLE)

    def test_worker_earning_history_paginates_with_stable_order_and_no_duplicates(self):
        sync_worker_earning(self.booking.pk, self.payment.pk)
        for index in range(51):
            booking = Booking.objects.create(
                customer=self.customer,
                address=self.booking.address,
                service=self.booking.service,
                booking_mode=Booking.BookingMode.SCHEDULED,
                scheduled_at=timezone.now() + timedelta(days=index + 2),
                status=Booking.Status.COMPLETED,
                pricing_snapshot={"total": "100.00"},
                completed_at=timezone.now(),
            )
            BookingAssignment.objects.create(
                booking=booking, worker=self.worker, completed_at=timezone.now(),
            )
            WorkerEarning.objects.create(
                worker=self.worker, booking=booking,
                gross_amount=Decimal("100.00"),
                commission_rate=Decimal("20.00"),
                commission_amount=Decimal("20.00"),
                net_amount=Decimal("80.00"),
                status=WorkerEarning.Status.AVAILABLE,
            )

        client = APIClient()
        client.force_authenticate(user=self.worker_user)
        first_page = client.get("/api/v1/workers/earnings/")
        second_page = client.get("/api/v1/workers/earnings/?offset=50")

        self.assertEqual(first_page.status_code, 200)
        self.assertEqual(len(first_page.data["results"]), 50)
        self.assertEqual(first_page.data["next_offset"], 50)
        self.assertEqual(second_page.status_code, 200)
        self.assertEqual(len(second_page.data["results"]), 2)
        self.assertIsNone(second_page.data["next_offset"])
        first_ids = {row["id"] for row in first_page.data["results"]}
        second_ids = {row["id"] for row in second_page.data["results"]}
        self.assertFalse(first_ids & second_ids)
        self.assertEqual(len(first_ids | second_ids), 52)
        self.assertTrue(all(row["earning_reference"] for row in first_page.data["results"] + second_page.data["results"]))

    def test_worker_earning_history_rejects_negative_offset(self):
        client = APIClient()
        client.force_authenticate(user=self.worker_user)
        response = client.get("/api/v1/workers/earnings/?offset=-1")
        self.assertEqual(response.status_code, 400)

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

    def test_separately_paid_extra_work_gets_its_own_worker_earning(self):
        order = Order.objects.create(
            customer=self.customer,
            address=self.booking.address,
            total_amount=Decimal("118.00"),
        )
        OrderItem.objects.create(
            order=order,
            booking=self.booking,
            quantity=1,
            line_subtotal=Decimal("100.00"),
            tax_amount=Decimal("18.00"),
            line_total=Decimal("118.00"),
        )
        base_payment = Payment.objects.create(
            order=order,
            customer=self.customer,
            stage=Payment.Stage.BALANCE,
            amount=Decimal("118.00"),
            status=Payment.Status.PAID,
            paid_at=timezone.now(),
        )
        service_earning = sync_worker_earning(self.booking.pk, base_payment.pk)
        self.assertEqual(service_earning.gross_amount, Decimal("100.00"))

        proposal = BookingExtraWork.objects.create(
            booking=self.booking,
            worker=self.worker,
            reason="Additional room cleaning",
            line_items=[{"description": "Extra room", "quantity": 1, "unit_price": "25.00", "line_total": "25.00"}],
            subtotal=Decimal("25.00"),
            tax_amount=Decimal("0.00"),
            total_amount=Decimal("25.00"),
            status=BookingExtraWork.Status.APPROVED,
            payment_choice=BookingExtraWork.PaymentChoice.SEPARATE,
            payment_status="pending",
        )
        extra_payment = Payment.objects.create(
            order=order,
            extra_work=proposal,
            customer=self.customer,
            stage=Payment.Stage.EXTRA_WORK,
            amount=Decimal("25.00"),
            status=Payment.Status.PAID,
            paid_at=timezone.now(),
        )
        proposal.payment_status = "paid"
        proposal.save(update_fields=["payment_status", "updated_at"])

        extra_earning = sync_worker_earning(self.booking.pk, extra_payment.pk)

        self.assertEqual(extra_earning.extra_work_id, proposal.pk)
        self.assertEqual(extra_earning.gross_amount, Decimal("25.00"))
        self.assertEqual(extra_earning.net_amount, Decimal("20.00"))
        self.assertEqual(
            WorkerEarning.objects.filter(booking=self.booking).count(),
            2,
        )


    def test_fixed_pricing_extra_work_uses_its_own_snapshotted_payout(self):
        order = Order.objects.create(
            customer=self.customer,
            address=self.booking.address,
            total_amount=Decimal("1180.00"),
        )
        OrderItem.objects.create(
            order=order,
            booking=self.booking,
            quantity=1,
            line_subtotal=Decimal("1000.00"),
            tax_amount=Decimal("180.00"),
            line_total=Decimal("1180.00"),
        )
        self.booking.worker_payout_snapshot = {
            "pricing_model": "fixed_service_payout_v1",
            "total": "600.00",
        }
        self.booking.save(update_fields=["worker_payout_snapshot", "updated_at"])
        base_payment = Payment.objects.create(
            order=order, customer=self.customer,
            stage=Payment.Stage.BALANCE, amount=Decimal("1180.00"),
            status=Payment.Status.PAID, paid_at=timezone.now(),
        )
        proposal = BookingExtraWork.objects.create(
            booking=self.booking,
            worker=self.worker,
            reason="Extra room",
            line_items=[{"description": "Extra room", "quantity": 1, "unit_price": "250.00", "line_total": "250.00"}],
            subtotal=Decimal("250.00"),
            worker_payout_amount=Decimal("150.00"),
            worker_payout_snapshot={
                "pricing_model": "booking_fixed_payout_ratio_v1",
                "payout_ratio": "0.6",
                "worker_payout_amount": "150.00",
            },
            total_amount=Decimal("250.00"),
            status=BookingExtraWork.Status.APPROVED,
            payment_choice=BookingExtraWork.PaymentChoice.SEPARATE,
            payment_status="paid",
        )
        extra_payment = Payment.objects.create(
            order=order, extra_work=proposal, customer=self.customer,
            stage=Payment.Stage.EXTRA_WORK, amount=Decimal("250.00"),
            status=Payment.Status.PAID, paid_at=timezone.now(),
        )

        earning = sync_worker_earning(self.booking.pk, extra_payment.pk)

        self.assertEqual(earning.extra_work_id, proposal.pk)
        self.assertEqual(earning.gross_amount, Decimal("250.00"))
        self.assertEqual(earning.net_amount, Decimal("150.00"))
        self.assertEqual(earning.commission_amount, Decimal("100.00"))
        self.assertEqual(WorkerEarning.objects.filter(extra_work=proposal).count(), 1)


    def test_held_extra_work_release_uses_its_own_payout_snapshot(self):
        order = Order.objects.create(
            customer=self.customer,
            address=self.booking.address,
            total_amount=Decimal("1180.00"),
        )
        OrderItem.objects.create(
            order=order, booking=self.booking, quantity=1,
            line_subtotal=Decimal("1000.00"),
            tax_amount=Decimal("180.00"),
            line_total=Decimal("1180.00"),
        )
        self.booking.worker_payout_snapshot = {
            "pricing_model": "fixed_service_payout_v1",
            "total": "600.00",
        }
        self.booking.save(update_fields=["worker_payout_snapshot", "updated_at"])
        base_payment = Payment.objects.create(
            order=order, customer=self.customer,
            stage=Payment.Stage.BALANCE, amount=Decimal("1180.00"),
            status=Payment.Status.PAID, paid_at=timezone.now(),
        )
        proposal = BookingExtraWork.objects.create(
            booking=self.booking, worker=self.worker, reason="Extra room",
            line_items=[{"description": "Extra room", "quantity": 1, "unit_price": "250.00", "line_total": "250.00"}],
            subtotal=Decimal("250.00"), tax_amount=Decimal("45.00"),
            total_amount=Decimal("295.00"),
            worker_payout_amount=Decimal("150.00"),
            worker_payout_snapshot={"pricing_model": "booking_fixed_payout_ratio_v1"},
            status=BookingExtraWork.Status.APPROVED,
            payment_choice=BookingExtraWork.PaymentChoice.SEPARATE,
            payment_status="paid",
        )
        extra_payment = Payment.objects.create(
            order=order, extra_work=proposal, customer=self.customer,
            stage=Payment.Stage.EXTRA_WORK, amount=Decimal("295.00"),
            status=Payment.Status.PAID, paid_at=timezone.now(),
        )
        PaymentRefund.objects.create(
            payment=extra_payment, booking=self.booking, extra_work=proposal,
            amount=Decimal("10.00"), wallet_amount=Decimal("10.00"),
            gateway_amount=Decimal("0.00"),
            reason=PaymentRefund.Reason.ADMIN_ADJUSTMENT,
            status=PaymentRefund.Status.PENDING,
        )

        earning = sync_worker_earning(self.booking.pk, extra_payment.pk)

        self.assertEqual(earning.status, WorkerEarning.Status.ON_HOLD)
        self.assertEqual(earning.net_amount, Decimal("150.00"))
        self.assertEqual(calculate_worker_earning_net(earning), Decimal("150.00"))

    def test_unpaid_or_incomplete_booking_does_not_create_earning(self):
        self.payment.status = Payment.Status.PENDING
        self.payment.save(update_fields=["status", "updated_at"])

        self.assertIsNone(sync_worker_earning(self.booking.pk, self.payment.pk))
        self.assertFalse(WorkerEarning.objects.filter(booking=self.booking).exists())

    def test_worker_cash_collection_requires_completion_otp_and_records_cod_balance(self):
        from apps.bookings.models import BookingCompletionOTP

        order = Order.objects.create(
            customer=self.customer,
            address=self.booking.address,
            status=Order.Status.AWAITING_ASSIGNMENT,
            subtotal=Decimal("100.00"),
            total_amount=Decimal("100.00"),
            metadata={
                "payment_allocation_v1": {
                    "balance": [{"order_item_id": 0, "booking_id": self.booking.pk, "amount": "70.00"}],
                    "advance": [{"order_item_id": 0, "booking_id": self.booking.pk, "amount": "30.00"}],
                    "balance_total": "70.00",
                }
            },
        )
        item = OrderItem.objects.create(
            order=order, booking=self.booking, quantity=1,
            line_subtotal=Decimal("100.00"), line_total=Decimal("100.00"),
        )
        order.metadata["payment_allocation_v1"]["balance"][0]["order_item_id"] = item.pk
        order.metadata["payment_allocation_v1"]["advance"][0]["order_item_id"] = item.pk
        order.save(update_fields=["metadata", "updated_at"])
        Payment.objects.create(
            order=order, customer=self.customer,
            stage=Payment.Stage.ADVANCE, amount=Decimal("30.00"),
            status=Payment.Status.PAID, paid_at=timezone.now(),
        )
        BookingCompletionOTP.objects.create(
            booking=self.booking, code_hash="unused",
            expires_at=timezone.now() + timedelta(minutes=5),
            last_sent_at=timezone.now(), verified_at=timezone.now(),
        )

        client = APIClient()
        client.force_authenticate(user=self.worker_user)
        response = client.post(
            f"/api/v1/workers/jobs/{self.booking.assignment.pk}/cash-received/",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        cash_payment = Payment.objects.get(order=order, stage=Payment.Stage.BALANCE)
        self.assertEqual(cash_payment.method, Payment.Method.COD)
        self.assertEqual(cash_payment.status, Payment.Status.PAID)
        self.assertEqual(cash_payment.amount, Decimal("70.00"))
        self.assertEqual(
            cash_payment.raw_response["cash_collection"]["confirmed_by_worker_id"],
            self.worker.pk,
        )
        self.assertEqual(response.data["payment_status"], Payment.Status.PAID)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PAID)

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
        self.assertEqual(response.data["results"], [])
