from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import AccountDeletionRequest

User = get_user_model()


class AccountDeletionRequestTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            phone="+919876543212",
            name="Deletion Test",
        )
        self.client.force_authenticate(user=self.user)

    def test_customer_can_submit_deletion_request_without_erasing_history(self):
        response = self.client.post(
            "/api/v1/auth/delete-account/",
            {"reason": "I no longer need the service."},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], "requested")
        self.assertTrue(User.objects.get(pk=self.user.pk).is_active)
        self.assertTrue(
            AccountDeletionRequest.objects.filter(
                user=self.user,
                status=AccountDeletionRequest.Status.REQUESTED,
            ).exists()
        )

    def test_active_deletion_request_is_not_duplicated(self):
        first = self.client.post(
            "/api/v1/auth/delete-account/",
            {"reason": "Please close my account."},
            format="json",
        )
        second = self.client.post(
            "/api/v1/auth/delete-account/",
            {"reason": "Duplicate request."},
            format="json",
        )

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(
            AccountDeletionRequest.objects.filter(user=self.user).count(),
            1,
        )

    def test_customer_can_check_deletion_request_status(self):
        self.client.post(
            "/api/v1/auth/delete-account/",
            {},
            format="json",
        )
        response = self.client.get("/api/v1/auth/delete-account/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["has_request"])
        self.assertEqual(response.data["status"], "requested")


    def test_wallet_balance_keeps_deletion_request_under_review(self):
        from decimal import Decimal
        from apps.wallet.models import Wallet

        cached_wallet = self.user.wallet  # Deliberately cache the old reverse relation.
        wallet = Wallet.objects.get(user=self.user)
        wallet.balance = Decimal("50.00")
        wallet.save(update_fields=["balance", "updated_at"])
        self.assertEqual(cached_wallet.balance, Decimal("0.00"))
        response = self.client.post(
            "/api/v1/auth/delete-account/",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], "under_review")
        self.assertTrue(response.data["has_financial_obligations"])
        self.assertTrue(User.objects.get(pk=self.user.pk).is_active)


    def test_status_refreshes_after_wallet_obligation_is_settled(self):
        from decimal import Decimal
        from apps.wallet.models import Wallet

        cached_wallet = self.user.wallet  # Deliberately cache the old reverse relation.
        wallet = Wallet.objects.get(user=self.user)
        wallet.balance = Decimal("25.00")
        wallet.save(update_fields=["balance", "updated_at"])
        self.assertEqual(cached_wallet.balance, Decimal("0.00"))
        created = self.client.post(
            "/api/v1/auth/delete-account/",
            {},
            format="json",
        )
        self.assertEqual(created.data["status"], "under_review")

        wallet.balance = Decimal("0.00")
        wallet.save(update_fields=["balance", "updated_at"])
        refreshed = self.client.get("/api/v1/auth/delete-account/")

        self.assertEqual(refreshed.status_code, status.HTTP_200_OK)
        self.assertEqual(refreshed.data["status"], "requested")
        self.assertFalse(refreshed.data["has_financial_obligations"])
