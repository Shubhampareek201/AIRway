from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import Referral
from apps.wallet.models import Wallet, WalletTransaction

User = get_user_model()


class CustomerReferralAPITests(APITestCase):
    def setUp(self):
        self.referrer = User.objects.create_user(
            phone="+919876543210",
            name="Referrer",
        )
        self.referred = User.objects.create_user(
            phone="+919876543211",
            name="New customer",
        )
        self.client.force_authenticate(user=self.referred)

    def test_applying_referral_code_does_not_credit_wallet_immediately(self):
        response = self.client.post(
            "/api/v1/auth/referrals/",
            {"referral_code": self.referrer.referral_code},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["new_customer_credit"], "100.00")
        self.assertEqual(response.data["referrer_reward"], "200.00")
        self.assertEqual(response.data["status"], "waiting_for_first_service")
        self.assertTrue(
            Referral.objects.filter(
                referrer=self.referrer,
                referred=self.referred,
                rewarded=False,
            ).exists()
        )
        self.assertFalse(Wallet.objects.filter(user=self.referred).exists())
        self.assertFalse(Wallet.objects.filter(user=self.referrer).exists())
        self.assertFalse(WalletTransaction.objects.exists())

    def test_referral_code_cannot_be_applied_twice(self):
        self.client.post(
            "/api/v1/auth/referrals/",
            {"referral_code": self.referrer.referral_code},
            format="json",
        )
        response = self.client.post(
            "/api/v1/auth/referrals/",
            {"referral_code": self.referrer.referral_code},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Referral.objects.filter(referred=self.referred).count(), 1)

    def test_referrer_dashboard_shows_configured_rewards(self):
        self.client.force_authenticate(user=self.referrer)
        response = self.client.get("/api/v1/auth/referrals/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["new_customer_credit"], "100.00")
        self.assertEqual(response.data["referrer_reward"], "200.00")
        self.assertIn("first service", response.data["reward_condition"].lower())
