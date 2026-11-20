from django.test import TestCase
from unittest.mock import patch
from datetime import timedelta
from decimal import Decimal
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User, Address
from apps.catalog.models import Category, Service
from apps.core.models import City, Zone
from apps.workers.models import WorkerProfile
from apps.bookings.models import Booking, BookingAssignment, BookingExtraWork, Order, OrderItem
from apps.payments.models import Payment


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
        self.order = Order.objects.create(
            customer=self.customer, address=address,
            subtotal="1000.00", total_amount="1000.00",
        )
        OrderItem.objects.create(
            order=self.order, booking=self.booking, quantity=1,
            line_subtotal="1000.00", line_total="1000.00",
        )

    def _proposal(self):
        return BookingExtraWork.objects.create(
            booking=self.booking, worker=self.worker, reason="Additional cleaning required",
            line_items=[{"description": "Deep clean", "quantity": 1, "unit_price": "250.00", "line_total": "250.00"}],
            subtotal="250.00", tax_amount="0.00", total_amount="250.00",
            expires_at=timezone.now() + timedelta(hours=24),
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

    @patch("apps.payments.views.client.order.create")
    def test_separate_extra_work_payment_creates_idempotent_razorpay_order(self, create_gateway_order):
        create_gateway_order.return_value = {"id": "order_extra_work_test"}
        proposal = self._proposal()
        proposal.status = BookingExtraWork.Status.APPROVED
        proposal.payment_choice = BookingExtraWork.PaymentChoice.SEPARATE
        proposal.payment_status = "pending"
        proposal.approved_at = timezone.now()
        proposal.save()

        self.client.force_authenticate(user=self.customer)
        response = self.client.post(
            f"/api/v1/payments/extra-work/{proposal.pk}/create-order/",
            {"wallet_amount": "0.00"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["order_id"], "order_extra_work_test")
        payment = Payment.objects.get(extra_work=proposal)
        self.assertEqual(payment.stage, Payment.Stage.EXTRA_WORK)
        self.assertEqual(payment.amount, proposal.total_amount)
        self.assertEqual(payment.order_id, self.order.pk)
        create_gateway_order.assert_called_once()

    @patch("apps.payments.views.client.order.create")
    def test_add_to_balance_extra_work_is_included_in_final_balance(self, create_gateway_order):
        from apps.payments.views import create_or_get_order_payment

        create_gateway_order.return_value = {"id": "order_balance_with_extra"}
        self.booking.status = Booking.Status.COMPLETED
        self.booking.save(update_fields=["status"])
        self.order.metadata = {
            "payment_allocation_v1": {
                "percentage": "30",
                "advance_total": "300.00",
                "balance_total": "700.00",
                "advance": [{"order_item_id": self.booking.order_item.pk, "booking_id": self.booking.pk, "amount": "300.00"}],
                "balance": [{"order_item_id": self.booking.order_item.pk, "booking_id": self.booking.pk, "amount": "700.00"}],
            }
        }
        self.order.save(update_fields=["metadata", "updated_at"])
        Payment.objects.create(
            order=self.order, customer=self.customer,
            stage=Payment.Stage.ADVANCE, amount="300.00",
            status=Payment.Status.PAID,
        )
        proposal = self._proposal()
        proposal.status = BookingExtraWork.Status.APPROVED
        proposal.payment_choice = BookingExtraWork.PaymentChoice.ADD_TO_BALANCE
        proposal.payment_status = "pending"
        proposal.approved_at = timezone.now()
        proposal.save()

        payment, order_id, _ = create_or_get_order_payment(
            self.order, self.customer, stage=Payment.Stage.BALANCE,
        )
        self.assertEqual(order_id, "order_balance_with_extra")
        self.assertEqual(payment.amount, proposal.total_amount + Decimal("700.00"))
        allocations = payment.raw_response["service_allocation_v1"]
        extra_allocation = next(row for row in allocations if row["extra_work_id"] == proposal.pk)
        self.assertEqual(extra_allocation["total"], "250.00")
        self.assertEqual(extra_allocation["gateway_amount"], "250.00")

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
