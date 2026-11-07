from django.core.management.base import BaseCommand

from apps.catalog.models import AddOn, Category, Service, ServiceVariant


LAUNCH_ROOTS = ("car-wash", "beauty", "electrical", "home-cleaning")


def image_state(obj):
    field = getattr(obj, "image", None)
    if not field:
        return False
    try:
        return bool(field.name)
    except (ValueError, AttributeError):
        return False


def fallback_group(title, category_slug):
    """Classify title using the same title-first intent as the Flutter resolver."""
    value = title.lower()
    groups = (
        ("Fan", ("fan",)),
        ("Lighting", ("chandelier", "ceiling light", "lighting", "light", "bulb", "led")),
        ("Switch / wiring / electrical repair", ("switch", "socket", "plug", "wiring", "short circuit", "mcb", "fuse", "electrician", "electrical")),
        ("Inverter / UPS", ("inverter", "ups", "battery backup")),
        ("Geyser", ("geyser", "water heater")),
        ("Sofa / upholstery", ("sofa", "upholstery", "cushion", "chair cleaning")),
        ("Kitchen / appliance", ("kitchen", "chimney", "refrigerator", "fridge", "microwave", "oven")),
        ("Bathroom", ("bathroom", "toilet", "washbasin", "sanitary")),
        ("Window / glass", ("window", "glass")),
        ("Mattress / bedroom", ("mattress", "bedroom", "bed cleaning")),
        ("Carpet / rug", ("carpet", "rug")),
        ("Floor / tile / outdoor", ("floor", "tile", "marble", "grout", "terrace", "balcony", "outdoor")),
        ("Garden", ("garden", "plant", "lawn")),
        ("Full-home cleaning", ("full home", "deep home", "move-in", "move-out", "home cleaning", "house cleaning", "general cleaning", "dusting", "maid")),
    )
    for label, words in groups:
        if any(word in value for word in words):
            return label

    if category_slug == "electrical":
        return "Electrical category fallback (generic)"
    if category_slug == "home-cleaning":
        return "Home-cleaning category fallback (generic)"
    if category_slug == "car-wash":
        return "Car-wash category fallback (generic)"
    if category_slug == "beauty":
        return "Beauty category fallback (generic)"
    return "NO MATCH"


class Command(BaseCommand):
    help = (
        "Audit active AIRway launch services and package/add-on images. "
        "Reports missing Admin uploads and title-based fallback classification; "
        "does not claim to visually verify image contents."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--all",
            action="store_true",
            help="Include inactive services, variants and add-ons.",
        )

    def handle(self, *args, **options):
        include_inactive = options["all"]
        roots = list(
            Category.objects.filter(parent__isnull=True, slug__in=LAUNCH_ROOTS)
            .order_by("sort_order", "title")
        )
        found = {root.slug for root in roots}
        missing_roots = [slug for slug in LAUNCH_ROOTS if slug not in found]
        if missing_roots:
            self.stderr.write(self.style.ERROR(
                "Missing launch root categories: " + ", ".join(missing_roots)
            ))

        total = missing_service_images = missing_option_images = 0
        no_title_match = []
        self.stdout.write("\nAIRway launch catalogue image audit")
        self.stdout.write("=" * 76)

        for root in roots:
            category_ids = [root.id]
            category_ids.extend(
                Category.objects.filter(parent=root).values_list("id", flat=True)
            )
            services = Service.objects.filter(category_id__in=category_ids)
            if not include_inactive:
                services = services.filter(is_active=True)
            services = services.select_related("category").prefetch_related(
                "images", "variants", "addons"
            ).order_by("category__title", "sort_order", "title")

            self.stdout.write(f"\n[{root.title}]")
            if not services.exists():
                self.stdout.write("  No matching services.")
                continue

            for service in services:
                total += 1
                gallery_images = [item for item in service.images.all() if image_state(item)]
                has_service_image = image_state(service) or bool(gallery_images)
                classification = fallback_group(service.title, root.slug)
                if not has_service_image:
                    missing_service_images += 1
                    status = "MISSING ADMIN IMAGE"
                else:
                    status = "ADMIN IMAGE PRESENT"
                if classification == "NO MATCH":
                    no_title_match.append(f"{root.title} > {service.category.title} > {service.title}")
                self.stdout.write(
                    f"  - {service.category.title} / {service.title} | "
                    f"{status} | fallback: {classification}"
                )

                variants = service.variants.all()
                addons = service.addons.all()
                if not include_inactive:
                    variants = variants.filter(is_active=True)
                    addons = addons.filter(is_active=True)
                for label, queryset in (("Package", variants), ("Add-on", addons)):
                    for option in queryset:
                        if not image_state(option):
                            missing_option_images += 1
                            self.stdout.write(
                                f"      * {label} missing image: {option.title}"
                            )

        self.stdout.write("\n" + "=" * 76)
        self.stdout.write(f"Services checked: {total}")
        self.stdout.write(f"Services without Admin image/gallery: {missing_service_images}")
        self.stdout.write(f"Packages/add-ons without their own image: {missing_option_images}")
        self.stdout.write(f"Titles with no specific fallback rule: {len(no_title_match)}")
        if no_title_match:
            self.stdout.write(self.style.WARNING("Review these titles:"))
            for item in no_title_match:
                self.stdout.write(f"  - {item}")
        self.stdout.write(
            self.style.WARNING(
                "NOTE: This is a metadata/rule audit, not visual image recognition. "
                "An uploaded image can still depict the wrong subject; verify or replace "
                "those assets in Admin."
            )
        )
