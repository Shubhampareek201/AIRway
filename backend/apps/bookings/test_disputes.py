from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Address, User
from apps.bookings.models import Booking, BookingAssignment, BookingDispute
from apps.catalog.models import Category, Service
from apps.core.models import City, Zone
from apps.workers.models import WorkerProfile


class BookingDisputeAPITests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            phone="+919876542001", password="password123"
        )
        self.worker_user = User.objects.create_user(
            phone="+919876542002", password="password123"
        )
        self.other_user = User.objects.create_user(
            phone="+919876542003", password="password123"
        )
        self.staff_user = User.objects.create_user(
            phone="+919876542004", password="password123", is_staff=True
        )
        city = City.objects.create(name="Dispute Test City", state="Rajasthan")
        zone = Zone.objects.create(name="Dispute Test Zone", city=city, is_active=True)
        address = Address.objects.create(
            user=self.customer,
            label="Home",
            house_details="House 1",
            full_address="Dispute Test Address",
            zone=zone,
        )
        category = Category.objects.create(
            title="Dispute Test", slug="dispute-test-category"
        )
        service = Service.objects.create(
            category=category,
            title="Test Service",
            booking_mode=Service.BookingMode.SCHEDULED,
            pricing_type=Service.PricingType.FIXED,
            is_active=True,
        )
        self.booking = Booking.objects.create(
            customer=self.customer,
            address=address,
            service=service,
            scheduled_at=timezone.now() - timedelta(hours=1),
            status=Booking.Status.IN_PROGRESS,
        )
        self.worker = WorkerProfile.objects.create(
            user=self.worker_user,
            status=WorkerProfile.Status.APPROVED,
        )
        self.assignment = BookingAssignment.objects.create(
            booking=self.booking,
            worker=self.worker,
            started_at=timezone.now() - timedelta(minutes=30),
        )
        self.customer_client = APIClient()
        self.customer_client.force_authenticate(self.customer)
        self.worker_client = APIClient()
        self.worker_client.force_authenticate(self.worker_user)
        self.other_client = APIClient()
        self.other_client.force_authenticate(self.other_user)
        self.staff_client = APIClient()
        self.staff_client.force_authenticate(self.staff_user)

    def _payload(self):
        return {
            "booking_id": self.booking.pk,
            "category": BookingDispute.Category.SERVICE_QUALITY,
            "description": "The service was not completed to the agreed standard.",
            "requested_outcome": BookingDispute.RequestedOutcome.REWORK,
            "evidence_items": [
                {"label": "Area", "detail": "Kitchen counter was not cleaned."}
            ],
        }

    def test_customer_can_raise_dispute_and_worker_can_view_it(self):
        response = self.customer_client.post(
            "/api/v1/bookings/disputes/", self._payload(), format="json"
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["raised_by_role"], "customer")
        detail = self.worker_client.get(
            f"/api/v1/bookings/disputes/{response.data['id']}/"
        )
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["booking_id"], self.booking.pk)

    def test_assigned_worker_can_raise_dispute(self):
        response = self.worker_client.post(
            "/api/v1/bookings/disputes/", self._payload(), format="json"
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["raised_by_role"], "worker")

    def test_unrelated_user_cannot_raise_or_view_dispute(self):
        response = self.other_client.post(
            "/api/v1/bookings/disputes/", self._payload(), format="json"
        )
        self.assertEqual(response.status_code, 403)
        dispute = BookingDispute.objects.create(
            booking=self.booking,
            raised_by=self.customer,
            raised_by_role="customer",
            category=BookingDispute.Category.SERVICE_QUALITY,
            description="A dispute raised by the customer.",
            requested_outcome=BookingDispute.RequestedOutcome.INVESTIGATION,
        )
        detail = self.other_client.get(
            f"/api/v1/bookings/disputes/{dispute.pk}/"
        )
        self.assertEqual(detail.status_code, 403)

    def test_only_one_active_dispute_can_exist_for_booking(self):
        first = self.customer_client.post(
            "/api/v1/bookings/disputes/", self._payload(), format="json"
        )
        self.assertEqual(first.status_code, 201)
        second = self.worker_client.post(
            "/api/v1/bookings/disputes/", self._payload(), format="json"
        )
        self.assertEqual(second.status_code, 409)

    def test_completed_booking_has_seven_day_dispute_window(self):
        self.booking.status = Booking.Status.COMPLETED
        self.booking.completed_at = timezone.now() - timedelta(days=8)
        self.booking.save(update_fields=["status", "completed_at", "updated_at"])
        response = self.customer_client.post(
            "/api/v1/bookings/disputes/", self._payload(), format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("window has expired", response.data["detail"])

    def test_staff_must_supply_resolution_note_and_cannot_skip_review(self):
        created = self.customer_client.post(
            "/api/v1/bookings/disputes/", self._payload(), format="json"
        )
        dispute_id = created.data["id"]
        invalid = self.staff_client.patch(
            f"/api/v1/bookings/disputes/{dispute_id}/",
            {"status": BookingDispute.Status.CLOSED},
            format="json",
        )
        self.assertEqual(invalid.status_code, 400)
        missing_note = self.staff_client.patch(
            f"/api/v1/bookings/disputes/{dispute_id}/",
            {"status": BookingDispute.Status.RESOLVED},
            format="json",
        )
        self.assertEqual(missing_note.status_code, 400)
        in_review = self.staff_client.patch(
            f"/api/v1/bookings/disputes/{dispute_id}/",
            {"status": BookingDispute.Status.IN_REVIEW},
            format="json",
        )
        self.assertEqual(in_review.status_code, 200)
        resolved = self.staff_client.patch(
            f"/api/v1/bookings/disputes/{dispute_id}/",
            {
                "status": BookingDispute.Status.RESOLVED,
                "resolution_note": "A rework visit has been approved.",
            },
            format="json",
        )
        self.assertEqual(resolved.status_code, 200, resolved.data)
        self.assertEqual(resolved.data["status"], BookingDispute.Status.RESOLVED)

    def test_non_staff_cannot_change_dispute_status(self):
        dispute = BookingDispute.objects.create(
            booking=self.booking,
            raised_by=self.customer,
            raised_by_role="customer",
            category=BookingDispute.Category.PAYMENT,
            description="Payment concern.",
            requested_outcome=BookingDispute.RequestedOutcome.REFUND_REVIEW,
        )
        response = self.customer_client.patch(
            f"/api/v1/bookings/disputes/{dispute.pk}/",
            {"status": BookingDispute.Status.IN_REVIEW},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
