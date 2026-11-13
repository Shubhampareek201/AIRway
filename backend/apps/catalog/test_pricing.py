from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from apps.catalog.models import Category, Service, ServiceVariant
from apps.catalog.pricing import service_pricing_ready


class ServicePricingReadinessTests(TestCase):
    def setUp(self):
        self.beauty = Category.objects.create(title="Beauty", slug="beauty")
        self.fixed_unpriced = Service.objects.create(
            category=self.beauty, title="Unpriced haircut",
            pricing_type=Service.PricingType.FIXED,
            booking_mode=Service.BookingMode.SCHEDULED,
        )
        self.fixed_priced = Service.objects.create(
            category=self.beauty, title="Priced haircut",
            pricing_type=Service.PricingType.FIXED,
            booking_mode=Service.BookingMode.SCHEDULED,
        )
        ServiceVariant.objects.create(
            service=self.fixed_priced, title="Standard",
            mrp=Decimal("250.00"), price=Decimal("200.00"),
        )
        self.quote_without_fee = Service.objects.create(
            category=self.beauty, title="Inspection without fee",
            pricing_type=Service.PricingType.QUOTE,
            booking_mode=Service.BookingMode.INSPECTION,
            visit_fee=Decimal("0.00"),
        )
        self.quote_with_fee = Service.objects.create(
            category=self.beauty, title="Inspection with fee",
            pricing_type=Service.PricingType.QUOTE,
            booking_mode=Service.BookingMode.INSPECTION,
            visit_fee=Decimal("99.00"),
        )
        self.per_unit = Service.objects.create(
            category=self.beauty, title="Per unit service",
            pricing_type=Service.PricingType.PER_UNIT,
            booking_mode=Service.BookingMode.SCHEDULED,
            unit_label="sq ft",
        )

    def test_pricing_readiness_requires_real_customer_price(self):
        self.assertFalse(service_pricing_ready(self.fixed_unpriced))
        self.assertTrue(service_pricing_ready(self.fixed_priced))
        self.assertFalse(service_pricing_ready(self.quote_without_fee))
        self.assertTrue(service_pricing_ready(self.quote_with_fee))
        self.assertFalse(service_pricing_ready(self.per_unit))

    def test_customer_service_api_hides_unpriced_and_unsupported_services(self):
        response = APIClient().get("/api/v1/catalog/services/?launch_only=true")
        self.assertEqual(response.status_code, 200, response.data)
        rows = response.data if isinstance(response.data, list) else response.data.get("results", [])
        ids = {row["id"] for row in rows}
        self.assertEqual(ids, {self.fixed_priced.id, self.quote_with_fee.id})

    def test_customer_categories_hide_roots_without_priced_services(self):
        response = APIClient().get("/api/v1/catalog/categories/?launch_only=true")
        self.assertEqual(response.status_code, 200, response.data)
        rows = response.data if isinstance(response.data, list) else response.data.get("results", [])
        self.assertEqual([row["slug"] for row in rows], ["beauty"])
