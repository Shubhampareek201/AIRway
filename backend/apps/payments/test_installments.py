from decimal import Decimal
import hashlib
import hmac
import json
from unittest.mock import patch

from rest_framework.test import APIClient
from django.test import override_settings

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Address, User
from apps.bookings.models import Booking, BookingAssignment, Order, OrderItem
from apps.catalog.models import Category, Service
from apps.core.models import City, Zone
from apps.workers.models import WorkerProfile
from apps.payments.installment_service import (
    InstallmentPaymentError,
    create_final_balance_attempt,
    mark_final_balance_attempt_failed,
    refund_duplicate_final_capture,
    refund_late_final_capture,
    settle_final_balance_attempt,
    issue_service_otp,
    verify_service_otp,
)
from apps.payments.models import (
    BookingFinancialPlan, PaymentAllocation, PaymentAttempt, PaymentInstallment,
)
from apps.wallet.models import Wallet, WalletReservation, WalletTransaction


class FinalBalanceAttemptTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            phone="+919876540001", password="test-password",
        )
        self.city = City.objects.create(name="Final Payment City", state="Rajasthan")
        self.zone = Zone.objects.create(name="Final Payment Zone", city=self.city, is_active=True)
        self.address = Address.objects.create(
            user=self.customer, label="Home", house_details="House 1",
            landmark="Near test landmark",
            full_address="Final Payment Test Address", zone=self.zone,
        )
        self.category = Category.objects.create(
            title="Final Payment Services", slug="final-payment-services",
        )
        self.service = Service.objects.create(
            category=self.category, title="Final Payment Service",
            booking_mode=Service.BookingMode.SCHEDULED,
            pricing_type=Service.PricingType.FIXED, is_active=True,
        )
        self.booking, self.plan, self.final = self._create_completed_booking("1000.00")

    def _create_completed_booking(self, total, *, order=None):
        booking = Booking.objects.create(
            customer=self.customer,
            address=self.address,
            service=self.service,
            scheduled_at=timezone.now() + timezone.timedelta(days=1),
            status=Booking.Status.COMPLETED,
            pricing_snapshot={"total": total},
            completed_at=timezone.now(),
        )
        gross = Decimal(total)
        advance = (gross / Decimal("2")).quantize(Decimal("0.01"))
        balance = gross - advance
        plan = BookingFinancialPlan.objects.create(
            booking=booking, gross_total=gross, advance_due=advance,
            balance_due=balance, advance_captured=advance,
            pricing_snapshot={"total": total},
        )
        PaymentInstallment.objects.create(
            financial_plan=plan, kind=PaymentInstallment.Kind.ADVANCE,
            amount_due=advance, amount_captured=advance,
            status=PaymentInstallment.Status.PAID, settled_at=timezone.now(),
        )
        final = PaymentInstallment.objects.create(
            financial_plan=plan, kind=PaymentInstallment.Kind.FINAL_BALANCE,
            amount_due=balance, status=PaymentInstallment.Status.DUE,
            due_at=timezone.now(),
        )
        if order:
            OrderItem.objects.create(
                order=order, booking=booking, quantity=1,
                line_subtotal=gross, tax_amount=Decimal("0.00"), line_total=gross,
            )
        return booking, plan, final

    def _attempt(self, installment=None, *, amount="500.00", gateway="500.00", wallet="0.00", order_id="order_final"):
        installment = installment or self.final
        return PaymentAttempt.objects.create(
            installment=installment,
            provider=PaymentAttempt.Provider.RAZORPAY if Decimal(gateway) else PaymentAttempt.Provider.WALLET,
            idempotency_key=f"test-final-{installment.pk}-{order_id}",
            amount=Decimal(amount), gateway_amount=Decimal(gateway),
            wallet_amount=Decimal(wallet), currency="INR",
            provider_order_id=order_id if Decimal(gateway) else None,
        )

    def test_captured_final_balance_is_allocated_exactly_once(self):
        attempt = self._attempt()
        settled = settle_final_balance_attempt(
            attempt_id=attempt.pk, razorpay_payment_id="pay_final",
            provider_order_id="order_final", amount_paise=50000,
            currency="INR", source="webhook",
        )
        self.assertEqual(settled.status, PaymentAttempt.Status.CAPTURED)
        self.final.refresh_from_db()
        self.plan.refresh_from_db()
        self.assertEqual(self.final.status, PaymentInstallment.Status.PAID)
        self.assertEqual(self.final.amount_captured, Decimal("500.00"))
        self.assertEqual(self.plan.balance_captured, Decimal("500.00"))
        self.assertEqual(PaymentAllocation.objects.filter(payment_attempt=attempt).count(), 1)

        settle_final_balance_attempt(
            attempt_id=attempt.pk, razorpay_payment_id="pay_final",
            provider_order_id="order_final", amount_paise=50000,
            currency="INR", source="webhook",
        )
        self.assertEqual(PaymentAllocation.objects.filter(payment_attempt=attempt).count(), 1)

    def test_wrong_amount_or_order_never_settles_installment(self):
        attempt = self._attempt()
        with self.assertRaises(InstallmentPaymentError):
            settle_final_balance_attempt(
                attempt_id=attempt.pk, razorpay_payment_id="pay_wrong",
                provider_order_id="order_final", amount_paise=49999,
                currency="INR", source="webhook",
            )
        with self.assertRaises(InstallmentPaymentError):
            settle_final_balance_attempt(
                attempt_id=attempt.pk, razorpay_payment_id="pay_wrong",
                provider_order_id="other_order", amount_paise=50000,
                currency="INR", source="webhook",
            )
        self.final.refresh_from_db()
        self.assertEqual(self.final.amount_captured, Decimal("0.00"))

    def test_wallet_only_final_payment_is_reserved_and_captured(self):
        wallet = Wallet.objects.create(user=self.customer, balance=Decimal("500.00"))
        attempt, existed = create_final_balance_attempt(
            booking_id=self.booking.pk, customer=self.customer, wallet_amount="500.00",
        )
        self.assertFalse(existed)
        attempt.refresh_from_db()
        wallet.refresh_from_db()
        self.final.refresh_from_db()
        reservation = WalletReservation.objects.get(payment_attempt=attempt)
        self.assertEqual(attempt.status, PaymentAttempt.Status.CAPTURED)
        self.assertEqual(reservation.status, WalletReservation.Status.CAPTURED)
        self.assertEqual(wallet.balance, Decimal("0.00"))
        self.assertEqual(wallet.pending_balance, Decimal("0.00"))
        self.assertEqual(self.final.status, PaymentInstallment.Status.PAID)
        self.assertTrue(WalletTransaction.objects.filter(
            reference_id=f"payment_attempt:{attempt.pk}",
            status=WalletTransaction.Status.COMPLETED,
        ).exists())

    def test_failed_attempt_releases_wallet_and_keeps_balance_due(self):
        wallet = Wallet.objects.create(user=self.customer, balance=Decimal("100.00"))
        attempt = self._attempt(amount="500.00", gateway="400.00", wallet="100.00")
        from apps.payments.installment_service import _reserve_wallet
        _reserve_wallet(attempt, Decimal("100.00"))
        mark_final_balance_attempt_failed(
            attempt_id=attempt.pk, provider_order_id="order_final",
            payload={"event": "payment.failed"},
        )
        wallet.refresh_from_db()
        self.final.refresh_from_db()
        self.assertEqual(wallet.balance, Decimal("100.00"))
        self.assertEqual(wallet.pending_balance, Decimal("0.00"))
        self.assertEqual(
            WalletReservation.objects.get(payment_attempt=attempt).status,
            WalletReservation.Status.RELEASED,
        )
        self.assertEqual(self.final.status, PaymentInstallment.Status.DUE)
        self.assertEqual(self.final.amount_captured, Decimal("0.00"))

    @override_settings(RAZORPAY_KEY_ID="rzp_test_key", RAZORPAY_KEY_SECRET="test_secret")
    @patch("apps.payments.installment_service.razorpay.Client")
    def test_final_balance_checkout_is_idempotent_for_active_attempt(self, client_class):
        gateway = client_class.return_value
        gateway.order.create.return_value = {"id": "order_final_api"}
        api = APIClient()
        api.force_authenticate(user=self.customer)

        first = api.post(
            "/api/v1/payments/final-balance/create-order/",
            {"booking_id": self.booking.pk, "wallet_amount": "0.00"},
            format="json",
        )
        second = api.post(
            "/api/v1/payments/final-balance/create-order/",
            {"booking_id": self.booking.pk, "wallet_amount": "0.00"},
            format="json",
        )
        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual(second.status_code, 200, second.data)
        self.assertEqual(first.data["order_id"], "order_final_api")
        self.assertEqual(second.data["order_id"], "order_final_api")
        self.assertTrue(second.data["payment_exists"])
        gateway.order.create.assert_called_once()

    @override_settings(RAZORPAY_KEY_ID="rzp_test_key", RAZORPAY_KEY_SECRET="test_secret")
    @patch("apps.payments.installment_views.razorpay.Client")
    def test_checkout_verification_requires_provider_capture(self, client_class):
        attempt = self._attempt(order_id="order_verify_final")
        gateway = client_class.return_value
        gateway.payment.fetch.return_value = {
            "id": "pay_verify_final",
            "order_id": "order_verify_final",
            "status": "captured",
            "captured": True,
            "amount": 50000,
            "currency": "INR",
        }
        signature = hmac.new(
            b"test_secret",
            b"order_verify_final|pay_verify_final",
            hashlib.sha256,
        ).hexdigest()
        api = APIClient()
        api.force_authenticate(user=self.customer)
        response = api.post(
            "/api/v1/payments/final-balance/verify/",
            {
                "razorpay_order_id": "order_verify_final",
                "razorpay_payment_id": "pay_verify_final",
                "razorpay_signature": signature,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        attempt.refresh_from_db()
        self.final.refresh_from_db()
        self.assertEqual(attempt.status, PaymentAttempt.Status.CAPTURED)
        self.assertEqual(self.final.status, PaymentInstallment.Status.PAID)

    @patch("apps.payments.installment_service.razorpay.Client")
    def test_late_capture_after_failed_attempt_is_refunded(self, client_class):
        wallet = Wallet.objects.create(user=self.customer, balance=Decimal("100.00"))
        attempt = self._attempt(
            amount="500.00", gateway="400.00", wallet="100.00",
            order_id="order_late_final",
        )
        from apps.payments.installment_service import _reserve_wallet
        _reserve_wallet(attempt, Decimal("100.00"))
        mark_final_balance_attempt_failed(
            attempt_id=attempt.pk, provider_order_id="order_late_final",
            payload={"event": "payment.failed"},
        )
        client_class.return_value.payment.refund.return_value = {
            "id": "rfnd_late_final", "status": "processed",
        }
        refund = refund_late_final_capture(
            attempt_id=attempt.pk,
            razorpay_payment_id="pay_late_final",
            provider_order_id="order_late_final",
            payload={"event": "payment.captured"},
        )
        attempt.refresh_from_db()
        wallet.refresh_from_db()
        self.final.refresh_from_db()
        self.assertEqual(refund.status, "processed")
        self.assertEqual(attempt.status, PaymentAttempt.Status.REFUNDED)
        self.assertEqual(wallet.balance, Decimal("100.00"))
        self.assertEqual(self.final.status, PaymentInstallment.Status.DUE)
        client_class.return_value.payment.refund.assert_called_once()

    @patch("apps.payments.installment_service.razorpay.Client")
    def test_second_distinct_capture_is_refunded_without_second_allocation(self, client_class):
        attempt = self._attempt(order_id="order_duplicate_final")
        settle_final_balance_attempt(
            attempt_id=attempt.pk, razorpay_payment_id="pay_first_final",
            provider_order_id="order_duplicate_final", amount_paise=50000,
            currency="INR", source="webhook",
        )
        client_class.return_value.payment.refund.return_value = {
            "id": "rfnd_duplicate_final", "status": "processed",
        }
        refund = refund_duplicate_final_capture(
            attempt_id=attempt.pk,
            razorpay_payment_id="pay_second_final",
            provider_order_id="order_duplicate_final",
            payload={"event": "payment.captured"},
        )
        attempt.refresh_from_db()
        self.final.refresh_from_db()
        self.assertEqual(refund.status, "processed")
        self.assertEqual(attempt.status, PaymentAttempt.Status.CAPTURED)
        self.assertEqual(self.final.amount_captured, Decimal("500.00"))
        self.assertEqual(PaymentAllocation.objects.filter(installment=self.final).count(), 1)

    def test_start_and_completion_otp_gate_service_and_make_balance_due(self):
        worker_user = User.objects.create_user(
            phone="+919876540002", password="worker-password",
        )
        worker = WorkerProfile.objects.create(
            user=worker_user, status=WorkerProfile.Status.APPROVED,
        )
        self.booking.status = Booking.Status.ASSIGNED
        self.booking.completed_at = None
        self.booking.save(update_fields=["status", "completed_at", "updated_at"])
        assignment = BookingAssignment.objects.create(
            booking=self.booking, worker=worker, accepted_at=timezone.now(),
        )

        _, start_code = issue_service_otp(
            booking_id=self.booking.pk,
            purpose="start",
            requested_by=self.customer,
        )
        started = verify_service_otp(
            booking_id=self.booking.pk,
            purpose="start",
            code=start_code,
            worker_user=worker_user,
        )
        assignment.refresh_from_db()
        self.assertEqual(started.status, Booking.Status.IN_PROGRESS)
        self.assertIsNotNone(assignment.started_at)

        _, completion_code = issue_service_otp(
            booking_id=self.booking.pk,
            purpose="completion",
            requested_by=self.customer,
        )
        completed = verify_service_otp(
            booking_id=self.booking.pk,
            purpose="completion",
            code=completion_code,
            worker_user=worker_user,
        )
        self.final.refresh_from_db()
        assignment.refresh_from_db()
        self.assertEqual(completed.status, Booking.Status.COMPLETED)
        self.assertIsNotNone(assignment.completed_at)
        self.assertEqual(self.final.status, PaymentInstallment.Status.DUE)
        self.assertEqual(self.final.due_at, assignment.completed_at)

    @override_settings(RAZORPAY_WEBHOOK_SECRET="webhook_test_secret")
    def test_capture_webhook_settles_final_installment_with_verified_signature(self):
        attempt = self._attempt(order_id="order_webhook_final")
        payload = {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_webhook_final",
                        "order_id": "order_webhook_final",
                        "amount": 50000,
                        "currency": "INR",
                        "status": "captured",
                        "captured": True,
                    }
                }
            },
        }
        raw = json.dumps(payload).encode()
        signature = hmac.new(
            b"webhook_test_secret", raw, hashlib.sha256,
        ).hexdigest()
        api = APIClient()
        response = api.generic(
            "POST", "/api/v1/payments/webhook/", data=raw,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=signature,
        )
        self.assertEqual(response.status_code, 200, response.data)
        attempt.refresh_from_db()
        self.final.refresh_from_db()
        self.assertEqual(attempt.status, PaymentAttempt.Status.CAPTURED)
        self.assertEqual(self.final.amount_captured, Decimal("500.00"))

    def test_parent_order_completes_only_after_every_line_balance_is_paid(self):
        order = Order.objects.create(
            customer=self.customer, address=self.address,
            status=Order.Status.AWAITING_FINAL_PAYMENT, total_amount="2000.00",
        )
        # Reuse the first completed line and attach the second.
        OrderItem.objects.create(
            order=order, booking=self.booking, quantity=1,
            line_subtotal="1000.00", tax_amount="0.00", line_total="1000.00",
        )
        second_booking, second_plan, second_final = self._create_completed_booking(
            "1000.00", order=order,
        )
        first_attempt = self._attempt(order_id="order_line_one")
        settle_final_balance_attempt(
            attempt_id=first_attempt.pk, razorpay_payment_id="pay_line_one",
            provider_order_id="order_line_one", amount_paise=50000,
            currency="INR", source="webhook",
        )
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.AWAITING_FINAL_PAYMENT)

        second_attempt = self._attempt(
            second_final, order_id="order_line_two",
        )
        settle_final_balance_attempt(
            attempt_id=second_attempt.pk, razorpay_payment_id="pay_line_two",
            provider_order_id="order_line_two", amount_paise=50000,
            currency="INR", source="webhook",
        )
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.COMPLETED)
