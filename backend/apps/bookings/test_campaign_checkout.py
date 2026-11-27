from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Address, User
from apps.bookings.models import (
    CampaignRedemption,
    CustomerCampaign,
    CustomerCart,
    CartItem,
    Order,
)
from apps.catalog.models import Category, CityService, Service, ServiceVariant
from apps.core.models import City, Zone


class CustomerCampaignCheckoutTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.customer = User.objects.create_user(
            phone="+919876543922",
            password="password123",
            name="Campaign Checkout",
        )
        self.city = City.objects.create(
            name="Campaign Checkout City",
            state="Rajasthan",
        )
        self.zone = Zone.objects.create(
            name="Campaign Checkout Zone",
            city=self.city,
            is_active=True,
            coverage_polygon={
                "type": "Polygon",
                "coordinates": [[
                    [72.80, 19.00], [72.95, 19.00], [72.95, 19.20],
                    [72.80, 19.20], [72.80, 19.00],
                ]],
            },
        )
        self.address = Address.objects.create(
            user=self.customer,
            house_details="House 1",
            landmark="Near market",
            full_address="Campaign Checkout Address",
            latitude=19.0760,
            longitude=72.8777,
            zone=self.zone,
        )
        self.category = Category.objects.create(
            title="Campaign Checkout Category",
            slug="campaign-checkout-category",
        )
        self.service = Service.objects.create(
            category=self.category,
            title="Campaign Checkout Service",
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
        CityService.objects.create(
            city=self.city,
            service=self.service,
            is_active=True,
        )
        self.variant = ServiceVariant.objects.create(
            service=self.service,
            title="Standard",
            price=Decimal("1000.00"),
            mrp=Decimal("1200.00"),
            duration_minutes=60,
            worker_payout=Decimal("600.00"),
        )
        self.cart = CustomerCart.objects.create(
            customer=self.customer,
            address=self.address,
        )
        self.cart_item = CartItem.objects.create(
            cart=self.cart,
            service=self.service,
            variant=self.variant,
            quantity=1,
            pricing_snapshot={"line_total": "1180.00"},
        )
        self.client.force_authenticate(user=self.customer)

    def create_campaign(self, **overrides):
        values = {
            "name": "First booking ₹50 off",
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

    def checkout(self):
        return self.client.post(
            "/api/v1/bookings/cart/checkout/",
            {
                "items": [{
                    "cart_item_id": self.cart_item.pk,
                    "scheduled_at": (timezone.now() + timedelta(days=2)).isoformat(),
                }],
            },
            format="json",
        )

    def test_cart_preview_shows_discount_tax_total_and_advance_without_reserving_budget(self):
        campaign = self.create_campaign()

        response = self.client.get("/api/v1/bookings/cart/")

        self.assertEqual(response.status_code, 200, response.data)
        preview = response.data["campaign_preview"]
        campaign.refresh_from_db()
        self.assertEqual(preview["subtotal"], "1000.00")
        self.assertEqual(preview["discount_amount"], "50.00")
        self.assertEqual(preview["tax_amount"], "171.00")
        self.assertEqual(preview["total_amount"], "1121.00")
        self.assertEqual(preview["advance_amount"], "336.30")
        self.assertEqual(preview["balance_amount"], "784.70")
        self.assertEqual(preview["applied_campaigns"][0]["name"], campaign.name)
        self.assertEqual(campaign.budget_reserved, Decimal("0.00"))
        self.assertFalse(CampaignRedemption.objects.filter(campaign=campaign).exists())

    def test_campaign_is_reserved_and_discount_applies_before_tax_and_advance(self):
        campaign = self.create_campaign()

        response = self.checkout()

        self.assertEqual(response.status_code, 201, response.data)
        order = Order.objects.get(pk=response.data["order_id"])
        item = order.items.select_related("booking").get()
        redemption = CampaignRedemption.objects.get(campaign=campaign, order=order)
        campaign.refresh_from_db()

        self.assertEqual(order.subtotal, Decimal("1000.00"))
        self.assertEqual(order.discount_amount, Decimal("50.00"))
        self.assertEqual(order.tax_amount, Decimal("171.00"))
        self.assertEqual(order.total_amount, Decimal("1121.00"))
        self.assertEqual(item.line_subtotal, Decimal("1000.00"))
        self.assertEqual(item.tax_amount, Decimal("171.00"))
        self.assertEqual(item.line_total, Decimal("1121.00"))
        self.assertEqual(
            Decimal(item.pricing_snapshot["campaign_discount_amount"]),
            Decimal("50.00"),
        )
        self.assertEqual(
            Decimal(item.pricing_snapshot["discounted_subtotal"]),
            Decimal("950.00"),
        )
        self.assertEqual(
            Decimal(item.booking.worker_payout_snapshot["total"]),
            Decimal("600.00"),
        )
        self.assertEqual(campaign.budget_reserved, Decimal("50.00"))
        self.assertEqual(redemption.status, CampaignRedemption.Status.RESERVED)
        self.assertEqual(
            Decimal(order.metadata["payment_allocation_v1"]["advance_total"]),
            Decimal("336.30"),
        )
        self.assertEqual(
            Decimal(response.data["discount_amount"]),
            Decimal("50.00"),
        )

    def test_cancelling_last_unpaid_booking_releases_campaign_reservation(self):
        campaign = self.create_campaign()
        checkout_response = self.checkout()

        self.assertEqual(checkout_response.status_code, 201, checkout_response.data)
        order = Order.objects.get(pk=checkout_response.data["order_id"])
        booking = order.items.select_related("booking").get().booking
        redemption = CampaignRedemption.objects.get(campaign=campaign, order=order)
        self.assertEqual(redemption.status, CampaignRedemption.Status.RESERVED)

        cancel_response = self.client.post(
            f"/api/v1/bookings/{booking.pk}/cancel/",
            {"reason": "Customer cancelled before advance payment."},
            format="json",
        )

        self.assertEqual(cancel_response.status_code, 200, cancel_response.data)
        order.refresh_from_db()
        campaign.refresh_from_db()
        redemption.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(campaign.budget_reserved, Decimal("0.00"))
        self.assertEqual(campaign.budget_spent, Decimal("0.00"))
        self.assertEqual(redemption.status, CampaignRedemption.Status.RELEASED)
        self.assertEqual(
            redemption.release_reason,
            "Entire order cancelled before advance payment.",
        )

    def test_insufficient_campaign_budget_caps_checkout_discount(self):
        campaign = self.create_campaign(budget_amount=Decimal("20.00"))

        response = self.checkout()

        self.assertEqual(response.status_code, 201, response.data)
        order = Order.objects.get(pk=response.data["order_id"])
        campaign.refresh_from_db()
        self.assertEqual(order.discount_amount, Decimal("20.00"))
        self.assertEqual(campaign.budget_reserved, Decimal("20.00"))
