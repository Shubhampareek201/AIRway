from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import Permission
from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.accounts.models import Address, User
from apps.bookings.models import Booking, BookingDispute, BookingExtraWork, Order, OrderItem
from apps.catalog.models import Category, Service
from apps.core.models import City, Zone
from apps.notifications.models import Notification
from apps.payments.admin import PaymentRefundAdmin
from apps.payments.models import Payment, PaymentRefund
from apps.payments.refunds import (
    _line_stage_amount,
    issue_admin_partial_refund,
    process_payment_refund,
    request_booking_refunds,
)
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
        finance_permission = Permission.objects.get(
            content_type__app_label="payments",
            codename="issue_partial_paymentrefund",
        )
        self.staff_user.user_permissions.add(finance_permission)
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


    def test_partial_refund_admin_requires_dedicated_finance_permission(self):
        model_admin = PaymentRefundAdmin(PaymentRefund, AdminSite())
        request = RequestFactory().get("/admin/payments/paymentrefund/add/")
        ordinary_staff = User.objects.create_user(
            phone="+919876543295",
            password="test-password",
            is_staff=True,
        )
        request.user = ordinary_staff

        self.assertFalse(model_admin.has_add_permission(request))
        permission = Permission.objects.get(
            content_type__app_label="payments",
            codename="issue_partial_paymentrefund",
        )
        ordinary_staff.user_permissions.add(permission)
        ordinary_staff = User.objects.get(pk=ordinary_staff.pk)
        request.user = ordinary_staff
        self.assertTrue(model_admin.has_add_permission(request))

    @patch("apps.payments.refunds.process_payment_refund")
    def test_admin_partial_refund_is_source_allocated_and_idempotent(self, process_refund):
        self.refund.delete()
        payment = Payment.objects.get(booking=self.booking)
        process_refund.side_effect = lambda refund_id: PaymentRefund.objects.get(pk=refund_id)

        first = issue_admin_partial_refund(
            payment=payment,
            booking=self.booking,
            amount="250.00",
            requested_by=self.staff_user,
            admin_note="Approved after service-quality review.",
            idempotency_key="admin-refund-request-001",
        )
        second = issue_admin_partial_refund(
            payment=payment,
            booking=self.booking,
            amount="250.00",
            requested_by=self.staff_user,
            admin_note="Approved after service-quality review.",
            idempotency_key="admin-refund-request-001",
        )

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(first.amount, Decimal("250.00"))
        self.assertEqual(first.wallet_amount, Decimal("0.00"))
        self.assertEqual(first.gateway_amount, Decimal("250.00"))
        self.assertEqual(first.requested_by, self.staff_user)
        self.assertEqual(PaymentRefund.objects.filter(payment=payment, booking=self.booking).count(), 1)

    @patch("apps.payments.refunds.process_payment_refund")
    def test_dispute_refund_requires_resolved_refund_case_and_records_link(self, process_refund):
        self.refund.delete()
        payment = Payment.objects.get(booking=self.booking)
        process_refund.side_effect = lambda refund_id: PaymentRefund.objects.get(pk=refund_id)
        dispute = BookingDispute.objects.create(
            booking=self.booking,
            raised_by=self.customer,
            raised_by_role="customer",
            category=BookingDispute.Category.SERVICE_QUALITY,
            description="Service quality issue requiring a partial refund.",
            requested_outcome=BookingDispute.RequestedOutcome.REFUND_REVIEW,
            status=BookingDispute.Status.RESOLVED,
            resolution_note="AIRway approved a partial refund after reviewing the evidence.",
            resolved_by=self.staff_user,
            resolved_at=timezone.now(),
        )

        refund = issue_admin_partial_refund(
            payment=payment,
            booking=self.booking,
            amount="200.00",
            requested_by=self.staff_user,
            admin_note="Partial refund approved under dispute case.",
            idempotency_key="dispute-refund-request-001",
            reason=PaymentRefund.Reason.DISPUTE_RESOLUTION,
            dispute=dispute,
        )

        self.assertEqual(refund.dispute_id, dispute.pk)
        self.assertEqual(refund.reason, PaymentRefund.Reason.DISPUTE_RESOLUTION)
        self.assertEqual(refund.amount, Decimal("200.00"))

    def test_dispute_refund_cannot_be_issued_without_resolved_case(self):
        self.refund.delete()
        payment = Payment.objects.get(booking=self.booking)
        dispute = BookingDispute.objects.create(
            booking=self.booking,
            raised_by=self.customer,
            raised_by_role="customer",
            category=BookingDispute.Category.PAYMENT,
            description="Refund requested.",
            requested_outcome=BookingDispute.RequestedOutcome.REFUND_REVIEW,
        )
        with self.assertRaisesMessage(ValueError, "resolved dispute"):
            issue_admin_partial_refund(
                payment=payment,
                booking=self.booking,
                amount="100.00",
                requested_by=self.staff_user,
                admin_note="Attempt before review.",
                idempotency_key="dispute-refund-request-002",
                reason=PaymentRefund.Reason.DISPUTE_RESOLUTION,
                dispute=dispute,
            )

    @patch("apps.payments.refunds.process_payment_refund")
    def test_admin_partial_refund_cannot_exceed_remaining_captured_amount(self, process_refund):
        self.refund.delete()
        payment = Payment.objects.get(booking=self.booking)
        issue_admin_partial_refund(
            payment=payment,
            booking=self.booking,
            amount="700.00",
            requested_by=self.staff_user,
            admin_note="First approved partial refund.",
            idempotency_key="admin-refund-request-002",
        )
        with self.assertRaisesMessage(ValueError, "remaining refundable amount"):
            issue_admin_partial_refund(
                payment=payment,
                booking=self.booking,
                amount="400.00",
                requested_by=self.staff_user,
                admin_note="Would exceed the captured amount.",
                idempotency_key="admin-refund-request-003",
            )

    @patch("apps.payments.refunds.process_payment_refund")
    def test_cancellation_refund_only_refunds_remaining_amount_after_admin_partial(self, process_refund):
        self.refund.delete()
        payment = Payment.objects.get(booking=self.booking)
        issue_admin_partial_refund(
            payment=payment,
            booking=self.booking,
            amount="250.00",
            requested_by=self.staff_user,
            admin_note="Partial refund before cancellation.",
            idempotency_key="admin-refund-request-004",
        )

        refunds = request_booking_refunds(self.booking)

        self.assertEqual(
            sum(refunds.values_list("amount", flat=True), Decimal("0.00")),
            Decimal("1000.00"),
        )
        cancellation_refund = refunds.get(reason=PaymentRefund.Reason.CUSTOMER_CANCELLATION)
        self.assertEqual(cancellation_refund.amount, Decimal("750.00"))
        self.assertEqual(cancellation_refund.gateway_amount, Decimal("750.00"))

    def test_repeated_cancellation_refund_call_retries_same_pending_record(self):
        self.refund.delete()
        refund_id = None
        with patch("apps.payments.refunds.process_payment_refund") as process_refund:
            first = request_booking_refunds(self.booking)
            refund_id = first.get().pk
            process_refund.assert_called_once_with(refund_id)
        with patch("apps.payments.refunds.process_payment_refund") as process_refund:
            second = request_booking_refunds(self.booking)
            process_refund.assert_called_once_with(refund_id)

        self.assertEqual(first.count(), 1)
        self.assertEqual(second.count(), 1)
        self.assertEqual(PaymentRefund.objects.filter(booking=self.booking).count(), 1)

    @patch("apps.payments.refunds.process_payment_refund")
    def test_admin_can_partially_refund_one_extra_work_line_from_balance_payment(self, process_refund):
        self.refund.delete()
        process_refund.side_effect = lambda refund_id: PaymentRefund.objects.get(pk=refund_id)
        worker_user = User.objects.create_user(
            phone="+919876543294",
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
            line_total=Decimal("800.00"),
        )
        extra_work = BookingExtraWork.objects.create(
            booking=self.booking,
            worker=worker,
            reason="Approved additional repair",
            line_items=[{
                "description": "Replacement part",
                "quantity": 1,
                "unit_price": "200.00",
                "line_total": "200.00",
            }],
            subtotal=Decimal("200.00"),
            tax_amount=Decimal("0.00"),
            total_amount=Decimal("200.00"),
            status=BookingExtraWork.Status.APPROVED,
            payment_choice=BookingExtraWork.PaymentChoice.ADD_TO_BALANCE,
            payment_status="paid",
        )
        payment = Payment.objects.create(
            order=order,
            customer=self.customer,
            stage=Payment.Stage.BALANCE,
            amount=Decimal("900.00"),
            wallet_amount=Decimal("100.00"),
            method=Payment.Method.RAZORPAY,
            status=Payment.Status.PAID,
            razorpay_payment_id="pay_group_balance_refund",
            raw_response={
                "service_allocation_v1": [
                    {
                        "allocation_type": "service",
                        "booking_id": self.booking.pk,
                        "order_item_id": order.items.get().pk,
                        "total": "800.00",
                        "wallet_amount": "80.00",
                        "gateway_amount": "720.00",
                    },
                    {
                        "allocation_type": "extra_work",
                        "booking_id": self.booking.pk,
                        "order_item_id": None,
                        "extra_work_id": extra_work.pk,
                        "total": "200.00",
                        "wallet_amount": "20.00",
                        "gateway_amount": "180.00",
                    },
                ],
            },
        )

        refund = issue_admin_partial_refund(
            payment=payment,
            booking=self.booking,
            extra_work=extra_work,
            amount="100.00",
            requested_by=self.staff_user,
            admin_note="Refund approved for the replacement part.",
            idempotency_key="admin-extra-work-refund-001",
        )

        self.assertEqual(refund.extra_work_id, extra_work.pk)
        self.assertEqual(refund.amount, Decimal("100.00"))
        self.assertEqual(refund.wallet_amount, Decimal("10.00"))
        self.assertEqual(refund.gateway_amount, Decimal("90.00"))
        with self.assertRaisesMessage(ValueError, "remaining refundable amount"):
            issue_admin_partial_refund(
                payment=payment,
                booking=self.booking,
                extra_work=extra_work,
                amount="150.00",
                requested_by=self.staff_user,
                admin_note="Would exceed this proposal's captured amount.",
                idempotency_key="admin-extra-work-refund-002",
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
