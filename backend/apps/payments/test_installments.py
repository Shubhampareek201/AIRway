from decimal import Decimal, ROUND_HALF_UP
from datetime import timedelta
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
from apps.notifications.models import Notification
from apps.workers.models import WorkerProfile
from apps.payments.installment_service import (
    InstallmentPaymentError,
    create_final_balance_attempt,
    mark_final_balance_attempt_failed,
    refund_duplicate_final_capture,
    refund_late_final_capture,
    reconcile_refund_record,
    settle_final_balance_attempt,
)
from apps.payments.lifecycle import issue_service_otp, verify_service_otp
from apps.payments.models import (
    BookingFinancialPlan, Payment, PaymentAllocation, PaymentAttempt,
    PaymentInstallment, RefundRecord,
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

    def _wallet_with_balance(self, balance):
        wallet = Wallet.objects.get(user=self.customer)
        wallet.balance = Decimal(balance)
        wallet.pending_balance = Decimal("0.00")
        wallet.save(update_fields=["balance", "pending_balance", "updated_at"])
        return wallet

    def _create_completed_booking(self, total, *, order=None):
        booking = Booking.objects.create(
            customer=self.customer,
            address=self.address,
            service=self.service,
            scheduled_at=timezone.now() + timedelta(days=1),
            status=Booking.Status.COMPLETED,
            pricing_snapshot={"total": total},
            completed_at=timezone.now(),
        )
        gross = Decimal(total)
        advance = (gross / Decimal("2")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
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
        wallet = self._wallet_with_balance("500.00")
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

    def test_wallet_only_active_attempt_is_settled_on_retry_after_interruption(self):
        wallet = self._wallet_with_balance("500.00")
        with patch(
            "apps.payments.installment_service.settle_final_balance_attempt",
            side_effect=InstallmentPaymentError("simulated process interruption"),
        ):
            with self.assertRaises(InstallmentPaymentError):
                create_final_balance_attempt(
                    booking_id=self.booking.pk,
                    customer=self.customer,
                    wallet_amount="500.00",
                )

        attempt = PaymentAttempt.objects.get(installment=self.final)
        reservation = WalletReservation.objects.get(payment_attempt=attempt)
        wallet.refresh_from_db()
        self.final.refresh_from_db()
        self.assertEqual(attempt.status, PaymentAttempt.Status.CREATED)
        self.assertEqual(reservation.status, WalletReservation.Status.RESERVED)
        self.assertEqual(wallet.pending_balance, Decimal("500.00"))
        self.assertEqual(self.final.status, PaymentInstallment.Status.PROCESSING)

        retried_attempt, existed = create_final_balance_attempt(
            booking_id=self.booking.pk,
            customer=self.customer,
            wallet_amount="500.00",
        )
        retried_attempt.refresh_from_db()
        reservation.refresh_from_db()
        wallet.refresh_from_db()
        self.final.refresh_from_db()
        self.assertTrue(existed)
        self.assertEqual(retried_attempt.pk, attempt.pk)
        self.assertEqual(retried_attempt.status, PaymentAttempt.Status.CAPTURED)
        self.assertEqual(reservation.status, WalletReservation.Status.CAPTURED)
        self.assertEqual(wallet.balance, Decimal("0.00"))
        self.assertEqual(wallet.pending_balance, Decimal("0.00"))
        self.assertEqual(self.final.status, PaymentInstallment.Status.PAID)
        self.assertEqual(
            PaymentAllocation.objects.filter(payment_attempt=attempt).count(),
            1,
        )

    @patch("apps.payments.installment_service.razorpay.Client")
    def test_mixed_wallet_and_gateway_tender_reconciles_all_sources(self, client_class):
        wallet = self._wallet_with_balance("100.00")
        client_class.return_value.order.create.return_value = {"id": "order_mixed_final"}
        attempt, _ = create_final_balance_attempt(
            booking_id=self.booking.pk, customer=self.customer,
            wallet_amount="100.00",
        )
        wallet.refresh_from_db()
        self.assertEqual(attempt.amount, Decimal("500.00"))
        self.assertEqual(attempt.wallet_amount, Decimal("100.00"))
        self.assertEqual(attempt.gateway_amount, Decimal("400.00"))
        self.assertEqual(wallet.balance, Decimal("0.00"))
        self.assertEqual(wallet.pending_balance, Decimal("100.00"))

        settle_final_balance_attempt(
            attempt_id=attempt.pk, razorpay_payment_id="pay_mixed_final",
            provider_order_id="order_mixed_final", amount_paise=40000,
            currency="INR", source="webhook",
        )
        wallet.refresh_from_db()
        allocation = PaymentAllocation.objects.get(payment_attempt=attempt)
        self.assertEqual(allocation.amount, Decimal("500.00"))
        self.assertEqual(allocation.gateway_amount, Decimal("400.00"))
        self.assertEqual(allocation.wallet_amount, Decimal("100.00"))
        self.assertEqual(wallet.balance, Decimal("0.00"))
        self.assertEqual(wallet.pending_balance, Decimal("0.00"))
        self.assertEqual(
            WalletReservation.objects.get(payment_attempt=attempt).status,
            WalletReservation.Status.CAPTURED,
        )

    def test_failed_attempt_releases_wallet_and_keeps_balance_due(self):
        wallet = self._wallet_with_balance("100.00")
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
        wallet = self._wallet_with_balance("100.00")
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

    @patch("apps.payments.installment_service.razorpay.Client")
    def test_failed_gateway_attempt_can_be_retried_with_a_new_order(self, client_class):
        first = self._attempt(order_id="order_first_failed")
        mark_final_balance_attempt_failed(
            attempt_id=first.pk, provider_order_id="order_first_failed",
            payload={"event": "payment.failed"},
        )
        client_class.return_value.order.create.return_value = {"id": "order_retry"}
        second, existed = create_final_balance_attempt(
            booking_id=self.booking.pk, customer=self.customer,
            wallet_amount="0.00",
        )
        self.assertFalse(existed)
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(second.provider_order_id, "order_retry")
        self.assertEqual(second.status, PaymentAttempt.Status.CREATED)

    @patch("apps.payments.installment_service.razorpay.Client")
    def test_failed_late_capture_refund_blocks_new_charge_until_reconciled(self, client_class):
        attempt = self._attempt(order_id="order_refund_failure")
        mark_final_balance_attempt_failed(
            attempt_id=attempt.pk, provider_order_id="order_refund_failure",
            payload={"event": "payment.failed"},
        )
        client_class.return_value.payment.refund.side_effect = RuntimeError("provider unavailable")
        refund = refund_late_final_capture(
            attempt_id=attempt.pk,
            razorpay_payment_id="pay_refund_failure",
            provider_order_id="order_refund_failure",
            payload={"event": "payment.captured"},
        )
        self.assertEqual(refund.status, "failed")
        with self.assertRaises(InstallmentPaymentError):
            create_final_balance_attempt(
                booking_id=self.booking.pk, customer=self.customer,
                wallet_amount="0.00",
            )

    @override_settings(RAZORPAY_WEBHOOK_SECRET="webhook_test_secret")
    @patch("apps.payments.installment_service.razorpay.Client")
    def test_refund_webhook_reconciles_before_refund_api_response_is_persisted(self, client_class):
        attempt = self._attempt(order_id="order_refund_webhook")
        mark_final_balance_attempt_failed(
            attempt_id=attempt.pk, provider_order_id="order_refund_webhook",
            payload={"event": "payment.failed"},
        )
        client_class.return_value.payment.refund.return_value = {
            "id": "rfnd_webhook_race", "status": "pending",
        }
        refund = refund_late_final_capture(
            attempt_id=attempt.pk,
            razorpay_payment_id="pay_refund_webhook",
            provider_order_id="order_refund_webhook",
            payload={"event": "payment.captured"},
        )
        # Simulate the webhook winning the race before the API response is stored.
        refund.provider_refund_id = None
        refund.save(update_fields=["provider_refund_id", "updated_at"])
        payload = {
            "event": "refund.processed",
            "payload": {
                "refund": {
                    "entity": {
                        "id": "rfnd_webhook_race",
                        "payment_id": "pay_refund_webhook",
                        "amount": 50000,
                        "notes": {"airway_refund_record_id": str(refund.pk)},
                    }
                }
            },
        }
        raw = json.dumps(payload).encode()
        signature = hmac.new(b"webhook_test_secret", raw, hashlib.sha256).hexdigest()
        response = APIClient().generic(
            "POST", "/api/v1/payments/webhook/", data=raw,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=signature,
        )
        refund.refresh_from_db()
        attempt.refresh_from_db()
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(refund.status, "processed")
        self.assertEqual(refund.provider_refund_id, "rfnd_webhook_race")
        self.assertEqual(attempt.status, PaymentAttempt.Status.REFUNDED)

    @override_settings(RAZORPAY_WEBHOOK_SECRET="webhook_test_secret")
    @patch("apps.payments.installment_service.razorpay.Client")
    def test_refund_webhook_with_wrong_amount_does_not_change_refund_ledger(self, client_class):
        attempt = self._attempt(order_id="order_refund_webhook_mismatch")
        mark_final_balance_attempt_failed(
            attempt_id=attempt.pk, provider_order_id="order_refund_webhook_mismatch",
            payload={"event": "payment.failed"},
        )
        client_class.return_value.payment.refund.return_value = {
            "id": "rfnd_webhook_mismatch", "status": "pending",
        }
        refund = refund_late_final_capture(
            attempt_id=attempt.pk,
            razorpay_payment_id="pay_refund_webhook_mismatch",
            provider_order_id="order_refund_webhook_mismatch",
            payload={"event": "payment.captured"},
        )
        payload = {
            "event": "refund.processed",
            "payload": {
                "refund": {
                    "entity": {
                        "id": "rfnd_webhook_mismatch",
                        "payment_id": "pay_refund_webhook_mismatch",
                        "amount": 49999,
                        "notes": {"airway_refund_record_id": str(refund.pk)},
                    }
                }
            },
        }
        raw = json.dumps(payload).encode()
        signature = hmac.new(b"webhook_test_secret", raw, hashlib.sha256).hexdigest()
        response = APIClient().generic(
            "POST", "/api/v1/payments/webhook/", data=raw,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=signature,
        )
        refund.refresh_from_db()
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(refund.status, RefundRecord.Status.PENDING)
        self.assertEqual(refund.provider_refund_id, "rfnd_webhook_mismatch")

    @patch("apps.payments.installment_service.razorpay.Client")
    def test_refund_reconciliation_matches_provider_note_and_amount(self, client_class):
        payment = Payment.objects.create(
            booking=self.booking, customer=self.customer, amount=Decimal("500.00"),
            method=Payment.Method.RAZORPAY, status=Payment.Status.PAID,
            razorpay_payment_id="pay_refund_reconcile",
        )
        record = RefundRecord.objects.create(
            booking=self.booking, payment=payment,
            idempotency_key="refund-reconcile-match",
            reason=RefundRecord.Reason.CUSTOMER_CANCELLATION,
            gross_amount=Decimal("500.00"), refund_amount=Decimal("460.00"),
            gateway_refund_amount=Decimal("460.00"),
            status=RefundRecord.Status.FAILED,
        )
        client_class.return_value.payment.fetch_multiple_refund.return_value = {
            "items": [{
                "id": "rfnd_reconcile_match", "amount": 46000,
                "status": "processed",
                "notes": {"airway_refund_record_id": str(record.pk)},
            }]
        }
        reconciled = reconcile_refund_record(record_id=record.pk)
        self.assertEqual(reconciled.status, RefundRecord.Status.PROCESSED)
        self.assertEqual(reconciled.provider_refund_id, "rfnd_reconcile_match")

    @patch("apps.payments.installment_service.razorpay.Client")
    def test_refund_reconciliation_searches_subsequent_provider_pages(self, client_class):
        payment = Payment.objects.create(
            booking=self.booking, customer=self.customer, amount=Decimal("500.00"),
            method=Payment.Method.RAZORPAY, status=Payment.Status.PAID,
            razorpay_payment_id="pay_refund_paginated",
        )
        record = RefundRecord.objects.create(
            booking=self.booking, payment=payment,
            idempotency_key="refund-reconcile-paginated",
            reason=RefundRecord.Reason.CUSTOMER_CANCELLATION,
            gross_amount=Decimal("500.00"), refund_amount=Decimal("460.00"),
            gateway_refund_amount=Decimal("460.00"),
            status=RefundRecord.Status.FAILED,
        )
        first_page = {"items": [
            {"id": f"rfnd_other_{index}", "amount": 100, "notes": {}}
            for index in range(100)
        ]}
        second_page = {"items": [{
            "id": "rfnd_reconcile_paginated", "amount": 46000,
            "status": "processed",
            "notes": {"airway_refund_record_id": str(record.pk)},
        }]}
        client_class.return_value.payment.fetch_multiple_refund.side_effect = [
            first_page, second_page,
        ]

        reconciled = reconcile_refund_record(record_id=record.pk)

        self.assertEqual(reconciled.status, RefundRecord.Status.PROCESSED)
        self.assertEqual(reconciled.provider_refund_id, "rfnd_reconcile_paginated")
        calls = client_class.return_value.payment.fetch_multiple_refund.call_args_list
        self.assertEqual(calls[0].args[1], {"count": 100, "skip": 0})
        self.assertEqual(calls[1].args[1], {"count": 100, "skip": 100})

    @patch("apps.payments.installment_service.razorpay.Client")
    def test_missing_refund_lookup_does_not_regress_concurrent_processed_webhook(self, client_class):
        payment = Payment.objects.create(
            booking=self.booking, customer=self.customer, amount=Decimal("500.00"),
            method=Payment.Method.RAZORPAY, status=Payment.Status.PAID,
            razorpay_payment_id="pay_refund_race",
        )
        record = RefundRecord.objects.create(
            booking=self.booking, payment=payment,
            idempotency_key="refund-reconcile-webhook-race",
            reason=RefundRecord.Reason.CUSTOMER_CANCELLATION,
            gross_amount=Decimal("500.00"), refund_amount=Decimal("460.00"),
            gateway_refund_amount=Decimal("460.00"),
            status=RefundRecord.Status.FAILED,
        )

        def provider_lookup(*args, **kwargs):
            # Simulate refund.processed webhook committing after the
            # reconciliation function's initial read and before its row lock.
            RefundRecord.objects.filter(pk=record.pk).update(
                status=RefundRecord.Status.PROCESSED,
                provider_refund_id="rfnd_processed_during_lookup",
                processed_at=timezone.now(),
            )
            return {"items": []}

        client_class.return_value.payment.fetch_multiple_refund.side_effect = provider_lookup
        reconciled = reconcile_refund_record(record_id=record.pk)

        self.assertEqual(reconciled.status, RefundRecord.Status.PROCESSED)
        self.assertEqual(
            reconciled.provider_refund_id,
            "rfnd_processed_during_lookup",
        )

    @patch("apps.payments.installment_service.razorpay.Client")
    def test_missing_provider_refund_stays_pending_without_resubmission(self, client_class):
        payment = Payment.objects.create(
            booking=self.booking, customer=self.customer, amount=Decimal("500.00"),
            method=Payment.Method.RAZORPAY, status=Payment.Status.PAID,
            razorpay_payment_id="pay_refund_not_found",
        )
        record = RefundRecord.objects.create(
            booking=self.booking, payment=payment,
            idempotency_key="refund-reconcile-missing",
            reason=RefundRecord.Reason.CUSTOMER_CANCELLATION,
            gross_amount=Decimal("500.00"), refund_amount=Decimal("460.00"),
            gateway_refund_amount=Decimal("460.00"),
            status=RefundRecord.Status.FAILED,
        )
        client_class.return_value.payment.fetch_multiple_refund.return_value = {"items": []}
        reconciled = reconcile_refund_record(record_id=record.pk)
        self.assertEqual(reconciled.status, RefundRecord.Status.PENDING)
        client_class.return_value.payment.refund.assert_not_called()

    @patch("apps.payments.installment_service.razorpay.Client")
    def test_reconciliation_rejects_provider_refund_id_owned_by_another_record(self, client_class):
        payment = Payment.objects.create(
            booking=self.booking, customer=self.customer, amount=Decimal("500.00"),
            method=Payment.Method.RAZORPAY, status=Payment.Status.PAID,
            razorpay_payment_id="pay_refund_owner_conflict",
        )
        owner = RefundRecord.objects.create(
            booking=self.booking, payment=payment,
            idempotency_key="refund-owner-existing",
            reason=RefundRecord.Reason.CUSTOMER_CANCELLATION,
            gross_amount=Decimal("500.00"), refund_amount=Decimal("460.00"),
            gateway_refund_amount=Decimal("460.00"),
            provider_refund_id="rfnd_already_owned",
            status=RefundRecord.Status.PENDING,
        )
        target = RefundRecord.objects.create(
            booking=self.booking, payment=payment,
            idempotency_key="refund-owner-target",
            reason=RefundRecord.Reason.CUSTOMER_CANCELLATION,
            gross_amount=Decimal("500.00"), refund_amount=Decimal("460.00"),
            gateway_refund_amount=Decimal("460.00"),
            status=RefundRecord.Status.FAILED,
        )
        client_class.return_value.payment.fetch_multiple_refund.return_value = {
            "items": [{
                "id": "rfnd_already_owned", "amount": 46000,
                "status": "processed",
                "notes": {"airway_refund_record_id": str(target.pk)},
            }]
        }

        with self.assertRaises(InstallmentPaymentError):
            reconcile_refund_record(record_id=target.pk)

        owner.refresh_from_db()
        target.refresh_from_db()
        self.assertEqual(owner.provider_refund_id, "rfnd_already_owned")
        self.assertIsNone(target.provider_refund_id)
        self.assertEqual(target.status, RefundRecord.Status.FAILED)

    def test_wallet_overdraft_does_not_create_attempt_or_change_balance(self):
        wallet = self._wallet_with_balance("10.00")
        with self.assertRaises(InstallmentPaymentError):
            create_final_balance_attempt(
                booking_id=self.booking.pk, customer=self.customer,
                wallet_amount="20.00",
            )
        wallet.refresh_from_db()
        self.final.refresh_from_db()
        self.assertEqual(wallet.balance, Decimal("10.00"))
        self.assertEqual(wallet.pending_balance, Decimal("0.00"))
        self.assertEqual(PaymentAttempt.objects.filter(installment=self.final).count(), 0)
        self.assertEqual(self.final.status, PaymentInstallment.Status.DUE)

    def test_completion_notification_is_created_when_final_balance_becomes_due(self):
        worker_user = User.objects.create_user(
            phone="+919876540003", password="worker-password",
        )
        worker = WorkerProfile.objects.create(
            user=worker_user, status=WorkerProfile.Status.APPROVED,
        )
        self.booking.status = Booking.Status.ASSIGNED
        self.booking.completed_at = None
        self.booking.save(update_fields=["status", "completed_at", "updated_at"])
        BookingAssignment.objects.create(
            booking=self.booking, worker=worker, accepted_at=timezone.now(),
        )
        _, start_code = issue_service_otp(
            booking_id=self.booking.pk, purpose="start", requested_by=self.customer,
        )
        verify_service_otp(
            booking_id=self.booking.pk, purpose="start",
            code=start_code, worker_user=worker_user,
        )
        _, completion_code = issue_service_otp(
            booking_id=self.booking.pk, purpose="completion", requested_by=self.customer,
        )
        verify_service_otp(
            booking_id=self.booking.pk, purpose="completion",
            code=completion_code, worker_user=worker_user,
        )
        self.assertTrue(Notification.objects.filter(
            user=self.customer,
            type=Notification.Type.FINAL_PAYMENT_DUE,
            data__booking_id=self.booking.pk,
        ).exists())

    def test_zero_balance_is_closed_by_completion_without_gateway_attempt(self):
        booking, plan, final = self._create_completed_booking("0.01")
        worker_user = User.objects.create_user(
            phone="+919876540004", password="worker-password",
        )
        worker = WorkerProfile.objects.create(
            user=worker_user, status=WorkerProfile.Status.APPROVED,
        )
        booking.status = Booking.Status.ASSIGNED
        booking.completed_at = None
        booking.save(update_fields=["status", "completed_at", "updated_at"])
        BookingAssignment.objects.create(
            booking=booking, worker=worker, accepted_at=timezone.now(),
        )
        _, start_code = issue_service_otp(
            booking_id=booking.pk, purpose="start", requested_by=self.customer,
        )
        verify_service_otp(
            booking_id=booking.pk, purpose="start",
            code=start_code, worker_user=worker_user,
        )
        _, completion_code = issue_service_otp(
            booking_id=booking.pk, purpose="completion", requested_by=self.customer,
        )
        verify_service_otp(
            booking_id=booking.pk, purpose="completion",
            code=completion_code, worker_user=worker_user,
        )
        final.refresh_from_db()
        self.assertEqual(final.amount_due, Decimal("0.00"))
        self.assertEqual(final.status, PaymentInstallment.Status.PAID)
        self.assertEqual(PaymentAttempt.objects.filter(installment=final).count(), 0)

    def test_parent_order_completes_when_cancelled_line_balance_is_cancelled(self):
        order = Order.objects.create(
            customer=self.customer, address=self.address,
            status=Order.Status.AWAITING_FINAL_PAYMENT, total_amount="1000.01",
        )
        cancelled_booking, _, cancelled_final = self._create_completed_booking(
            "1000.00", order=order,
        )
        cancelled_booking.status = Booking.Status.CANCELLED
        cancelled_booking.save(update_fields=["status", "updated_at"])
        cancelled_final.status = PaymentInstallment.Status.CANCELLED
        cancelled_final.save(update_fields=["status", "updated_at"])

        active_booking, _, active_final = self._create_completed_booking(
            "0.01", order=order,
        )
        active_booking.status = Booking.Status.IN_PROGRESS
        active_booking.completed_at = None
        active_booking.save(update_fields=["status", "completed_at", "updated_at"])
        worker_user = User.objects.create_user(
            phone="+919876540005", password="worker-password",
        )
        worker = WorkerProfile.objects.create(
            user=worker_user, status=WorkerProfile.Status.APPROVED,
        )
        BookingAssignment.objects.create(
            booking=active_booking, worker=worker, accepted_at=timezone.now(),
        )
        _, completion_code = issue_service_otp(
            booking_id=active_booking.pk,
            purpose="completion",
            requested_by=self.customer,
        )
        verify_service_otp(
            booking_id=active_booking.pk,
            purpose="completion",
            code=completion_code,
            worker_user=worker_user,
        )

        active_final.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(active_final.status, PaymentInstallment.Status.PAID)
        self.assertEqual(order.status, Order.Status.COMPLETED)

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
