from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import AccountDeletionRequest

User = get_user_model()


class AccountDeletionRequestTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            phone="+919876543219",
            name="Deletion Customer",
        )
        self.client.force_authenticate(user=self.user)

    def test_customer_can_cancel_pending_deletion_request(self):
        submitted = self.client.post(
            "/api/v1/auth/delete-account/",
            {"reason": "I changed my mind."},
            format="json",
        )
        self.assertEqual(submitted.status_code, status.HTTP_201_CREATED)
        request_id = submitted.data["id"]

        cancelled = self.client.delete("/api/v1/auth/delete-account/")

        self.assertEqual(cancelled.status_code, status.HTTP_200_OK)
        self.assertEqual(cancelled.data["status"], AccountDeletionRequest.Status.CANCELLED)
        self.assertTrue(self.user.is_active)
        self.assertEqual(
            AccountDeletionRequest.objects.get(pk=request_id).status,
            AccountDeletionRequest.Status.CANCELLED,
        )

    def test_customer_cannot_cancel_when_no_active_request_exists(self):
        response = self.client.delete("/api/v1/auth/delete-account/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
