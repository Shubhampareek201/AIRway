from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Address, User
from apps.bookings.models import Booking
from apps.catalog.models import Category, Service
from apps.core.models import City, Zone
from apps.notifications.models import Notification
from apps.payments.models import Payment, PaymentRefund
from apps.payments.refunds import process_payment_refund


class RefundRetrySafetyTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            phone="+919876543298",
            password="test-password",
        )
        self.staff_user = User.objects.create_user(
            phone="+919876543297",
            password="test-password",
            is_staff=True,
        )
        city = City.objects.create(name="Refund City", state="Rajasthan")
        zone = Zone.objects.create(name="Refund Zone", city=city, is_active=True)
        address = Address.objects.create(
            user=self.customer,
            label="home",
            house_details="House 1",
            landmark="Main road",
            full_address="Refund test address",
            zone=zone,
        )
        category = Category.objects.create(title="Refund", slug="refund-safety")
        service = Service.objects.create(
            category=category,
            title="Refund test service",
            booking_mode=Service.BookingMode.SCHEDULED,
            pricing_type=Service.PricingType.FIXED,
            is_active=True,
        )
        booking = Booking.objects.create(
            customer=self.customer,
            address=address,
            service=service,
            booking_mode=Booking.BookingMode.SCHEDULED,
            scheduled_at=timezone.now() + timedelta(days=1),
            status=Booking.Status.CANCELLED,
            pricing_snapshot={"total": "1000.00"},
        )
        payment = Payment.objects.create(
            booking=booking,
            customer=self.customer,
            stage=Payment.Stage.LEGACY,
            amount=Decimal("1000.00"),
            method=Payment.Method.RAZORPAY,
            status=Payment.Status.PAID,
            razorpay_payment_id="pay_refund_safety",
        )
        self.refund = PaymentRefund.objects.create(
            payment=payment,
            booking=booking,
            amount=Decimal("1000.00"),
            wallet_amount=Decimal("0.00"),
            gateway_amount=Decimal("1000.00"),
            reason=PaymentRefund.Reason.CUSTOMER_CANCELLATION,
            status=PaymentRefund.Status.PENDING,
        )

    @patch("apps.payments.refunds.razorpay.Client", side_effect=RuntimeError("gateway timeout"))
    def test_uncertain_gateway_result_is_not_automatically_retried(self, gateway_client):
        first = process_payment_refund(self.refund.pk)
        self.assertEqual(first.status, PaymentRefund.Status.PROCESSING)
        self.assertIn("Manual reconciliation is required", first.failure_reason)

        second = process_payment_refund(self.refund.pk)
        self.assertEqual(second.status, PaymentRefund.Status.PROCESSING)
        gateway_client.assert_called_once()

        self.assertEqual(
            Notification.objects.filter(
                user=self.customer,
                title="Refund needs attention",
                data__refund_id=self.refund.pk,
            ).count(),
            1,
        )
        self.assertEqual(
            Notification.objects.filter(
                user=self.staff_user,
                title="Refund requires reconciliation",
                data__refund_id=self.refund.pk,
            ).count(),
            1,
        )
