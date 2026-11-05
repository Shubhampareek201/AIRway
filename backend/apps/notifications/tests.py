from django.test import TestCase
from django.utils import timezone
import datetime

from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.notifications.models import Notification
from apps.notifications.service import create_notification


class NotificationServiceTest(TestCase):
    """Test notification service functions."""

    def setUp(self):
        self.user = User.objects.create_user(phone="+919876543210")

    def test_create_notification_returns_notification_instance(self):
        """create_notification should return a Notification instance."""
        notification = create_notification(
            user=self.user,
            type=Notification.Type.BOOKING_CONFIRMED,
            title="Booking Confirmed",
            body="Your booking is confirmed.",
        )

        self.assertIsInstance(notification, Notification)
        self.assertEqual(notification.user, self.user)
        self.assertEqual(notification.type, Notification.Type.BOOKING_CONFIRMED)
        self.assertEqual(notification.title, "Booking Confirmed")
        self.assertEqual(notification.body, "Your booking is confirmed.")

    def test_create_notification_default_channel_is_in_app(self):
        """create_notification should default to IN_APP channel."""
        notification = create_notification(
            user=self.user,
            type=Notification.Type.BOOKING_ASSIGNED,
            title="Worker Assigned",
            body="A worker has accepted.",
        )

        self.assertEqual(notification.channel, Notification.Channel.IN_APP)

    def test_create_notification_with_custom_channel(self):
        """create_notification should accept custom channel."""
        notification = create_notification(
            user=self.user,
            type=Notification.Type.PAYMENT_SUCCESS,
            title="Payment Success",
            body="Payment received.",
            channel="push",
        )

        self.assertEqual(notification.channel, "push")

    def test_create_notification_with_data_payload(self):
        """create_notification should store data payload."""
        notification = create_notification(
            user=self.user,
            type=Notification.Type.BOOKING_ASSIGNED,
            title="Worker Assigned",
            body="Worker assigned to your job.",
            channel="in_app",
            data={"booking_id": 123, "worker_id": 456, "late_webhook": False},
        )

        self.assertEqual(notification.data["booking_id"], 123)
        self.assertEqual(notification.data["worker_id"], 456)
        self.assertEqual(notification.data["late_webhook"], False)

    def test_create_notification_empty_data_defaults_to_empty_dict(self):
        """create_notification should default empty data to {}."""
        notification = create_notification(
            user=self.user,
            type=Notification.Type.BOOKING_COMPLETED,
            title="Job Done",
            body="Worker completed the job.",
        )

        self.assertEqual(notification.data, {})

    def test_create_notification_stores_in_database(self):
        """create_notification should persist the notification."""
        notification = create_notification(
            user=self.user,
            type=Notification.Type.BOOKING_CANCELLED,
            title="Cancelled",
            body="Your booking was cancelled.",
        )

        saved = Notification.objects.get(id=notification.id)
        self.assertEqual(saved.title, "Cancelled")
        self.assertEqual(saved.user, self.user)


class NotificationModelTest(TestCase):
    """Test Notification model methods."""

    def setUp(self):
        self.user = User.objects.create_user(phone="+919876543210")

    def test_mark_read_sets_is_read_and_timestamp(self):
        """mark_read() should set is_read=True and read_at timestamp."""
        notification = Notification.objects.create(
            user=self.user,
            type=Notification.Type.BOOKING_ASSIGNED,
            title="Worker Assigned",
            body="A worker has accepted your job.",
        )

        self.assertFalse(notification.is_read)
        self.assertIsNone(notification.read_at)

        notification.mark_read()

        notification.refresh_from_db()
        self.assertTrue(notification.is_read)
        self.assertIsNotNone(notification.read_at)

    def test_mark_read_is_idempotent(self):
        """Calling mark_read() twice should not cause errors."""
        notification = Notification.objects.create(
            user=self.user,
            type=Notification.Type.BOOKING_ASSIGNED,
            title="Worker Assigned",
            body="A worker has accepted your job.",
            is_read=True,
            read_at=timezone.now(),
        )

        original_read_at = notification.read_at

        notification.mark_read()

        notification.refresh_from_db()
        self.assertTrue(notification.is_read)
        self.assertEqual(notification.read_at, original_read_at)


class NotificationTypeTest(TestCase):
    """Test Notification type choices."""

    def setUp(self):
        self.user = User.objects.create_user(phone="+919876543210")

    def test_all_booking_notification_types(self):
        """Each booking-related notification type should work."""
        types_to_test = [
            Notification.Type.BOOKING_CONFIRMED,
            Notification.Type.BOOKING_ASSIGNED,
            Notification.Type.BOOKING_STARTED,
            Notification.Type.BOOKING_COMPLETED,
            Notification.Type.BOOKING_CANCELLED,
            Notification.Type.WORKER_OFFER,
            Notification.Type.WORKER_OFFER_WITHDRAWN,
            Notification.Type.WORKER_OFFER_EXPIRED,
        ]

        for notif_type in types_to_test:
            notification = Notification.objects.create(
                user=self.user,
                type=notif_type,
                title="Test",
                body="Test body",
            )
            self.assertEqual(notification.type, notif_type)

    def test_all_channel_types(self):
        """Each channel type should work."""
        channels_to_test = [
            Notification.Channel.IN_APP,
            Notification.Channel.PUSH,
            Notification.Channel.SMS,
            Notification.Channel.EMAIL,
        ]

        for channel in channels_to_test:
            notification = Notification.objects.create(
                user=self.user,
                type=Notification.Type.BOOKING_CONFIRMED,
                title="Test",
                body="Test body",
                channel=channel,
            )
            self.assertEqual(notification.channel, channel)


class NotificationAPITest(TestCase):
    """Test Notification API endpoints."""

    def setUp(self):
        self.user = User.objects.create_user(phone="+919876543210")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_list_notifications(self):
        """Should return user's notifications."""
        Notification.objects.create(
            user=self.user,
            type=Notification.Type.BOOKING_CONFIRMED,
            title="Test Notification",
            body="Test body",
        )

        response = self.client.get("/api/v1/notifications/")
        self.assertEqual(response.status_code, 200)
        results = response.data.get("results", response.data) if isinstance(response.data, dict) else response.data
        self.assertEqual(len(results), 1)

    def test_mark_notification_read(self):
        """Should mark a notification as read."""
        notification = Notification.objects.create(
            user=self.user,
            type=Notification.Type.BOOKING_ASSIGNED,
            title="Worker Assigned",
            body="Test body",
        )

        self.assertFalse(notification.is_read)

        response = self.client.post(f"/api/v1/notifications/{notification.id}/mark-read/", format="json")
        self.assertEqual(response.status_code, 200)

        notification.refresh_from_db()
        self.assertTrue(notification.is_read)
        self.assertIsNotNone(notification.read_at)

    def test_mark_all_notifications_read(self):
        """Should mark all unread notifications as read."""
        Notification.objects.create(
            user=self.user,
            type=Notification.Type.BOOKING_CONFIRMED,
            title="Notification 1",
            body="Body 1",
        )
        Notification.objects.create(
            user=self.user,
            type=Notification.Type.BOOKING_ASSIGNED,
            title="Notification 2",
            body="Body 2",
            is_read=True,
        )

        result = Notification.objects.filter(user=self.user, is_read=False).count()
        self.assertEqual(result, 1)

        response = self.client.post("/api/v1/notifications/mark-all-read/", format="json")
        self.assertEqual(response.status_code, 200)
        self.assertIn("count", response.data)

        result = Notification.objects.filter(user=self.user, is_read=False).count()
        self.assertEqual(result, 0)

    def test_cannot_mark_other_user_notification_read(self):
        """Should return 404 for another user's notification (filtered by user)."""
        other_user = User.objects.create_user(phone="+919876543211")
        notification = Notification.objects.create(
            user=other_user,
            type=Notification.Type.BOOKING_CONFIRMED,
            title="Other User Notification",
            body="Test body",
        )

        response = self.client.post(f"/api/v1/notifications/{notification.id}/mark-read/", format="json")
        # 404 because the notification doesn't belong to the authenticated user
        self.assertEqual(response.status_code, 404)

    def test_mark_read_response_format(self):
        """Should return is_read in response."""
        notification = Notification.objects.create(
            user=self.user,
            type=Notification.Type.BOOKING_ASSIGNED,
            title="Worker Assigned",
            body="Test body",
        )

        response = self.client.post(f"/api/v1/notifications/{notification.id}/mark-read/", format="json")
        self.assertEqual(response.status_code, 200)
        self.assertIn("is_read", response.data)
        self.assertTrue(response.data["is_read"])