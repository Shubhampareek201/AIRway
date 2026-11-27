from decimal import Decimal
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import Address, User
from apps.bookings.models import AppointmentGroup, Booking, Order, OrderItem
from apps.catalog.models import Category, Service, ServiceVariant
from apps.core.models import City, Zone
from apps.workers.models import WorkerProfile, WorkerService, WorkerZone, WorkerSchedule
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
        self.variant = ServiceVariant.objects.create(
            service=self.service,
            title="Standard",
            mrp=Decimal("1000.00"),
            price=Decimal("1000.00"),
            worker_payout=Decimal("200.00"),
        )
        self.booking = Booking.objects.create(
            customer=self.customer,
            address=self.address,
            service=self.service,
            variant=self.variant,
            scheduled_at=timezone.now() + timedelta(days=1),
            status=Booking.Status.PENDING,
            pricing_snapshot={"total": "1000.00"},
            worker_payout_snapshot={"pricing_model": "fixed_service_payout_v1", "total": "200.00", "configured": True, "currency": "INR"},
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

        # Advance checkout must prove a real worker can cover the selected slot.
        worker_user = User.objects.create_user(
            phone="+919876543212", password="password123"
        )
        worker = WorkerProfile.objects.create(
            user=worker_user,
            status=WorkerProfile.Status.APPROVED,
            is_online=True,
            commission_rate=Decimal("20.00"),
        )
        WorkerService.objects.create(worker=worker, service=self.service)
        WorkerZone.objects.create(worker=worker, zone=zone)
        # This shared fixture covers bookings on any weekday; each test can
        # still verify slot availability without depending on the calendar day.
        WorkerSchedule.objects.bulk_create([
            WorkerSchedule(
                worker=worker,
                weekday=weekday,
                is_active=True,
                start_time="00:00",
                end_time="23:59",
            )
            for weekday in range(7)
        ])

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
    @patch("apps.bookings.dispatcher.DispatcherService.dispatch_order")
    def test_advance_payment_redeems_campaign_reservation(self, dispatch_order, create_gateway_order):
        from apps.bookings.models import CustomerCampaign, CampaignRedemption
        from apps.payments.verify_view import _process_verified_payment

        create_gateway_order.return_value = {"id": "order_campaign_advance"}
        advance, gateway_order_id, _ = create_or_get_order_payment(
            self.order, self.customer
        )
        campaign = CustomerCampaign.objects.create(
            name="Payment lifecycle offer",
            is_active=True,
            booking_sequence=CustomerCampaign.BookingSequence.FIRST,
            discount_type=CustomerCampaign.DiscountType.FIXED,
            discount_value=Decimal("50.00"),
            minimum_subtotal=Decimal("0.00"),
            budget_amount=Decimal("100.00"),
            budget_reserved=Decimal("50.00"),
            max_redemptions_per_customer=1,
        )
        redemption = CampaignRedemption.objects.create(
            campaign=campaign,
            customer=self.customer,
            order=self.order,
            discount_amount=Decimal("50.00"),
            status=CampaignRedemption.Status.RESERVED,
        )

        response = _process_verified_payment(
            advance, "pay_campaign_advance", gateway_order_id, self.customer, "test"
        )

        self.assertEqual(response.status_code, 200)
        advance.refresh_from_db()
        campaign.refresh_from_db()
        redemption.refresh_from_db()
        self.assertEqual(advance.status, Payment.Status.PAID)
        self.assertEqual(campaign.budget_reserved, Decimal("0.00"))
        self.assertEqual(campaign.budget_spent, Decimal("50.00"))
        self.assertEqual(redemption.status, CampaignRedemption.Status.REDEEMED)
        self.assertIsNotNone(redemption.redeemed_at)
        dispatch_order.assert_called_once()

    @patch("apps.payments.views.client.order.create")
    def test_completed_appointment_group_can_pay_balance_while_another_group_is_pending(self, create_gateway_order):
        create_gateway_order.side_effect = [
            {"id": "order_group_advance"},
            {"id": "order_group_a_balance"},
            {"id": "order_group_b_balance"},
        ]
        second_booking = Booking.objects.create(
            customer=self.customer,
            address=self.address,
            service=self.service,
            scheduled_at=timezone.now() + timedelta(days=2),
            status=Booking.Status.PENDING,
            pricing_snapshot={"total": "1000.00"},
        )
        second_item = OrderItem.objects.create(
            order=self.order,
            booking=second_booking,
            quantity=1,
            line_total=Decimal("1000.00"),
        )
        self.order.subtotal = Decimal("2000.00")
        self.order.total_amount = Decimal("2000.00")
        self.order.save(update_fields=["subtotal", "total_amount", "updated_at"])
        group_a = AppointmentGroup.objects.create(
            order=self.order, group_number=1, scheduled_at=self.booking.scheduled_at
        )
        group_b = AppointmentGroup.objects.create(
            order=self.order, group_number=2, scheduled_at=second_booking.scheduled_at
        )
        self.booking.appointment_group = group_a
        self.booking.save(update_fields=["appointment_group", "updated_at"])
        second_booking.appointment_group = group_b
        second_booking.save(update_fields=["appointment_group", "updated_at"])

        advance, _, _ = create_or_get_order_payment(self.order, self.customer)
        advance.status = Payment.Status.PAID
        advance.save(update_fields=["status"])

        self.booking.status = Booking.Status.COMPLETED
        self.booking.completed_at = timezone.now()
        self.booking.save(update_fields=["status", "completed_at"])

        group_a_balance, group_a_order_id, _ = create_or_get_order_payment(
            self.order,
            self.customer,
            stage=Payment.Stage.BALANCE,
            appointment_group=group_a,
        )
        self.assertEqual(group_a_order_id, "order_group_a_balance")
        self.assertEqual(group_a_balance.appointment_group_id, group_a.pk)
        self.assertEqual(group_a_balance.amount, Decimal("700.00"))

        with self.assertRaisesMessage(ValueError, "every active service in the appointment"):
            create_or_get_order_payment(
                self.order,
                self.customer,
                stage=Payment.Stage.BALANCE,
                appointment_group=group_b,
            )

        from apps.payments.verify_view import _process_verified_payment
        result = _process_verified_payment(
            group_a_balance,
            "pay_group_a",
            group_a_order_id,
            self.customer,
            "test",
        )
        self.assertEqual(result.status_code, 200)
        group_a_balance.refresh_from_db()
        self.assertEqual(group_a_balance.status, Payment.Status.PAID)
        self.order.refresh_from_db()
        self.assertNotEqual(self.order.status, Order.Status.PAID)

        second_booking.status = Booking.Status.COMPLETED
        second_booking.completed_at = timezone.now()
        second_booking.save(update_fields=["status", "completed_at"])
        group_b_balance, group_b_order_id, _ = create_or_get_order_payment(
            self.order,
            self.customer,
            stage=Payment.Stage.BALANCE,
            appointment_group=group_b,
        )
        self.assertEqual(group_b_order_id, "order_group_b_balance")
        self.assertEqual(group_b_balance.appointment_group_id, group_b.pk)
        self.assertEqual(group_b_balance.amount, Decimal("700.00"))

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


class GatewayFeeSnapshotTests(TestCase):
    def test_records_confirmed_gateway_fee_and_fee_gst_in_rupees(self):
        from types import SimpleNamespace
        from apps.payments.verify_view import _record_gateway_fee_snapshot

        payment = SimpleNamespace(
            amount=Decimal("300.00"), gateway_fee_amount=None,
            gateway_fee_tax_amount=None, gateway_fee_recorded_at=None,
        )
        self.assertTrue(_record_gateway_fee_snapshot(payment, 590, 106))
        self.assertEqual(payment.gateway_fee_amount, Decimal("5.90"))
        self.assertEqual(payment.gateway_fee_tax_amount, Decimal("1.06"))
        recorded_at = payment.gateway_fee_recorded_at
        self.assertIsNotNone(recorded_at)
        self.assertFalse(_record_gateway_fee_snapshot(payment, 999, 999))
        self.assertEqual(payment.gateway_fee_amount, Decimal("5.90"))
        self.assertEqual(payment.gateway_fee_tax_amount, Decimal("1.06"))
        self.assertEqual(payment.gateway_fee_recorded_at, recorded_at)

    def test_missing_gateway_fee_is_not_misreported_as_zero(self):
        from types import SimpleNamespace
        from apps.payments.verify_view import _record_gateway_fee_snapshot

        payment = SimpleNamespace(
            amount=Decimal("300.00"), gateway_fee_amount=None,
            gateway_fee_tax_amount=None, gateway_fee_recorded_at=None,
        )
        self.assertFalse(_record_gateway_fee_snapshot(payment, None, None))
        self.assertIsNone(payment.gateway_fee_amount)
        self.assertIsNone(payment.gateway_fee_tax_amount)

    def test_wallet_only_payment_records_zero_gateway_cost(self):
        from types import SimpleNamespace
        from apps.payments.verify_view import _record_gateway_fee_snapshot

        payment = SimpleNamespace(
            amount=Decimal("0.00"), gateway_fee_amount=None,
            gateway_fee_tax_amount=None, gateway_fee_recorded_at=None,
        )
        self.assertTrue(_record_gateway_fee_snapshot(payment))
        self.assertEqual(payment.gateway_fee_amount, Decimal("0.00"))
        self.assertEqual(payment.gateway_fee_tax_amount, Decimal("0.00"))
