import re
from datetime import timedelta

from django.contrib.auth.hashers import check_password
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Address, User
from apps.bookings.models import Booking, BookingAssignment, BookingCompletionOTP
from apps.catalog.models import Category, Service
from apps.core.models import City, Zone
from apps.notifications.models import Notification
from apps.workers.models import WorkerProfile


class WorkerCompletionOTPTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            phone="+919876543201", password="password123"
        )
        self.worker_user = User.objects.create_user(
            phone="+919876543202", password="password123"
        )
        self.worker = WorkerProfile.objects.create(
            user=self.worker_user,
            status=WorkerProfile.Status.APPROVED,
            is_online=True,
        )
        city = City.objects.create(name="Jaipur", state="Rajasthan")
        zone = Zone.objects.create(name="Test Zone", city=city, is_active=True)
        address = Address.objects.create(
            user=self.customer,
            label="home",
            house_details="House 1",
            landmark="Near test landmark",
            full_address="Test address, Jaipur",
            latitude=26.9124,
            longitude=75.7873,
            zone=zone,
        )
        category = Category.objects.create(title="Cleaning", slug="otp-cleaning")
        service = Service.objects.create(
            category=category,
            title="OTP Test Cleaning",
            booking_mode=Service.BookingMode.SCHEDULED,
            pricing_type=Service.PricingType.FIXED,
            is_active=True,
        )
        self.booking = Booking.objects.create(
            customer=self.customer,
            address=address,
            service=service,
            scheduled_at=timezone.now() + timedelta(days=1),
            status=Booking.Status.IN_PROGRESS,
            pricing_snapshot={"total": "100.00"},
        )
        self.assignment = BookingAssignment.objects.create(
            booking=self.booking,
            worker=self.worker,
            accepted_at=timezone.now(),
            started_at=timezone.now(),
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.worker_user)
        self.url = f"/api/v1/workers/jobs/{self.assignment.pk}/complete/"

    def test_worker_must_verify_customer_shared_code_before_completion(self):
        issue_response = self.client.post(self.url, {}, format="json")
        self.assertEqual(issue_response.status_code, 200)
        self.assertTrue(issue_response.data["otp_required"])
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.IN_PROGRESS)

        notification = Notification.objects.get(
            user=self.customer,
            title="Share your service completion code",
        )
        match = re.search(r"\bis (\d{6})\.", notification.body)
        self.assertIsNotNone(match)
        code = match.group(1)

        otp_record = BookingCompletionOTP.objects.get(booking=self.booking)
        self.assertNotEqual(otp_record.code_hash, code)
        self.assertTrue(check_password(code, otp_record.code_hash))

        verify_response = self.client.post(
            self.url, {"otp": code}, format="json"
        )
        self.assertEqual(verify_response.status_code, 200, verify_response.data)
        self.booking.refresh_from_db()
        self.assignment.refresh_from_db()
        otp_record.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.COMPLETED)
        self.assertIsNotNone(self.booking.completed_at)
        self.assertIsNotNone(self.assignment.completed_at)
        self.assertIsNotNone(otp_record.verified_at)

    def test_invalid_code_does_not_complete_booking_and_counts_attempt(self):
        self.client.post(self.url, {}, format="json")
        notification = Notification.objects.get(
            user=self.customer,
            title="Share your service completion code",
        )
        actual_code = re.search(r"\bis (\d{6})\.", notification.body).group(1)
        invalid_code = "999999" if actual_code != "999999" else "999998"
        response = self.client.post(self.url, {"otp": invalid_code}, format="json")
        self.assertEqual(response.status_code, 400)
        self.booking.refresh_from_db()
        otp_record = BookingCompletionOTP.objects.get(booking=self.booking)
        self.assertEqual(self.booking.status, Booking.Status.IN_PROGRESS)
        self.assertEqual(otp_record.attempts, 1)

    def test_only_assigned_worker_can_request_completion_code(self):
        other_user = User.objects.create_user(
            phone="+919876543203", password="password123"
        )
        other_profile = WorkerProfile.objects.create(
            user=other_user,
            status=WorkerProfile.Status.APPROVED,
            is_online=True,
        )
        self.client.force_authenticate(user=other_user)
        response = self.client.post(self.url, {}, format="json")
        self.assertEqual(response.status_code, 404)
        self.assertFalse(BookingCompletionOTP.objects.filter(booking=self.booking).exists())
