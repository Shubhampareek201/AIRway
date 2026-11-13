from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import DeviceToken, User


class DeviceTokenAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(phone="+919876543210", password="password123")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.url = "/api/v1/auth/devices/token/"

    def test_authenticated_user_can_register_device_token(self):
        response = self.client.post(
            self.url,
            {"token": "fcm-test-token", "platform": "android"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["registered"])
        device = DeviceToken.objects.get(token="fcm-test-token")
        self.assertEqual(device.user, self.user)
        self.assertEqual(device.platform, "android")

    def test_registering_existing_token_moves_it_to_current_account(self):
        other = User.objects.create_user(phone="+919876543211", password="password123")
        DeviceToken.objects.create(user=other, token="shared-device-token", platform="android")

        response = self.client.post(
            self.url,
            {"token": "shared-device-token", "platform": "ios"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        device = DeviceToken.objects.get(token="shared-device-token")
        self.assertEqual(device.user, self.user)
        self.assertEqual(device.platform, "ios")

    def test_user_can_unregister_only_their_own_device_token(self):
        device = DeviceToken.objects.create(user=self.user, token="my-device-token")
        other = User.objects.create_user(phone="+919876543212", password="password123")
        other_device = DeviceToken.objects.create(user=other, token="other-device-token")

        response = self.client.delete(self.url, {"token": "my-device-token"}, format="json")

        self.assertEqual(response.status_code, 204)
        self.assertFalse(DeviceToken.objects.filter(pk=device.pk).exists())
        self.assertTrue(DeviceToken.objects.filter(pk=other_device.pk).exists())

    def test_invalid_platform_is_rejected(self):
        response = self.client.post(
            self.url,
            {"token": "fcm-test-token", "platform": "desktop"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_unauthenticated_user_cannot_register_token(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(
            self.url,
            {"token": "fcm-test-token", "platform": "android"},
            format="json",
        )
        self.assertEqual(response.status_code, 401)
