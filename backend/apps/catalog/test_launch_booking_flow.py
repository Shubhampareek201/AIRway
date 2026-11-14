from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase

from apps.catalog.models import (
    Category, CategoryAudienceOption, FormField, Service, ServiceVariant,
)


class LaunchBookingFlowConfigurationTests(TestCase):
    def setUp(self):
        self.roots = {
            slug: Category.objects.create(title=title, slug=slug)
            for slug, title in [
                ("beauty", "Beauty"),
                ("car-wash", "Car Wash"),
                ("electrical", "Electrical"),
                ("home-cleaning", "Home Cleaning"),
            ]
        }
        self.car_groups = [
            "exterior-car-cleaning", "interior-car-cleaning",
            "complete-car-cleaning", "car-detailing-paint-protection",
            "monthly-car-wash-plans",
        ]
        self.home_groups = [
            "full-home-cleaning", "kitchen-cleaning", "bathroom-cleaning",
            "bedroom-cleaning", "living-room-dining-room", "garden-cleaning",
            "balcony-terrace-cleaning", "window-glass-cleaning", "floor-cleaning",
            "sofa-upholstery-cleaning", "mattress-cleaning", "carpet-rug-cleaning",
        ]
        self.electrical_groups = [
            "fan-services", "lighting-services", "switch-socket-services",
            "wiring-electrical-repairs", "inverter-ups",
            "geyser-electrical-connections", "electrical-inspection-setup",
        ]
        for slug in self.car_groups:
            Category.objects.create(
                title=slug.replace("-", " ").title(),
                slug=slug,
                parent=self.roots["car-wash"],
            )
        for slug in self.home_groups:
            Category.objects.create(
                title=slug.replace("-", " ").title(),
                slug=slug,
                parent=self.roots["home-cleaning"],
            )
        for slug in self.electrical_groups:
            Category.objects.create(
                title=slug.replace("-", " ").title(),
                slug=slug,
                parent=self.roots["electrical"],
            )
        full_home_category = Category.objects.get(slug="full-home-cleaning")
        self.full_home_service = Service.objects.create(
            category=full_home_category,
            title="Full Home Cleaning",
            pricing_type=Service.PricingType.FIXED,
        )
        ServiceVariant.objects.create(
            service=self.full_home_service,
            title="Deep Full Home Cleaning",
            mrp=Decimal("0.00"),
            price=Decimal("0.00"),
        )
        electrical_service = Service.objects.create(
            category=Category.objects.get(slug="fan-services"),
            title="Ceiling Fan",
        )
        FormField.objects.create(
            service=electrical_service,
            key="work_type",
            label="Work type",
            field_type=FormField.FieldType.SELECT,
            options=["Repair", "Installation"],
            is_required=True,
            is_active=True,
        )

    def test_preview_rolls_back_all_configuration_changes(self):
        call_command("configure_launch_booking_flow", verbosity=0)

        self.assertFalse(Category.objects.filter(slug="car").exists())
        self.assertFalse(CategoryAudienceOption.objects.filter(category=self.roots["beauty"]).exists())
        self.assertEqual(self.roots["car-wash"].flow_steps, [])
        self.assertEqual(
            Category.objects.get(slug="exterior-car-cleaning").parent_id,
            self.roots["car-wash"].id,
        )

    def test_apply_configures_nested_journeys_and_preserves_existing_service(self):
        call_command("configure_launch_booking_flow", "--apply", verbosity=0)

        self.roots["car-wash"].refresh_from_db()
        self.roots["home-cleaning"].refresh_from_db()
        self.assertEqual(self.roots["car-wash"].flow_steps[0]["key"], "vehicle_kind")
        self.assertEqual(self.roots["home-cleaning"].flow_steps[0]["key"], "cleaning_scope")
        self.assertEqual(
            Category.objects.get(slug="exterior-car-cleaning").parent.slug,
            "car",
        )
        self.assertEqual(
            Category.objects.get(slug="full-home-cleaning").parent.slug,
            "full-home",
        )
        self.assertEqual(
            CategoryAudienceOption.objects.filter(category=self.roots["beauty"], is_active=True).count(),
            3,
        )
        self.assertEqual(
            Service.objects.filter(category__slug__in=["bike-exterior-cleaning", "bike-complete-cleaning", "bike-detailing"]).count(),
            3,
        )
        self.assertEqual(
            ServiceVariant.objects.filter(
                service=self.full_home_service,
                attributes__property_size__isnull=False,
                price__gt=0,
            ).count(),
            4,
        )
