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
        self.assertEqual(Wallet.objects.get(user=self.referred).balance, 0)
        self.assertEqual(Wallet.objects.get(user=self.referrer).balance, 0)
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


    def test_applied_referral_is_returned_to_referred_customer(self):
        Referral.objects.create(referrer=self.referrer, referred=self.referred)
        response = self.client.get("/api/v1/auth/referrals/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["applied_referral"]["code"],
            self.referrer.referral_code,
        )
        self.assertFalse(response.data["applied_referral"]["rewarded"])

    def test_referral_can_be_applied_to_an_older_account_before_first_booking(self):
        from datetime import timedelta
        from django.utils import timezone
        from apps.accounts.referrals import apply_referral_code

        self.referred.created_at = timezone.now() - timedelta(days=30)
        self.referred.save(update_fields=["created_at"])
        referral = apply_referral_code(self.referred, self.referrer.referral_code)
        self.assertEqual(referral.referrer, self.referrer)
        self.assertEqual(referral.referred, self.referred)

    def test_pending_booking_does_not_earn_referral_rewards(self):
        from types import SimpleNamespace
        from apps.accounts.referrals import reward_referral_for_first_completed_booking

        referral = Referral.objects.create(
            referrer=self.referrer,
            referred=self.referred,
        )
        pending_booking = SimpleNamespace(
            status="in_progress",
            customer=self.referred,
            pk=987655,
        )
        self.assertFalse(reward_referral_for_first_completed_booking(pending_booking))
        referral.refresh_from_db()
        self.assertFalse(referral.rewarded)
        self.assertFalse(WalletTransaction.objects.exists())


    def test_first_completed_service_credits_both_wallets_once(self):
        from types import SimpleNamespace
        from apps.accounts.referrals import reward_referral_for_first_completed_booking

        referral = Referral.objects.create(
            referrer=self.referrer,
            referred=self.referred,
        )
        completed_booking = SimpleNamespace(
            status="completed",
            customer=self.referred,
            pk=987654,
        )

        self.assertTrue(reward_referral_for_first_completed_booking(completed_booking))
        self.assertFalse(reward_referral_for_first_completed_booking(completed_booking))

        referral.refresh_from_db()
        self.assertTrue(referral.rewarded)
        self.assertIsNotNone(referral.rewarded_at)

        referrer_wallet = Wallet.objects.get(user=self.referrer)
        referred_wallet = Wallet.objects.get(user=self.referred)
        self.assertEqual(str(referrer_wallet.balance), "200.00")
        self.assertEqual(str(referred_wallet.balance), "100.00")
        self.assertEqual(WalletTransaction.objects.filter(wallet=referrer_wallet).count(), 1)
        self.assertEqual(WalletTransaction.objects.filter(wallet=referred_wallet).count(), 1)
        from apps.notifications.models import Notification
        self.assertEqual(
            Notification.objects.filter(type=Notification.Type.REFERRAL_REWARD).count(),
            2,
        )


    def test_cancelled_booking_does_not_earn_referral_rewards(self):
        from types import SimpleNamespace
        from apps.accounts.referrals import reward_referral_for_first_completed_booking

        referral = Referral.objects.create(
            referrer=self.referrer,
            referred=self.referred,
        )
        cancelled_booking = SimpleNamespace(
            status="cancelled",
            customer=self.referred,
            pk=987653,
        )

        self.assertFalse(reward_referral_for_first_completed_booking(cancelled_booking))
        referral.refresh_from_db()
        self.assertFalse(referral.rewarded)
        self.assertFalse(WalletTransaction.objects.exists())


    def test_registration_applies_referral_code_exactly_once(self):
        response = self.client.post(
            "/api/v1/auth/register/",
            {
                "phone": "+919876543212",
                "name": "Signup Referred",
                "password": "StrongPass!234",
                "confirm_password": "StrongPass!234",
                "referral_code": self.referrer.referral_code,
                "terms_accepted": True,
                "privacy_accepted": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        new_user = User.objects.get(phone="+919876543212")
        self.assertEqual(
            Referral.objects.filter(referrer=self.referrer, referred=new_user).count(),
            1,
        )
        self.assertEqual(Wallet.objects.get(user=new_user).balance, 0)
        self.assertEqual(Wallet.objects.get(user=self.referrer).balance, 0)
        self.assertFalse(WalletTransaction.objects.exists())
