from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.wallet.models import Wallet, WalletTransaction

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

    def test_top_up_creates_pending_transaction(self):
        response = self.client.post(
            "/api/v1/wallet/top-up/",
            {"amount": 500, "reference_id": "order_123"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["type"], "credit")
        self.assertEqual(response.data["status"], "pending")
        self.assertEqual(response.data["amount"], "500.00")

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

    def test_refund_creates_completed_transaction(self):
        response = self.client.post(
            "/api/v1/wallet/refund/",
            {"booking_id": 42, "amount": 250, "reason": "Cancelled booking"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["type"], "refund")
        self.assertEqual(response.data["status"], "completed")
        self.assertEqual(response.data["amount"], "250.00")
        self.assertEqual(response.data["reference_id"], "42")

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


class WalletTopUpConfirmTest(TestCase):
    """Test top-up confirmation flow."""

    def setUp(self):
        self.user = User.objects.create_user(phone="9876543213", password="test123456")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_confirm_top_up_completes_transaction(self):
        """Confirming a pending top-up should mark it completed and update balance."""
        # Create a pending top-up transaction
        response = self.client.post(
            "/api/v1/wallet/top-up/",
            {"amount": 1000, "reference_id": "order_abc"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        transaction_id = response.data["id"]
        wallet = Wallet.objects.get(user=self.user)
        self.assertEqual(wallet.balance, 0)  # Balance still 0 (pending)

        # Confirm the top-up
        confirm_response = self.client.post(
            f"/api/v1/wallet/top-up/{transaction_id}/confirm/",
            {"razorpay_payment_id": "pay_xyz"},
            format="json",
        )
        self.assertEqual(confirm_response.status_code, 200)
        self.assertEqual(confirm_response.data["status"], "completed")

        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, 1000)  # Balance now updated

    def test_confirm_nonexistent_transaction(self):
        """Confirming non-existent transaction should return 404."""
        response = self.client.post(
            "/api/v1/wallet/top-up/99999/confirm/",
            {"razorpay_payment_id": "pay_xyz"},
            format="json",
        )
        self.assertEqual(response.status_code, 404)

    def test_confirm_already_completed_transaction(self):
        """Confirming an already completed transaction should return 404."""
        # Create and complete a transaction via credit
        wallet = Wallet.objects.get_or_create(user=self.user)[0]
        WalletTransaction.objects.create(
            wallet=wallet,
            type=WalletTransaction.Type.CREDIT,
            amount=500,
            description="Bonus",
            status=WalletTransaction.Status.COMPLETED,
        )
        transaction_id = wallet.transactions.first().id

        response = self.client.post(
            f"/api/v1/wallet/top-up/{transaction_id}/confirm/",
            format="json",
        )
        self.assertEqual(response.status_code, 404)