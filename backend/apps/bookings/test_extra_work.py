from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User, Address
from apps.catalog.models import Category, Service
from apps.core.models import City, Zone
from apps.workers.models import WorkerProfile
from apps.bookings.models import Booking, BookingAssignment, BookingExtraWork


class ExtraWorkAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        city = City.objects.create(name="Jaipur", state="Rajasthan")
        zone = Zone.objects.create(name="Test Zone", city=city, is_active=True)
        category = Category.objects.create(title="Home Care", slug="extra-work-home-care")
        service = Service.objects.create(
            category=category, title="Home Cleaning",
            booking_mode="scheduled", pricing_type="fixed", is_active=True,
        )
        self.customer = User.objects.create_user(phone="+919876541001", password="password123")
        self.worker_user = User.objects.create_user(phone="+919876541002", password="password123")
        address = Address.objects.create(
            user=self.customer, label="home", house_details="House 1",
            full_address="Test address, Jaipur", zone=zone,
        )
        self.worker = WorkerProfile.objects.create(
            user=self.worker_user, status=WorkerProfile.Status.APPROVED,
        )
        self.booking = Booking.objects.create(
            customer=self.customer, address=address, service=service,
            scheduled_at=timezone.now(), status=Booking.Status.IN_PROGRESS,
        )
        BookingAssignment.objects.create(
            booking=self.booking, worker=self.worker, accepted_at=timezone.now(),
        )

    def _proposal(self):
        return BookingExtraWork.objects.create(
            booking=self.booking, worker=self.worker, reason="Additional cleaning required",
            line_items=[{"description": "Deep clean", "quantity": 1, "unit_price": "250.00", "line_total": "250.00"}],
            subtotal="250.00", tax_amount="0.00", total_amount="250.00",
            expires_at=timezone.now() + timezone.timedelta(hours=24),
        )

    def test_worker_can_propose_extra_work_for_started_assigned_job(self):
        self.client.force_authenticate(user=self.worker_user)
        response = self.client.post(
            f"/api/v1/workers/jobs/{self.booking.pk}/extra-work/",
            {
                "reason": "Additional cleaning required",
                "line_items": [{"description": "Deep clean", "quantity": 1, "unit_price": "250.00"}],
                "additional_duration_minutes": 30,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["total_amount"], "250.00")
        self.assertEqual(response.data["status"], BookingExtraWork.Status.PENDING_CUSTOMER)

    def test_customer_can_approve_with_separate_payment_choice(self):
        proposal = self._proposal()
        self.client.force_authenticate(user=self.customer)
        response = self.client.post(
            f"/api/v1/bookings/extra-work/{proposal.pk}/decision/",
            {"decision": "approve", "payment_choice": BookingExtraWork.PaymentChoice.SEPARATE},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, BookingExtraWork.Status.APPROVED)
        self.assertEqual(proposal.payment_choice, BookingExtraWork.PaymentChoice.SEPARATE)

    def test_customer_can_reject_proposal(self):
        proposal = self._proposal()
        self.client.force_authenticate(user=self.customer)
        response = self.client.post(
            f"/api/v1/bookings/extra-work/{proposal.pk}/decision/",
            {"decision": "reject", "note": "Not required"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, BookingExtraWork.Status.REJECTED)

    def test_other_customer_cannot_read_or_decide_proposal(self):
        proposal = self._proposal()
        other = User.objects.create_user(phone="+919876541003", password="password123")
        self.client.force_authenticate(user=other)
        response = self.client.post(
            f"/api/v1/bookings/extra-work/{proposal.pk}/decision/",
            {"decision": "approve", "payment_choice": BookingExtraWork.PaymentChoice.ADD_TO_BALANCE},
            format="json",
        )
        self.assertEqual(response.status_code, 404)
