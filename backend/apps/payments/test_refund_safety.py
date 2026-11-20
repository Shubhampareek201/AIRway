from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Address, User
from apps.bookings.models import Booking, BookingExtraWork, Order, OrderItem
from apps.catalog.models import Category, Service
from apps.core.models import City, Zone
from apps.notifications.models import Notification
from apps.payments.models import Payment, PaymentRefund
from apps.payments.refunds import _line_stage_amount, process_payment_refund, request_booking_refunds
from apps.workers.models import WorkerProfile


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
        self.booking = Booking.objects.create(
            customer=self.customer,
            address=address,
            service=service,
            booking_mode=Booking.BookingMode.SCHEDULED,
            scheduled_at=timezone.now() + timedelta(days=1),
            status=Booking.Status.CANCELLED,
            pricing_snapshot={"total": "1000.00"},
        )
        payment = Payment.objects.create(
            booking=self.booking,
            customer=self.customer,
            stage=Payment.Stage.LEGACY,
            amount=Decimal("1000.00"),
            method=Payment.Method.RAZORPAY,
            status=Payment.Status.PAID,
            razorpay_payment_id="pay_refund_safety",
        )
        self.refund = PaymentRefund.objects.create(
            payment=payment,
            booking=self.booking,
            amount=Decimal("1000.00"),
            wallet_amount=Decimal("0.00"),
            gateway_amount=Decimal("1000.00"),
            reason=PaymentRefund.Reason.CUSTOMER_CANCELLATION,
            status=PaymentRefund.Status.PENDING,
        )


    @patch("apps.payments.refunds.process_payment_refund")
    def test_separately_paid_extra_work_is_included_in_booking_refund(self, process_refund):
        worker_user = User.objects.create_user(
            phone="+919876543296",
            password="test-password",
        )
        worker = WorkerProfile.objects.create(
            user=worker_user,
            status=WorkerProfile.Status.APPROVED,
        )
        order = Order.objects.create(
            customer=self.customer,
            address=self.booking.address,
            total_amount=Decimal("1000.00"),
        )
        OrderItem.objects.create(
            order=order,
            booking=self.booking,
            line_total=Decimal("1000.00"),
        )
        extra_work = BookingExtraWork.objects.create(
            booking=self.booking,
            worker=worker,
            reason="Additional repair requested during service",
            line_items=[{
                "description": "Replacement part",
                "quantity": 1,
                "unit_price": "100.00",
                "line_total": "100.00",
            }],
            subtotal=Decimal("100.00"),
            tax_amount=Decimal("0.00"),
            total_amount=Decimal("100.00"),
            status=BookingExtraWork.Status.APPROVED,
            payment_choice=BookingExtraWork.PaymentChoice.SEPARATE,
            payment_status="paid",
        )
        extra_payment = Payment.objects.create(
            order=order,
            extra_work=extra_work,
            customer=self.customer,
            stage=Payment.Stage.EXTRA_WORK,
            amount=Decimal("80.00"),
            wallet_amount=Decimal("20.00"),
            method=Payment.Method.RAZORPAY,
            status=Payment.Status.PAID,
            razorpay_payment_id="pay_extra_work_refund",
        )

        refunds = request_booking_refunds(self.booking)

        refund = refunds.get(payment=extra_payment)
        self.assertEqual(refund.amount, Decimal("100.00"))
        self.assertEqual(refund.wallet_amount, Decimal("20.00"))
        self.assertEqual(refund.gateway_amount, Decimal("80.00"))
        process_refund.assert_called_once_with(refund.pk)


    def test_balance_refund_allocation_includes_extra_work_added_to_balance(self):
        from types import SimpleNamespace
        from apps.bookings.models import OrderItem

        order = Order.objects.create(
            customer=self.customer,
            address=self.booking.address,
            total_amount=Decimal("1000.00"),
        )
        item = OrderItem.objects.create(
            order=order,
            booking=self.booking,
            line_total=Decimal("1000.00"),
        )
        payment = SimpleNamespace(
            extra_work_id=None,
            booking_id=None,
            order_id=order.pk,
            raw_response={
                "service_allocation_v1": [
                    {
                        "allocation_type": "service",
                        "booking_id": self.booking.pk,
                        "order_item_id": item.pk,
                        "total": "700.00",
                        "wallet_amount": "100.00",
                        "gateway_amount": "600.00",
                    },
                    {
                        "allocation_type": "extra_work",
                        "booking_id": self.booking.pk,
                        "order_item_id": None,
                        "total": "250.00",
                        "wallet_amount": "50.00",
                        "gateway_amount": "200.00",
                    },
                ],
            },
        )

        total, wallet, gateway, allocated_item = _line_stage_amount(payment, self.booking)

        self.assertEqual(total, Decimal("950.00"))
        self.assertEqual(wallet, Decimal("150.00"))
        self.assertEqual(gateway, Decimal("800.00"))
        self.assertEqual(allocated_item, item)

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
