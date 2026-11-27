from datetime import timedelta
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Address, User
from apps.bookings.models import CampaignRedemption, CustomerCampaign, Order
from apps.catalog.models import Category, Service
from apps.core.models import City, Zone


class CustomerCampaignModelTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            phone="+919876543901", password="password123", name="Campaign Customer"
        )
        self.city = City.objects.create(name="Campaign Test City", state="Rajasthan")
        self.zone = Zone.objects.create(
            name="Campaign Test Zone", city=self.city, is_active=True
        )
        self.category = Category.objects.create(
            title="Campaign Test Category", slug="campaign-test-category"
        )
        self.service = Service.objects.create(
            category=self.category,
            title="Campaign Test Service",
            booking_mode=Service.BookingMode.SCHEDULED,
            pricing_type=Service.PricingType.FIXED,
            is_active=True,
        )
        self.address = Address.objects.create(
            user=self.customer,
            house_details="House 1",
            landmark="Near test market",
            full_address="Campaign Test Address",
            zone=self.zone,
        )
        self.order = Order.objects.create(
            customer=self.customer,
            address=self.address,
            subtotal=Decimal("500.00"),
            total_amount=Decimal("590.00"),
        )

    def make_campaign(self, **overrides):
        values = {
            "name": "First booking offer",
            "booking_sequence": CustomerCampaign.BookingSequence.FIRST,
            "discount_type": CustomerCampaign.DiscountType.FIXED,
            "discount_value": Decimal("50.00"),
            "budget_amount": Decimal("1000.00"),
        }
        values.update(overrides)
        return CustomerCampaign.objects.create(**values)

    def test_campaign_defaults_and_remaining_budget(self):
        campaign = self.make_campaign(
            budget_reserved=Decimal("100.00"),
            budget_spent=Decimal("250.00"),
        )

        self.assertFalse(campaign.is_active)
        self.assertEqual(campaign.max_redemptions_per_customer, 1)
        self.assertEqual(campaign.remaining_budget, Decimal("650.00"))

    def test_service_and_zone_eligibility_can_be_configured(self):
        campaign = self.make_campaign()
        campaign.eligible_services.add(self.service)
        campaign.eligible_zones.add(self.zone)

        self.assertQuerySetEqual(
            campaign.eligible_services.all(), [self.service], transform=lambda obj: obj
        )
        self.assertQuerySetEqual(
            campaign.eligible_zones.all(), [self.zone], transform=lambda obj: obj
        )

    def test_percentage_discount_above_one_hundred_is_rejected(self):
        campaign = self.make_campaign(
            discount_type=CustomerCampaign.DiscountType.PERCENTAGE,
            discount_value=Decimal("100.01"),
        )

        with self.assertRaises(ValidationError):
            campaign.full_clean()

    def test_campaign_end_must_be_after_start(self):
        start = timezone.now()
        campaign = self.make_campaign(
            starts_at=start,
            ends_at=start - timedelta(minutes=1),
        )

        with self.assertRaises(ValidationError):
            campaign.full_clean()

    def test_reserved_and_spent_budget_cannot_exceed_budget(self):
        campaign = self.make_campaign(
            budget_reserved=Decimal("700.00"),
            budget_spent=Decimal("400.00"),
        )

        with self.assertRaises(ValidationError):
            campaign.full_clean()

    def test_redemption_defaults_to_reserved_and_is_order_level(self):
        campaign = self.make_campaign()
        redemption = CampaignRedemption.objects.create(
            campaign=campaign,
            customer=self.customer,
            order=self.order,
            discount_amount=Decimal("50.00"),
        )

        self.assertEqual(redemption.status, CampaignRedemption.Status.RESERVED)
        self.assertEqual(campaign.redemptions.count(), 1)
        self.assertEqual(self.order.campaign_redemptions.get(), redemption)

    def test_campaign_cannot_be_redeemed_twice_for_same_order(self):
        campaign = self.make_campaign()
        CampaignRedemption.objects.create(
            campaign=campaign,
            customer=self.customer,
            order=self.order,
            discount_amount=Decimal("50.00"),
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CampaignRedemption.objects.create(
                    campaign=campaign,
                    customer=self.customer,
                    order=self.order,
                    discount_amount=Decimal("25.00"),
                )

    def test_redemption_discount_must_be_positive(self):
        campaign = self.make_campaign()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CampaignRedemption.objects.create(
                    campaign=campaign,
                    customer=self.customer,
                    order=self.order,
                    discount_amount=Decimal("0.00"),
                )
