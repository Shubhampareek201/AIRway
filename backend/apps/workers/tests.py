import io
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from datetime import datetime, time, timedelta
from PIL import Image

def _tomorrow_at_noon():
    """Return a stable daytime booking slot for worker-schedule tests."""
    tomorrow = timezone.localtime().date() + timedelta(days=1)
    return timezone.make_aware(
        datetime.combine(tomorrow, time(12, 0)),
        timezone.get_current_timezone(),
    )


from apps.accounts.models import User, Address
from apps.catalog.models import Category, Service, ServiceVariant
from apps.workers.models import WorkerProfile, WorkerService, WorkerZone, WorkerSchedule, WorkerDocument
from apps.core.models import City, Zone
from apps.bookings.models import Booking, WorkerOffer, BookingAssignment


class WorkerProfileAPITest(TestCase):
    """Test worker profile endpoint."""

    def setUp(self):
        self.client = APIClient()
        self.worker_user = User.objects.create_user(
            phone="+919876543210",
            name="Test Worker",
            password="password123"
        )
        self.worker_profile = WorkerProfile.objects.create(
            user=self.worker_user,
            status=WorkerProfile.Status.APPROVED,
            is_online=True,
            rating_avg=4.5,
            experience_years=5,
            upi_id="upi://test@upi",
        )
        self.client.force_authenticate(user=self.worker_user)

    def test_worker_profile_returns_profile_data(self):
        """Should return worker profile data for authenticated worker."""
        response = self.client.get("/api/v1/workers/me/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], self.worker_profile.id)
        self.assertEqual(response.data["status"], "approved")
        self.assertEqual(response.data["is_online"], True)
        self.assertEqual(float(response.data["rating_avg"]), 4.5)
        self.assertEqual(response.data["experience_years"], 5)
        self.assertEqual(response.data["upi_id"], "upi://test@upi")

    def test_worker_profile_no_profile_returns_empty(self):
        """Should return empty profile structure when user has no worker profile."""
        regular_user = User.objects.create_user(
            phone="+919876543211",
            password="password123"
        )
        self.client.force_authenticate(user=regular_user)

        response = self.client.get("/api/v1/workers/me/")

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["id"])
        self.assertEqual(response.data["status"], "no_profile")
        self.assertFalse(response.data["is_online"])

    def test_unauthenticated_worker_profile_denied(self):
        """Should return 401 for unauthenticated request."""
        self.client.force_authenticate(user=None)

        response = self.client.get("/api/v1/workers/me/")

        self.assertEqual(response.status_code, 401)


class NearbyWorkersAPITest(TestCase):
    """Test nearby workers endpoint."""

    def setUp(self):
        self.client = APIClient()

        self.city = City.objects.create(name="Mumbai", state="Maharashtra")
        self.zone = Zone.objects.create(name="Dadar", city=self.city, is_active=True)

        self.category = Category.objects.create(title="Cleaning", slug="cleaning")
        self.service = Service.objects.create(
            category=self.category,
            title="Home Cleaning",
            booking_mode="scheduled",
            pricing_type="fixed",
            is_active=True,
        )

        self.customer_user = User.objects.create_user(phone="+919876543210")
        self.customer_address = Address.objects.create(
            user=self.customer_user,
            label="home",
            house_details="Floor 2, Apt 301",
            full_address="123 Main Street, Mumbai 400001",
            latitude=19.0760,
            longitude=72.8777,
            zone=self.zone,
        )

        self.client.force_authenticate(user=self.customer_user)

    def test_nearby_workers_requires_authentication(self):
        """Should return 401 for unauthenticated request."""
        self.client.force_authenticate(user=None)

        response = self.client.get("/api/v1/workers/nearby/")

        self.assertEqual(response.status_code, 401)

    def test_nearby_workers_without_zone(self):
        """Should return empty results when address has no zone."""
        address_no_zone = Address.objects.create(
            user=self.customer_user,
            label="work",
            house_details="Office",
            full_address="456 Business Ave, Mumbai 400002",
            zone=None,
        )

        response = self.client.get(f"/api/v1/workers/nearby/?address_id={address_no_zone.id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 0)

    def test_nearby_workers_with_address_id(self):
        """Should return approved workers in same zone."""
        worker_user = User.objects.create_user(phone="+919876543220", name="Worker")
        worker_profile = WorkerProfile.objects.create(
            user=worker_user,
            status=WorkerProfile.Status.APPROVED,
            is_online=True,
        )
        WorkerService.objects.create(worker=worker_profile, service=self.service)
        WorkerZone.objects.create(worker=worker_profile, zone=self.zone)
        WorkerSchedule.objects.create(
            worker=worker_profile,
            weekday=0,
            start_time="09:00",
            end_time="18:00",
            is_active=True,
        )

        response = self.client.get(f"/api/v1/workers/nearby/?address_id={self.customer_address.id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], worker_profile.id)

    def test_nearby_workers_filters_inactive(self):
        """Should not return suspended or non-online workers."""
        suspended_user = User.objects.create_user(phone="+919876543221", name="Suspended")
        suspended_profile = WorkerProfile.objects.create(
            user=suspended_user,
            status=WorkerProfile.Status.SUSPENDED,
            is_online=True,
        )
        WorkerZone.objects.create(worker=suspended_profile, zone=self.zone)

        offline_user = User.objects.create_user(phone="+919876543222", name="Offline")
        offline_profile = WorkerProfile.objects.create(
            user=offline_user,
            status=WorkerProfile.Status.APPROVED,
            is_online=False,
        )
        WorkerZone.objects.create(worker=offline_profile, zone=self.zone)

        response = self.client.get(f"/api/v1/workers/nearby/?address_id={self.customer_address.id}")

        self.assertEqual(response.data["count"], 0)


class JobOfferAPITest(TestCase):
    """Test worker job offer endpoints."""

    def setUp(self):
        self.client = APIClient()

        self.city = City.objects.create(name="Mumbai", state="Maharashtra")
        self.zone = Zone.objects.create(name="Dadar", city=self.city, is_active=True)

        self.category = Category.objects.create(title="Cleaning", slug="cleaning")
        self.service = Service.objects.create(
            category=self.category,
            title="Home Cleaning",
            booking_mode="scheduled",
            pricing_type="fixed",
            is_active=True,
        )

        self.customer_user = User.objects.create_user(phone="+919876543210", name="Customer")
        self.worker_user = User.objects.create_user(phone="+919876543220", name="Worker")

        self.customer_address = Address.objects.create(
            user=self.customer_user,
            label="home",
            house_details="Floor 2, Apt 301",
            full_address="123 Main Street, Mumbai 400001",
            zone=self.zone,
        )

        self.worker_profile = WorkerProfile.objects.create(
            user=self.worker_user,
            status=WorkerProfile.Status.APPROVED,
            is_online=True,
        )
        WorkerService.objects.create(worker=self.worker_profile, service=self.service)
        WorkerZone.objects.create(worker=self.worker_profile, zone=self.zone)

        self.booking = Booking.objects.create(
            customer=self.customer_user,
            address=self.customer_address,
            service=self.service,
            booking_mode=Booking.BookingMode.SCHEDULED,
            scheduled_at=_tomorrow_at_noon(),
            status=Booking.Status.PENDING,
        )
        booking_local = timezone.localtime(self.booking.scheduled_at)
        WorkerSchedule.objects.create(
            worker=self.worker_profile,
            weekday=booking_local.weekday(),
            start_time="00:00:00",
            end_time="23:59:00",
            is_active=True,
        )


    def test_offers_requires_authentication(self):
        """Should return 401 for unauthenticated request."""
        self.client.force_authenticate(user=None)

        response = self.client.get("/api/v1/workers/offers/")

        self.assertEqual(response.status_code, 401)

    def test_offers_for_non_worker(self):
        """Should return 404 for user without worker profile."""
        self.client.force_authenticate(user=self.customer_user)

        response = self.client.get("/api/v1/workers/offers/")

        self.assertEqual(response.status_code, 404)

    def test_offers_returns_pending_offers(self):
        """Should return list of pending offers for worker."""
        self.client.force_authenticate(user=self.worker_user)

        offer = WorkerOffer.objects.create(
            booking=self.booking,
            worker=self.worker_profile,
            expires_at=timezone.now() + timedelta(hours=1),
        )

        response = self.client.get("/api/v1/workers/offers/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], offer.id)
        self.assertEqual(response.data["results"][0]["status"], "pending")

    def test_accept_offer(self):
        """Should accept an offer and create booking assignment."""
        self.client.force_authenticate(user=self.worker_user)

        offer = WorkerOffer.objects.create(
            booking=self.booking,
            worker=self.worker_profile,
            expires_at=timezone.now() + timedelta(hours=1),
        )

        response = self.client.post(f"/api/v1/workers/offers/{offer.id}/accept/", format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "accepted")

        offer.refresh_from_db()
        self.assertEqual(offer.status, WorkerOffer.Status.ACCEPTED)

        assignment = BookingAssignment.objects.get(booking=self.booking)
        self.assertEqual(assignment.worker, self.worker_profile)

    def test_accept_rejects_worker_who_went_offline_after_offer(self):
        self.client.force_authenticate(user=self.worker_user)
        offer = WorkerOffer.objects.create(
            booking=self.booking,
            worker=self.worker_profile,
            expires_at=timezone.now() + timedelta(hours=1),
        )
        self.worker_profile.is_online = False
        self.worker_profile.save(update_fields=["is_online", "updated_at"])

        response = self.client.post(f"/api/v1/workers/offers/{offer.id}/accept/", format="json")

        self.assertEqual(response.status_code, 409)
        self.assertFalse(BookingAssignment.objects.filter(booking=self.booking).exists())
        offer.refresh_from_db()
        self.assertEqual(offer.status, WorkerOffer.Status.PENDING)

    def test_accept_rejects_worker_after_service_skill_is_removed(self):
        self.client.force_authenticate(user=self.worker_user)
        offer = WorkerOffer.objects.create(
            booking=self.booking,
            worker=self.worker_profile,
            expires_at=timezone.now() + timedelta(hours=1),
        )
        WorkerService.objects.filter(
            worker=self.worker_profile,
            service=self.service,
        ).delete()

        response = self.client.post(f"/api/v1/workers/offers/{offer.id}/accept/", format="json")

        self.assertEqual(response.status_code, 409)
        self.assertFalse(BookingAssignment.objects.filter(booking=self.booking).exists())

    def test_accept_rejects_worker_after_zone_is_removed(self):
        self.client.force_authenticate(user=self.worker_user)
        offer = WorkerOffer.objects.create(
            booking=self.booking,
            worker=self.worker_profile,
            expires_at=timezone.now() + timedelta(hours=1),
        )
        WorkerZone.objects.filter(
            worker=self.worker_profile,
            zone=self.zone,
        ).delete()

        response = self.client.post(f"/api/v1/workers/offers/{offer.id}/accept/", format="json")

        self.assertEqual(response.status_code, 409)
        self.assertFalse(BookingAssignment.objects.filter(booking=self.booking).exists())

    def test_accept_rejects_worker_with_blocked_slot(self):
        from apps.availability.models import WorkerBlockedSlot

        self.client.force_authenticate(user=self.worker_user)
        offer = WorkerOffer.objects.create(
            booking=self.booking,
            worker=self.worker_profile,
            expires_at=timezone.now() + timedelta(hours=1),
        )
        WorkerBlockedSlot.objects.create(
            worker=self.worker_user,
            start_at=self.booking.scheduled_at - timedelta(minutes=15),
            end_at=self.booking.scheduled_at + timedelta(minutes=90),
            reason="Emergency",
        )

        response = self.client.post(f"/api/v1/workers/offers/{offer.id}/accept/", format="json")

        self.assertEqual(response.status_code, 409)
        self.assertFalse(BookingAssignment.objects.filter(booking=self.booking).exists())

    def test_accept_marks_expired_offer_and_rejects_it(self):
        self.client.force_authenticate(user=self.worker_user)
        offer = WorkerOffer.objects.create(
            booking=self.booking,
            worker=self.worker_profile,
            expires_at=timezone.now() - timedelta(minutes=1),
        )

        response = self.client.post(f"/api/v1/workers/offers/{offer.id}/accept/", format="json")

        self.assertEqual(response.status_code, 410)
        offer.refresh_from_db()
        self.assertEqual(offer.status, WorkerOffer.Status.EXPIRED)
        self.assertFalse(BookingAssignment.objects.filter(booking=self.booking).exists())

    def test_accept_rejects_worker_with_overlapping_active_assignment(self):
        self.client.force_authenticate(user=self.worker_user)
        overlapping = Booking.objects.create(
            customer=self.customer_user,
            address=self.customer_address,
            service=self.service,
            booking_mode=Booking.BookingMode.SCHEDULED,
            scheduled_at=self.booking.scheduled_at,
            status=Booking.Status.ASSIGNED,
        )
        BookingAssignment.objects.create(booking=overlapping, worker=self.worker_profile)
        offer = WorkerOffer.objects.create(
            booking=self.booking,
            worker=self.worker_profile,
            expires_at=timezone.now() + timedelta(hours=1),
        )

        response = self.client.post(f"/api/v1/workers/offers/{offer.id}/accept/", format="json")

        self.assertEqual(response.status_code, 409)
        self.assertFalse(BookingAssignment.objects.filter(booking=self.booking).exists())

    def test_decline_offer(self):
        """Should decline an offer."""
        self.client.force_authenticate(user=self.worker_user)

        offer = WorkerOffer.objects.create(
            booking=self.booking,
            worker=self.worker_profile,
            expires_at=timezone.now() + timedelta(hours=1),
        )

        response = self.client.post(f"/api/v1/workers/offers/{offer.id}/decline/", format="json")

        self.assertEqual(response.status_code, 200)

        offer.refresh_from_db()
        self.assertEqual(offer.status, WorkerOffer.Status.DECLINED)

    def test_withdraw_offer(self):
        """Should withdraw a pending offer."""
        self.client.force_authenticate(user=self.worker_user)

        offer = WorkerOffer.objects.create(
            booking=self.booking,
            worker=self.worker_profile,
            expires_at=timezone.now() + timedelta(hours=1),
        )

        response = self.client.post(f"/api/v1/workers/offers/{offer.id}/withdraw/", format="json")

        self.assertEqual(response.status_code, 200)

        offer.refresh_from_db()
        self.assertEqual(offer.status, WorkerOffer.Status.WITHDRAWN)

    def test_accept_already_accepted_offer_fails(self):
        """Should not allow accepting an already accepted offer."""
        self.client.force_authenticate(user=self.worker_user)

        offer = WorkerOffer.objects.create(
            booking=self.booking,
            worker=self.worker_profile,
            status=WorkerOffer.Status.ACCEPTED,
            expires_at=timezone.now() + timedelta(hours=1),
        )

        response = self.client.post(f"/api/v1/workers/offers/{offer.id}/accept/", format="json")

        self.assertEqual(response.status_code, 400)

    def test_offer_not_found(self):
        """Should return 404 for non-existent offer."""
        self.client.force_authenticate(user=self.worker_user)

        response = self.client.post("/api/v1/workers/offers/99999/accept/", format="json")

        self.assertEqual(response.status_code, 404)

    def test_offer_belongs_to_different_worker(self):
        """Should return 404 when trying to access another worker's offer."""
        other_worker_user = User.objects.create_user(phone="+919876543221", name="Other Worker")
        other_worker_profile = WorkerProfile.objects.create(
            user=other_worker_user,
            status=WorkerProfile.Status.APPROVED,
            is_online=True,
        )

        self.client.force_authenticate(user=self.worker_user)

        response = self.client.post(f"/api/v1/workers/offers/99999/accept/", format="json")

        self.assertEqual(response.status_code, 404)


class WorkerJobLifecycleTest(TestCase):
    """Test worker job lifecycle status transitions."""

    def setUp(self):
        self.client = APIClient()

        self.city = City.objects.create(name="Mumbai", state="Maharashtra")
        self.zone = Zone.objects.create(name="Dadar", city=self.city, is_active=True)

        self.category = Category.objects.create(title="Cleaning", slug="cleaning")
        self.service = Service.objects.create(
            category=self.category,
            title="Home Cleaning",
            booking_mode="scheduled",
            pricing_type="fixed",
            is_active=True,
        )

        self.customer_user = User.objects.create_user(phone="+919876543210", name="Customer")
        self.worker_user = User.objects.create_user(phone="+919876543220", name="Worker")

        self.customer_address = Address.objects.create(
            user=self.customer_user,
            label="home",
            house_details="Floor 2, Apt 301",
            full_address="123 Main Street, Mumbai 400001",
            zone=self.zone,
        )

        self.worker_profile = WorkerProfile.objects.create(
            user=self.worker_user,
            status=WorkerProfile.Status.APPROVED,
            is_online=True,
        )
        WorkerService.objects.create(worker=self.worker_profile, service=self.service)
        WorkerZone.objects.create(worker=self.worker_profile, zone=self.zone)

        self.client.force_authenticate(user=self.customer_user)

    def test_worker_can_start_assigned_job(self):
        """Worker can mark a job as in progress after accepting offer."""
        booking = Booking.objects.create(
            customer=self.customer_user,
            address=self.customer_address,
            service=self.service,
            booking_mode="scheduled",
            scheduled_at=_tomorrow_at_noon(),
            status=Booking.Status.ASSIGNED,
        )
        assignment = BookingAssignment.objects.create(
            booking=booking,
            worker=self.worker_profile,
        )

        self.client.force_authenticate(user=self.worker_user)
        response = self.client.post(f"/api/v1/bookings/{booking.id}/start/", format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "in_progress")

    def test_worker_can_complete_in_progress_job(self):
        """Worker can mark a job as completed when in progress."""
        booking = Booking.objects.create(
            customer=self.customer_user,
            address=self.customer_address,
            service=self.service,
            booking_mode="scheduled",
            scheduled_at=_tomorrow_at_noon(),
            status=Booking.Status.IN_PROGRESS,
        )
        assignment = BookingAssignment.objects.create(
            booking=booking,
            worker=self.worker_profile,
            started_at=timezone.now(),
        )

        self.client.force_authenticate(user=self.worker_user)
        response = self.client.post(f"/api/v1/bookings/{booking.id}/complete/", format="json")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["otp_required"])

        import re
        from apps.notifications.models import Notification
        otp_notice = Notification.objects.filter(
            user=self.customer_user,
            data__purpose="service_completion_otp",
            data__booking_id=booking.id,
        ).latest("created_at")
        otp_match = re.search(r"\b(\d{6})\b", otp_notice.body)
        self.assertIsNotNone(otp_match, otp_notice.body)

        verified_response = self.client.post(
            f"/api/v1/bookings/{booking.id}/complete/",
            {"otp": otp_match.group(1)},
            format="json",
        )
        self.assertEqual(verified_response.status_code, 200, verified_response.data)
        self.assertEqual(verified_response.data["status"], "completed")

    def test_worker_can_start_paid_confirmed_job(self):
        """A paid booking remains startable after payment changes ASSIGNED to CONFIRMED."""
        booking = Booking.objects.create(
            customer=self.customer_user,
            address=self.customer_address,
            service=self.service,
            booking_mode="scheduled",
            scheduled_at=_tomorrow_at_noon(),
            status=Booking.Status.CONFIRMED,
        )
        BookingAssignment.objects.create(
            booking=booking,
            worker=self.worker_profile,
            accepted_at=timezone.now(),
        )

        self.client.force_authenticate(user=self.worker_user)
        response = self.client.post(f"/api/v1/bookings/{booking.id}/start/", format="json")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], Booking.Status.IN_PROGRESS)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.IN_PROGRESS)

    def test_worker_jobs_start_endpoint_accepts_paid_confirmed_job(self):
        """The worker-specific start endpoint also supports paid confirmed bookings."""
        booking = Booking.objects.create(
            customer=self.customer_user,
            address=self.customer_address,
            service=self.service,
            booking_mode="scheduled",
            scheduled_at=_tomorrow_at_noon(),
            status=Booking.Status.CONFIRMED,
        )
        assignment = BookingAssignment.objects.create(
            booking=booking,
            worker=self.worker_profile,
            accepted_at=timezone.now(),
        )

        self.client.force_authenticate(user=self.worker_user)
        response = self.client.post(
            f"/api/v1/workers/jobs/{assignment.id}/start/",
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], Booking.Status.IN_PROGRESS)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.IN_PROGRESS)

    def test_cannot_start_job_not_assigned(self):
        """Cannot start a job without assignment."""
        booking = Booking.objects.create(
            customer=self.customer_user,
            address=self.customer_address,
            service=self.service,
            booking_mode="scheduled",
            scheduled_at=_tomorrow_at_noon(),
            status=Booking.Status.PENDING,
        )

        self.client.force_authenticate(user=self.worker_user)
        response = self.client.post(f"/api/v1/bookings/{booking.id}/start/", format="json")

        self.assertEqual(response.status_code, 400)

    def test_cannot_start_job_wrong_status(self):
        """Cannot start a job that is not assigned."""
        booking = Booking.objects.create(
            customer=self.customer_user,
            address=self.customer_address,
            service=self.service,
            booking_mode="scheduled",
            scheduled_at=_tomorrow_at_noon(),
            status=Booking.Status.CONFIRMED,
        )

        self.client.force_authenticate(user=self.worker_user)
        response = self.client.post(f"/api/v1/bookings/{booking.id}/start/", format="json")

        self.assertEqual(response.status_code, 400)

    def test_cannot_complete_job_not_in_progress(self):
        """Cannot complete a job that is not in progress."""
        booking = Booking.objects.create(
            customer=self.customer_user,
            address=self.customer_address,
            service=self.service,
            booking_mode="scheduled",
            scheduled_at=_tomorrow_at_noon(),
            status=Booking.Status.ASSIGNED,
        )
        assignment = BookingAssignment.objects.create(
            booking=booking,
            worker=self.worker_profile,
        )

        self.client.force_authenticate(user=self.worker_user)
        response = self.client.post(f"/api/v1/bookings/{booking.id}/complete/", format="json")

        self.assertEqual(response.status_code, 400)


class JobOfferConcurrencyTest(TestCase):
    """Test concurrency scenarios for job offer acceptance."""

    def setUp(self):
        self.client = APIClient()

        self.city = City.objects.create(name="Mumbai", state="Maharashtra")
        self.zone = Zone.objects.create(name="Dadar", city=self.city, is_active=True)

        self.category = Category.objects.create(title="Cleaning", slug="cleaning")
        self.service = Service.objects.create(
            category=self.category,
            title="Home Cleaning",
            booking_mode="scheduled",
            pricing_type="fixed",
            is_active=True,
        )

        self.customer_user = User.objects.create_user(phone="+919876543210", name="Customer")
        self.customer_address = Address.objects.create(
            user=self.customer_user,
            label="home",
            house_details="Floor 2, Apt 301",
            full_address="123 Main Street, Mumbai 400001",
            zone=self.zone,
        )

        self.booking = Booking.objects.create(
            customer=self.customer_user,
            address=self.customer_address,
            service=self.service,
            booking_mode=Booking.BookingMode.SCHEDULED,
            scheduled_at=_tomorrow_at_noon(),
            status=Booking.Status.PENDING,
        )

    def _schedule_for_booking(self, worker):
        booking_local = timezone.localtime(self.booking.scheduled_at)
        WorkerSchedule.objects.create(
            worker=worker,
            weekday=booking_local.weekday(),
            start_time="00:00:00",
            end_time="23:59:00",
            is_active=True,
        )

    def test_accept_offer_assigns_worker(self):
        """Accepting an offer creates booking assignment."""
        worker_user = User.objects.create_user(phone="+919876543220", name="Worker")
        worker_profile = WorkerProfile.objects.create(
            user=worker_user,
            status=WorkerProfile.Status.APPROVED,
            is_online=True,
        )
        WorkerService.objects.create(worker=worker_profile, service=self.service)
        WorkerZone.objects.create(worker=worker_profile, zone=self.zone)
        self._schedule_for_booking(worker_profile)

        offer = WorkerOffer.objects.create(
            booking=self.booking,
            worker=worker_profile,
            expires_at=timezone.now() + timedelta(hours=1),
        )

        self.client.force_authenticate(user=worker_user)
        response = self.client.post(f"/api/v1/workers/offers/{offer.id}/accept/", format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "accepted")

        offer.refresh_from_db()
        self.assertEqual(offer.status, WorkerOffer.Status.ACCEPTED)

        assignment = BookingAssignment.objects.get(booking=self.booking)
        self.assertEqual(assignment.worker, worker_profile)

    def test_different_worker_offer_for_assigned_booking_fails(self):
        """Accepting different worker's offer for assigned booking fails."""
        # First worker accepts the offer
        worker1_user = User.objects.create_user(phone="+919876543220", name="Worker1")
        worker1_profile = WorkerProfile.objects.create(
            user=worker1_user,
            status=WorkerProfile.Status.APPROVED,
            is_online=True,
        )
        WorkerService.objects.create(worker=worker1_profile, service=self.service)
        WorkerZone.objects.create(worker=worker1_profile, zone=self.zone)
        self._schedule_for_booking(worker1_profile)

        offer1 = WorkerOffer.objects.create(
            booking=self.booking,
            worker=worker1_profile,
            expires_at=timezone.now() + timedelta(hours=1),
        )

        # Second worker has a different offer for the same booking
        worker2_user = User.objects.create_user(phone="+919876543230", name="Worker2")
        worker2_profile = WorkerProfile.objects.create(
            user=worker2_user,
            status=WorkerProfile.Status.APPROVED,
            is_online=True,
        )
        WorkerService.objects.create(worker=worker2_profile, service=self.service)
        WorkerZone.objects.create(worker=worker2_profile, zone=self.zone)
        self._schedule_for_booking(worker2_profile)

        offer2 = WorkerOffer.objects.create(
            booking=self.booking,
            worker=worker2_profile,
            expires_at=timezone.now() + timedelta(hours=1),
        )

        # First worker accepts
        self.client.force_authenticate(user=worker1_user)
        response1 = self.client.post(f"/api/v1/workers/offers/{offer1.id}/accept/", format="json")
        self.assertEqual(response1.status_code, 200)

        # Second worker's accept should fail
        self.client.force_authenticate(user=worker2_user)
        response2 = self.client.post(f"/api/v1/workers/offers/{offer2.id}/accept/", format="json")
        self.assertEqual(response2.status_code, 400)
        self.assertIn("assigned", response2.data["detail"].lower())

        # Verify assignment exists
        self.assertTrue(BookingAssignment.objects.filter(booking=self.booking).exists())


class WorkerDocumentUploadTest(TestCase):
    """Test worker ID document upload endpoints."""

    def setUp(self):
        self.client = APIClient()

        self.user = User.objects.create_user(
            phone="+919876543210",
            name="Test Worker",
        )
        self.worker_profile = WorkerProfile.objects.create(
            user=self.user,
            status=WorkerProfile.Status.PENDING,
        )
        self.client.force_authenticate(user=self.user)

        # Create test service and zone for later use
        self.city = City.objects.create(name="Test City", state="Test State", is_active=True)
        self.category = Category.objects.create(title="Test Category", slug="test-category", is_active=True)
        self.service = Service.objects.create(category=self.category, title="Test Service", is_active=True)
        self.zone = Zone.objects.create(name="Test Zone", city=self.city, is_active=True)

    def _create_test_image(self, name="test_image.jpg"):
        """Helper to create a test image file."""
        img = Image.new('RGB', (100, 100), color='red')
        image_io = io.BytesIO()
        img.save(image_io, format='JPEG')
        image_io.seek(0)

        return SimpleUploadedFile(
            name=name,
            content=image_io.read(),
            content_type="image/jpeg",
        )

    def test_upload_id_document_requires_authentication(self):
        """Should return 401 for unauthenticated request."""
        self.client.force_authenticate(user=None)

        response = self.client.post(
            "/api/v1/workers/documents/upload/",
            {
                "doc_type": "aadhaar",
                "file": self._create_test_image(),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 401)

    def test_upload_id_document_for_non_worker_fails(self):
        """Should return 404 for user without worker profile."""
        regular_user = User.objects.create_user(phone="+919876543211")
        self.client.force_authenticate(user=regular_user)

        response = self.client.post(
            "/api/v1/workers/documents/upload/",
            {
                "doc_type": "aadhaar",
                "file": self._create_test_image(),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 404)
        self.assertIn("not found", response.data["error"].lower())

    def test_upload_id_document_only_for_pending_profiles(self):
        """Should return 400 for non-pending worker profiles."""
        self.worker_profile.status = WorkerProfile.Status.APPROVED
        self.worker_profile.save()

        response = self.client.post(
            "/api/v1/workers/documents/upload/",
            {
                "doc_type": "aadhaar",
                "file": self._create_test_image(),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("pending", response.data["error"].lower())

    def test_upload_aadhaar_document_success(self):
        """Should successfully upload AADHAAR document for pending profile."""
        response = self.client.post(
            "/api/v1/workers/documents/upload/",
            {
                "doc_type": "aadhaar",
                "file": self._create_test_image("aadhaar.jpg"),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["doc_type"], "aadhaar")
        self.assertEqual(response.data["status"], "pending")
        self.assertIn("uploaded", response.data["message"].lower())

        # Verify document was created
        doc = WorkerDocument.objects.get(
            worker=self.worker_profile,
            doc_type="aadhaar",
        )
        self.assertEqual(doc.status, WorkerDocument.Status.PENDING)

    def test_upload_id_document_type_success(self):
        """Should successfully upload ID document for pending profile."""
        response = self.client.post(
            "/api/v1/workers/documents/upload/",
            {
                "doc_type": "id",
                "file": self._create_test_image("id_card.jpg"),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["doc_type"], "id")

    def test_upload_id_document_requires_doc_type(self):
        """Should return 400 when doc_type is missing."""
        response = self.client.post(
            "/api/v1/workers/documents/upload/",
            {
                "file": self._create_test_image(),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("doc_type", response.data)

    def test_upload_id_document_invalid_doc_type(self):
        """Should return 400 for invalid doc_type."""
        response = self.client.post(
            "/api/v1/workers/documents/upload/",
            {
                "doc_type": "invalid_type",
                "file": self._create_test_image(),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 400)

    def test_upload_id_document_requires_file(self):
        """Should return 400 when file is missing."""
        response = self.client.post(
            "/api/v1/workers/documents/upload/",
            {
                "doc_type": "aadhaar",
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("file", response.data)

    def test_upload_id_document_validates_file_size(self):
        """Should reject files larger than 5MB."""
        # Create a valid JPEG image and manually pad it to exceed 5MB
        # SimpleUploadedFile's content is used directly, bypassing image validation
        large_content = b"fake_jpeg_header\xff\xd8\xff\xe0\x00\x10JFIF" + b"x" * (6 * 1024 * 1024)
        large_file = SimpleUploadedFile(
            name="large.jpg",
            content=large_content,
            content_type="image/jpeg",
        )

        response = self.client.post(
            "/api/v1/workers/documents/upload/",
            {
                "doc_type": "aadhaar",
                "file": large_file,
            },
            format="multipart",
        )

        # Should get 400 error - either for invalid image or size
        self.assertEqual(response.status_code, 400)

    def test_cannot_upload_duplicate_document_type(self):
        """Should allow replacing PENDING document, but fail for VERIFIED document."""
        # Upload first document
        self.client.post(
            "/api/v1/workers/documents/upload/",
            {
                "doc_type": "aadhaar",
                "file": self._create_test_image("aadhaar1.jpg"),
            },
            format="multipart",
        )

        # Re-upload same type should succeed (replaces pending document)
        response = self.client.post(
            "/api/v1/workers/documents/upload/",
            {
                "doc_type": "aadhaar",
                "file": self._create_test_image("aadhaar2.jpg"),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 201)

    def test_cannot_replace_verified_document(self):
        """Should return 400 when trying to replace a VERIFIED document."""
        from apps.workers.models import WorkerDocument

        # Upload first document
        self.client.post(
            "/api/v1/workers/documents/upload/",
            {
                "doc_type": "aadhaar",
                "file": self._create_test_image("aadhaar1.jpg"),
            },
            format="multipart",
        )

        # Mark document as VERIFIED directly in DB
        doc = WorkerDocument.objects.filter(doc_type='aadhaar').first()
        self.assertIsNotNone(doc)
        doc.status = WorkerDocument.Status.VERIFIED
        doc.save()

        # Try to upload another aadhaar - should fail
        response = self.client.post(
            "/api/v1/workers/documents/upload/",
            {
                "doc_type": "aadhaar",
                "file": self._create_test_image("aadhaar2.jpg"),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("verified", response.data["error"].lower())


class WorkerDocumentListTest(TestCase):
    """Test worker document listing endpoint."""

    def setUp(self):
        self.client = APIClient()

        self.user = User.objects.create_user(
            phone="+919876543210",
            name="Test Worker",
        )
        self.worker_profile = WorkerProfile.objects.create(
            user=self.user,
            status=WorkerProfile.Status.PENDING,
        )
        self.client.force_authenticate(user=self.user)

    def _create_test_image(self, name="test_image.jpg"):
        """Helper to create a test image file."""
        img = Image.new('RGB', (100, 100), color='red')
        image_io = io.BytesIO()
        img.save(image_io, format='JPEG')
        image_io.seek(0)

        return SimpleUploadedFile(
            name=name,
            content=image_io.read(),
            content_type="image/jpeg",
        )

    def test_list_documents_for_non_worker_fails(self):
        """Should return empty results for user without worker profile."""
        regular_user = User.objects.create_user(phone="+919876543211")
        self.client.force_authenticate(user=regular_user)

        response = self.client.get("/api/v1/workers/documents/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"], [])

    def test_list_documents_returns_existing_documents(self):
        """Should return list of documents for worker profile."""
        # Create some documents
        WorkerDocument.objects.create(
            worker=self.worker_profile,
            doc_type=WorkerDocument.DocumentType.AADHAAR,
            file="test_aadhaar.jpg",
            status=WorkerDocument.Status.PENDING,
        )
        WorkerDocument.objects.create(
            worker=self.worker_profile,
            doc_type=WorkerDocument.DocumentType.ID,
            file="test_id.jpg",
            status=WorkerDocument.Status.VERIFIED,
        )

        response = self.client.get("/api/v1/workers/documents/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 2)

        doc_types = [doc["doc_type"] for doc in response.data["results"]]
        self.assertIn("aadhaar", doc_types)
        self.assertIn("id", doc_types)

    def test_document_list_excludes_file_urls(self):
        """Should NOT include file URLs in document list for security."""
        WorkerDocument.objects.create(
            worker=self.worker_profile,
            doc_type=WorkerDocument.DocumentType.AADHAAR,
            file="test_aadhaar.jpg",
            status=WorkerDocument.Status.PENDING,
        )

        response = self.client.get("/api/v1/workers/documents/")

        self.assertEqual(response.status_code, 200)
        for doc in response.data["results"]:
            self.assertNotIn("file", doc)
            self.assertNotIn("url", doc)


class WorkerProfilePhotoTest(TestCase):
    """Test worker profile photo handling."""

    def setUp(self):
        self.client = APIClient()

    def _create_test_image(self, name="test_image.jpg"):
        """Helper to create a test image file."""
        img = Image.new('RGB', (100, 100), color='red')
        image_io = io.BytesIO()
        img.save(image_io, format='JPEG')
        image_io.seek(0)

        return SimpleUploadedFile(
            name=name,
            content=image_io.read(),
            content_type="image/jpeg",
        )

    def test_worker_profile_returns_photo_url_for_verified_photo(self):
        """Should return photo URL from WorkerDocument for approved profiles with verified photo."""
        user = User.objects.create_user(phone="+919876543210", name="Test Worker")
        worker_profile = WorkerProfile.objects.create(
            user=user,
            status=WorkerProfile.Status.APPROVED,
        )

        # Create VERIFIED photo document
        photo_doc = WorkerDocument.objects.create(
            worker=worker_profile,
            doc_type=WorkerDocument.DocumentType.PHOTO,
            file="photos/test.jpg",
            status=WorkerDocument.Status.VERIFIED,
        )

        self.client.force_authenticate(user=user)

        response = self.client.get("/api/v1/workers/me/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "approved")
        # Photo URL should be present for VERIFIED status photo
        self.assertIsNotNone(response.data.get("photo_url"))

    def test_worker_profile_no_photo_url_for_pending_status(self):
        """Should return None photo_url for PENDING status photos (not yet verified)."""
        user = User.objects.create_user(phone="+919876543210", name="Test Worker")
        worker_profile = WorkerProfile.objects.create(
            user=user,
            status=WorkerProfile.Status.APPROVED,
        )

        # Create PENDING photo document (not yet verified)
        WorkerDocument.objects.create(
            worker=worker_profile,
            doc_type=WorkerDocument.DocumentType.PHOTO,
            file="photos/test.jpg",
            status=WorkerDocument.Status.PENDING,
        )

        self.client.force_authenticate(user=user)

        response = self.client.get("/api/v1/workers/me/")

        self.assertEqual(response.status_code, 200)
        # Photo URL should be None for PENDING status
        self.assertIsNone(response.data.get("photo_url"))

    def test_worker_profile_photo_url_none_for_no_photo(self):
        """Should return None photo_url when no photo document exists."""
        user = User.objects.create_user(phone="+919876543211", name="Test Worker 2")
        worker_profile = WorkerProfile.objects.create(
            user=user,
            status=WorkerProfile.Status.APPROVED,
        )

        self.client.force_authenticate(user=user)

        response = self.client.get("/api/v1/workers/me/")

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data.get("photo_url"))


class ModeSwitchWithPendingProfileTest(TestCase):
    """Test mode switching behavior with different worker profile statuses."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            phone="+919876543210",
            name="Test User",
        )
        self.client.force_authenticate(user=self.user)

    def test_pending_profile_cannot_switch_to_worker_mode(self):
        """Should reject mode switch to worker with PENDING profile."""
        WorkerProfile.objects.create(
            user=self.user,
            status=WorkerProfile.Status.PENDING,
        )
        self.user.active_mode = User.Mode.CUSTOMER
        self.user.save()

        response = self.client.post(
            "/api/v1/auth/switch-mode/",
            {"mode": "worker"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("not approved", response.data["error"].lower())

    def test_rejected_profile_cannot_switch_to_worker_mode(self):
        """Should reject mode switch to worker with REJECTED profile."""
        profile = WorkerProfile.objects.create(
            user=self.user,
            status=WorkerProfile.Status.REJECTED,
            rejection_reason="Insufficient documentation",
        )
        self.user.active_mode = User.Mode.CUSTOMER
        self.user.save()

        response = self.client.post(
            "/api/v1/auth/switch-mode/",
            {"mode": "worker"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("rejected", response.data["error"].lower())

    def test_suspended_profile_cannot_switch_to_worker_mode(self):
        """Should reject mode switch to worker with SUSPENDED profile."""
        WorkerProfile.objects.create(
            user=self.user,
            status=WorkerProfile.Status.SUSPENDED,
        )
        self.user.active_mode = User.Mode.CUSTOMER
        self.user.save()

        response = self.client.post(
            "/api/v1/auth/switch-mode/",
            {"mode": "worker"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("not approved", response.data["error"].lower())

    def test_approved_profile_can_switch_to_worker_mode(self):
        """Should allow mode switch with APPROVED profile."""
        WorkerProfile.objects.create(
            user=self.user,
            status=WorkerProfile.Status.APPROVED,
        )
        self.user.active_mode = User.Mode.CUSTOMER
        self.user.save()

        response = self.client.post(
            "/api/v1/auth/switch-mode/",
            {"mode": "worker"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["active_mode"], "worker")


class WorkerAcceptancePaymentTest(TestCase):
    """Tests for payment auto-creation after worker acceptance."""

    def setUp(self):
        self.client = APIClient()

        self.city = City.objects.create(name="Mumbai", state="Maharashtra")
        self.zone = Zone.objects.create(name="Dadar", city=self.city, is_active=True)

        self.category = Category.objects.create(title="Cleaning", slug="cleaning-payment")
        self.service = Service.objects.create(
            category=self.category,
            title="Home Cleaning",
            booking_mode="scheduled",
            pricing_type="fixed",
            is_active=True,
        )

        self.variant = ServiceVariant.objects.create(
            service=self.service,
            title="Premium",
            price=500,
            mrp=600,
            duration_minutes=60,
        )

        self.customer_user = User.objects.create_user(phone="+919876543810", name="Customer")
        self.worker_user = User.objects.create_user(phone="+919876543820", name="Worker")
        self.other_worker_user = User.objects.create_user(phone="+919876543821", name="Other Worker")

        self.customer_address = Address.objects.create(
            user=self.customer_user,
            label="home",
            house_details="Floor 2, Apt 301",
            full_address="123 Main Street, Mumbai 400001",
            zone=self.zone,
        )

        self.worker_profile = WorkerProfile.objects.create(
            user=self.worker_user,
            status=WorkerProfile.Status.APPROVED,
            is_online=True,
        )
        WorkerService.objects.create(worker=self.worker_profile, service=self.service)
        WorkerZone.objects.create(worker=self.worker_profile, zone=self.zone)
        booking_weekday = timezone.localtime(_tomorrow_at_noon()).weekday()
        WorkerSchedule.objects.create(
            worker=self.worker_profile,
            weekday=booking_weekday,
            start_time="00:00:00",
            end_time="23:59:00",
            is_active=True,
        )

        self.other_worker_profile = WorkerProfile.objects.create(
            user=self.other_worker_user,
            status=WorkerProfile.Status.APPROVED,
            is_online=True,
        )
        WorkerService.objects.create(worker=self.other_worker_profile, service=self.service)
        WorkerZone.objects.create(worker=self.other_worker_profile, zone=self.zone)
        WorkerSchedule.objects.create(
            worker=self.other_worker_profile,
            weekday=booking_weekday,
            start_time="00:00:00",
            end_time="23:59:00",
            is_active=True,
        )

        self.client.force_authenticate(user=self.customer_user)

    def _create_booking_with_offer(self):
        """Helper to create a booking with a pending offer for the worker."""
        from apps.bookings.models import Booking

        booking = Booking.objects.create(
            customer=self.customer_user,
            address=self.customer_address,
            service=self.service,
            variant=self.variant,
            booking_mode="scheduled",
            scheduled_at=_tomorrow_at_noon(),
            status=Booking.Status.CONFIRMED,
        )

        offer = WorkerOffer.objects.create(
            booking=booking,
            worker=self.worker_profile,
            expires_at=timezone.now() + timedelta(hours=1),
        )

        return booking, offer

    def test_accept_offer_creates_payment_record(self):
        """Worker acceptance should create a payment record with Razorpay order."""
        from apps.payments.models import Payment

        booking, offer = self._create_booking_with_offer()

        # Worker accepts the offer
        worker_client = APIClient()
        worker_client.force_authenticate(user=self.worker_user)

        # Mock the Razorpay client to return a fake order
        from unittest.mock import patch, MagicMock
        mock_order = {"id": "order_test_123", "status": "created"}

        with patch('apps.payments.views.client') as mock_client:
            mock_client.order.create.return_value = mock_order

            response = worker_client.post(f"/api/v1/workers/offers/{offer.id}/accept/", format="json")

        self.assertEqual(response.status_code, 200)
        self.assertIn("detail", response.data)
        self.assertIn("assignment_id", response.data)

        # Verify payment was created
        payment = Payment.objects.get(booking=booking)
        self.assertEqual(payment.status, Payment.Status.PENDING)
        self.assertEqual(payment.razorpay_order_id, "order_test_123")
        self.assertEqual(payment.method, Payment.Method.RAZORPAY)
        self.assertEqual(float(payment.amount), float(booking.total_amount))

    def test_accept_offer_returns_payment_order_id(self):
        """Accept response should include payment_order_id for Flutter integration."""
        from apps.payments.models import Payment

        booking, offer = self._create_booking_with_offer()

        worker_client = APIClient()
        worker_client.force_authenticate(user=self.worker_user)

        # Mock the Razorpay client to return a fake order
        from unittest.mock import patch, MagicMock
        mock_order = {"id": "order_test_456", "status": "created"}

        with patch('apps.payments.views.client') as mock_client:
            mock_client.order.create.return_value = mock_order

            response = worker_client.post(f"/api/v1/workers/offers/{offer.id}/accept/", format="json")

        self.assertEqual(response.status_code, 200)
        self.assertIn("payment_order_id", response.data)
        self.assertEqual(response.data["payment_order_id"], "order_test_456")

    def test_double_accept_does_not_create_duplicate_payment(self):
        """Repeated acceptance should be idempotent and not create duplicate payments."""
        from apps.payments.models import Payment
        from unittest.mock import patch

        booking, offer = self._create_booking_with_offer()

        worker_client = APIClient()
        worker_client.force_authenticate(user=self.worker_user)

        # Mock the Razorpay client
        mock_order = {"id": "order_test_789", "status": "created"}

        with patch('apps.payments.views.client') as mock_client:
            mock_client.order.create.return_value = mock_order

            # First acceptance - creates payment
            response1 = worker_client.post(f"/api/v1/workers/offers/{offer.id}/accept/", format="json")
            self.assertEqual(response1.status_code, 200)

            # Second acceptance should fail (offer already accepted)
            response2 = worker_client.post(f"/api/v1/workers/offers/{offer.id}/accept/", format="json")
            self.assertEqual(response2.status_code, 400)  # Offer already accepted

        # Verify only one payment exists
        payments = Payment.objects.filter(booking=booking)
        self.assertEqual(payments.count(), 1)

    def test_concurrent_acceptance_prevents_duplicate_assignment_and_payment(self):
        """Two workers accepting same offer should only create one assignment/payment."""
        from unittest.mock import patch

        customer_client = APIClient()
        customer_client.force_authenticate(user=self.customer_user)

        booking, offer = self._create_booking_with_offer()

        # Mock the Razorpay client
        mock_order = {"id": "order_test_concurrent", "status": "created"}

        # Worker 1 accepts
        worker1_client = APIClient()
        worker1_client.force_authenticate(user=self.worker_user)
        with patch('apps.payments.views.client') as mock_client:
            mock_client.order.create.return_value = mock_order
            response1 = worker1_client.post(f"/api/v1/workers/offers/{offer.id}/accept/", format="json")
        self.assertEqual(response1.status_code, 200)

        # Worker 2 accepts (should fail - booking already assigned)
        worker2_client = APIClient()
        worker2_client.force_authenticate(user=self.other_worker_user)
        response2 = worker2_client.post(f"/api/v1/workers/offers/{offer.id}/accept/", format="json")
        self.assertEqual(response2.status_code, 404)  # Offer not found (already assigned)

        # Verify only one assignment exists
        from apps.bookings.models import BookingAssignment
        self.assertEqual(BookingAssignment.objects.filter(booking=booking).count(), 1)

        # Verify only one payment exists
        from apps.payments.models import Payment
        self.assertEqual(Payment.objects.filter(booking=booking).count(), 1)

    def test_unauthorized_worker_cannot_trigger_payment_creation(self):
        """Worker not owning the offer should not be able to accept."""
        from apps.payments.models import Payment
        from unittest.mock import patch

        booking, offer = self._create_booking_with_offer()

        # Other worker (not the offer owner) tries to accept
        other_worker_client = APIClient()
        other_worker_client.force_authenticate(user=self.other_worker_user)

        response = other_worker_client.post(f"/api/v1/workers/offers/{offer.id}/accept/", format="json")

        self.assertEqual(response.status_code, 404)

        # No payment should be created
        self.assertFalse(Payment.objects.filter(booking=booking).exists())

    def test_worker_acceptance_succeeds_even_if_razorpay_fails(self):
        """Worker acceptance should succeed even if Razorpay order creation fails.

        The payment creation is best-effort - if Razorpay is unavailable,
        the acceptance should still proceed and payment can be created later.
        """
        from apps.payments.models import Payment
        from unittest.mock import patch

        booking, offer = self._create_booking_with_offer()

        worker_client = APIClient()
        worker_client.force_authenticate(user=self.worker_user)

        # Mock Razorpay client to raise an exception
        with patch('apps.payments.views.client') as mock_client:
            mock_client.order.create.side_effect = Exception("Razorpay service unavailable")

            response = worker_client.post(f"/api/v1/workers/offers/{offer.id}/accept/", format="json")

        # Acceptance should succeed
        self.assertEqual(response.status_code, 200)
        self.assertIn("detail", response.data)
        self.assertIn("assignment_id", response.data)

        # Booking should be assigned
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.ASSIGNED)

    def test_booking_assignment_preserved_on_payment_creation(self):
        """Booking assignment should be correct after payment auto-creation."""
        from apps.bookings.models import Booking
        from unittest.mock import patch

        booking, offer = self._create_booking_with_offer()

        worker_client = APIClient()
        worker_client.force_authenticate(user=self.worker_user)

        # Mock the Razorpay client
        mock_order = {"id": "order_test_preserved", "status": "created"}

        with patch('apps.payments.views.client') as mock_client:
            mock_client.order.create.return_value = mock_order

            response = worker_client.post(f"/api/v1/workers/offers/{offer.id}/accept/", format="json")

        self.assertEqual(response.status_code, 200)

        # Verify booking status is ASSIGNED
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.ASSIGNED)

        # Verify assignment exists with correct worker
        from apps.bookings.models import BookingAssignment
        assignment = booking.assignment
        self.assertIsNotNone(assignment)
        self.assertEqual(assignment.worker, self.worker_profile)

    def test_payment_timeout_task_marks_past_timeout_as_failed(self):
        """Payment timeout should mark PENDING payments past timeout as FAILED.

        For ASSIGNED bookings with timed out payment:
        1. Mark payment as FAILED
        2. Withdraw the accepted offer
        3. Delete the BookingAssignment
        4. Revert booking to PENDING
        5. Notify customer
        """
        from apps.payments.models import Payment
        from apps.bookings.tasks import timeout_pending_payments
        from unittest.mock import patch

        booking, offer = self._create_booking_with_offer()

        worker_client = APIClient()
        worker_client.force_authenticate(user=self.worker_user)

        # Mock the Razorpay client
        mock_order = {"id": "order_test_timeout", "status": "created"}

        with patch('apps.payments.views.client') as mock_client:
            mock_client.order.create.return_value = mock_order

            worker_client.post(f"/api/v1/workers/offers/{offer.id}/accept/", format="json")

        payment = Payment.objects.get(booking=booking)

        # Verify booking was assigned
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.ASSIGNED)

        # Set payment to pending past timeout
        payment.created_at = timezone.now() - timedelta(minutes=10)
        payment.save()

        # Run timeout task
        count = timeout_pending_payments()

        # Payment should be marked as FAILED
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.FAILED)
        self.assertIsNotNone(payment.failed_at)

        # Booking should be reverted to PENDING (worker released)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.PENDING)

        # Assignment should be deleted
        from apps.bookings.models import BookingAssignment
        self.assertFalse(BookingAssignment.objects.filter(booking=booking).exists())

    def test_webhook_confirms_booking_idempotently(self):
        """Webhook should update booking from ASSIGNED to CONFIRMED on payment capture."""
        from apps.payments.models import Payment
        from apps.payments.verify_view import _process_verified_payment

        # Create booking and payment
        booking = Booking.objects.create(
            customer=self.customer_user,
            address=self.customer_address,
            service=self.service,
            variant=self.variant,
            booking_mode="scheduled",
            scheduled_at=_tomorrow_at_noon(),
            status=Booking.Status.ASSIGNED,
        )

        payment = Payment.objects.create(
            booking=booking,
            customer=self.customer_user,
            amount=booking.total_amount,
            method=Payment.Method.RAZORPAY,
            status=Payment.Status.PENDING,
            razorpay_order_id="order_test_webhook",
        )

        # Simulate webhook processing
        response = _process_verified_payment(
            payment=payment,
            razorpay_payment_id="pay_test_webhook",
            razorpay_order_id="order_test_webhook",
            customer=self.customer_user,
            source="webhook",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "paid")

        # Verify booking is now CONFIRMED
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CONFIRMED)

        # Verify payment is PAID
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PAID)
        self.assertEqual(payment.razorpay_payment_id, "pay_test_webhook")

        # Verify notification was created
        from apps.notifications.models import Notification
        notification = Notification.objects.filter(
            user=self.customer_user,
            type=Notification.Type.PAYMENT_SUCCESS,
        ).first()
        self.assertIsNotNone(notification)
        self.assertIn("confirmed", notification.body.lower())
        self.assertEqual(notification.data.get("booking_id"), booking.id)


class PaymentIdempotencyTests(TestCase):
    """Tests for payment creation idempotency at the function level."""

    def setUp(self):
        self.city = City.objects.create(name="Mumbai", state="Maharashtra")
        self.zone = Zone.objects.create(name="Dadar", city=self.city, is_active=True)

        self.category = Category.objects.create(title="Cleaning", slug="cleaning-payment")
        self.service = Service.objects.create(
            category=self.category,
            title="Home Cleaning",
            booking_mode="scheduled",
            pricing_type="fixed",
            is_active=True,
        )

        self.variant = ServiceVariant.objects.create(
            service=self.service,
            title="Premium",
            price=500,
            mrp=600,
            duration_minutes=60,
        )

        self.customer_user = User.objects.create_user(phone="+919876543810", name="Customer")

        self.customer_address = Address.objects.create(
            user=self.customer_user,
            label="home",
            house_details="Floor 2, Apt 301",
            full_address="123 Main Street, Mumbai 400001",
            zone=self.zone,
        )

    def test_create_or_get_payment_idempotent_returns_existing(self):
        """Two calls with same booking should return same payment/order."""
        from apps.payments.views import create_or_get_payment
        from apps.payments.models import Payment

        booking = Booking.objects.create(
            customer=self.customer_user,
            address=self.customer_address,
            service=self.service,
            variant=self.variant,
            booking_mode="scheduled",
            scheduled_at=_tomorrow_at_noon(),
            status=Booking.Status.ASSIGNED,
        )

        from unittest.mock import patch

        mock_order1 = {"id": "order_test_idempotent_1", "status": "created"}

        with patch('apps.payments.views.client') as mock_client:
            mock_client.order.create.return_value = mock_order1

            # First call creates payment
            payment1, order_id1, already_existed1 = create_or_get_payment(
                booking=booking, customer=self.customer_user, trigger_source="test"
            )

        # Second call should return existing
        with patch('apps.payments.views.client') as mock_client:
            # This should NOT call Razorpay if payment already exists
            mock_client.order.create.return_value = {"id": "order_should_not_be_called", "status": "created"}

            payment2, order_id2, already_existed2 = create_or_get_payment(
                booking=booking, customer=self.customer_user, trigger_source="test"
            )

        self.assertEqual(payment1.id, payment2.id)
        self.assertEqual(order_id1, order_id2)
        self.assertEqual(order_id2, "order_test_idempotent_1")
        self.assertTrue(already_existed2)
        self.assertEqual(Payment.objects.filter(booking=booking).count(), 1)

    def test_create_or_get_payment_reuses_existing_without_razorpay_call(self):
        """Existing payment with order ID should be returned without Razorpay call count 2."""
        from apps.payments.views import create_or_get_payment
        from apps.payments.models import Payment

        booking = Booking.objects.create(
            customer=self.customer_user,
            address=self.customer_address,
            service=self.service,
            variant=self.variant,
            booking_mode="scheduled",
            scheduled_at=_tomorrow_at_noon(),
            status=Booking.Status.ASSIGNED,
        )

        from unittest.mock import patch, MagicMock

        mock_order = {"id": "order_test_reuse", "status": "created"}

        with patch('apps.payments.views.client') as mock_client:
            mock_client.order.create.return_value = mock_order

            # First call creates payment
            payment, _, _ = create_or_get_payment(
                booking=booking, customer=self.customer_user, trigger_source="test"
            )
            self.assertEqual(mock_client.order.create.call_count, 1)

        # Second call without mock should return existing payment without calling Razorpay
        payment2, order_id, already_existed = create_or_get_payment(
            booking=booking, customer=self.customer_user, trigger_source="test"
        )

        # Verify existing payment returned, no new Razorpay call
        self.assertEqual(payment.id, payment2.id)
        self.assertEqual(order_id, "order_test_reuse")
        self.assertTrue(already_existed)

    def test_create_or_get_payment_after_failure_can_recover(self):
        """After Razorpay failure, a new Payment record should allow recovery."""
        from apps.payments.views import create_or_get_payment
        from apps.payments.models import Payment

        booking = Booking.objects.create(
            customer=self.customer_user,
            address=self.customer_address,
            service=self.service,
            variant=self.variant,
            booking_mode="scheduled",
            scheduled_at=_tomorrow_at_noon(),
            status=Booking.Status.ASSIGNED,
        )

        from unittest.mock import patch

        # First call fails
        with patch('apps.payments.views.client') as mock_client:
            mock_client.order.create.side_effect = Exception("Razorpay API failure")

            with self.assertRaises(Exception):
                create_or_get_payment(
                    booking=booking, customer=self.customer_user, trigger_source="test"
                )

        # No payment should exist after failure
        self.assertFalse(Payment.objects.filter(booking=booking).exists())

        # Now Razorpay should work
        mock_order = {"id": "order_test_recovery", "status": "created"}

        with patch('apps.payments.views.client') as mock_client:
            mock_client.order.create.return_value = mock_order

            payment, order_id, already_existed = create_or_get_payment(
                booking=booking, customer=self.customer_user, trigger_source="test"
            )

        # Payment should now exist with new order
        self.assertIsNotNone(payment)
        self.assertEqual(payment.razorpay_order_id, "order_test_recovery")
        self.assertFalse(already_existed)
        self.assertEqual(Payment.objects.filter(booking=booking).count(), 1)

    def test_create_or_get_payment_concurrent_attempts_single_payment(self):
        """Concurrent calls should only create one payment (test via serial execution with locks)."""
        from apps.payments.views import create_or_get_payment
        from apps.payments.models import Payment

        booking = Booking.objects.create(
            customer=self.customer_user,
            address=self.customer_address,
            service=self.service,
            variant=self.variant,
            booking_mode="scheduled",
            scheduled_at=_tomorrow_at_noon(),
            status=Booking.Status.ASSIGNED,
        )

        from unittest.mock import patch

        # Simulate two sequential calls with mocks
        mock_order = {"id": "order_test_concurrent", "status": "created"}
        razorpay_call_count = [0]

        def mock_create(data):
            razorpay_call_count[0] += 1
            return mock_order

        with patch('apps.payments.views.client') as mock_client:
            mock_client.order.create = mock_create

            # First call
            payment1, order_id1, _ = create_or_get_payment(
                booking=booking, customer=self.customer_user, trigger_source="test"
            )

            # Second call - should find existing
            payment2, order_id2, already_existed = create_or_get_payment(
                booking=booking, customer=self.customer_user, trigger_source="test"
            )

        # Both payments should be the same
        self.assertEqual(payment1.id, payment2.id)
        self.assertEqual(order_id1, order_id2)
        self.assertEqual(order_id2, "order_test_concurrent")
        self.assertTrue(already_existed)

        # Only one Razorpay call should have been made
        self.assertEqual(razorpay_call_count[0], 1)

        # Only one payment record
        self.assertEqual(Payment.objects.filter(booking=booking).count(), 1)


class CompleteWorkerOnboardingSubmissionTests(TestCase):
    def setUp(self):
        from apps.accounts.models import User
        from apps.core.models import City, Zone
        from apps.catalog.models import Category, Service

        self.user = User.objects.create_user(
            phone="+919876543221",
            password="password123",
            name="Applicant",
        )
        self.city = City.objects.create(name="Rawatbhata", state="Rajasthan")
        self.zone = Zone.objects.create(name="Rawatbhata Main", city=self.city, is_active=True)
        self.category = Category.objects.create(title="Electrical", slug="onboarding-electrical")
        self.service = Service.objects.create(
            category=self.category,
            title="Electrical Repair",
            booking_mode="scheduled",
            pricing_type="fixed",
            is_active=True,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _profile_photo(self):
        from io import BytesIO
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile

        output = BytesIO()
        Image.new("RGB", (20, 20), color="white").save(output, format="PNG")
        return SimpleUploadedFile(
            "worker-profile.png", output.getvalue(), content_type="image/png"
        )

    def _payload(self):
        import json
        return {
            "name": "Applicant Worker",
            "email": "worker@example.com",
            "gender": "other",
            "services": json.dumps([self.service.pk]),
            "service_capabilities": json.dumps({str(self.service.pk): ["Electrical repair"]}),
            "zones": json.dumps([self.zone.pk]),
            "experience_years": "3",
            "qualification": "ITI Electrical",
            "equipment_details": "Tester, insulated tools",
            "residential_address": "Rawatbhata, Rajasthan",
            "landmark": "Near main market",
            "bio": "Experienced electrical repair professional",
            "schedule": json.dumps({
                "0": {"start": "09:00", "end": "18:00"},
                "2": {"start": "10:00", "end": "17:00"},
            }),
            "profile_photo": self._profile_photo(),
        }

    def test_complete_application_persists_services_zones_profile_and_hours(self):
        response = self.client.post(
            "/api/v1/workers/apply/", self._payload(), format="multipart"
        )

        self.assertEqual(response.status_code, 201, response.data)
        profile = WorkerProfile.objects.get(user=self.user)
        self.assertEqual(profile.status, WorkerProfile.Status.PENDING)
        self.assertEqual(profile.qualification, "ITI Electrical")
        self.assertEqual(profile.equipment_details, "Tester, insulated tools")
        self.assertEqual(profile.residential_address, "Rawatbhata, Rajasthan")
        self.assertEqual(profile.landmark, "Near main market")
        self.assertEqual(list(profile.worker_services.values_list("service_id", flat=True)), [self.service.pk])
        self.assertEqual(list(profile.worker_zones.values_list("zone_id", flat=True)), [self.zone.pk])
        self.assertEqual(profile.schedules.count(), 2)
        self.assertTrue(profile.documents.filter(doc_type=WorkerDocument.DocumentType.PHOTO).exists())

    def test_application_can_submit_service_and_experience_without_preconfigured_tasks(self):
        import json
        payload = self._payload()
        payload["service_capabilities"] = json.dumps({str(self.service.pk): []})
        payload["service_experience_years"] = json.dumps({str(self.service.pk): 4})

        response = self.client.post(
            "/api/v1/workers/apply/", payload, format="multipart"
        )

        self.assertEqual(response.status_code, 201, response.data)
        profile = WorkerProfile.objects.get(user=self.user)
        worker_service = profile.worker_services.get(service=self.service)
        self.assertEqual(worker_service.capabilities, [])
        self.assertFalse(worker_service.capabilities_verified)
        self.assertEqual(worker_service.experience_years, 4)

        # The application may be submitted, but empty/unverified skills cannot
        # pass the separate admin approval gate.
        from apps.workers.approval import get_approval_requirements
        requirements = get_approval_requirements(profile)
        self.assertFalse(requirements["has_verified_capabilities"])
        self.assertFalse(requirements["eligible"])

    def test_gps_coordinates_do_not_override_worker_selected_service_areas(self):
        payload = self._payload()
        payload["latitude"] = "25.123456"
        payload["longitude"] = "75.123456"

        response = self.client.post(
            "/api/v1/workers/apply/", payload, format="multipart"
        )

        self.assertEqual(response.status_code, 201, response.data)
        profile = WorkerProfile.objects.get(user=self.user)
        self.assertEqual(
            list(profile.worker_zones.values_list("zone_id", flat=True)),
            [self.zone.pk],
        )
        self.assertEqual(str(profile.latitude), "25.123456")
        self.assertEqual(str(profile.longitude), "75.123456")

    def test_worker_can_select_multiple_working_areas(self):
        import json
        second_zone = Zone.objects.create(
            name="Rawatbhata North", city=self.city, is_active=True
        )
        payload = self._payload()
        payload["zones"] = json.dumps([self.zone.pk, second_zone.pk])

        response = self.client.post(
            "/api/v1/workers/apply/", payload, format="multipart"
        )

        self.assertEqual(response.status_code, 201, response.data)
        profile = WorkerProfile.objects.get(user=self.user)
        self.assertCountEqual(
            profile.worker_zones.values_list("zone_id", flat=True),
            [self.zone.pk, second_zone.pk],
        )

    def test_invalid_selected_service_rejects_application_without_partial_profile(self):
        payload = self._payload()
        payload["services"] = "[999999]"
        response = self.client.post(
            "/api/v1/workers/apply/", payload, format="multipart"
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(WorkerProfile.objects.filter(user=self.user).exists())

    def test_missing_weekly_hours_rejects_application_without_partial_profile(self):
        import json
        payload = self._payload()
        payload["schedule"] = json.dumps({})
        response = self.client.post(
            "/api/v1/workers/apply/", payload, format="multipart"
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(WorkerProfile.objects.filter(user=self.user).exists())


class WorkerAvailabilityPrerequisiteTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            phone="+919876543222", password="password123", name="Approved Worker"
        )
        self.profile = WorkerProfile.objects.create(
            user=self.user, status=WorkerProfile.Status.APPROVED
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.city = City.objects.create(name="Rawatbhata", state="Rajasthan")
        self.zone = Zone.objects.create(name="Availability Zone", city=self.city, is_active=True)
        self.category = Category.objects.create(title="Car Wash", slug="availability-car-wash")
        self.service = Service.objects.create(
            category=self.category,
            title="Exterior Wash",
            booking_mode="scheduled",
            pricing_type="fixed",
            is_active=True,
        )

    def test_worker_cannot_go_online_without_service_area_and_schedule(self):
        response = self.client.post(
            "/api/v1/workers/status/", {"is_online": True}, format="json"
        )

        self.assertEqual(response.status_code, 409)
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.is_online)

    def test_worker_can_go_online_with_active_service_area_and_schedule(self):
        WorkerService.objects.create(worker=self.profile, service=self.service)
        WorkerZone.objects.create(worker=self.profile, zone=self.zone)
        WorkerSchedule.objects.create(
            worker=self.profile,
            weekday=0,
            start_time="09:00",
            end_time="18:00",
            is_active=True,
        )

        response = self.client.post(
            "/api/v1/workers/status/", {"is_online": True}, format="json"
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.profile.refresh_from_db()
        self.assertTrue(self.profile.is_online)


class WorkerCapabilityEligibilityRegressionTests(TestCase):
    def setUp(self):
        self.city = City.objects.create(name="Capability City", state="Rajasthan")
        self.zone = Zone.objects.create(name="Capability Zone", city=self.city, is_active=True)
        self.category = Category.objects.create(title="Electrical", slug="capability-electrical")
        self.service = Service.objects.create(
            category=self.category, title="Fan Repair",
            booking_mode="scheduled", pricing_type="fixed", is_active=True,
        )
        self.user = User.objects.create_user(
            phone="+919876540001", password="password123", name="Legacy Worker",
        )
        self.worker = WorkerProfile.objects.create(
            user=self.user, status=WorkerProfile.Status.APPROVED, is_online=True,
        )
        WorkerZone.objects.create(worker=self.worker, zone=self.zone)
        WorkerSchedule.objects.create(
            worker=self.worker, weekday=0, start_time="00:00", end_time="23:59",
            is_active=True,
        )
        self.link = WorkerService.objects.create(worker=self.worker, service=self.service)

    def test_legacy_worker_remains_eligible_for_task_neutral_service(self):
        from apps.workers.eligibility import eligible_workers_for_service

        self.assertTrue(
            eligible_workers_for_service(self.service, zone=self.zone).filter(pk=self.worker.pk).exists()
        )

    def test_task_specific_work_requires_verified_matching_capability(self):
        from apps.workers.eligibility import eligible_workers_for_service

        self.assertFalse(
            eligible_workers_for_service(
                self.service, zone=self.zone, required_tasks=["Wiring replacement"],
            ).filter(pk=self.worker.pk).exists()
        )
        self.link.capabilities = ["Wiring replacement"]
        self.link.capabilities_verified = True
        self.link.save(update_fields=["capabilities", "capabilities_verified", "updated_at"])
        self.assertTrue(
            eligible_workers_for_service(
                self.service, zone=self.zone, required_tasks=["Wiring replacement"],
            ).filter(pk=self.worker.pk).exists()
        )
        self.assertFalse(
            eligible_workers_for_service(
                self.service, zone=self.zone, required_tasks=["Motor rewinding"],
            ).filter(pk=self.worker.pk).exists()
        )

    def test_approval_requires_capabilities_for_every_active_service(self):
        from apps.workers.approval import get_approval_requirements

        second_service = Service.objects.create(
            category=self.category, title="Switch Repair",
            booking_mode="scheduled", pricing_type="fixed", is_active=True,
        )
        second_link = WorkerService.objects.create(
            worker=self.worker, service=second_service,
            capabilities=["Switch replacement"], capabilities_verified=True,
        )
        self.link.capabilities = ["Wiring replacement"]
        self.link.capabilities_verified = True
        self.link.save(update_fields=["capabilities", "capabilities_verified", "updated_at"])
        self.assertTrue(get_approval_requirements(self.worker)["has_verified_capabilities"])
        second_link.capabilities_verified = False
        second_link.save(update_fields=["capabilities_verified", "updated_at"])
        self.assertFalse(get_approval_requirements(self.worker)["has_verified_capabilities"])
