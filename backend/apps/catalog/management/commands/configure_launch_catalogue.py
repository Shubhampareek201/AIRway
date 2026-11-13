from decimal import Decimal, ROUND_HALF_UP

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.catalog.models import AddOn, Category, Service, ServiceVariant


ROOTS = {"car-wash", "beauty", "electrical", "home-cleaning"}
MONEY = Decimal("1")


def money(value):
    return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)


def root_for(service):
    category = service.category
    while category.parent_id and category.parent is not None:
        category = category.parent
    return category.slug


def beauty_audience(service):
    title = service.title.lower().strip()
    men_only = {
        "men's haircut", "men's hair styling", "men's hair wash",
        "men's haircut + hair wash", "men's hair colour", "grey hair coverage",
        "men's hair spa", "beard trim", "beard styling", "clean shave",
        "chest wax", "back wax",
    }
    women_only = {
        "women's haircut", "hair trimming", "women's hair wash", "blow dry",
        "women's hair styling", "hair curling", "hair straightening",
        "hair smoothening", "keratin treatment", "hair rebonding",
        "women's hair spa", "global hair colour", "root touch-up",
        "hair highlights", "eyebrow threading", "upper lip threading",
        "lower lip threading", "chin threading", "forehead threading",
        "side locks threading", "full face threading", "threading combination",
        "half arms", "full arms", "half legs", "full legs", "underarms",
        "full face", "bikini line", "bikini wax", "brazilian wax",
        "full body wax", "party makeup", "light makeup", "engagement makeup",
        "bridal makeup", "hd makeup", "hairstyling", "bridal hairstyle",
        "party hairstyle", "saree draping",
    }
    if title in men_only:
        return Service.Audience.MEN
    if title in women_only:
        return Service.Audience.WOMEN
    return Service.Audience.ALL


def service_base_price(service, root):
    title = service.title.lower()
    category = service.category.title.lower()

    if root == "beauty":
        if "thread" in title:
            return 49
        if "haircut" in title:
            return 149 if "men" in title else 249
        if "trim" in title:
            return 149
        if "beard" in title or "shave" in title:
            return 99
        if "wax" in title:
            for key, amount in (
                ("brazilian", 999), ("full body", 1499), ("bikini", 599),
                ("full legs", 399), ("half legs", 249), ("full arms", 299),
                ("half arms", 199), ("underarms", 99), ("chest", 299), ("back", 399),
            ):
                if key in title:
                    return amount
            return 199
        if "bridal makeup" in title:
            return 9999
        if "engagement makeup" in title:
            return 3999
        if "party makeup" in title or "hd makeup" in title:
            return 1499
        if "light makeup" in title:
            return 999
        if "keratin" in title or "smoothening" in title or "rebonding" in title:
            return 2499
        if "highlight" in title or "global hair colour" in title:
            return 1299
        if "colour" in title or "coverage" in title or "root touch" in title:
            return 499
        if "hair spa" in title:
            return 499
        if "hair wash" in title:
            return 99 if "men" in title else 199
        if "hair styling" in title or "hairstyle" in title or "blow dry" in title:
            return 299
        if "facial" in title:
            return 499
        if "cleanup" in title or "bleaching" in title:
            return 299
        if "manicure" in title:
            return 299
        if "pedicure" in title:
            return 349
        if "nail" in title or "gel polish" in title:
            return 499
        if "massage" in title or "spa" in title:
            return 299
        return 299

    if root == "car-wash":
        if "interior" in title:
            return 399
        if "complete" in title:
            return 599
        if "monthly" in title:
            return 999
        if "exterior" in title:
            return 249
        return 499

    if root == "electrical":
        if "wiring" in title or "short circuit" in title or "power failure" in title:
            return 249
        if "fan" in title:
            return 149
        if "light" in title or "bulb" in title or "tube" in title:
            return 99
        if "switch" in title or "socket" in title or "plug" in title:
            return 99
        if "geyser" in title or "motor" in title or "inverter" in title or "ups" in title:
            return 199
        if "mcb" in title or "fuse" in title or "rccb" in title or "elcb" in title:
            return 199
        return 149

    if root == "home-cleaning":
        if "bathroom" in title:
            return 599
        if "kitchen" in title:
            return 1299
        if "full home" in title or "move-in" in title or "move-out" in title:
            return 2499
        if "sofa" in title or "upholstery" in title:
            return 549
        if "mattress" in title:
            return 299
        if "carpet" in title or "rug" in title:
            return 299
        if "balcony" in title or "terrace" in title or "garden" in title:
            return 399
        if "window" in title or "glass" in title:
            return 399
        if "floor" in title or "tile" in title or "marble" in title:
            return 499
        return 499

    return 0


def package_price(base, variant, root):
    title = variant.title.lower()
    multiplier = Decimal("1.00")
    if "premium" in title or "bridal package" in title:
        multiplier = Decimal("2.00")
    elif "deep" in title or "hd" in title or "engagement package" in title:
        multiplier = Decimal("1.50")
    elif "spa" in title or "rica" in title or "special occasion" in title:
        multiplier = Decimal("1.40")
    elif "basic" in title or "regular" in title or "standard" in title:
        multiplier = Decimal("1.00")

    if root == "car-wash":
        vehicle = str((variant.attributes or {}).get("vehicle_type", "")).lower()
        if "luxury" in vehicle:
            multiplier *= Decimal("1.80")
        elif "7 seater" in vehicle or "muv" in vehicle or "mpv" in vehicle:
            multiplier *= Decimal("1.45")
        elif "suv" in vehicle:
            multiplier *= Decimal("1.30")
        elif "sedan" in vehicle:
            multiplier *= Decimal("1.15")
    return money(Decimal(base) * multiplier)


def addon_price(addon, root):
    title = addon.title.lower()
    if root == "beauty":
        if "full body" in title or "brazilian" in title:
            return 499
        return 99
    if root == "car-wash":
        if "engine" in title or "roof" in title or "leather" in title:
            return 299
        return 149
    if root == "electrical":
        return 99
    return 199


class Command(BaseCommand):
    help = (
        "Apply editable Rawatbhata launch starting prices and exact Beauty audience "
        "tags. Existing non-zero admin prices are preserved."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Report changes without saving.")

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        changed = {"audiences": 0, "service_modes": 0, "packages_priced": 0,
                   "packages_created": 0, "addons_priced": 0, "visit_fees": 0}
        services = list(
            Service.objects.select_related("category", "category__parent")
            .prefetch_related("variants", "addons")
            .filter(is_active=True)
        )

        for service in services:
            root = root_for(service)
            if root not in ROOTS:
                continue

            if root == "beauty":
                audience = beauty_audience(service)
                if service.audience != audience:
                    service.audience = audience
                    changed["audiences"] += 1

            base = service_base_price(service, root)
            if service.pricing_type == Service.PricingType.PER_UNIT:
                service.pricing_type = Service.PricingType.QUOTE
                service.booking_mode = Service.BookingMode.INSPECTION
                changed["service_modes"] += 1

            if service.pricing_type == Service.PricingType.QUOTE:
                if service.booking_mode != Service.BookingMode.INSPECTION:
                    service.booking_mode = Service.BookingMode.INSPECTION
                    changed["service_modes"] += 1
                if service.visit_fee <= 0:
                    service.visit_fee = Decimal("299.00") if root == "car-wash" else Decimal("149.00")
                    changed["visit_fees"] += 1

            variants = list(service.variants.all())
            if service.pricing_type == Service.PricingType.FIXED and not variants:
                variant = ServiceVariant(
                    service=service,
                    title="Standard Service",
                    description="Standard service scope. Confirm any material or extra-work charges before work begins.",
                    included_tasks=[],
                    duration_minutes=service.duration_minutes,
                    mrp=Decimal(base),
                    price=Decimal(base),
                    is_active=True,
                )
                if not dry_run:
                    variant.save()
                changed["packages_created"] += 1
                variants = [variant]

            for variant in variants:
                if not variant.is_active or variant.price > 0:
                    continue
                amount = package_price(base, variant, root)
                variant.price = amount
                variant.mrp = max(variant.mrp, amount)
                if not dry_run:
                    variant.save(update_fields=["price", "mrp", "updated_at"])
                changed["packages_priced"] += 1

            for addon in service.addons.all():
                if not addon.is_active or addon.price > 0:
                    continue
                amount = money(addon_price(addon, root))
                addon.price = amount
                addon.mrp = max(addon.mrp, amount)
                if not dry_run:
                    addon.save(update_fields=["price", "mrp", "updated_at"])
                changed["addons_priced"] += 1

            if not dry_run:
                service.save(update_fields=["audience", "booking_mode", "pricing_type", "visit_fee", "updated_at"])

        self.stdout.write(self.style.SUCCESS(
            ("DRY RUN - " if dry_run else "UPDATED - ")
            + ", ".join(f"{key}: {value}" for key, value in changed.items())
        ))
        self.stdout.write(
            "Prices are launch estimates, not provider quotes. Review them in Admin before "
            "opening the catalogue; existing non-zero prices were not overwritten."
        )
