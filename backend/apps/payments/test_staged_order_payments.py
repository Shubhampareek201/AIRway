from decimal import Decimal
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import Address, User
from apps.bookings.models import Booking, Order, OrderItem
from apps.catalog.models import Category, Service
from apps.core.models import City, Zone
from apps.payments.models import Payment
from apps.payments.views import create_or_get_order_payment


@override_settings(ORDER_ADVANCE_PERCENTAGE=30)
class StagedOrderPaymentServiceTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            phone="+919876543211", password="password123"
        )
        city = City.objects.create(name="Jaipur", state="Rajasthan")
        zone = Zone.objects.create(name="Payment Test Zone", city=city, is_active=True)
        self.address = Address.objects.create(
            user=self.customer,
            label="home",
            house_details="House 1",
            landmark="Near test landmark",
            full_address="Payment test address, Jaipur",
            latitude=26.9124,
            longitude=75.7873,
            zone=zone,
        )
        category = Category.objects.create(
            title="Payment Test", slug="payment-test"
        )
        self.service = Service.objects.create(
            category=category,
            title="Payment Test Service",
            booking_mode=Service.BookingMode.SCHEDULED,
            pricing_type=Service.PricingType.FIXED,
            is_active=True,
        )
        self.booking = Booking.objects.create(
            customer=self.customer,
            address=self.address,
            service=self.service,
            scheduled_at=timezone.now() + timedelta(days=1),
            status=Booking.Status.PENDING,
            pricing_snapshot={"total": "1000.00"},
        )
        self.order = Order.objects.create(
            customer=self.customer,
            address=self.address,
            status=Order.Status.AWAITING_ASSIGNMENT,
            subtotal=Decimal("1000.00"),
            total_amount=Decimal("1000.00"),
        )
        self.item = OrderItem.objects.create(
            order=self.order,
            booking=self.booking,
            quantity=1,
            line_total=Decimal("1000.00"),
        )

    @patch("apps.payments.views.client.order.create")
    def test_advance_is_30_percent_and_balance_is_locked_until_advance_and_completion(self, create_gateway_order):
        create_gateway_order.return_value = {"id": "order_advance_test"}
        advance, gateway_id, existed = create_or_get_order_payment(
            self.order, self.customer
        )
        self.assertFalse(existed)
        self.assertEqual(gateway_id, "order_advance_test")
        self.assertEqual(advance.stage, Payment.Stage.ADVANCE)
        self.assertEqual(advance.amount, Decimal("300.00"))
        self.assertEqual(
            self.order.metadata["payment_allocation_v1"]["balance_total"],
            "700.00",
        )

        with self.assertRaisesMessage(ValueError, "advance payment must be completed first"):
            create_or_get_order_payment(
                self.order,
                self.customer,
                stage=Payment.Stage.BALANCE,
            )

        advance.status = Payment.Status.PAID
        advance.save(update_fields=["status"])
        self.booking.status = Booking.Status.COMPLETED
        self.booking.completed_at = timezone.now()
        self.booking.save(update_fields=["status", "completed_at"])

        create_gateway_order.return_value = {"id": "order_balance_test"}
        balance, balance_gateway_id, balance_existed = create_or_get_order_payment(
            self.order,
            self.customer,
            stage=Payment.Stage.BALANCE,
        )
        self.assertFalse(balance_existed)
        self.assertEqual(balance_gateway_id, "order_balance_test")
        self.assertEqual(balance.stage, Payment.Stage.BALANCE)
        self.assertEqual(balance.amount, Decimal("700.00"))

    @patch("apps.payments.views.client.order.create")
    def test_balance_is_rejected_until_every_active_service_is_completed(self, create_gateway_order):
        create_gateway_order.return_value = {"id": "order_advance_pending"}
        advance, _, _ = create_or_get_order_payment(self.order, self.customer)
        advance.status = Payment.Status.PAID
        advance.save(update_fields=["status"])
        with self.assertRaisesMessage(ValueError, "every active service is completed"):
            create_or_get_order_payment(
                self.order,
                self.customer,
                stage=Payment.Stage.BALANCE,
            )
