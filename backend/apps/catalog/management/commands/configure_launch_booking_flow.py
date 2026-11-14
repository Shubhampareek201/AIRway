from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.catalog.models import (
    Category, CategoryAudienceOption, FormField, Service, ServiceVariant,
)


class DryRunRollback(Exception):
    pass


def _category(slug, title, parent=None, sort_order=0):
    category, _ = Category.objects.get_or_create(
        slug=slug,
        defaults={
            "title": title,
            "parent": parent,
            "sort_order": sort_order,
            "is_active": True,
        },
    )
    changed = []
    if category.title != title:
        category.title = title
        changed.append("title")
    if category.parent_id != (parent.id if parent else None):
        category.parent = parent
        changed.append("parent")
    if category.sort_order != sort_order:
        category.sort_order = sort_order
        changed.append("sort_order")
    if not category.is_active:
        category.is_active = True
        changed.append("is_active")
    if changed:
        category.save(update_fields=changed + ["updated_at"])
    return category


def _move_category(slug, parent):
    category = Category.objects.filter(slug=slug).first()
    if category is None:
        raise CommandError(f"Required existing category '{slug}' was not found.")
    if category.parent_id != parent.id:
        category.parent = parent
        category.save(update_fields=["parent", "updated_at"])
    return category


def _ensure_bike_service(category, title, description, packages, *, quote=False):
    service, _ = Service.objects.get_or_create(
        category=category,
        title=title,
        defaults={
            "description": description,
            "booking_mode": Service.BookingMode.INSPECTION if quote else Service.BookingMode.SCHEDULED,
            "pricing_type": Service.PricingType.QUOTE if quote else Service.PricingType.FIXED,
            "duration_minutes": 60,
            "visit_fee": Decimal("149.00") if quote else Decimal("0.00"),
            "audience": Service.Audience.ALL,
            "is_active": True,
        },
    )
    if not service.is_active:
        service.is_active = True
        service.save(update_fields=["is_active", "updated_at"])
    if quote:
        if service.booking_mode != Service.BookingMode.INSPECTION or service.pricing_type != Service.PricingType.QUOTE:
            service.booking_mode = Service.BookingMode.INSPECTION
            service.pricing_type = Service.PricingType.QUOTE
            service.save(update_fields=["booking_mode", "pricing_type", "updated_at"])
        if service.visit_fee <= 0:
            service.visit_fee = Decimal("149.00")
            service.save(update_fields=["visit_fee", "updated_at"])
    else:
        for index, (vehicle, label, price, duration) in enumerate(packages, start=1):
            variant, created = ServiceVariant.objects.get_or_create(
                service=service,
                title=label,
                defaults={
                    "description": f"{label} for {vehicle.lower()}.",
                    "attributes": {"vehicle_type": vehicle},
                    "included_tasks": ["Exterior wash", "Rinse", "Body wipe-down"],
                    "duration_minutes": duration,
                    "mrp": (Decimal(price) * Decimal("1.20")).quantize(Decimal("1")),
                    "price": Decimal(price),
                    "sort_order": index,
                    "is_active": True,
                },
            )
            if not created and variant.price <= 0:
                variant.price = Decimal(price)
                variant.mrp = (Decimal(price) * Decimal("1.20")).quantize(Decimal("1"))
                variant.is_active = True
                variant.save(update_fields=["price", "mrp", "is_active", "updated_at"])
    return service


class Command(BaseCommand):
    help = (
        "Configure the four launch customer journeys in the existing database. "
        "Safe preview by default; pass --apply to save changes."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Persist the planned catalogue hierarchy and flow changes. Without this flag, all writes roll back.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        summary = {}
        try:
            with transaction.atomic():
                summary = self._configure()
                if not apply_changes:
                    raise DryRunRollback
        except DryRunRollback:
            self.stdout.write(self.style.WARNING("DRY RUN ONLY — no database changes were saved."))
        self.stdout.write("Launch booking-flow configuration:")
        for key, value in summary.items():
            self.stdout.write(f"  {key}: {value}")
        if apply_changes:
            self.stdout.write(self.style.SUCCESS("Database configuration applied. Existing category and service IDs were preserved."))

    def _configure(self):
        roots = {
            slug: Category.objects.filter(slug=slug, parent__isnull=True).first()
            for slug in ("beauty", "car-wash", "electrical", "home-cleaning")
        }
        missing = [slug for slug, item in roots.items() if item is None]
        if missing:
            raise CommandError("Missing launch root categories: " + ", ".join(missing))

        beauty, car_wash, electrical, home = (
            roots["beauty"], roots["car-wash"], roots["electrical"], roots["home-cleaning"]
        )
        initial_category_slugs = set(Category.objects.values_list("slug", flat=True))
        changes = {
            "categories_created": 0,
            "existing_categories_reparented": 0,
            "bike_services_created_or_found": 0,
            "bike_packages_created_or_found": 0,
            "beauty_audience_options_created_or_found": 0,
            "electrical_work_type_fields_deactivated": 0,
        }

        # Beauty audience selection remains an explicit first step. "Both"
        # means only services intentionally reviewed and marked audience=all.
        for index, (audience, title, subtitle) in enumerate([
            ("men", "Men", "Hair, skin and grooming services for men"),
            ("women", "Women", "Hair, skin, nails and beauty services for women"),
            ("both", "Unisex", "Services explicitly available to all customers"),
        ], start=1):
            option, created = CategoryAudienceOption.objects.get_or_create(
                category=beauty,
                audience=audience,
                defaults={
                    "title": title,
                    "subtitle": subtitle,
                    "image": "",
                    "sort_order": index,
                    "is_active": True,
                },
            )
            if not created:
                option.title = title
                option.subtitle = subtitle
                option.sort_order = index
                option.is_active = True
                option.save(update_fields=["title", "subtitle", "sort_order", "is_active", "updated_at"])
            changes["beauty_audience_options_created_or_found"] += int(created)

        # Car Wash: Car/Bike first, then the existing car service families.
        car = _category("car", "Car", car_wash, 1)
        bike = _category("bike", "Bike", car_wash, 2)
        existing_car_groups = [
            "exterior-car-cleaning", "interior-car-cleaning",
            "complete-car-cleaning", "car-detailing-paint-protection",
            "monthly-car-wash-plans",
        ]
        for index, slug in enumerate(existing_car_groups, start=1):
            old_parent_id = Category.objects.filter(slug=slug).values_list("parent_id", flat=True).first()
            _move_category(slug, car)
            if old_parent_id != car.id:
                changes["existing_categories_reparented"] += 1

        bike_exterior = _category("bike-exterior-cleaning", "Exterior Bike Cleaning", bike, 1)
        bike_complete = _category("bike-complete-cleaning", "Complete Bike Cleaning", bike, 2)
        bike_detailing = _category("bike-detailing", "Bike Detailing", bike, 3)
        _ensure_bike_service(
            bike_exterior,
            "Bike Exterior Wash",
            "Exterior wash for scooters and motorcycles.",
            [
                ("Scooter", "Basic Scooter Wash", "149.00", 30),
                ("Motorcycle", "Basic Motorcycle Wash", "199.00", 35),
            ],
        )
        _ensure_bike_service(
            bike_complete,
            "Bike Complete Cleaning",
            "Exterior wash with detailed wheel, panel and accessible surface cleaning.",
            [
                ("Scooter", "Complete Scooter Cleaning", "249.00", 45),
                ("Motorcycle", "Complete Motorcycle Cleaning", "299.00", 50),
            ],
        )
        _ensure_bike_service(
            bike_detailing,
            "Bike Detailing & Paint Protection",
            "Specialist bike detailing. Final scope and price are confirmed after inspection.",
            [],
            quote=True,
        )
        changes["bike_services_created_or_found"] = Service.objects.filter(
            category__in=[bike_exterior, bike_complete, bike_detailing]
        ).count()
        changes["bike_packages_created_or_found"] = ServiceVariant.objects.filter(
            service__category__in=[bike_exterior, bike_complete]
        ).count()

        car.flow_steps = [{
            "key": "vehicle_type",
            "title": "Select your car size",
            "type": "select",
            "required": True,
            "options": [
                {"label": "Hatchback", "value": "Hatchback"},
                {"label": "Sedan", "value": "Sedan"},
                {"label": "Compact SUV", "value": "Compact SUV"},
                {"label": "SUV – 5 Seater", "value": "SUV – 5 Seater"},
                {"label": "SUV – 7 Seater", "value": "SUV – 7 Seater"},
                {"label": "MUV / MPV", "value": "MUV / MPV"},
                {"label": "Luxury Car", "value": "Luxury Car"},
                {"label": "Luxury SUV", "value": "Luxury SUV"},
            ],
        }]
        car.save(update_fields=["flow_steps", "updated_at"])
        bike.flow_steps = [{
            "key": "vehicle_type",
            "title": "Select your two-wheeler type",
            "type": "select",
            "required": True,
            "options": [
                {"label": "Scooter", "value": "Scooter"},
                {"label": "Motorcycle", "value": "Motorcycle"},
            ],
        }]
        bike.save(update_fields=["flow_steps", "updated_at"])

        car_wash.flow_steps = [{
            "key": "vehicle_kind",
            "title": "What do you want to get cleaned?",
            "description": "Choose your vehicle type to see the relevant services.",
            "type": "select",
            "required": True,
            "filter_children": True,
            "options": [
                {"label": "Car", "value": "Car"},
                {"label": "Bike / Scooter", "value": "Bike"},
            ],
        }]
        car_wash.save(update_fields=["flow_steps", "updated_at"])

        # Home Cleaning: choose scope before the area/item category.
        full_home = _category("full-home", "Full Home", home, 1)
        specific_area = _category("specific-area", "Specific Area", home, 2)
        specific_item = _category("specific-item", "Specific Item", home, 3)
        _move_category("full-home-cleaning", full_home)
        full_home_service_category = Category.objects.get(slug="full-home-cleaning")
        full_home_service = Service.objects.filter(
            category=full_home_service_category,
            title__iexact="Full Home Cleaning",
            is_active=True,
        ).first()
        if full_home_service:
            for index, (bhk, price) in enumerate([
                ("1 BHK", "2499.00"),
                ("2 BHK", "3499.00"),
                ("3 BHK", "4999.00"),
                ("4 BHK", "6499.00"),
            ], start=1):
                variant, created = ServiceVariant.objects.get_or_create(
                    service=full_home_service,
                    title=f"Deep Cleaning — {bhk}",
                    defaults={
                        "description": f"Deep cleaning for a {bhk} home. Review the included tasks before booking.",
                        "attributes": {"property_size": bhk},
                        "included_tasks": [
                            "Room-by-room dusting and surface cleaning",
                            "Floor sweeping and mopping",
                            "Kitchen and bathroom deep cleaning",
                            "Fans, doors, furniture and accessible corners",
                        ],
                        "duration_minutes": 300 + (index * 60),
                        "mrp": (Decimal(price) * Decimal("1.20")).quantize(Decimal("1")),
                        "price": Decimal(price),
                        "sort_order": index,
                        "is_active": True,
                    },
                )
                if not created and variant.price <= 0:
                    variant.price = Decimal(price)
                    variant.mrp = (Decimal(price) * Decimal("1.20")).quantize(Decimal("1"))
                    variant.attributes = {"property_size": bhk}
                    variant.is_active = True
                    variant.save(update_fields=["price", "mrp", "attributes", "is_active", "updated_at"])
        for slug in [
            "kitchen-cleaning", "bathroom-cleaning", "bedroom-cleaning",
            "living-room-dining-room", "garden-cleaning", "balcony-terrace-cleaning",
            "window-glass-cleaning", "floor-cleaning",
        ]:
            _move_category(slug, specific_area)
        for slug in ["sofa-upholstery-cleaning", "mattress-cleaning", "carpet-rug-cleaning"]:
            _move_category(slug, specific_item)
        full_home.flow_steps = [{
            "key": "property_size",
            "title": "Select your home size",
            "type": "select",
            "required": True,
            "options": [
                {"label": "1 BHK", "value": "1 BHK"},
                {"label": "2 BHK", "value": "2 BHK"},
                {"label": "3 BHK", "value": "3 BHK"},
                {"label": "4 BHK", "value": "4 BHK"},
            ],
        }]
        full_home.save(update_fields=["flow_steps", "updated_at"])
        home.flow_steps = [{
            "key": "cleaning_scope",
            "title": "What would you like cleaned?",
            "description": "Choose full-home cleaning, a specific area or an individual item.",
            "type": "select",
            "required": True,
            "filter_children": True,
            "options": [
                {"label": "Full Home", "value": "Full Home"},
                {"label": "Specific Area", "value": "Specific Area"},
                {"label": "Specific Item", "value": "Specific Item"},
            ],
        }]
        home.save(update_fields=["flow_steps", "updated_at"])
        changes["categories_created"] = len(
            set(Category.objects.values_list("slug", flat=True)) - initial_category_slugs
        )

        # Electrical: first choose the work intent, then the existing equipment
        # group and its specific service. Do not ask the same work type twice.
        electrical.flow_steps = [{
            "key": "work_type",
            "title": "What kind of electrical work do you need?",
            "description": "Choose the job type, then select the electrical item.",
            "type": "select",
            "required": True,
            "options": [
                {"label": "Repair", "value": "Repair"},
                {"label": "Installation", "value": "Installation"},
                {"label": "Maintenance", "value": "Maintenance"},
                {"label": "Inspection", "value": "Inspection"},
            ],
        }]
        electrical.save(update_fields=["flow_steps", "updated_at"])
        work_type_fields = FormField.objects.filter(
            service__category__parent=electrical,
            key="work_type",
            is_active=True,
        )
        changes["electrical_work_type_fields_deactivated"] = work_type_fields.update(is_active=False)

        return changes
