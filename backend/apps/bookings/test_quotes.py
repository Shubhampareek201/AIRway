from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Address, User
from apps.bookings.models import (
    Booking, BookingAssignment, BookingQuote, BookingStatusHistory,
    AppointmentGroup, Order, OrderItem,
)
from apps.catalog.models import Category, Service, ServiceInspectionRate
from apps.core.models import City, Zone
from apps.payments.models import Payment
from apps.workers.models import WorkerEarning, WorkerProfile


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
            visit_fee_worker_payout=Decimal("60.00"),
            is_active=True,
        )
        self.labour_rate = ServiceInspectionRate.objects.create(service=self.service, code="fan-labour", title="Fan repair labour", rate_type="labour", customer_price=Decimal("200.00"), worker_payout=Decimal("100.00"))
        self.material_rate = ServiceInspectionRate.objects.create(service=self.service, code="capacitor", title="Capacitor and wiring", rate_type="material", customer_price=Decimal("300.00"), worker_payout=Decimal("150.00"))
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
                "inspection_fee_credit_model": "visit_fee_credit_v1",
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
                    "advance_total": "118.00",
                    "balance_total": "0.00",
                    "advance": [{"order_item_id": 1, "booking_id": self.booking.id, "amount": "118.00"}],
                    "balance": [{"order_item_id": 1, "booking_id": self.booking.id, "amount": "0.00"}],
                }
            },
        )
        self.appointment_group = AppointmentGroup.objects.create(
            order=self.order,
            group_number=1,
            scheduled_at=self.booking.scheduled_at,
        )
        self.booking.appointment_group = self.appointment_group
        self.booking.save(update_fields=["appointment_group", "updated_at"])
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
            amount=Decimal("118.00"),
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
                "items": [
                    {"rate_id": self.labour_rate.id, "quantity": 1},
                    {"rate_id": self.material_rate.id, "quantity": 1},
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

    def test_worker_quote_is_sent_directly_to_customer_with_configured_payout(self):
        response = self._submit_quote()
        self.assertEqual(response.status_code, 201, response.data)
        quote = BookingQuote.objects.get(pk=response.data["id"])
        self.assertEqual(quote.status, BookingQuote.Status.PENDING_CUSTOMER)
        self.assertEqual(quote.worker_payout_amount, Decimal("250.00"))
        self.assertTrue(all("rate_id" in row for row in quote.line_items))

    def test_customer_acceptance_updates_booking_order_and_remaining_balance(self):
        submitted = self._submit_quote()
        self.assertEqual(submitted.status_code, 201, submitted.data)
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
        self.assertEqual(Decimal(self.booking.pricing_snapshot["total"]), Decimal("590.00"))
        self.assertEqual(self.booking.worker_payout_snapshot["pricing_model"], "fixed_service_payout_v1")
        self.assertEqual(Decimal(self.booking.worker_payout_snapshot["total"]), Decimal("310.00"))
        self.assertEqual(self.order_item.line_subtotal, Decimal("500.00"))
        self.assertEqual(self.order_item.tax_amount, Decimal("90.00"))
        self.assertEqual(self.order_item.line_total, Decimal("590.00"))
        self.assertEqual(self.order.total_amount, Decimal("590.00"))
        allocation = self.order.metadata["payment_allocation_v1"]
        self.assertEqual(Decimal(allocation["advance_total"]), Decimal("118.00"))
        self.assertEqual(Decimal(allocation["percentage"]), Decimal("20.00"))
        self.assertEqual(Decimal(allocation["balance_total"]), Decimal("472.00"))
        self.assertEqual(Decimal(allocation["balance"][0]["amount"]), Decimal("472.00"))

        order_response = self.customer_client.get(
            f"/api/v1/bookings/orders/{self.order.id}/"
        )
        self.assertEqual(order_response.status_code, 200, order_response.data)
        order_row = next(
            row for row in order_response.data["items"]
            if row["booking_id"] == self.booking.id
        )
        self.assertEqual(
            Decimal(order_row["quote"]["inspection_fee_credit"]),
            Decimal("118.00"),
        )
        self.assertTrue(order_response.data["ready_for_balance"])
        group_row = order_response.data["appointment_groups"][0]
        self.assertEqual(group_row["id"], self.appointment_group.id)
        self.assertTrue(group_row["ready_for_balance"])
        self.assertEqual(Decimal(group_row["balance_due"]), Decimal("472.00"))

    def test_worker_can_start_repair_only_after_balance_payment_is_confirmed(self):
        submitted = self._submit_quote()
        self.assertEqual(submitted.status_code, 201, submitted.data)
        accepted = self.customer_client.post(
            f"/api/v1/bookings/{self.booking.id}/quote/respond/",
            {"decision": "accept"},
            format="json",
        )
        self.assertEqual(accepted.status_code, 200, accepted.data)

        start_url = f"/api/v1/workers/jobs/{self.assignment.id}/start-repair/"
        unpaid_attempt = self.worker_client.post(start_url, {}, format="json")
        self.assertEqual(unpaid_attempt.status_code, 409, unpaid_attempt.data)

        Payment.objects.create(
            order=self.order,
            appointment_group=self.appointment_group,
            customer=self.customer,
            stage=Payment.Stage.BALANCE,
            amount=Decimal("472.00"),
            method=Payment.Method.RAZORPAY,
            status=Payment.Status.PAID,
            razorpay_payment_id="quote_test_balance_paid",
        )
        paid_attempt = self.worker_client.post(start_url, {}, format="json")
        self.assertEqual(paid_attempt.status_code, 200, paid_attempt.data)
        quote = BookingQuote.objects.get(booking=self.booking)
        self.assertIsNotNone(quote.repair_started_at)

    def test_customer_can_decline_repair_and_settle_paid_inspection_visit(self):
        submitted = self._submit_quote()
        self.assertEqual(submitted.status_code, 201, submitted.data)

        response = self.customer_client.post(
            f"/api/v1/bookings/{self.booking.id}/quote/respond/",
            {"decision": "cancel"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)

        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.CANCELLED)
        self.assertEqual(self.booking.worker_payout_snapshot["total"], "60.00")
        earning = WorkerEarning.objects.get(booking=self.booking)
        self.assertEqual(earning.gross_amount, Decimal("100.00"))
        self.assertEqual(earning.net_amount, Decimal("60.00"))
        self.assertEqual(earning.status, WorkerEarning.Status.AVAILABLE)

    def test_customer_can_reject_quote_and_worker_can_submit_a_revision(self):
        first = self._submit_quote()
        self.assertEqual(first.status_code, 201, first.data)
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
            {"items": [{"rate_id": 999999, "quantity": 1}]},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    @patch("apps.payments.views.client.order.create")
    def test_customer_balance_checkout_api_creates_appointment_scoped_payment_idempotently(self, create_gateway_order):
        submitted = self._submit_quote()
        self.assertEqual(submitted.status_code, 201, submitted.data)
        accepted = self.customer_client.post(
            f"/api/v1/bookings/{self.booking.id}/quote/respond/",
            {"decision": "accept"},
            format="json",
        )
        self.assertEqual(accepted.status_code, 200, accepted.data)
        create_gateway_order.return_value = {"id": "order_quote_balance_api"}

        payload = {
            "order_id": self.order.id,
            "stage": Payment.Stage.BALANCE,
            "appointment_group_id": self.appointment_group.id,
        }
        first = self.customer_client.post(
            "/api/v1/payments/create-order/", payload, format="json"
        )
        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual(first.data["payment_stage"], Payment.Stage.BALANCE)
        self.assertEqual(first.data["appointment_group_id"], self.appointment_group.id)
        self.assertEqual(Decimal(first.data["stage_amount"]), Decimal("472.00"))
        payment = Payment.objects.get(pk=first.data["payment_id"])
        self.assertEqual(payment.amount, Decimal("472.00"))
        self.assertEqual(payment.appointment_group_id, self.appointment_group.id)
        create_gateway_order.assert_called_once()

        retry = self.customer_client.post(
            "/api/v1/payments/create-order/", payload, format="json"
        )
        self.assertEqual(retry.status_code, 200, retry.data)
        self.assertEqual(retry.data["payment_id"], payment.id)
        self.assertTrue(retry.data["payment_exists"])
        create_gateway_order.assert_called_once()

    def test_customer_cannot_create_balance_payment_for_another_orders_appointment(self):
        other_order = Order.objects.create(
            customer=self.customer,
            address=self.address,
            status=Order.Status.AWAITING_ASSIGNMENT,
            subtotal=Decimal("100.00"),
            total_amount=Decimal("100.00"),
        )
        foreign_group = AppointmentGroup.objects.create(
            order=other_order,
            group_number=1,
            scheduled_at=timezone.now() + timedelta(days=2),
        )
        response = self.customer_client.post(
            "/api/v1/payments/create-order/",
            {
                "order_id": self.order.id,
                "stage": Payment.Stage.BALANCE,
                "appointment_group_id": foreign_group.id,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 404, response.data)
        self.assertFalse(
            Payment.objects.filter(
                order=self.order,
                stage=Payment.Stage.BALANCE,
                appointment_group=foreign_group,
            ).exists()
        )

