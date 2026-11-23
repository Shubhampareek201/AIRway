from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Address, User
from apps.bookings.models import (
    Booking, BookingAssignment, BookingQuote, BookingStatusHistory,
    Order, OrderItem,
)
from apps.catalog.models import Category, Service
from apps.core.models import City, Zone
from apps.payments.models import Payment
from apps.workers.models import WorkerProfile


class InspectionQuoteLifecycleTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            phone="+919876543801", password="password123", name="Quote Customer"
        )
        self.worker_user = User.objects.create_user(
            phone="+919876543802", password="password123", name="Quote Worker"
        )
        self.worker = WorkerProfile.objects.create(
            user=self.worker_user, status=WorkerProfile.Status.APPROVED
        )
        self.city = City.objects.create(name="Quote Test City", state="Rajasthan")
        self.zone = Zone.objects.create(
            name="Quote Test Zone", city=self.city, is_active=True
        )
        self.address = Address.objects.create(
            user=self.customer,
            label="Home",
            house_details="House 1",
            full_address="Quote Test Address",
            zone=self.zone,
        )
        self.category = Category.objects.create(
            title="Electrical", slug="quote-test-electrical"
        )
        self.service = Service.objects.create(
            category=self.category,
            title="Electrical Inspection",
            booking_mode=Service.BookingMode.INSPECTION,
            pricing_type=Service.PricingType.QUOTE,
            visit_fee=Decimal("100.00"),
            is_active=True,
        )
        self.booking = Booking.objects.create(
            customer=self.customer,
            address=self.address,
            service=self.service,
            booking_mode=Booking.BookingMode.INSPECTION,
            scheduled_at=timezone.now() + timedelta(hours=1),
            status=Booking.Status.IN_PROGRESS,
            pricing_snapshot={
                "visit_fee": "100.00",
                "subtotal": "100.00",
                "tax": "18.00",
                "total": "118.00",
                "currency": "INR",
            },
        )
        self.assignment = BookingAssignment.objects.create(
            booking=self.booking,
            worker=self.worker,
            accepted_at=timezone.now() - timedelta(minutes=30),
            started_at=timezone.now() - timedelta(minutes=10),
        )
        self.order = Order.objects.create(
            customer=self.customer,
            address=self.address,
            status=Order.Status.AWAITING_ASSIGNMENT,
            subtotal=Decimal("100.00"),
            tax_amount=Decimal("18.00"),
            total_amount=Decimal("118.00"),
            metadata={
                "payment_allocation_v1": {
                    "percentage": "30",
                    "advance_total": "35.40",
                    "balance_total": "82.60",
                    "advance": [{"order_item_id": 1, "booking_id": self.booking.id, "amount": "35.40"}],
                    "balance": [{"order_item_id": 1, "booking_id": self.booking.id, "amount": "82.60"}],
                }
            },
        )
        self.order_item = OrderItem.objects.create(
            order=self.order,
            booking=self.booking,
            quantity=1,
            service_snapshot={"service_title": self.service.title},
            pricing_snapshot=self.booking.pricing_snapshot,
            line_subtotal=Decimal("100.00"),
            tax_amount=Decimal("18.00"),
            line_total=Decimal("118.00"),
        )
        allocation = self.order.metadata["payment_allocation_v1"]
        allocation["advance"][0]["order_item_id"] = self.order_item.id
        allocation["balance"][0]["order_item_id"] = self.order_item.id
        self.order.metadata = {"payment_allocation_v1": allocation}
        self.order.save(update_fields=["metadata", "updated_at"])
        Payment.objects.create(
            order=self.order,
            customer=self.customer,
            stage=Payment.Stage.ADVANCE,
            amount=Decimal("35.40"),
            method=Payment.Method.RAZORPAY,
            status=Payment.Status.PAID,
            razorpay_payment_id="quote_test_advance_paid",
        )
        self.worker_client = APIClient()
        self.worker_client.force_authenticate(self.worker_user)
        self.customer_client = APIClient()
        self.customer_client.force_authenticate(self.customer)
        self.admin_user = User.objects.create_user(
            phone="+919876543804", password="password123",
            name="AIRway Admin", is_staff=True, is_superuser=True,
        )
        self.admin_client = APIClient()
        self.admin_client.force_login(self.admin_user)

    def _submit_quote(self):
        return self.worker_client.post(
            f"/api/v1/workers/jobs/{self.assignment.id}/quote/",
            {
                "line_items": [
                    {"type": "labour", "description": "Fan repair labour", "quantity": "2", "unit_price": "100.00"},
                    {"type": "material", "description": "Capacitor and wiring", "quantity": "1", "unit_price": "300.00"},
                ],
                "notes": "Includes labour and required replacement parts.",
            },
            format="json",
        )

    def _approve_quote_for_customer(self, quote_id, payout="350.00"):
        response = self.admin_client.post(
            reverse("admin:bookings_bookingquote_change", args=[quote_id]),
            {
                "worker_payout_amount": payout,
                "payout_approval_note": "Reviewed quote and approved fixed worker payout.",
                "approve_for_customer": "on",
                "_save": "Save",
            },
        )
        self.assertEqual(response.status_code, 302, getattr(response, "context", None))
        quote = BookingQuote.objects.get(pk=quote_id)
        self.assertEqual(quote.status, BookingQuote.Status.PENDING_CUSTOMER)
        self.assertEqual(quote.worker_payout_amount, Decimal(payout))
        self.assertEqual(quote.payout_approved_by, self.admin_user)
        self.assertTrue(quote.payout_approved_at)
        return quote

    def test_worker_quote_waits_for_admin_payout_approval(self):
        response = self._submit_quote()
        self.assertEqual(response.status_code, 201, response.data)
        quote = BookingQuote.objects.get(pk=response.data["id"])
        self.assertEqual(quote.status, BookingQuote.Status.PENDING_ADMIN)
        self.assertIsNone(quote.worker_payout_amount)

        customer_response = self.customer_client.post(
            f"/api/v1/bookings/{self.booking.id}/quote/respond/",
            {"decision": "accept"},
            format="json",
        )
        self.assertEqual(customer_response.status_code, 404, customer_response.data)

        approved = self._approve_quote_for_customer(quote.id)
        self.assertEqual(approved.status, BookingQuote.Status.PENDING_CUSTOMER)

    def test_customer_acceptance_updates_booking_order_and_remaining_balance(self):
        submitted = self._submit_quote()
        self.assertEqual(submitted.status_code, 201, submitted.data)
        self._approve_quote_for_customer(submitted.data["id"])

        response = self.customer_client.post(
            f"/api/v1/bookings/{self.booking.id}/quote/respond/",
            {"decision": "accept"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)

        quote = BookingQuote.objects.get(pk=submitted.data["id"])
        self.assertEqual(quote.status, BookingQuote.Status.ACCEPTED)
        self.booking.refresh_from_db()
        self.order.refresh_from_db()
        self.order_item.refresh_from_db()
        self.assertEqual(Decimal(self.booking.pricing_snapshot["total"]), Decimal("708.00"))
        self.assertEqual(self.booking.worker_payout_snapshot["pricing_model"], "admin_approved_quote_payout_v1")
        self.assertEqual(Decimal(self.booking.worker_payout_snapshot["total"]), Decimal("350.00"))
        self.assertEqual(self.booking.worker_payout_snapshot["approved_by_id"], self.admin_user.id)
        self.assertEqual(self.order_item.line_subtotal, Decimal("600.00"))
        self.assertEqual(self.order_item.tax_amount, Decimal("108.00"))
        self.assertEqual(self.order_item.line_total, Decimal("708.00"))
        self.assertEqual(self.order.total_amount, Decimal("708.00"))
        allocation = self.order.metadata["payment_allocation_v1"]
        self.assertEqual(Decimal(allocation["advance_total"]), Decimal("35.40"))
        self.assertEqual(Decimal(allocation["percentage"]), Decimal("5.00"))
        self.assertEqual(Decimal(allocation["balance_total"]), Decimal("672.60"))
        self.assertEqual(Decimal(allocation["balance"][0]["amount"]), Decimal("672.60"))

    def test_customer_can_reject_quote_and_worker_can_submit_a_revision(self):
        first = self._submit_quote()
        self.assertEqual(first.status_code, 201, first.data)
        self._approve_quote_for_customer(first.data["id"])
        rejected = self.customer_client.post(
            f"/api/v1/bookings/{self.booking.id}/quote/respond/",
            {"decision": "reject", "note": "Please explain the material cost."},
            format="json",
        )
        self.assertEqual(rejected.status_code, 200, rejected.data)
        revision = self._submit_quote()
        self.assertEqual(revision.status_code, 201, revision.data)
        self.assertEqual(revision.data["version"], 2)

    def test_worker_cannot_quote_another_workers_job(self):
        other_user = User.objects.create_user(
            phone="+919876543803", password="password123"
        )
        other_client = APIClient()
        other_client.force_authenticate(other_user)
        response = other_client.post(
            f"/api/v1/workers/jobs/{self.assignment.id}/quote/",
            {"line_items": [{"type": "labour", "description": "Repair", "quantity": 1, "unit_price": 100}]},
            format="json",
        )
        self.assertEqual(response.status_code, 404)

    def test_worker_cannot_complete_inspection_before_customer_approves_quote(self):
        response = self.worker_client.post(
            f"/api/v1/workers/jobs/{self.assignment.id}/complete/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, 409, response.data)
        self.assertIn("approve", response.data["detail"].lower())

    def test_quote_rejects_negative_or_malformed_prices(self):
        response = self.worker_client.post(
            f"/api/v1/workers/jobs/{self.assignment.id}/quote/",
            {"line_items": [{"type": "material", "description": "Unsafe amount", "quantity": 1, "unit_price": -10}]},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
