from decimal import Decimal
import json
from urllib.parse import urlencode

from django.test import TestCase
from rest_framework.test import APIClient

from apps.catalog.models import Category, FormField, Service, ServiceVariant
from apps.catalog.pricing import service_pricing_ready
from apps.catalog.management.commands.configure_launch_catalogue import _package_price, _service_base_price


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

    def test_home_cleaning_sofa_and_carpet_have_indicative_starting_prices(self):
        self.assertEqual(
            _service_base_price("Home Cleaning", type("ServiceStub", (), {"title": "Sofa & Upholstery Cleaning"})()),
            Decimal("399"),
        )
        self.assertEqual(
            _service_base_price("Home Cleaning", type("ServiceStub", (), {"title": "Carpet & Rug Cleaning"})()),
            Decimal("299"),
        )
        self.assertEqual(
            _package_price("Home Cleaning", "Sofa & Upholstery Cleaning", "Deep Sofa Cleaning", {}),
            Decimal("599"),
        )
        self.assertEqual(
            _package_price("Home Cleaning", "Carpet & Rug Cleaning", "Premium Carpet Cleaning", {}),
            Decimal("699"),
        )

    def test_pricing_readiness_requires_real_customer_price(self):
        self.assertFalse(service_pricing_ready(self.fixed_unpriced))
        self.assertTrue(service_pricing_ready(self.fixed_priced))
        self.assertFalse(service_pricing_ready(self.quote_without_fee))
        self.assertTrue(service_pricing_ready(self.quote_with_fee))
        self.assertFalse(service_pricing_ready(self.per_unit))

    def test_per_unit_service_becomes_bookable_when_a_unit_rate_variant_exists(self):
        self.assertFalse(service_pricing_ready(self.per_unit))
        ServiceVariant.objects.create(
            service=self.per_unit, title="Rate per sq ft",
            mrp=Decimal("18.00"), price=Decimal("15.00"),
        )
        self.assertTrue(service_pricing_ready(self.per_unit))

    def test_customer_service_api_hides_unpriced_and_unsupported_services(self):
        response = APIClient().get("/api/v1/catalog/services/?launch_only=true")
        self.assertEqual(response.status_code, 200, response.data)
        rows = response.data if isinstance(response.data, list) else response.data.get("results", [])
        ids = {row["id"] for row in rows}
        self.assertEqual(ids, {self.fixed_priced.id, self.quote_with_fee.id})


    def test_worker_catalogue_can_still_see_unpriced_services_for_enrolment(self):
        response = APIClient().get(
            "/api/v1/catalog/services/?launch_only=true&for_worker=true"
        )
        self.assertEqual(response.status_code, 200, response.data)
        rows = response.data if isinstance(response.data, list) else response.data.get("results", [])
        ids = {row["id"] for row in rows}
        self.assertIn(self.fixed_unpriced.id, ids)

    def test_customer_audience_filter_keeps_men_and_women_services_separate(self):
        mens = Service.objects.create(
            category=self.beauty, title="Men's grooming",
            audience=Service.Audience.MEN,
        )
        womens = Service.objects.create(
            category=self.beauty, title="Women's styling",
            audience=Service.Audience.WOMEN,
        )
        for service in (mens, womens):
            ServiceVariant.objects.create(
                service=service, title="Standard",
                mrp=Decimal("300.00"), price=Decimal("250.00"),
            )

        men_response = APIClient().get(
            "/api/v1/catalog/services/?launch_only=true&audience=men"
        )
        men_rows = men_response.data if isinstance(men_response.data, list) else men_response.data.get("results", [])
        men_ids = {row["id"] for row in men_rows}
        self.assertIn(mens.id, men_ids)
        self.assertNotIn(womens.id, men_ids)

        women_response = APIClient().get(
            "/api/v1/catalog/services/?launch_only=true&audience=women"
        )
        women_rows = women_response.data if isinstance(women_response.data, list) else women_response.data.get("results", [])
        women_ids = {row["id"] for row in women_rows}
        self.assertIn(womens.id, women_ids)
        self.assertNotIn(mens.id, women_ids)

    def test_electrical_work_type_filters_services_using_database_options(self):
        electrical = Category.objects.create(title="Electrical", slug="electrical")
        fans = Category.objects.create(title="Fan Services", slug="fan-services", parent=electrical)
        lighting = Category.objects.create(title="Lighting Services", slug="lighting-services", parent=electrical)
        repair = Service.objects.create(category=fans, title="Ceiling Fan Repair")
        install = Service.objects.create(category=lighting, title="LED Light Installation")
        for service in (repair, install):
            ServiceVariant.objects.create(
                service=service, title="Standard",
                mrp=Decimal("300.00"), price=Decimal("250.00"),
            )
        FormField.objects.create(
            service=repair, key="work_type", label="Work type",
            field_type=FormField.FieldType.SELECT, options=["Repair"],
            is_required=True,
        )
        FormField.objects.create(
            service=install, key="work_type", label="Work type",
            field_type=FormField.FieldType.SELECT, options=["Installation"],
            is_required=True,
        )

        answers = urlencode({"category_answers": json.dumps({"work_type": "Repair"})})
        response = APIClient().get(
            f"/api/v1/catalog/services/?launch_only=true&category={fans.id}&{answers}"
        )
        self.assertEqual(response.status_code, 200, response.data)
        rows = response.data if isinstance(response.data, list) else response.data.get("results", [])
        self.assertEqual({row["id"] for row in rows}, {repair.id})

    def test_electrical_work_type_filters_category_tree_before_service_selection(self):
        electrical = Category.objects.create(title="Electrical", slug="electrical")
        fans = Category.objects.create(title="Fan Services", slug="fan-services", parent=electrical)
        lighting = Category.objects.create(title="Lighting Services", slug="lighting-services", parent=electrical)
        repair = Service.objects.create(category=fans, title="Ceiling Fan Repair")
        install = Service.objects.create(category=lighting, title="LED Light Installation")
        for service in (repair, install):
            ServiceVariant.objects.create(
                service=service, title="Standard",
                mrp=Decimal("300.00"), price=Decimal("250.00"),
            )
        FormField.objects.create(
            service=repair, key="work_type", label="Work type",
            field_type=FormField.FieldType.SELECT, options=["Repair"],
            is_required=True,
        )
        FormField.objects.create(
            service=install, key="work_type", label="Work type",
            field_type=FormField.FieldType.SELECT, options=["Installation"],
            is_required=True,
        )

        answers = urlencode({"category_answers": json.dumps({"work_type": "Repair"})})
        response = APIClient().get(f"/api/v1/catalog/categories/?launch_only=true&{answers}")
        self.assertEqual(response.status_code, 200, response.data)
        roots = response.data if isinstance(response.data, list) else response.data.get("results", [])
        electrical_row = next(row for row in roots if row["slug"] == "electrical")
        child_slugs = {row["slug"] for row in electrical_row["children"]}
        self.assertIn("fan-services", child_slugs)
        self.assertNotIn("lighting-services", child_slugs)

    def test_electrical_work_type_rejects_malformed_category_answers(self):
        response = APIClient().get(
            "/api/v1/catalog/services/?launch_only=true&category_answers=not-json"
        )
        self.assertEqual(response.status_code, 400)

    def test_customer_categories_hide_roots_without_priced_services(self):
        response = APIClient().get("/api/v1/catalog/categories/?launch_only=true")
        self.assertEqual(response.status_code, 200, response.data)
        rows = response.data if isinstance(response.data, list) else response.data.get("results", [])
        self.assertEqual([row["slug"] for row in rows], ["beauty"])
