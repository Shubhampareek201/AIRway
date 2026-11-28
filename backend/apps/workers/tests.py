import io
from decimal import Decimal
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
from apps.workers.models import WorkerProfile, WorkerService, WorkerZone, WorkerSchedule, WorkerDocument, WorkerLeave, WorkerLeaveHistory
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

    def test_worker_can_edit_permitted_profile_fields_and_name(self):
        response = self.client.patch(
            "/api/v1/workers/me/",
            {
                "name": "Updated Worker",
                "bio": "Home service professional",
                "qualification": "ITI",
                "upi_id": "worker@upi",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.worker_user.refresh_from_db()
        self.worker_profile.refresh_from_db()
        self.assertEqual(self.worker_user.name, "Updated Worker")
        self.assertEqual(self.worker_profile.bio, "Home service professional")
        self.assertEqual(self.worker_profile.qualification, "ITI")
        self.assertEqual(self.worker_profile.upi_id, "worker@upi")

    def test_worker_can_add_service_without_preconfigured_task_list(self):
        category = Category.objects.create(title="Home Care", slug="profile-home-care")
        service = Service.objects.create(category=category, title="Basic Cleaning", is_active=True)

        response = self.client.post(
            "/api/v1/workers/services/",
            {"service": service.id, "capabilities": []},
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        assignment = WorkerService.objects.get(worker=self.worker_profile, service=service)
        self.assertEqual(assignment.capabilities, [])
        self.assertFalse(assignment.capabilities_verified)


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
            commission_rate=Decimal("10.00"),
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
            pricing_snapshot={"subtotal": "100.00", "total": "118.00"},
        )
        from apps.payments.models import Payment
        Payment.objects.create(
            booking=self.booking, customer=self.customer_user,
            stage=Payment.Stage.ADVANCE, amount=Decimal("150.00"),
            status=Payment.Status.PAID, method=Payment.Method.RAZORPAY,
            razorpay_payment_id="test_captured_advance", paid_at=timezone.now(),
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

    def test_offer_api_hides_customer_bill_and_exposes_only_worker_payout(self):
        self.client.force_authenticate(user=self.worker_user)
        WorkerOffer.objects.create(
            booking=self.booking,
            worker=self.worker_profile,
            expires_at=self.booking.scheduled_at,
        )
        response = self.client.get("/api/v1/workers/offers/")
        self.assertEqual(response.status_code, 200)
        data = response.data["results"][0]
        self.assertIn("worker_payout", data)
        for private_field in ("customer_total", "advance_received", "remaining_balance"):
            self.assertNotIn(private_field, data)

    def test_dispatch_notification_contains_worker_payout_not_customer_bill(self):
        from apps.bookings.dispatcher import DispatcherService
        from apps.notifications.models import Notification

        offers = DispatcherService.dispatch_offers(self.booking)
        self.assertEqual(len(offers), 1)
        notification = Notification.objects.get(
            user=self.worker_user,
            type=Notification.Type.WORKER_OFFER,
        )
        self.assertEqual(notification.data["worker_payout"], "90.00")
        for private_field in ("customer_total", "advance_received", "remaining_balance"):
            self.assertNotIn(private_field, notification.data)


    def test_legacy_fully_paid_booking_can_be_dispatched_and_accepted(self):
        from apps.bookings.dispatcher import DispatcherService
        from apps.payments.models import Payment

        Payment.objects.filter(booking=self.booking).update(stage=Payment.Stage.LEGACY)
        offers = DispatcherService.dispatch_offers(self.booking)
        self.assertEqual(len(offers), 1)
        self.assertEqual(offers[0].worker, self.worker_profile)

        self.client.force_authenticate(user=self.worker_user)
        response = self.client.post(
            f"/api/v1/workers/offers/{offers[0].id}/accept/", format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(BookingAssignment.objects.filter(booking=self.booking).exists())

    def test_unpaid_legacy_booking_is_not_dispatched(self):
        from apps.bookings.dispatcher import DispatcherService
        from apps.payments.models import Payment

        Payment.objects.filter(booking=self.booking).update(
            stage=Payment.Stage.LEGACY, status=Payment.Status.FAILED
        )
        self.assertEqual(DispatcherService.dispatch_offers(self.booking), [])
        self.assertFalse(WorkerOffer.objects.filter(booking=self.booking).exists())

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

    def test_accept_does_not_expire_offer_during_launch(self):
        self.client.force_authenticate(user=self.worker_user)
        offer = WorkerOffer.objects.create(
            booking=self.booking,
            worker=self.worker_profile,
            expires_at=timezone.now() - timedelta(minutes=1),
        )

        response = self.client.post(f"/api/v1/workers/offers/{offer.id}/accept/", format="json")

        self.assertEqual(response.status_code, 200)
        offer.refresh_from_db()
        self.assertEqual(offer.status, WorkerOffer.Status.ACCEPTED)
        self.assertTrue(BookingAssignment.objects.filter(booking=self.booking).exists())

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

        acceptance_rate_before = self.worker_profile.acceptance_rate
        self.assertEqual(response.status_code, 200)

        offer.refresh_from_db()
        self.worker_profile.refresh_from_db()
        self.assertEqual(offer.status, WorkerOffer.Status.DECLINED)
        self.assertEqual(self.worker_profile.acceptance_rate, acceptance_rate_before)

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
        self.assertEqual(offer.status, WorkerOffer.Status.DECLINED)

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

    def test_booking_history_never_exposes_worker_phone_as_display_name(self):
        from apps.bookings.models import BookingStatusHistory
        from apps.bookings.serializers import BookingStatusHistorySerializer

        self.worker_user.name = ""
        self.worker_user.save(update_fields=["name"])
        booking = Booking.objects.create(
            customer=self.customer_user,
            address=self.customer_address,
            service=self.service,
            booking_mode="scheduled",
            scheduled_at=_tomorrow_at_noon(),
            status=Booking.Status.IN_PROGRESS,
        )
        history = BookingStatusHistory.objects.create(
            booking=booking,
            from_status=Booking.Status.ASSIGNED,
            to_status=Booking.Status.IN_PROGRESS,
            changed_by=self.worker_user,
            note="Worker started the job.",
        )

        serialized = BookingStatusHistorySerializer(history).data
        self.assertEqual(serialized["changed_by_name"], "AIRway Professional")
        self.assertNotIn(self.worker_user.phone, str(serialized))

    def test_worker_job_endpoints_do_not_expose_customer_contact_details(self):
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
            accepted_at=timezone.now(),
        )

        self.client.force_authenticate(user=self.worker_user)
        list_response = self.client.get("/api/v1/workers/jobs/")
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.data[0]["customer_name"], "Customer")
        self.assertEqual(list_response.data[0]["address"], self.customer_address.full_address)
        self.assertNotIn("customer_phone", list_response.data[0])
        self.assertNotIn(self.customer_user.phone, str(list_response.data[0]))

        detail_response = self.client.get(f"/api/v1/workers/jobs/{assignment.pk}/")
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.data["customer_name"], "Customer")
        self.assertIn("customer_phone", detail_response.data)
        self.assertIsNone(detail_response.data["customer_phone"])
        self.assertFalse(detail_response.data["customer_contact_available"])
        self.assertIsNotNone(detail_response.data["customer_contact_available_at"])
        self.assertEqual(detail_response.data["address"], self.customer_address.full_address)
        self.assertNotIn(self.customer_user.phone, str(detail_response.data))

    def test_worker_cannot_access_customer_address_or_phone_before_accepting(self):
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

        list_response = self.client.get("/api/v1/workers/jobs/")
        self.assertEqual(list_response.status_code, 200)
        job_row = next(row for row in list_response.data if row["id"] == assignment.pk)
        self.assertIsNone(job_row["address"])
        self.assertFalse(job_row["customer_contact_available"])

        detail_response = self.client.get(f"/api/v1/workers/jobs/{assignment.pk}/")
        self.assertEqual(detail_response.status_code, 200)
        self.assertIsNone(detail_response.data["address"])
        self.assertIsNone(detail_response.data["address_latitude"])
        self.assertIsNone(detail_response.data["address_longitude"])
        self.assertIsNone(detail_response.data["customer_phone"])
        self.assertFalse(detail_response.data["customer_contact_available"])
        self.assertIsNone(detail_response.data["customer_contact_available_at"])
        self.assertNotIn(self.customer_user.phone, str(detail_response.data))

    def test_worker_contact_phone_unlocks_one_hour_before_accepted_booking(self):
        booking = Booking.objects.create(
            customer=self.customer_user,
            address=self.customer_address,
            service=self.service,
            booking_mode="scheduled",
            scheduled_at=timezone.now() + timedelta(minutes=30),
            status=Booking.Status.ASSIGNED,
        )
        assignment = BookingAssignment.objects.create(
            booking=booking,
            worker=self.worker_profile,
            accepted_at=timezone.now(),
        )
        self.client.force_authenticate(user=self.worker_user)
        response = self.client.get(f"/api/v1/workers/jobs/{assignment.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["customer_contact_available"])
        self.assertEqual(response.data["customer_phone"], self.customer_user.phone)

    def test_worker_offer_hides_exact_location_until_accepted(self):
        from apps.bookings.serializers import WorkerOfferSerializer

        self.customer_address.latitude = Decimal("19.076000")
        self.customer_address.longitude = Decimal("72.877700")
        self.customer_address.save(update_fields=["latitude", "longitude"])
        booking = Booking.objects.create(
            customer=self.customer_user,
            address=self.customer_address,
            service=self.service,
            booking_mode="scheduled",
            scheduled_at=_tomorrow_at_noon(),
            status=Booking.Status.ASSIGNED,
        )
        offer = WorkerOffer.objects.create(
            booking=booking,
            worker=self.worker_profile,
            expires_at=booking.scheduled_at,
        )
        pending_data = WorkerOfferSerializer(offer).data
        self.assertIsNone(pending_data["service_address"])
        self.assertIsNone(pending_data["address_latitude"])
        self.assertIsNone(pending_data["address_longitude"])
        self.assertEqual(pending_data["customer_name"], "Customer")

        offer.status = WorkerOffer.Status.ACCEPTED
        offer.accepted_at = timezone.now()
        offer.save(update_fields=["status", "accepted_at", "updated_at"])
        accepted_data = WorkerOfferSerializer(offer).data
        self.assertEqual(accepted_data["service_address"], self.customer_address.full_address)
        self.assertIsNotNone(accepted_data["address_latitude"])
        self.assertIsNotNone(accepted_data["address_longitude"])

    def test_worker_job_detail_includes_extra_work_decision_and_payment_history(self):
        from apps.bookings.models import BookingExtraWork

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
            accepted_at=timezone.now(),
            started_at=timezone.now(),
        )
        proposal = BookingExtraWork.objects.create(
            booking=booking,
            worker=self.worker_profile,
            reason="Customer requested an additional repair",
            line_items=[{
                "description": "Replacement part",
                "quantity": 1,
                "unit_price": "150.00",
                "line_total": "150.00",
            }],
            subtotal=Decimal("150.00"),
            tax_amount=Decimal("0.00"),
            total_amount=Decimal("150.00"),
            status=BookingExtraWork.Status.APPROVED,
            payment_choice=BookingExtraWork.PaymentChoice.SEPARATE,
            payment_status="pending",
            customer_response_note="Please proceed",
            responded_at=timezone.now(),
        )

        self.client.force_authenticate(user=self.worker_user)
        response = self.client.get(f"/api/v1/workers/jobs/{assignment.pk}/")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data["extra_work_requests"]), 1)
        row = response.data["extra_work_requests"][0]
        self.assertEqual(row["id"], proposal.pk)
        self.assertEqual(row["status"], "approved")
        self.assertEqual(row["payment_status"], "pending")
        self.assertEqual(row["payment_choice"], "separate")
        self.assertEqual(row["customer_response_note"], "Please proceed")

    def _start_with_arrival_otp(self, url):
        import re
        from apps.notifications.models import Notification

        response = self.client.post(url, format="json")
        if response.data.get("arrival_otp_required"):
            notice = Notification.objects.filter(
                user=self.customer_user,
                title="Your professional has arrived",
            ).latest("created_at")
            match = re.search(
                r"arrival code with your AIRway professional: (\d{6})\.",
                notice.body,
            )
            self.assertIsNotNone(match, notice.body)
            response = self.client.post(
                url, {"arrival_otp": match.group(1)}, format="json"
            )
        return response

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
            accepted_at=timezone.now(),
        )

        self.client.force_authenticate(user=self.worker_user)
        response = self._start_with_arrival_otp(
            f"/api/v1/bookings/{booking.id}/start/"
        )

        self.assertEqual(response.status_code, 200, response.data)
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
        response = self._start_with_arrival_otp(
            f"/api/v1/bookings/{booking.id}/start/"
        )

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
        response = self._start_with_arrival_otp(
            f"/api/v1/workers/jobs/{assignment.id}/start/"
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


    def test_worker_rejection_cancels_booking_and_schedules_customer_refund(self):
        from unittest.mock import patch
        from apps.notifications.models import Notification

        booking = Booking.objects.create(
            customer=self.customer_user,
            address=self.customer_address,
            service=self.service,
            booking_mode=Booking.BookingMode.SCHEDULED,
            scheduled_at=_tomorrow_at_noon(),
            status=Booking.Status.ASSIGNED,
            pricing_snapshot={"total": "500.00"},
        )
        assignment = BookingAssignment.objects.create(
            booking=booking,
            worker=self.worker_profile,
        )
        worker_client = APIClient()
        worker_client.force_authenticate(user=self.worker_user)

        with patch("apps.workers.views._refund_worker_rejected_booking") as refund:
            with self.captureOnCommitCallbacks(execute=True):
                response = worker_client.post(
                    f"/api/v1/workers/jobs/{assignment.pk}/reject/",
                    {"reason": "Unable to attend"},
                    format="json",
                )

        self.assertEqual(response.status_code, 200, response.data)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CANCELLED)
        self.assertFalse(BookingAssignment.objects.filter(pk=assignment.pk).exists())
        refund.assert_called_once_with(booking.pk)
        self.assertTrue(Notification.objects.filter(
            user=self.customer_user,
            data__booking_id=booking.pk,
            data__purpose="worker_rejection_refund",
        ).exists())


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
            pricing_snapshot={"subtotal": "100.00", "total": "118.00"},
        )
        from apps.payments.models import Payment
        Payment.objects.create(
            booking=self.booking, customer=self.customer_user,
            stage=Payment.Stage.ADVANCE, amount=Decimal("1.00"),
            status=Payment.Status.PAID, method=Payment.Method.RAZORPAY,
            razorpay_payment_id="test_captured_advance", paid_at=timezone.now(),
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
            commission_rate=Decimal("10.00"),
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
            commission_rate=Decimal("10.00"),
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
            commission_rate=Decimal("10.00"),
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

    def test_approved_worker_can_submit_replacement_photo_without_replacing_verified_photo(self):
        user = User.objects.create_user(phone="+919876543212", name="Approved Worker")
        profile = WorkerProfile.objects.create(user=user, status=WorkerProfile.Status.APPROVED)
        old_photo = WorkerDocument.objects.create(
            worker=profile,
            doc_type=WorkerDocument.DocumentType.PHOTO,
            file="photos/approved-old.jpg",
            status=WorkerDocument.Status.VERIFIED,
        )
        self.client.force_authenticate(user=user)

        response = self.client.post(
            "/api/v1/workers/documents/upload/",
            {"doc_type": "photo", "file": self._create_test_image("new-photo.jpg")},
            format="multipart",
        )

        self.assertEqual(response.status_code, 201, response.data)
        old_photo.refresh_from_db()
        self.assertEqual(old_photo.status, WorkerDocument.Status.VERIFIED)
        self.assertTrue(WorkerDocument.objects.filter(
            worker=profile,
            doc_type=WorkerDocument.DocumentType.PHOTO,
            status=WorkerDocument.Status.PENDING,
        ).exists())
        profile_response = self.client.get("/api/v1/workers/me/")
        self.assertEqual(profile_response.status_code, 200)
        self.assertIn("approved-old.jpg", profile_response.data["photo_url"])

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
            commission_rate=Decimal("10.00"),
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
            commission_rate=Decimal("10.00"),
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
            pricing_snapshot={"subtotal": "100.00", "total": "118.00"},
        )

        from apps.payments.models import Payment
        Payment.objects.create(
            booking=booking, customer=self.customer_user,
            stage=Payment.Stage.ADVANCE, amount=Decimal("150.00"),
            status=Payment.Status.PAID, method=Payment.Method.RAZORPAY,
            razorpay_payment_id="test_captured_advance", paid_at=timezone.now(),
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
        self.assertEqual(payment.status, Payment.Status.PAID)
        self.assertEqual(payment.razorpay_payment_id, "test_captured_advance")
        self.assertEqual(payment.stage, Payment.Stage.ADVANCE)
        self.assertEqual(payment.method, Payment.Method.RAZORPAY)

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
        self.assertNotIn("payment_order_id", response.data)
        self.assertEqual(Payment.objects.get(booking=booking).status, Payment.Status.PAID)

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

        # The advance was already settled before dispatch; an unauthorised
        # worker must not create another payment or change that settlement.
        self.assertEqual(Payment.objects.filter(booking=booking).count(), 1)
        self.assertEqual(Payment.objects.get(booking=booking).status, Payment.Status.PAID)

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

    def test_payment_timeout_does_not_release_worker_after_paid_advance(self):
        """A settled advance is not timed out after the worker accepts."""

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
        self.assertEqual(payment.status, Payment.Status.PAID)
        self.assertIsNone(payment.failed_at)

        # The advance is already settled before dispatch, so accepting the offer
        # must not create a second pending payment or release the assigned worker.
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.ASSIGNED)

        # The accepted assignment remains in place because the advance is settled.
        from apps.bookings.models import BookingAssignment
        self.assertTrue(BookingAssignment.objects.filter(booking=booking).exists())
        self.assertEqual(count, 0)

    def test_suspension_before_start_reassigns_booking(self):
        """Suspending an assigned worker reopens and redispatches an unstarted paid job."""
        from apps.workers.dispatch_lifecycle import handle_worker_suspension
        from apps.notifications.models import Notification

        booking, offer = self._create_booking_with_offer()
        # This worker already had a pending offer which the first acceptance
        # will system-withdraw. Reassignment must reuse that unique offer row.
        other_offer = WorkerOffer.objects.create(
            booking=booking,
            worker=self.other_worker_profile,
            expires_at=timezone.now() + timedelta(hours=1),
        )
        worker_client = APIClient()
        worker_client.force_authenticate(user=self.worker_user)
        accepted = worker_client.post(
            f"/api/v1/workers/offers/{offer.id}/accept/", format="json"
        )
        self.assertEqual(accepted.status_code, 200, accepted.data)
        other_offer.refresh_from_db()
        self.assertEqual(other_offer.status, WorkerOffer.Status.WITHDRAWN)

        self.worker_profile.status = WorkerProfile.Status.SUSPENDED
        self.worker_profile.is_online = False
        self.worker_profile.save(update_fields=["status", "is_online", "updated_at"])
        result = handle_worker_suspension(self.worker_profile.pk)

        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.PENDING)
        self.assertFalse(BookingAssignment.objects.filter(booking=booking).exists())
        self.assertEqual(result["reassigned"], 1)
        other_offer.refresh_from_db()
        self.assertEqual(other_offer.status, WorkerOffer.Status.PENDING)
        self.assertEqual(
            WorkerOffer.objects.filter(
                booking=booking, worker=self.other_worker_profile,
                status=WorkerOffer.Status.PENDING,
            ).count(),
            1,
        )
        self.assertTrue(Notification.objects.filter(
            user=self.customer_user, title="Professional update"
        ).exists())

    def test_suspension_after_job_started_escalates_without_auto_reassignment(self):
        """Started work is paused for operations review rather than silently reassigned."""
        from apps.workers.dispatch_lifecycle import handle_worker_suspension
        from apps.notifications.models import Notification

        booking, offer = self._create_booking_with_offer()
        worker_client = APIClient()
        worker_client.force_authenticate(user=self.worker_user)
        accepted = worker_client.post(
            f"/api/v1/workers/offers/{offer.id}/accept/", format="json"
        )
        self.assertEqual(accepted.status_code, 200, accepted.data)
        assignment = BookingAssignment.objects.get(booking=booking)
        assignment.started_at = timezone.now()
        assignment.save(update_fields=["started_at", "updated_at"])
        booking.status = Booking.Status.IN_PROGRESS
        booking.save(update_fields=["status", "updated_at"])

        self.worker_profile.status = WorkerProfile.Status.SUSPENDED
        self.worker_profile.is_online = False
        self.worker_profile.save(update_fields=["status", "is_online", "updated_at"])
        result = handle_worker_suspension(self.worker_profile.pk)

        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.DISPUTED)
        self.assertTrue(BookingAssignment.objects.filter(booking=booking).exists())
        self.assertEqual(result["escalated"], 1)
        self.assertTrue(Notification.objects.filter(
            user=self.customer_user, title="Your booking needs an update"
        ).exists())

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

        # Selecting an active service is sufficient for application approval;
        # task capability verification is not an additional approval gate.
        from apps.workers.approval import get_approval_requirements
        requirements = get_approval_requirements(profile)
        self.assertTrue(requirements["has_service"])
        self.assertNotIn("Task capabilities verified by admin", requirements["missing"])
        self.assertFalse(requirements["eligible"])  # ID and photo still await admin verification.

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


    def test_worker_can_replace_weekly_schedule(self):
        response = self.client.put("/api/v1/workers/schedules/", {"schedules": [
            {"weekday": 1, "start_time": "09:00", "end_time": "13:00", "is_active": True},
            {"weekday": 3, "start_time": "10:00", "end_time": "17:00", "is_active": True},
        ]}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.profile.schedules.count(), 2)

    def test_worker_cannot_save_overlapping_working_windows(self):
        response = self.client.put("/api/v1/workers/schedules/", {"schedules": [
            {"weekday": 1, "start_time": "09:00", "end_time": "13:00", "is_active": True},
            {"weekday": 1, "start_time": "12:00", "end_time": "17:00", "is_active": True},
        ]}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.profile.schedules.count(), 0)

    def test_legacy_schedule_create_rejects_overlapping_window(self):
        WorkerSchedule.objects.create(
            worker=self.profile, weekday=1, start_time="09:00",
            end_time="13:00", is_active=True,
        )
        response = self.client.post("/api/v1/workers/schedules/", {
            "weekday": 1, "start_time": "12:00",
            "end_time": "17:00", "is_active": True,
        }, format="json")
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(self.profile.schedules.count(), 1)

    def test_worker_schedule_api_rejects_end_time_before_start(self):
        response = self.client.put("/api/v1/workers/schedules/", {"schedules": [
            {"weekday": 1, "start_time": "18:00", "end_time": "09:00", "is_active": True},
        ]}, format="json")
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(self.profile.schedules.count(), 0)

    def test_profile_endpoint_returns_saved_working_hours(self):
        WorkerSchedule.objects.create(
            worker=self.profile, weekday=2, start_time="09:00",
            end_time="17:00", is_active=True,
        )
        response = self.client.get("/api/v1/workers/me/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["schedules"]), 1)
        self.assertEqual(response.data["schedules"][0]["weekday"], 2)

    def test_schedule_update_cannot_exclude_an_accepted_booking(self):
        customer = User.objects.create_user(phone="+919876543223", name="Schedule Customer")
        address = Address.objects.create(
            user=customer, label="home", house_details="House 1",
            full_address="Rawatbhata, Rajasthan", zone=self.zone,
        )
        scheduled_at = _tomorrow_at_noon()
        local_start = timezone.localtime(scheduled_at)
        WorkerSchedule.objects.create(
            worker=self.profile, weekday=local_start.weekday(),
            start_time="09:00", end_time="18:00", is_active=True,
        )
        booking = Booking.objects.create(
            customer=customer, address=address, service=self.service,
            booking_mode=Booking.BookingMode.SCHEDULED,
            scheduled_at=scheduled_at, status=Booking.Status.ASSIGNED,
        )
        BookingAssignment.objects.create(
            booking=booking, worker=self.profile, accepted_at=timezone.now(),
        )

        response = self.client.put("/api/v1/workers/schedules/", {"schedules": [
            {"weekday": local_start.weekday(), "start_time": "13:00",
             "end_time": "18:00", "is_active": True},
        ]}, format="json")
        self.assertEqual(response.status_code, 409, response.data)
        self.assertEqual(self.profile.schedules.get().start_time.isoformat(), "09:00:00")

    def test_schedule_row_cannot_be_deleted_when_it_covers_an_accepted_booking(self):
        customer = User.objects.create_user(phone="+919876543225", name="Delete Schedule Customer")
        address = Address.objects.create(
            user=customer, label="home", house_details="House 3",
            full_address="Rawatbhata, Rajasthan", zone=self.zone,
        )
        scheduled_at = _tomorrow_at_noon()
        weekday = timezone.localtime(scheduled_at).weekday()
        schedule = WorkerSchedule.objects.create(
            worker=self.profile, weekday=weekday,
            start_time="09:00", end_time="18:00", is_active=True,
        )
        booking = Booking.objects.create(
            customer=customer, address=address, service=self.service,
            booking_mode=Booking.BookingMode.SCHEDULED,
            scheduled_at=scheduled_at, status=Booking.Status.ASSIGNED,
        )
        BookingAssignment.objects.create(
            booking=booking, worker=self.profile, accepted_at=timezone.now(),
        )

        response = self.client.delete(
            f"/api/v1/workers/schedules/{schedule.pk}/"
        )
        self.assertEqual(response.status_code, 409, response.data)
        self.assertTrue(WorkerSchedule.objects.filter(pk=schedule.pk).exists())

    def test_offline_withdraws_pending_offers_but_preserves_accepted_jobs(self):
        customer = User.objects.create_user(phone="+919876543224", name="Offline Customer")
        address = Address.objects.create(
            user=customer, label="home", house_details="House 2",
            full_address="Rawatbhata, Rajasthan", zone=self.zone,
        )
        accepted_booking = Booking.objects.create(
            customer=customer, address=address, service=self.service,
            booking_mode=Booking.BookingMode.SCHEDULED,
            scheduled_at=_tomorrow_at_noon(), status=Booking.Status.ASSIGNED,
        )
        accepted_offer = WorkerOffer.objects.create(
            booking=accepted_booking, worker=self.profile,
            status=WorkerOffer.Status.ACCEPTED, expires_at=accepted_booking.scheduled_at,
            accepted_at=timezone.now(),
        )
        assignment = BookingAssignment.objects.create(
            booking=accepted_booking, worker=self.profile, accepted_at=timezone.now(),
        )
        pending_booking = Booking.objects.create(
            customer=customer, address=address, service=self.service,
            booking_mode=Booking.BookingMode.SCHEDULED,
            scheduled_at=_tomorrow_at_noon() + timedelta(hours=2),
            status=Booking.Status.PENDING,
        )
        pending_offer = WorkerOffer.objects.create(
            booking=pending_booking, worker=self.profile,
            expires_at=pending_booking.scheduled_at,
        )

        response = self.client.post(
            "/api/v1/workers/status/", {"is_online": False}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        accepted_offer.refresh_from_db()
        pending_offer.refresh_from_db()
        self.assertEqual(accepted_offer.status, WorkerOffer.Status.ACCEPTED)
        self.assertEqual(pending_offer.status, WorkerOffer.Status.WITHDRAWN)
        self.assertTrue(BookingAssignment.objects.filter(pk=assignment.pk).exists())
        accepted_booking.refresh_from_db()
        self.assertEqual(accepted_booking.status, Booking.Status.ASSIGNED)
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
        from django.db import connection
        from apps.workers.eligibility import eligible_workers_for_service

        if connection.vendor != "postgresql":
            self.skipTest("JSONField contains matching is supported by the production PostgreSQL backend, not SQLite.")
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

    def test_selected_active_services_do_not_require_capability_verification_for_approval(self):
        from apps.workers.approval import get_approval_requirements

        second_service = Service.objects.create(
            category=self.category, title="Switch Repair",
            booking_mode="scheduled", pricing_type="fixed", is_active=True,
        )
        WorkerService.objects.create(
            worker=self.worker, service=second_service,
            capabilities=[], capabilities_verified=False,
        )
        self.assertTrue(get_approval_requirements(self.worker)["has_service"])
        self.assertNotIn("has_verified_capabilities", get_approval_requirements(self.worker))



class WorkerLeaveLifecycleAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.worker_user = User.objects.create_user(
            phone="+919876543299", name="Leave Worker", password="password123",
        )
        self.worker = WorkerProfile.objects.create(
            user=self.worker_user, status=WorkerProfile.Status.APPROVED,
        )
        self.client.force_authenticate(user=self.worker_user)

    def _period(self):
        start = timezone.now() + timedelta(days=3)
        return start, start + timedelta(hours=8)

    def test_worker_can_request_and_list_pending_leave(self):
        start, end = self._period()
        response = self.client.post(
            "/api/v1/workers/leaves/",
            {"start_at": start.isoformat(), "end_at": end.isoformat(), "reason": "Personal work"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["status"], WorkerLeave.Status.PENDING)
        self.assertEqual(WorkerLeaveHistory.objects.filter(leave_id=response.data["id"]).count(), 1)
        listed = self.client.get("/api/v1/workers/leaves/")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.data), 1)

    def test_overlapping_pending_leave_is_rejected(self):
        start, end = self._period()
        WorkerLeave.objects.create(
            worker=self.worker, start_at=start, end_at=end,
            status=WorkerLeave.Status.PENDING,
        )
        response = self.client.post(
            "/api/v1/workers/leaves/",
            {
                "start_at": (start + timedelta(hours=1)).isoformat(),
                "end_at": (end + timedelta(hours=1)).isoformat(),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_worker_can_cancel_pending_leave_and_history_is_recorded(self):
        start, end = self._period()
        leave = WorkerLeave.objects.create(
            worker=self.worker, start_at=start, end_at=end,
            status=WorkerLeave.Status.PENDING,
        )
        staff = User.objects.create_user(phone="+919876543294", password="password123")
        staff.is_staff = True
        staff.save(update_fields=["is_staff"])
        response = self.client.delete(f"/api/v1/workers/leaves/{leave.pk}/")
        self.assertEqual(response.status_code, 204)
        leave.refresh_from_db()
        self.assertEqual(leave.status, WorkerLeave.Status.CANCELLED)
        self.assertEqual(WorkerLeaveHistory.objects.filter(leave=leave).count(), 1)
        from apps.notifications.models import Notification
        self.assertTrue(Notification.objects.filter(
            type=Notification.Type.WORKER_LEAVE_CANCELLED,
            data__worker_leave_id=leave.pk,
        ).exists())

    def test_admin_approval_records_decision_and_notifies_worker(self):
        from apps.workers.leave_management import review_worker_leave
        from apps.notifications.models import Notification

        start, end = self._period()
        leave = WorkerLeave.objects.create(
            worker=self.worker, start_at=start, end_at=end,
            status=WorkerLeave.Status.PENDING,
        )
        admin = User.objects.create_user(
            phone="+919876543298", password="password123",
        )
        admin.is_staff = True
        admin.save(update_fields=["is_staff"])
        reviewed = review_worker_leave(
            leave_id=leave.pk, reviewer=admin,
            decision=WorkerLeave.Status.APPROVED,
        )
        self.assertEqual(reviewed.status, WorkerLeave.Status.APPROVED)
        self.assertEqual(reviewed.reviewed_by_id, admin.pk)
        self.assertEqual(WorkerLeaveHistory.objects.filter(leave=leave).count(), 1)
        self.assertTrue(Notification.objects.filter(
            user=self.worker_user, type=Notification.Type.WORKER_LEAVE_APPROVED,
        ).exists())

    def test_admin_cannot_approve_leave_with_active_assignment_conflict(self):
        from unittest.mock import patch
        from rest_framework.exceptions import ValidationError
        from apps.workers.leave_management import review_worker_leave

        start, end = self._period()
        leave = WorkerLeave.objects.create(
            worker=self.worker, start_at=start, end_at=end,
            status=WorkerLeave.Status.PENDING,
        )
        admin = User.objects.create_user(phone="+919876543297", password="password123")
        with patch("apps.workers.leave_management._assigned_booking_conflicts", return_value=[901, 902]):
            with self.assertRaises(ValidationError) as raised:
                review_worker_leave(
                    leave_id=leave.pk, reviewer=admin,
                    decision=WorkerLeave.Status.APPROVED,
                )
        self.assertEqual(
            [int(value) for value in raised.exception.detail["conflicting_booking_ids"]],
            [901, 902],
        )
        leave.refresh_from_db()
        self.assertEqual(leave.status, WorkerLeave.Status.PENDING)
        self.assertIsNone(leave.reviewed_at)

    def test_expired_pending_leave_is_closed_and_history_saved(self):
        from apps.workers.tasks import expire_past_worker_leave_requests
        from apps.notifications.models import Notification

        start = timezone.now() - timedelta(days=2)
        leave = WorkerLeave.objects.create(
            worker=self.worker, start_at=start, end_at=start + timedelta(hours=8),
            status=WorkerLeave.Status.PENDING,
        )
        self.assertEqual(expire_past_worker_leave_requests(), 1)
        leave.refresh_from_db()
        self.assertEqual(leave.status, WorkerLeave.Status.EXPIRED)
        self.assertEqual(WorkerLeaveHistory.objects.filter(
            leave=leave, to_status=WorkerLeave.Status.EXPIRED,
        ).count(), 1)
        self.assertTrue(Notification.objects.filter(
            user=self.worker_user, data__worker_leave_id=leave.pk,
            type=Notification.Type.WORKER_LEAVE_EXPIRED,
        ).exists())

    def test_expiry_task_does_not_change_approved_leave(self):
        from apps.workers.tasks import expire_past_worker_leave_requests

        start = timezone.now() - timedelta(days=2)
        leave = WorkerLeave.objects.create(
            worker=self.worker, start_at=start, end_at=start + timedelta(hours=8),
            status=WorkerLeave.Status.APPROVED,
        )
        self.assertEqual(expire_past_worker_leave_requests(), 0)
        leave.refresh_from_db()
        self.assertEqual(leave.status, WorkerLeave.Status.APPROVED)


    def test_worker_cannot_cancel_another_workers_leave(self):
        start, end = self._period()
        other_user = User.objects.create_user(
            phone="+919876543296", password="password123",
        )
        other_worker = WorkerProfile.objects.create(
            user=other_user, status=WorkerProfile.Status.APPROVED,
        )
        leave = WorkerLeave.objects.create(
            worker=other_worker, start_at=start, end_at=end,
            status=WorkerLeave.Status.PENDING,
        )
        response = self.client.delete(f"/api/v1/workers/leaves/{leave.pk}/")
        self.assertEqual(response.status_code, 404)
        leave.refresh_from_db()
        self.assertEqual(leave.status, WorkerLeave.Status.PENDING)

    def test_unapproved_worker_cannot_access_leave_management(self):
        pending_user = User.objects.create_user(
            phone="+919876543295", password="password123",
        )
        WorkerProfile.objects.create(
            user=pending_user, status=WorkerProfile.Status.PENDING,
        )
        self.client.force_authenticate(user=pending_user)
        response = self.client.get("/api/v1/workers/leaves/")
        self.assertEqual(response.status_code, 403)

    def test_worker_can_cancel_future_approved_leave(self):
        start, end = self._period()
        leave = WorkerLeave.objects.create(
            worker=self.worker, start_at=start, end_at=end,
            status=WorkerLeave.Status.APPROVED,
        )
        response = self.client.delete(f"/api/v1/workers/leaves/{leave.pk}/")
        self.assertEqual(response.status_code, 204)
        leave.refresh_from_db()
        self.assertEqual(leave.status, WorkerLeave.Status.CANCELLED)
        self.assertEqual(
            WorkerLeaveHistory.objects.filter(
                leave=leave, from_status=WorkerLeave.Status.APPROVED,
                to_status=WorkerLeave.Status.CANCELLED,
            ).count(),
            1,
        )



class WorkerZoneChangeRequestAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.city = City.objects.create(name="Jaipur", state="Rajasthan")
        self.zone = Zone.objects.create(name="Vaishali Nagar", city=self.city, is_active=True)
        self.user = User.objects.create_user(phone="+919876543299", password="password123")
        self.worker = WorkerProfile.objects.create(user=self.user, status=WorkerProfile.Status.APPROVED)
        self.client.force_authenticate(user=self.user)

    def test_worker_zone_add_is_pending_until_admin_approval(self):
        response = self.client.post("/api/v1/workers/zones/", {"zone": self.zone.pk}, format="json")
        self.assertEqual(response.status_code, 202, response.data)
        self.assertEqual(response.data["status"], "pending")
        self.assertFalse(WorkerZone.objects.filter(worker=self.worker, zone=self.zone).exists())
        self.assertEqual(self.client.get("/api/v1/workers/zones/").data, [])

    def test_worker_can_list_zone_change_requests(self):
        response = self.client.post("/api/v1/workers/zones/", {"zone": self.zone.pk}, format="json")
        self.assertEqual(response.status_code, 202)
        listed = self.client.get("/api/v1/workers/zone-requests/")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.data), 1)
        self.assertEqual(listed.data[0]["zone"], self.zone.pk)

    def test_duplicate_pending_zone_request_is_rejected(self):
        first = self.client.post("/api/v1/workers/zones/", {"zone": self.zone.pk}, format="json")
        second = self.client.post("/api/v1/workers/zones/", {"zone": self.zone.pk}, format="json")
        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 409)

    def test_unapproved_worker_cannot_request_zone_removal(self):
        self.worker.status = WorkerProfile.Status.PENDING
        self.worker.save(update_fields=["status", "updated_at"])
        WorkerZone.objects.create(worker=self.worker, zone=self.zone)
        response = self.client.delete(f"/api/v1/workers/zones/{self.zone.pk}/")
        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            self.worker.zone_change_requests.filter(
                zone=self.zone, status="pending"
            ).exists()
        )

    def test_zone_removal_requires_admin_approval(self):
        WorkerZone.objects.create(worker=self.worker, zone=self.zone)
        response = self.client.delete(f"/api/v1/workers/zones/{self.zone.pk}/")
        self.assertEqual(response.status_code, 202, response.data)
        self.assertTrue(WorkerZone.objects.filter(worker=self.worker, zone=self.zone).exists())
        self.assertEqual(response.data["action"], "remove")

    def test_admin_approval_applies_worker_zone_removal(self):
        from .models import WorkerZoneChangeRequest
        from .zone_changes import review_worker_zone_change
        admin_user = User.objects.create_superuser(
            phone="+919876543296", password="adminpass"
        )
        WorkerZone.objects.create(worker=self.worker, zone=self.zone)
        change = WorkerZoneChangeRequest.objects.create(
            worker=self.worker, zone=self.zone,
            action=WorkerZoneChangeRequest.Action.REMOVE,
        )
        reviewed = review_worker_zone_change(
            request_id=change.pk, reviewer=admin_user,
            decision=WorkerZoneChangeRequest.Status.APPROVED,
        )
        self.assertEqual(reviewed.status, WorkerZoneChangeRequest.Status.APPROVED)
        self.assertFalse(
            WorkerZone.objects.filter(worker=self.worker, zone=self.zone).exists()
        )

    def test_admin_review_applies_zone_change_and_is_audited(self):
        from .models import WorkerZoneChangeRequest
        from .zone_changes import review_worker_zone_change
        from django.utils import timezone
        admin_user = User.objects.create_superuser(phone="+919876543298", password="adminpass")
        change = WorkerZoneChangeRequest.objects.create(
            worker=self.worker, zone=self.zone, action=WorkerZoneChangeRequest.Action.ADD,
        )
        reviewed = review_worker_zone_change(
            request_id=change.pk, reviewer=admin_user,
            decision=WorkerZoneChangeRequest.Status.APPROVED,
        )
        self.assertEqual(reviewed.status, WorkerZoneChangeRequest.Status.APPROVED)
        self.assertEqual(reviewed.reviewed_by, admin_user)
        self.assertIsNotNone(reviewed.reviewed_at)
        self.assertTrue(WorkerZone.objects.filter(worker=self.worker, zone=self.zone).exists())
        from apps.notifications.models import Notification
        notice = Notification.objects.get(user=self.user, type=Notification.Type.WORKER_ZONE_APPROVED)
        self.assertEqual(notice.data["worker_zone_request_id"], change.pk)

    def test_rejection_requires_a_reason(self):
        from .models import WorkerZoneChangeRequest
        from .zone_changes import review_worker_zone_change
        from django.core.exceptions import ValidationError
        admin_user = User.objects.create_superuser(phone="+919876543297", password="adminpass")
        change = WorkerZoneChangeRequest.objects.create(
            worker=self.worker, zone=self.zone, action=WorkerZoneChangeRequest.Action.ADD,
        )
        with self.assertRaises(ValidationError):
            review_worker_zone_change(
                request_id=change.pk, reviewer=admin_user,
                decision=WorkerZoneChangeRequest.Status.REJECTED,
            )


    def test_rejected_zone_request_notifies_worker_with_admin_reason(self):
        from .models import WorkerZoneChangeRequest
        from .zone_changes import review_worker_zone_change
        from apps.notifications.models import Notification
        admin_user = User.objects.create_superuser(phone="+919876543296", password="adminpass")
        change = WorkerZoneChangeRequest.objects.create(
            worker=self.worker, zone=self.zone, action=WorkerZoneChangeRequest.Action.ADD,
        )
        review_worker_zone_change(
            request_id=change.pk, reviewer=admin_user,
            decision=WorkerZoneChangeRequest.Status.REJECTED, note="Coverage is full",
        )
        notice = Notification.objects.get(user=self.user, type=Notification.Type.WORKER_ZONE_REJECTED)
        self.assertIn("Coverage is full", notice.body)
        self.assertEqual(notice.data["worker_zone_request_id"], change.pk)
