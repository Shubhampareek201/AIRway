from decimal import Decimal, ROUND_UP

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import Address
from apps.catalog.models import CityService, Service, ServiceVariant, AddOn


ROOT_CATEGORIES = {"Beauty", "Car Wash", "Electrical", "Home Cleaning"}


def _money(value):
    return Decimal(str(value)).quantize(Decimal("0.01"))


def _mrp(price):
    return (price * Decimal("1.20")).quantize(Decimal("1"), rounding=ROUND_UP)


def _root_name(category):
    node = category
    while node.parent_id:
        node = node.parent
    return node.title


def _package_price(root, service_title, package_title, attributes):
    service = service_title.lower()
    package = package_title.lower()
    if root == "Car Wash":
        if "monthly" in service or "plan" in service:
            base = 999 if "7-day" in package or "weekly" in package else 1999
        elif "complete" in service:
            base = 599 if "basic" in package else 999 if "deep" in package else 1499
        elif "interior" in service:
            base = 399 if "basic" in package else 799 if "deep" in package else 1199
        elif "exterior" in service:
            base = 249 if "basic" in package else 399 if "deep" in package else 599
        else:
            base = 999 if "basic" in package else 1999 if "premium" in package else 1499
        vehicle = str((attributes or {}).get("vehicle_type", "")).lower()
        factor = Decimal("1.0")
        if "suv" in vehicle or "muv" in vehicle or "mpv" in vehicle:
            factor = Decimal("1.20")
        if "luxury" in vehicle:
            factor = Decimal("1.50")
        return _money(Decimal(base) * factor)

    if root == "Beauty":
        if any(word in service for word in ("bridal", "engagement", "party makeup", "hd makeup")):
            base = 999 if "basic" in package or "party" in package else 2499 if "engagement" in package else 4999
        elif any(word in service for word in ("facial", "cleanup", "bleach")):
            base = 499 if "basic" in package else 899 if "deep" in package else 1299
        elif "wax" in service:
            base = 199 if "regular" in package else 399 if "rica" in package else 699
        elif any(word in service for word in ("colour", "color", "keratin", "rebond", "smoothening", "highlight")):
            base = 899 if "root" in package or "basic" in package else 1499 if "global" in package or "deep" in package else 2499
        elif "spa" in service:
            base = 499 if "basic" in package else 799 if "deep" in package else 1199
        elif "haircut" in service or "trimming" in service:
            base = 199 if "regular" in package else 349
        else:
            base = 299 if "basic" in package else 499 if "premium" not in package else 799
        return _money(base)

    if root == "Home Cleaning":
        if "bathroom" in service:
            base = 399 if "basic" in package else 599 if "deep" in package else 799
        elif "kitchen" in service:
            base = 799 if "basic" in package else 1299 if "deep" in package else 1799
        elif "full home" in service:
            base = 1499 if "basic" in package else 2499 if "deep" in package else 3499
        elif "sofa" in service or "upholstery" in service:
            base = 299 if "basic" in package else 499 if "deep" in package else 699
        elif "mattress" in service:
            base = 299 if "basic" in package else 499 if "deep" in package else 699
        elif "carpet" in service or "rug" in service:
            base = 199 if "basic" in package else 349 if "deep" in package else 499
        elif "window" in service or "glass" in service or "balcony" in service or "terrace" in service:
            base = 399 if "basic" in package else 699 if "deep" in package else 999
        else:
            base = 499 if "basic" in package else 799 if "deep" in package else 1199
        return _money(base)

    return Decimal("0.00")


def _service_base_price(root, service):
    title = service.title.lower()
    if root == "Electrical":
        if service.pricing_type == Service.PricingType.QUOTE or service.booking_mode == Service.BookingMode.INSPECTION:
            return Decimal("199.00")
        if any(word in title for word in ("fan", "light", "bulb", "led", "tube", "switch", "socket", "doorbell")):
            return Decimal("249.00")
        if any(word in title for word in ("geyser", "inverter", "ups", "pump", "motor")):
            return Decimal("349.00")
        return Decimal("299.00")
    if root == "Beauty":
        if any(word in title for word in ("threading", "eyebrow", "upper lip", "chin")):
            return Decimal("79.00")
        if any(word in title for word in ("haircut", "hair wash", "beard", "shave", "trim")):
            return Decimal("199.00")
        if "massage" in title:
            return Decimal("399.00")
        if "manicure" in title or "pedicure" in title or "nail" in title:
            return Decimal("299.00")
        if "wax" in title:
            return Decimal("199.00")
        if "makeup" in title or "bridal" in title:
            return Decimal("999.00")
        return Decimal("499.00")
    if root == "Car Wash":
        return Decimal("299.00")
    if root == "Home Cleaning":
        return Decimal("499.00")
    return Decimal("0.00")


def _addon_price(root, title):
    name = title.lower()
    if any(word in name for word in ("polish", "conditioning", "stain", "hard water")):
        return Decimal("199.00")
    if any(word in name for word in ("shampoo", "deep", "removal", "cleaning")):
        return Decimal("249.00")
    if any(word in name for word in ("engine", "ceramic", "graphene", "coating")):
        return Decimal("499.00")
    if root == "Beauty":
        return Decimal("149.00")
    return Decimal("99.00")

def _beauty_audience(service):
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


class Command(BaseCommand):
    help = (
        "Set indicative launch prices without overwriting non-zero admin prices, "
        "and enable the launch catalogue for the city of a selected customer address."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--address-id",
            type=int,
            required=True,
            help="Existing customer Address ID; its active city receives the launch catalogue.",
        )

    def handle(self, *args, **options):
        address_id = options["address_id"]
        try:
            address = Address.objects.select_related("zone__city").get(
                pk=address_id, deleted_at__isnull=True
            )
        except Address.DoesNotExist as exc:
            raise CommandError(f"Active address {address_id} was not found.") from exc

        if not address.zone_id or not address.zone.is_active:
            raise CommandError(
                f"Address {address_id} has no active service zone. Fix its zone before enabling services."
            )
        city = address.zone.city
        if not city.is_active:
            raise CommandError(f"{city.name} is inactive. Activate the city before enabling services.")

        services = [
            service for service in Service.objects.select_related("category__parent").filter(
                is_active=True, category__is_active=True
            )
            if _root_name(service.category) in ROOT_CATEGORIES
        ]
        if not services:
            raise CommandError("No active launch-catalogue services were found. Run seed_launch_catalogue first.")

        counts = {"city_services_created": 0, "audiences_updated": 0, "packages_created": 0, "packages_priced": 0, "addons_priced": 0, "services_priced": 0}
        for service in services:
            _, created = CityService.objects.update_or_create(
                city=city, service=service, defaults={"is_active": True}
            )
            if created:
                counts["city_services_created"] += 1

            root = _root_name(service.category)
            if root == "Beauty":
                audience = _beauty_audience(service)
                if service.audience != audience:
                    service.audience = audience
                    service.save(update_fields=["audience", "updated_at"])
                    counts["audiences_updated"] += 1

            variants = list(service.variants.filter(is_active=True))
            if not variants and service.pricing_type == Service.PricingType.FIXED:
                base_price = _service_base_price(root, service)
                if base_price > 0:
                    variant = ServiceVariant.objects.create(
                        service=service,
                        title="Standard Service",
                        description="Standard service scope. Confirm material or extra-work charges before work begins.",
                        mrp=_mrp(base_price),
                        price=base_price,
                        duration_minutes=service.duration_minutes,
                        is_active=True,
                    )
                    variants = [variant]
                    counts["packages_created"] += 1
            for variant in variants:
                if variant.price > 0:
                    if variant.mrp <= 0:
                        variant.mrp = variant.price
                        variant.save(update_fields=["mrp", "updated_at"])
                    continue
                price = _package_price(root, service.title, variant.title, variant.attributes)
                if price <= 0:
                    price = _service_base_price(root, service)
                if price <= 0:
                    continue
                variant.price = price
                variant.mrp = _mrp(price)
                variant.save(update_fields=["price", "mrp", "updated_at"])
                counts["packages_priced"] += 1

            for addon in service.addons.filter(is_active=True):
                if addon.price > 0:
                    if addon.mrp <= 0:
                        addon.mrp = addon.price
                        addon.save(update_fields=["mrp", "updated_at"])
                    continue
                price = _addon_price(root, addon.title)
                addon.price = price
                addon.mrp = _mrp(price)
                addon.save(update_fields=["price", "mrp", "updated_at"])
                counts["addons_priced"] += 1

            if service.pricing_type == Service.PricingType.QUOTE and service.visit_fee <= 0:
                service.visit_fee = _service_base_price(root, service)
                service.booking_mode = Service.BookingMode.INSPECTION
                service.save(update_fields=["visit_fee", "booking_mode", "updated_at"])
                counts["services_priced"] += 1

        self.stdout.write(self.style.SUCCESS(
            f"Launch catalogue configured for {city.name}: " +
            ", ".join(f"{key}={value}" for key, value in counts.items())
        ))
        self.stdout.write(
            "Rates are indicative test prices in INR, not guaranteed market quotes. "
            "Non-zero package/add-on prices are preserved; inspection and quote jobs use visit fees."
        )
