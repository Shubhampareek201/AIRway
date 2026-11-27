from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Address, User
from apps.bookings.campaigns import (
    evaluate_customer_campaigns, reserve_customer_campaigns,
    redeem_customer_campaigns_for_order, release_customer_campaigns_for_order,
)
from apps.bookings.models import CampaignRedemption, CustomerCampaign, Order
from apps.catalog.models import Category, Service
from apps.core.models import City, Zone
from apps.payments.models import Payment


class CustomerCampaignCalculatorTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            phone="+919876543911", password="password123", name="Campaign Calculator"
        )
        self.city = City.objects.create(name="Campaign Calculator City", state="Rajasthan")
        self.zone = Zone.objects.create(
            name="Campaign Calculator Zone", city=self.city, is_active=True
        )
        self.category = Category.objects.create(
            title="Campaign Calculator Category", slug="campaign-calculator-category"
        )
        self.service = Service.objects.create(
            category=self.category,
            title="Campaign Calculator Service",
            booking_mode=Service.BookingMode.SCHEDULED,
            pricing_type=Service.PricingType.FIXED,
            tax_rate=Decimal("18.00"),
            estimated_gateway_fee_percent=Decimal("2.00"),
            discount_reserve_percent=Decimal("0.00"),
            rewards_reserve_percent=Decimal("0.00"),
            refund_reserve_percent=Decimal("0.00"),
            rework_reserve_percent=Decimal("0.00"),
            other_variable_cost_per_booking=Decimal("0.00"),
            minimum_contribution_floor=Decimal("10.00"),
            target_contribution_margin_percent=Decimal("0.00"),
            is_active=True,
        )
        self.address = Address.objects.create(
            user=self.customer,
            house_details="House 1",
            landmark="Near market",
            full_address="Campaign Calculator Address",
            zone=self.zone,
        )
        self.order = Order.objects.create(
            customer=self.customer,
            address=self.address,
            subtotal=Decimal("1000.00"),
            total_amount=Decimal("1180.00"),
        )

    def make_campaign(self, **overrides):
        values = {
            "name": "Calculator offer",
            "is_active": True,
            "booking_sequence": CustomerCampaign.BookingSequence.FIRST,
            "discount_type": CustomerCampaign.DiscountType.FIXED,
            "discount_value": Decimal("50.00"),
            "minimum_subtotal": Decimal("0.00"),
            "budget_amount": Decimal("1000.00"),
            "max_redemptions_per_customer": 1,
        }
        values.update(overrides)
        return CustomerCampaign.objects.create(**values)

    def evaluate(self, subtotal="1000.00", payout="300.00", now=None):
        return evaluate_customer_campaigns(
            customer=self.customer,
            zone=self.zone,
            now=now,
            lines=[{
                "key": "line-1",
                "service": self.service,
                "subtotal": Decimal(subtotal),
                "worker_payout": Decimal(payout),
            }],
        )

    def test_first_paid_booking_campaign_applies_fixed_fifty(self):
        self.make_campaign()
        result = self.evaluate()

        self.assertEqual(result["discount_amount"], Decimal("50.00"))
        self.assertEqual(result["line_discounts"]["line-1"], Decimal("50.00"))
        self.assertEqual(len(result["applied_campaigns"]), 1)

    def test_second_booking_percentage_discount_is_capped_at_seventy_five(self):
        Payment.objects.create(
            order=self.order,
            customer=self.customer,
            stage=Payment.Stage.ADVANCE,
            amount=Decimal("354.00"),
            method=Payment.Method.RAZORPAY,
            status=Payment.Status.PAID,
            razorpay_payment_id="campaign-second-booking",
        )
        self.make_campaign(
            name="Second booking",
            booking_sequence=CustomerCampaign.BookingSequence.SECOND,
            discount_type=CustomerCampaign.DiscountType.PERCENTAGE,
            discount_value=Decimal("10.00"),
            max_discount_amount=Decimal("75.00"),
        )

        result = self.evaluate()

        self.assertEqual(result["discount_amount"], Decimal("75.00"))

    def test_pending_advance_does_not_count_as_paid_booking(self):
        Payment.objects.create(
            order=self.order,
            customer=self.customer,
            stage=Payment.Stage.ADVANCE,
            amount=Decimal("354.00"),
            method=Payment.Method.RAZORPAY,
            status=Payment.Status.PENDING,
            razorpay_order_id="campaign-pending-advance",
        )
        self.make_campaign()

        self.assertEqual(self.evaluate()["discount_amount"], Decimal("50.00"))

    def test_first_booking_campaign_does_not_apply_after_paid_advance(self):
        Payment.objects.create(
            order=self.order,
            customer=self.customer,
            stage=Payment.Stage.ADVANCE,
            amount=Decimal("354.00"),
            method=Payment.Method.RAZORPAY,
            status=Payment.Status.PAID,
            razorpay_payment_id="campaign-first-already-paid",
        )
        self.make_campaign()

        self.assertEqual(self.evaluate()["discount_amount"], Decimal("0.00"))

    def test_campaign_respects_validity_window(self):
        now = timezone.now()
        self.make_campaign(
            starts_at=now + timedelta(minutes=5),
            ends_at=now + timedelta(hours=1),
        )

        self.assertEqual(self.evaluate(now=now)["discount_amount"], Decimal("0.00"))

    def test_campaign_respects_minimum_order_subtotal(self):
        self.make_campaign(minimum_subtotal=Decimal("1001.00"))

        self.assertEqual(self.evaluate()["discount_amount"], Decimal("0.00"))

    def test_campaign_respects_service_and_zone_filters(self):
        other_city = City.objects.create(name="Other Campaign City", state="Rajasthan")
        other_zone = Zone.objects.create(name="Other Campaign Zone", city=other_city)
        campaign = self.make_campaign()
        campaign.eligible_services.add(self.service)
        campaign.eligible_zones.add(other_zone)

        self.assertEqual(self.evaluate()["discount_amount"], Decimal("0.00"))

    def test_campaign_budget_limits_discount(self):
        self.make_campaign(
            budget_amount=Decimal("100.00"),
            budget_reserved=Decimal("20.00"),
            budget_spent=Decimal("60.00"),
        )

        self.assertEqual(self.evaluate()["discount_amount"], Decimal("20.00"))

    def test_exhausted_campaign_budget_prevents_discount(self):
        self.make_campaign(
            budget_amount=Decimal("100.00"),
            budget_reserved=Decimal("50.00"),
            budget_spent=Decimal("50.00"),
        )

        self.assertEqual(self.evaluate()["discount_amount"], Decimal("0.00"))

    def test_reserved_redemption_consumes_per_customer_limit(self):
        campaign = self.make_campaign()
        CampaignRedemption.objects.create(
            campaign=campaign,
            customer=self.customer,
            order=self.order,
            discount_amount=Decimal("50.00"),
            status=CampaignRedemption.Status.RESERVED,
        )

        self.assertEqual(self.evaluate()["discount_amount"], Decimal("0.00"))

    def test_missing_finance_assumption_fails_closed(self):
        self.service.estimated_gateway_fee_percent = None
        self.service.save(update_fields=["estimated_gateway_fee_percent", "updated_at"])
        self.make_campaign()

        self.assertEqual(self.evaluate()["discount_amount"], Decimal("0.00"))

    def test_contribution_floor_prevents_loss_making_discount(self):
        self.make_campaign()

        self.assertEqual(
            self.evaluate(subtotal="500.00", payout="490.00")["discount_amount"],
            Decimal("0.00"),
        )



    def test_advance_payment_redeems_campaign_and_moves_budget_to_spent(self):
        campaign = self.make_campaign(budget_amount=Decimal("100.00"))
        campaign.budget_reserved = Decimal("50.00")
        campaign.save(update_fields=["budget_reserved", "updated_at"])
        redemption = CampaignRedemption.objects.create(
            campaign=campaign,
            customer=self.customer,
            order=self.order,
            discount_amount=Decimal("50.00"),
            status=CampaignRedemption.Status.RESERVED,
        )

        self.assertEqual(redeem_customer_campaigns_for_order(order=self.order), 1)
        self.assertEqual(redeem_customer_campaigns_for_order(order=self.order), 0)

        campaign.refresh_from_db()
        redemption.refresh_from_db()
        self.assertEqual(campaign.budget_reserved, Decimal("0.00"))
        self.assertEqual(campaign.budget_spent, Decimal("50.00"))
        self.assertEqual(redemption.status, CampaignRedemption.Status.REDEEMED)
        self.assertIsNotNone(redemption.redeemed_at)

    def test_cancelled_unpaid_order_releases_reserved_campaign_budget_once(self):
        campaign = self.make_campaign(budget_amount=Decimal("100.00"))
        campaign.budget_reserved = Decimal("50.00")
        campaign.save(update_fields=["budget_reserved", "updated_at"])
        redemption = CampaignRedemption.objects.create(
            campaign=campaign,
            customer=self.customer,
            order=self.order,
            discount_amount=Decimal("50.00"),
            status=CampaignRedemption.Status.RESERVED,
        )

        self.assertEqual(
            release_customer_campaigns_for_order(
                order=self.order, reason="Order cancelled before advance."
            ),
            1,
        )
        self.assertEqual(
            release_customer_campaigns_for_order(order=self.order, reason="duplicate"),
            0,
        )

        campaign.refresh_from_db()
        redemption.refresh_from_db()
        self.assertEqual(campaign.budget_reserved, Decimal("0.00"))
        self.assertEqual(campaign.budget_spent, Decimal("0.00"))
        self.assertEqual(redemption.status, CampaignRedemption.Status.RELEASED)
        self.assertEqual(redemption.release_reason, "Order cancelled before advance.")

    def test_unpaid_order_campaign_release_is_blocked_after_advance_capture(self):
        from apps.bookings.campaigns import release_unpaid_customer_campaigns_for_order
        from apps.bookings.models import CampaignRedemption
        from apps.payments.models import Payment

        campaign = self.make_campaign(budget_amount=Decimal("100.00"))
        campaign.budget_reserved = Decimal("50.00")
        campaign.save(update_fields=["budget_reserved", "updated_at"])
        redemption = CampaignRedemption.objects.create(
            campaign=campaign,
            customer=self.customer,
            order=self.order,
            discount_amount=Decimal("50.00"),
            status=CampaignRedemption.Status.RESERVED,
        )
        Payment.objects.create(
            order=self.order,
            customer=self.customer,
            stage=Payment.Stage.ADVANCE,
            amount=Decimal("300.00"),
            method=Payment.Method.RAZORPAY,
            status=Payment.Status.PAID,
            razorpay_payment_id="captured-advance-protects-campaign",
        )

        self.assertEqual(
            release_unpaid_customer_campaigns_for_order(
                order=self.order, reason="Order cancelled"
            ),
            0,
        )
        campaign.refresh_from_db()
        redemption.refresh_from_db()
        self.assertEqual(campaign.budget_reserved, Decimal("50.00"))
        self.assertEqual(redemption.status, CampaignRedemption.Status.RESERVED)

    def test_checkout_reservation_increments_budget_and_creates_redemption(self):
        campaign = self.make_campaign()
        result = reserve_customer_campaigns(
            customer=self.customer,
            order=self.order,
            zone=self.zone,
            lines=[{
                "key": "line-1",
                "service": self.service,
                "subtotal": Decimal("1000.00"),
                "worker_payout": Decimal("300.00"),
            }],
        )

        campaign.refresh_from_db()
        redemption = CampaignRedemption.objects.get(
            campaign=campaign, order=self.order
        )
        self.assertEqual(result["discount_amount"], Decimal("50.00"))
        self.assertEqual(campaign.budget_reserved, Decimal("50.00"))
        self.assertEqual(redemption.discount_amount, Decimal("50.00"))
        self.assertEqual(redemption.status, CampaignRedemption.Status.RESERVED)
