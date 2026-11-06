import hashlib
import hmac
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.wallet.models import Wallet, WalletTransaction
from apps.accounts.models import Address
from apps.bookings.models import Booking
from apps.catalog.models import Category, Service
from apps.core.models import City, Zone
from apps.payments.models import Payment

User = get_user_model()


class WalletModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(phone="9876543210", password="test123456")

    def test_wallet_created_automatically(self):
        wallet = Wallet.objects.get(user=self.user)
        self.assertEqual(wallet.balance, 0)
        self.assertEqual(wallet.pending_balance, 0)

    def test_deposit_increases_balance(self):
        wallet = Wallet.objects.get(user=self.user)
        wallet.deposit(500, description="Top-up")
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, 500)
        self.assertEqual(wallet.transactions.count(), 1)
        self.assertEqual(wallet.transactions.first().type, WalletTransaction.Type.CREDIT)

    def test_debit_decreases_balance(self):
        wallet = Wallet.objects.get(user=self.user)
        wallet.deposit(1000)
        wallet.debit(300, description="Payment")
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, 700)
        self.assertEqual(wallet.transactions.count(), 2)
        self.assertEqual(wallet.transactions.first().type, WalletTransaction.Type.DEBIT)


class WalletAPITest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(phone="9876543210", password="test123456")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_balance_requires_authentication(self):
        client = APIClient()
        response = client.get("/api/v1/wallet/balance/")
        self.assertEqual(response.status_code, 401)

    def test_balance_returns_default_zero(self):
        response = self.client.get("/api/v1/wallet/balance/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["balance"], "0.00")

    @patch("apps.wallet.views.razorpay_client.order.create")
    def test_top_up_creates_server_side_razorpay_order(self, create_order):
        create_order.return_value = {"id": "order_wallet_123"}
        response = self.client.post(
            "/api/v1/wallet/top-up/",
            {"amount": "500.00", "reference_id": "client_cannot_choose_order"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["type"], "credit")
        self.assertEqual(response.data["status"], "pending")
        self.assertEqual(response.data["amount"], "500.00")
        self.assertEqual(response.data["amount_paise"], 50000)
        self.assertEqual(response.data["order_id"], "order_wallet_123")
        self.assertEqual(response.data["reference_id"], "order_wallet_123")
        create_order.assert_called_once()
        self.assertEqual(create_order.call_args.kwargs["data"]["amount"], 50000)

    @patch("apps.wallet.views.razorpay_client.order.create")
    def test_top_up_does_not_create_pending_credit_if_gateway_fails(self, create_order):
        create_order.side_effect = RuntimeError("gateway unavailable")
        response = self.client.post(
            "/api/v1/wallet/top-up/", {"amount": 500}, format="json"
        )
        self.assertEqual(response.status_code, 502)
        self.assertFalse(WalletTransaction.objects.filter(wallet__user=self.user).exists())

    def test_top_up_rejects_more_than_two_decimal_places(self):
        response = self.client.post(
            "/api/v1/wallet/top-up/", {"amount": "10.999"}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_top_up_rejects_invalid_amount(self):
        response = self.client.post(
            "/api/v1/wallet/top-up/",
            {"amount": -100},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_top_up_requires_amount(self):
        response = self.client.post(
            "/api/v1/wallet/top-up/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_customer_cannot_mint_wallet_refund_credit(self):
        response = self.client.post(
            "/api/v1/wallet/refund/",
            {"booking_id": 42, "amount": 250, "reason": "Cancelled booking"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Wallet.objects.get(user=self.user).balance, Decimal("0.00"))

    def test_transactions_list_returns_user_transactions(self):
        wallet = Wallet.objects.get(user=self.user)
        wallet.deposit(100, description="Deposit")
        wallet.debit(50, description="Payment")

        response = self.client.get("/api/v1/wallet/transactions/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 2)

    def test_credit_endpoint_requires_admin(self):
        """Non-admin users should not be able to credit wallets."""
        response = self.client.post(
            "/api/v1/wallet/credit/",
            {"user_id": self.user.id, "amount": 300, "description": "Bonus", "reference_id": "bonus_1"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)  # Forbidden for non-admin


class WalletCreditViewAdminTest(TestCase):
    """Test wallet credit functionality for admin users only."""

    def setUp(self):
        # Regular user
        self.customer = User.objects.create_user(phone="9876543211", password="test123456")
        # Admin user (is_staff=True)
        self.admin = User.objects.create_user(phone="9876543212", password="test123456", is_staff=True)
        self.admin_client = APIClient()
        self.admin_client.force_authenticate(user=self.admin)

    def test_admin_can_credit_wallet(self):
        """Admin users should be able to credit wallets."""
        response = self.admin_client.post(
            "/api/v1/wallet/credit/",
            {"user_id": self.customer.id, "amount": 500, "description": "Bonus credit", "reference_id": "bonus_1"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["type"], "credit")
        self.assertEqual(response.data["status"], "completed")
        self.assertEqual(response.data["amount"], "500.00")

        wallet = Wallet.objects.get(user=self.customer)
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, 500)

    def test_admin_cannot_credit_nonexistent_user(self):
        """Admin should get 404 when crediting non-existent user."""
        response = self.admin_client.post(
            "/api/v1/wallet/credit/",
            {"user_id": 99999, "amount": 300, "description": "Bonus", "reference_id": "bonus_2"},
            format="json",
        )
        self.assertEqual(response.status_code, 404)

    def test_credit_rejects_invalid_amount(self):
        """Admin credit should reject invalid amounts."""
        response = self.admin_client.post(
            "/api/v1/wallet/credit/",
            {"user_id": self.customer.id, "amount": -100, "description": "Bonus", "reference_id": "bonus_3"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_credit_requires_amount(self):
        """Admin credit requires amount field."""
        response = self.admin_client.post(
            "/api/v1/wallet/credit/",
            {"user_id": self.customer.id, "description": "Bonus", "reference_id": "bonus_4"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)


@override_settings(RAZORPAY_KEY_SECRET="wallet-test-secret")
class WalletTopUpConfirmTest(TestCase):
    """Top-up confirmation must be owner-scoped and signature-verified."""

    def setUp(self):
        self.user = User.objects.create_user(phone="9876543213", password="test123456")
        self.other_user = User.objects.create_user(phone="9876543214", password="test123456")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.wallet = Wallet.objects.get(user=self.user)
        self.pending = WalletTransaction.objects.create(
            wallet=self.wallet,
            type=WalletTransaction.Type.CREDIT,
            amount=Decimal("1000.00"),
            description="Wallet top-up",
            status=WalletTransaction.Status.PENDING,
            reference_id="order_wallet_abc",
        )

    def _signature(self, order_id="order_wallet_abc", payment_id="pay_xyz"):
        message = f"{order_id}|{payment_id}".encode()
        return hmac.new(b"wallet-test-secret", message, hashlib.sha256).hexdigest()

    def _confirm(self, client=None, **overrides):
        data = {
            "razorpay_order_id": "order_wallet_abc",
            "razorpay_payment_id": "pay_xyz",
            "razorpay_signature": self._signature(),
        }
        data.update(overrides)
        return (client or self.client).post(
            f"/api/v1/wallet/top-up/{self.pending.id}/confirm/",
            data,
            format="json",
        )

    def test_valid_signature_credits_wallet_once(self):
        response = self._confirm()
        self.assertEqual(response.status_code, 200, response.data)
        self.wallet.refresh_from_db()
        self.pending.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("1000.00"))
        self.assertEqual(self.pending.status, WalletTransaction.Status.COMPLETED)
        self.assertEqual(self.pending.razorpay_payment_id, "pay_xyz")

        duplicate = self._confirm()
        self.assertEqual(duplicate.status_code, 200)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("1000.00"))

    def test_checkout_callback_is_idempotent_after_webhook_capture(self):
        from apps.wallet.views import complete_top_up_transaction

        completed = complete_top_up_transaction(
            self.pending.id,
            razorpay_payment_id="pay_xyz",
            user=self.user,
            razorpay_order_id="order_wallet_abc",
        )
        self.assertIsNotNone(completed)
        response = self._confirm()
        self.assertEqual(response.status_code, 200)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("1000.00"))

    def test_invalid_signature_does_not_credit_wallet(self):
        response = self._confirm(razorpay_signature="invalid")
        self.assertEqual(response.status_code, 400)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("0.00"))
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.status, WalletTransaction.Status.PENDING)

    def test_another_customer_cannot_confirm_top_up(self):
        other_client = APIClient()
        other_client.force_authenticate(user=self.other_user)
        response = self._confirm(client=other_client)
        self.assertEqual(response.status_code, 404)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("0.00"))

    def test_wrong_razorpay_order_cannot_confirm_top_up(self):
        response = self._confirm(razorpay_order_id="order_someone_elses")
        self.assertEqual(response.status_code, 404)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("0.00"))

    def test_confirm_requires_all_gateway_signature_fields(self):
        response = self.client.post(
            f"/api/v1/wallet/top-up/{self.pending.id}/confirm/",
            {"razorpay_payment_id": "pay_xyz"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_completed_credit_transaction_cannot_be_confirmed(self):
        self.pending.status = WalletTransaction.Status.COMPLETED
        self.pending.save(update_fields=["status"])
        response = self._confirm()
        self.assertEqual(response.status_code, 404)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("0.00"))

@override_settings(RAZORPAY_WEBHOOK_SECRET="wallet-webhook-test-secret")
class WalletTopUpWebhookTest(TestCase):
    """Only a valid Razorpay capture webhook may settle a pending top-up."""

    def setUp(self):
        self.user = User.objects.create_user(phone="9876543215", password="test123456")
        self.wallet = Wallet.objects.get(user=self.user)
        self.wallet_tx = WalletTransaction.objects.create(
            wallet=self.wallet,
            type=WalletTransaction.Type.CREDIT,
            amount=Decimal("500.00"),
            description="Wallet top-up",
            status=WalletTransaction.Status.PENDING,
            reference_id="order_wallet_webhook",
        )

    def _post_capture(self, amount=50000, currency="INR"):
        import json
        from django.test import Client

        payload = {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_wallet_webhook",
                        "order_id": "order_wallet_webhook",
                        "amount": amount,
                        "currency": currency,
                        "status": "captured",
                    }
                }
            },
        }
        raw_body = json.dumps(payload).encode("utf-8")
        signature = hmac.new(
            b"wallet-webhook-test-secret", raw_body, hashlib.sha256
        ).hexdigest()
        return Client().post(
            "/api/v1/payments/webhook/",
            data=raw_body,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=signature,
        )

    def test_captured_webhook_credits_wallet(self):
        response = self._post_capture()
        self.assertEqual(response.status_code, 200)
        self.wallet.refresh_from_db()
        self.wallet_tx.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("500.00"))
        self.assertEqual(self.wallet_tx.status, WalletTransaction.Status.COMPLETED)
        self.assertEqual(self.wallet_tx.razorpay_payment_id, "pay_wallet_webhook")

    def test_wallet_webhook_amount_mismatch_does_not_credit(self):
        response = self._post_capture(amount=60000)
        self.assertEqual(response.status_code, 400)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("0.00"))
        self.wallet_tx.refresh_from_db()
        self.assertEqual(self.wallet_tx.status, WalletTransaction.Status.PENDING)

    def test_wallet_webhook_currency_mismatch_does_not_credit(self):
        response = self._post_capture(currency="USD")
        self.assertEqual(response.status_code, 400)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("0.00"))

    def test_duplicate_wallet_capture_webhook_does_not_double_credit(self):
        first = self._post_capture()
        second = self._post_capture()
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("500.00"))


class WalletRefundAdminTest(TestCase):
    """Admin refunds must be tied to a paid cancelled booking and its customer."""

    def setUp(self):
        self.customer = User.objects.create_user(phone="9876543216", password="test123456")
        self.admin = User.objects.create_user(
            phone="9876543217", password="test123456", is_staff=True
        )
        self.admin_client = APIClient()
        self.admin_client.force_authenticate(user=self.admin)
        city = City.objects.create(name="Rawatbhata", state="Rajasthan")
        zone = Zone.objects.create(name="Test Zone", city=city, is_active=True)
        address = Address.objects.create(
            user=self.customer,
            label=Address.Label.HOME,
            house_details="House 1",
            landmark="Main road",
            full_address="Test address, Rawatbhata",
            zone=zone,
        )
        category = Category.objects.create(title="Cleaning", slug="refund-cleaning")
        service = Service.objects.create(category=category, title="Home Cleaning")
        self.booking = Booking.objects.create(
            customer=self.customer,
            address=address,
            service=service,
            scheduled_at=timezone.now() + timezone.timedelta(days=1),
            status=Booking.Status.CANCELLED,
            pricing_snapshot={"total": "250.00"},
        )
        Payment.objects.create(
            booking=self.booking,
            customer=self.customer,
            amount=Decimal("250.00"),
            method=Payment.Method.RAZORPAY,
            status=Payment.Status.PAID,
        )

    def test_admin_refund_credits_booking_customer_not_admin(self):
        response = self.admin_client.post(
            "/api/v1/wallet/refund/",
            {"booking_id": self.booking.id, "amount": "200.00"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        customer_wallet = Wallet.objects.get(user=self.customer)
        admin_wallet = Wallet.objects.get(user=self.admin)
        self.assertEqual(customer_wallet.balance, Decimal("200.00"))
        self.assertEqual(admin_wallet.balance, Decimal("0.00"))
        self.assertFalse(admin_wallet.transactions.filter(
            type=WalletTransaction.Type.REFUND,
            status=WalletTransaction.Status.COMPLETED,
        ).exists())

    def test_refund_cannot_exceed_remaining_booking_amount(self):
        first = self.admin_client.post(
            "/api/v1/wallet/refund/",
            {"booking_id": self.booking.id, "amount": "200.00"},
            format="json",
        )
        second = self.admin_client.post(
            "/api/v1/wallet/refund/",
            {"booking_id": self.booking.id, "amount": "100.00"},
            format="json",
        )
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 400)
        self.assertEqual(Wallet.objects.get(user=self.customer).balance, Decimal("200.00"))

    def test_unpaid_booking_cannot_be_refunded(self):
        Payment.objects.filter(booking=self.booking).update(status=Payment.Status.FAILED)
        response = self.admin_client.post(
            "/api/v1/wallet/refund/",
            {"booking_id": self.booking.id, "amount": "100.00"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(WalletTransaction.objects.filter(type=WalletTransaction.Type.REFUND).exists())

    def test_non_cancelled_booking_cannot_be_refunded(self):
        self.booking.status = Booking.Status.COMPLETED
        self.booking.save(update_fields=["status"])
        response = self.admin_client.post(
            "/api/v1/wallet/refund/",
            {"booking_id": self.booking.id, "amount": "100.00"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(WalletTransaction.objects.filter(type=WalletTransaction.Type.REFUND).exists())
