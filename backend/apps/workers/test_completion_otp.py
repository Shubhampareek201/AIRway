import re
from datetime import timedelta

from django.contrib.auth.hashers import check_password
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Address, User
from apps.bookings.models import Booking, BookingAssignment, BookingCompletionOTP, BookingStartOTPException, BookingStatusHistory
from apps.catalog.models import Category, Service
from apps.core.models import City, Zone
from apps.notifications.models import Notification
from apps.workers.models import (
    WorkerProfile,
    WorkerRewardWallet,
    WorkerRewardTransaction,
    WorkerRewardWithdrawal,
    WorkerMonthlyMissionProgress,
)
from apps.workers.missions import award_mission_reward_for_completed_booking


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

    def test_worker_arrival_is_separate_from_service_start_and_saves_gps(self):
        self.booking.status = Booking.Status.ASSIGNED
        self.booking.save(update_fields=["status", "updated_at"])
        self.assignment.started_at = None
        self.assignment.save(update_fields=["started_at", "updated_at"])

        response = self.client.post(
            f"/api/v1/workers/jobs/{self.assignment.pk}/arrived/",
            {"latitude": 26.9124, "longitude": 75.7873, "accuracy_m": 12},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], Booking.Status.ASSIGNED)
        self.assertIsNotNone(response.data["arrived_at"])

        self.assignment.refresh_from_db()
        self.booking.refresh_from_db()
        self.assertIsNotNone(self.assignment.arrived_at)
        self.assertEqual(float(self.assignment.arrival_latitude), 26.9124)
        self.assertEqual(float(self.assignment.arrival_longitude), 75.7873)
        self.assertIsNone(self.assignment.started_at)
        self.assertEqual(self.booking.status, Booking.Status.ASSIGNED)

    def test_only_assigned_worker_can_record_arrival(self):
        other_user = User.objects.create_user(
            phone="+919876543204", password="password123"
        )
        self.client.force_authenticate(user=other_user)
        response = self.client.post(
            f"/api/v1/workers/jobs/{self.assignment.pk}/arrived/",
            {"latitude": 26.9124, "longitude": 75.7873},
            format="json",
        )
        self.assertEqual(response.status_code, 404)
        self.assignment.refresh_from_db()
        self.assertIsNone(self.assignment.arrived_at)

    def test_worker_must_verify_customer_four_digit_service_start_otp(self):
        self.booking.status = Booking.Status.ASSIGNED
        self.booking.save(update_fields=["status", "updated_at"])
        self.assignment.started_at = None
        self.assignment.save(update_fields=["started_at", "updated_at"])
        arrival_url = f"/api/v1/workers/jobs/{self.assignment.pk}/arrived/"
        start_url = f"/api/v1/workers/jobs/{self.assignment.pk}/start/"

        arrived = self.client.post(
            arrival_url,
            {"latitude": 26.9124, "longitude": 75.7873},
            format="json",
        )
        self.assertEqual(arrived.status_code, 200, arrived.data)
        self.booking.refresh_from_db()
        self.assignment.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.ASSIGNED)
        self.assertIsNotNone(self.assignment.arrived_at)
        self.assertIsNone(self.assignment.started_at)

        notification = Notification.objects.get(
            user=self.customer,
            title="Your service start OTP is ready",
        )
        code = notification.data["service_start_code"]
        self.assertRegex(code, r"^\d{4}$")
        self.assertTrue(check_password(code, self.assignment.start_otp_hash))
        self.assertNotIn(code, str(self.client.get(
            f"/api/v1/workers/jobs/{self.assignment.pk}/"
        ).data))

        missing = self.client.post(start_url, {}, format="json")
        self.assertEqual(missing.status_code, 400)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.ASSIGNED)

        invalid_code = "9999" if code != "9999" else "9998"
        invalid = self.client.post(
            start_url, {"start_otp": invalid_code}, format="json"
        )
        self.assertEqual(invalid.status_code, 400)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.start_otp_attempts, 1)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.ASSIGNED)

        verified = self.client.post(
            start_url, {"start_otp": code}, format="json"
        )
        self.assertEqual(verified.status_code, 200, verified.data)
        self.assertEqual(verified.data["status"], Booking.Status.IN_PROGRESS)
        self.assignment.refresh_from_db()
        self.booking.refresh_from_db()
        self.assertIsNotNone(self.assignment.start_otp_verified_at)
        self.assertIsNone(self.assignment.arrival_verified_at)
        self.assertEqual(self.booking.status, Booking.Status.IN_PROGRESS)

    def test_only_customer_can_refresh_service_start_otp(self):
        self.booking.status = Booking.Status.ASSIGNED
        self.booking.save(update_fields=["status", "updated_at"])
        self.assignment.started_at = None
        self.assignment.arrived_at = timezone.now()
        self.assignment.save(update_fields=["started_at", "arrived_at", "updated_at"])
        response = self.client.post(
            f"/api/v1/bookings/{self.booking.pk}/service-start-otp/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, 404)

    def test_customer_can_refresh_expired_service_start_otp_but_worker_cannot(self):
        self.booking.status = Booking.Status.ASSIGNED
        self.booking.save(update_fields=["status", "updated_at"])
        self.assignment.started_at = None
        self.assignment.arrived_at = timezone.now()
        self.assignment.start_otp_last_sent_at = timezone.now() - timedelta(minutes=11)
        self.assignment.start_otp_expires_at = timezone.now() - timedelta(minutes=1)
        self.assignment.save(update_fields=[
            "started_at", "arrived_at", "start_otp_last_sent_at",
            "start_otp_expires_at", "updated_at",
        ])
        url = f"/api/v1/bookings/{self.booking.pk}/service-start-otp/"

        worker_attempt = self.client.post(url, {}, format="json")
        self.assertEqual(worker_attempt.status_code, 404)

        customer_client = APIClient()
        customer_client.force_authenticate(user=self.customer)
        refreshed = customer_client.post(url, {}, format="json")
        self.assertEqual(refreshed.status_code, 200, refreshed.data)
        self.assertRegex(refreshed.data["code"], r"^\d{4}$")
        self.assignment.refresh_from_db()
        self.assertTrue(check_password(refreshed.data["code"], self.assignment.start_otp_hash))
        self.assertEqual(self.assignment.start_otp_attempts, 0)

        throttled = customer_client.post(url, {}, format="json")
        self.assertEqual(throttled.status_code, 429)

    def test_service_start_otp_locks_after_five_wrong_attempts(self):
        self.booking.status = Booking.Status.ASSIGNED
        self.booking.save(update_fields=["status", "updated_at"])
        self.assignment.started_at = None
        self.assignment.save(update_fields=["started_at", "updated_at"])
        self.client.post(
            f"/api/v1/workers/jobs/{self.assignment.pk}/arrived/",
            {},
            format="json",
        )
        for attempt in range(5):
            wrong = "9999"
            self.assignment.refresh_from_db()
            if check_password(wrong, self.assignment.start_otp_hash):
                wrong = "9998"
            response = self.client.post(
                f"/api/v1/workers/jobs/{self.assignment.pk}/start/",
                {"start_otp": wrong},
                format="json",
            )
            self.assertEqual(response.status_code, 400, response.data)
        locked = self.client.post(
            f"/api/v1/workers/jobs/{self.assignment.pk}/start/",
            {"start_otp": "1234"},
            format="json",
        )
        self.assertEqual(locked.status_code, 429)

    def test_worker_can_request_admin_exception_for_expired_start_otp(self):
        self.booking.status = Booking.Status.ASSIGNED
        self.booking.save(update_fields=["status", "updated_at"])
        self.assignment.started_at = None
        self.assignment.arrived_at = timezone.now()
        self.assignment.start_otp_hash = "expired-hash"
        self.assignment.start_otp_expires_at = timezone.now() - timedelta(minutes=1)
        self.assignment.start_otp_attempts = 5
        self.assignment.save(update_fields=[
            "started_at", "arrived_at", "start_otp_hash",
            "start_otp_expires_at", "start_otp_attempts", "updated_at",
        ])
        url = f"/api/v1/workers/jobs/{self.assignment.pk}/start-otp-exception/"
        response = self.client.post(
            url,
            {"reason": "Customer app OTP refresh is failing after repeated retries."},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        exception = BookingStartOTPException.objects.get(assignment=self.assignment)
        self.assertEqual(exception.status, BookingStartOTPException.Status.PENDING)
        self.assertEqual(exception.requested_by, self.worker)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.ASSIGNED)
        self.assertIsNone(self.assignment.started_at)

        duplicate = self.client.post(
            url,
            {"reason": "Duplicate request while admin review is pending."},
            format="json",
        )
        self.assertEqual(duplicate.status_code, 409)

    def test_admin_approval_of_start_otp_exception_starts_and_audits_booking(self):
        from django.contrib.admin.sites import AdminSite
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.test import RequestFactory
        from apps.bookings.admin import BookingStartOTPExceptionAdmin

        self.booking.status = Booking.Status.ASSIGNED
        self.booking.save(update_fields=["status", "updated_at"])
        self.assignment.started_at = None
        self.assignment.arrived_at = timezone.now()
        self.assignment.save(update_fields=["started_at", "arrived_at", "updated_at"])
        exception = BookingStartOTPException.objects.create(
            booking=self.booking,
            assignment=self.assignment,
            requested_by=self.worker,
            reason="Customer cannot retrieve the active service OTP.",
        )
        admin_user = User.objects.create_user(
            phone="+919876543299", password="admin-password"
        )
        admin_user.is_staff = True
        admin_user.is_superuser = True
        admin_user.save(update_fields=["is_staff", "is_superuser"])
        request = RequestFactory().post("/admin/")
        request.user = admin_user
        request.session = {}
        request._messages = FallbackStorage(request)
        model_admin = BookingStartOTPExceptionAdmin(
            BookingStartOTPException, AdminSite()
        )
        model_admin.approve_service_start_exception(
            request, BookingStartOTPException.objects.filter(pk=exception.pk)
        )

        exception.refresh_from_db()
        self.booking.refresh_from_db()
        self.assignment.refresh_from_db()
        self.assertEqual(exception.status, BookingStartOTPException.Status.APPROVED)
        self.assertEqual(exception.reviewed_by, admin_user)
        self.assertEqual(self.booking.status, Booking.Status.IN_PROGRESS)
        self.assertIsNotNone(self.assignment.started_at)
        self.assertTrue(
            BookingStatusHistory.objects.filter(
                booking=self.booking,
                changed_by=admin_user,
                note__contains=f"exception #{exception.pk}",
            ).exists()
        )

    def test_worker_location_requires_explicit_consent_and_30_minute_window(self):
        self.booking.status = Booking.Status.ASSIGNED
        self.booking.scheduled_at = timezone.now() + timedelta(hours=2)
        self.booking.save(update_fields=["status", "scheduled_at", "updated_at"])
        location_url = f"/api/v1/workers/jobs/{self.assignment.pk}/location/"
        consent_url = f"/api/v1/workers/jobs/{self.assignment.pk}/location-sharing/"

        denied = self.client.post(
            location_url,
            {"latitude": 26.9124, "longitude": 75.7873},
            format="json",
        )
        self.assertEqual(denied.status_code, 403)

        consent = self.client.post(
            consent_url, {"enabled": True}, format="json"
        )
        self.assertEqual(consent.status_code, 200, consent.data)
        self.assignment.refresh_from_db()
        self.assertTrue(self.assignment.location_sharing_enabled)

        too_early = self.client.post(
            location_url,
            {"latitude": 26.9124, "longitude": 75.7873},
            format="json",
        )
        self.assertEqual(too_early.status_code, 409)

        self.booking.scheduled_at = timezone.now() + timedelta(minutes=20)
        self.booking.save(update_fields=["scheduled_at", "updated_at"])
        accepted = self.client.post(
            location_url,
            {"latitude": 26.9124, "longitude": 75.7873, "accuracy_m": 10},
            format="json",
        )
        self.assertEqual(accepted.status_code, 200, accepted.data)

        disabled = self.client.post(
            consent_url, {"enabled": False}, format="json"
        )
        self.assertEqual(disabled.status_code, 200)
        self.assignment.refresh_from_db()
        self.assertFalse(self.assignment.location_sharing_enabled)
        self.assertIsNone(self.assignment.live_latitude)
        self.assertIsNone(self.assignment.live_location_updated_at)

        customer_client = APIClient()
        customer_client.force_authenticate(user=self.customer)
        tracking = customer_client.get(
            f"/api/v1/bookings/{self.booking.pk}/track/"
        )
        self.assertEqual(tracking.status_code, 200)
        self.assertFalse(tracking.data["location_is_fresh"])
        self.assertIsNone(tracking.data["worker_latitude"])

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
    def test_mission_rewards_are_cumulative_and_idempotent(self):
        last_booking = None
        for index in range(25):
            booking = Booking.objects.create(
                customer=self.customer,
                address=self.booking.address,
                service=self.booking.service,
                scheduled_at=timezone.now() + timedelta(days=1),
                status=Booking.Status.COMPLETED,
                pricing_snapshot={"subtotal": "501.00", "total": "501.00"},
                completed_at=timezone.now(),
            )
            BookingAssignment.objects.create(
                booking=booking,
                worker=self.worker,
                accepted_at=timezone.now(),
                completed_at=timezone.now(),
            )
            BookingCompletionOTP.objects.create(
                booking=booking, code_hash="verified-test-code",
                expires_at=timezone.now() + timedelta(hours=1),
                last_sent_at=timezone.now(), verified_at=timezone.now(),
            )
            award_mission_reward_for_completed_booking(booking)
            last_booking = booking

        wallet = WorkerRewardWallet.objects.get(worker=self.worker)
        self.assertEqual(wallet.eligible_jobs_count, 25)
        progress = WorkerMonthlyMissionProgress.objects.get(worker=self.worker, month_start=timezone.localdate().replace(day=1))
        self.assertEqual(progress.eligible_jobs_count, 25)
        self.assertEqual(wallet.balance, 1900)
        self.assertEqual(wallet.total_earned, 1900)
        rewards = {
            row.milestone_jobs: row.amount
            for row in WorkerRewardTransaction.objects.filter(
                worker=self.worker,
                type=WorkerRewardTransaction.Type.MISSION_REWARD,
            )
        }
        self.assertEqual(rewards, {5: 300, 15: 600, 25: 1000})

        award_mission_reward_for_completed_booking(last_booking)
        wallet.refresh_from_db()
        self.assertEqual(wallet.eligible_jobs_count, 25)
        self.assertEqual(wallet.balance, 1900)

    def test_service_cost_of_500_or_less_is_not_eligible(self):
        booking = Booking.objects.create(
            customer=self.customer,
            address=self.booking.address,
            service=self.booking.service,
            scheduled_at=timezone.now() + timedelta(days=1),
            status=Booking.Status.COMPLETED,
            pricing_snapshot={"subtotal": "500.00", "total": "500.00"},
            completed_at=timezone.now(),
        )
        BookingAssignment.objects.create(
            booking=booking,
            worker=self.worker,
            accepted_at=timezone.now(),
            completed_at=timezone.now(),
        )
        BookingCompletionOTP.objects.create(
            booking=booking, code_hash="verified-test-code",
            expires_at=timezone.now() + timedelta(hours=1),
            last_sent_at=timezone.now(), verified_at=timezone.now(),
        )
        award_mission_reward_for_completed_booking(booking)
        self.assertFalse(WorkerMonthlyMissionProgress.objects.filter(worker=self.worker).exists())
        wallet = WorkerRewardWallet.objects.get(worker=self.worker)
        self.assertEqual(wallet.balance, 0)
        self.assertEqual(wallet.eligible_jobs_count, 1)

    def test_mission_wallet_withdrawal_is_separate_and_debits_available_rewards(self):
        self.worker.upi_id = "worker@upi"
        self.worker.save(update_fields=["upi_id", "updated_at"])
        wallet = WorkerRewardWallet.objects.create(
            worker=self.worker,
            balance=500,
            total_earned=500,
        )
        response = self.client.post(
            "/api/v1/workers/mission-wallet/",
            {"amount": "200.00"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="completion-otp-worker-withdrawal-1",
        )
        self.assertEqual(response.status_code, 201, response.data)
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance, 300)
        withdrawal = WorkerRewardWithdrawal.objects.get(worker=self.worker)
        self.assertEqual(withdrawal.amount, 200)
        self.assertEqual(withdrawal.status, WorkerRewardWithdrawal.Status.PENDING)
        self.assertTrue(WorkerRewardTransaction.objects.filter(
            wallet=wallet,
            reference_key=f"mission-withdrawal:{withdrawal.pk}",
            type=WorkerRewardTransaction.Type.WITHDRAWAL,
        ).exists())

