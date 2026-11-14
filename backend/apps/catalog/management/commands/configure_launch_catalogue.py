from decimal import Decimal, ROUND_UP

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.catalog.models import AddOn, Category, Service, ServiceVariant


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
        vehicle = str((attributes or {}).get("vehicle_type", "")).lower()
        factor = Decimal("1.00")
        if "sedan" in vehicle:
            factor = Decimal("1.33")
        elif "compact suv" in vehicle:
            factor = Decimal("1.50")
        elif "suv" in vehicle or "muv" in vehicle or "mpv" in vehicle:
            factor = Decimal("1.67")
        elif "luxury" in vehicle:
            factor = Decimal("2.00")
        if "monthly" in service or "plan" in service:
            base = 999
        elif "complete" in service:
            base = 699 if "basic" in package else 999 if "deep" in package else 1499
        elif "interior" in service:
            base = 399 if "basic" in package else 799 if "deep" in package else 1199
        elif "exterior" in service:
            base = 299 if "basic" in package else 399 if "deep" in package else 599
        else:
            base = 999 if "basic" in package else 1999 if "premium" in package else 1499
        return _money(Decimal(base) * factor)

    if root == "Beauty":
        exact = {
            "face cleanup": Decimal("349"),
            "fruit facial": Decimal("499"),
            "de-tan facial": Decimal("599"),
            "gold facial": Decimal("699"),
            "diamond facial": Decimal("899"),
            "brightening facial": Decimal("1299"),
            "hydra facial": Decimal("1899"),
            "face bleaching": Decimal("249"),
            "full arms": Decimal("249"),
            "full legs": Decimal("299"),
            "underarms": Decimal("79"),
            "full body wax": Decimal("899"),
            "eyebrow threading": Decimal("39"),
            "upper lip threading": Decimal("30"),
            "full face threading": Decimal("149"),
            "manicure": Decimal("349"),
            "pedicure": Decimal("449"),
            "women's haircut": Decimal("299"),
            "hd makeup": Decimal("1499"),
        }
        for key, price in exact.items():
            if key in service:
                return price
        if "bridal" in service:
            return Decimal("6999")
        if "keratin" in service:
            return Decimal("3499")
        if "smoothening" in service or "straightening" in service:
            return Decimal("2999")
        if "global hair colour" in service or "global colour" in service:
            return Decimal("1499")
        if "hair spa" in service:
            return Decimal("649") if "short" in package or "shoulder" in package else Decimal("899")
        if "wax" in service:
            return Decimal("299") if "leg" in service else Decimal("249")
        if "haircut" in service or "trimming" in service:
            return Decimal("299") if "women" in service else Decimal("199")
        if "threading" in service:
            return Decimal("39")
        return Decimal("299") if "basic" in package else Decimal("499") if "deep" in package else Decimal("799")

    if root == "Home Cleaning":
        if "full home" in service:
            if "1 bhk" in package:
                return Decimal("2499")
            if "2 bhk" in package:
                return Decimal("3499")
            if "3 bhk" in package:
                return Decimal("4999")
            if "4 bhk" in package:
                return Decimal("6499")
            return Decimal("2499")
        if "bathroom" in service:
            return Decimal("499") if "basic" in package else Decimal("599") if "deep" in package else Decimal("799")
        if "kitchen" in service:
            return Decimal("799") if "basic" in package else Decimal("999") if "deep" in package else Decimal("1799")
        if "sofa" in service or "upholstery" in service:
            if "basic" in package:
                return Decimal("399")
            if "deep" in package:
                return Decimal("599")
            return Decimal("799")
        if "mattress" in service:
            return Decimal("499") if "basic" in package else Decimal("599") if "deep" in package else Decimal("799")
        if "carpet" in service or "rug" in service:
            if "basic" in package:
                return Decimal("299")
            if "deep" in package:
                return Decimal("499")
            return Decimal("699")
        if "window" in service or "glass" in service or "balcony" in service or "terrace" in service:
            return Decimal("399") if "basic" in package else Decimal("699") if "deep" in package else Decimal("999")
        return Decimal("499") if "basic" in package else Decimal("799") if "deep" in package else Decimal("1199")

    return Decimal("0.00")


def _service_base_price(root, service):
    title = service.title.lower()
    if root == "Electrical":
        if service.pricing_type == Service.PricingType.QUOTE or service.booking_mode == Service.BookingMode.INSPECTION:
            return Decimal("149.00")
        if "fan" in title and "repair" in title:
            return Decimal("299.00")
        if any(word in title for word in ("fan", "light", "bulb", "led", "tube", "switch", "socket", "doorbell", "fuse")):
            return Decimal("149.00") if any(word in title for word in ("switch", "socket", "fuse")) else Decimal("249.00")
        if any(word in title for word in ("geyser", "inverter", "ups", "pump", "motor", "mcb")):
            return Decimal("299.00") if "mcb" in title else Decimal("499.00")
        return Decimal("299.00")
    if root == "Beauty":
        exact = {
            "eyebrow threading": Decimal("39"), "upper lip threading": Decimal("30"),
            "full face threading": Decimal("149"), "face bleaching": Decimal("249"),
            "face cleanup": Decimal("349"), "fruit facial": Decimal("499"),
            "de-tan facial": Decimal("599"), "gold facial": Decimal("699"),
            "diamond facial": Decimal("899"), "brightening facial": Decimal("1299"),
            "hydra facial": Decimal("1899"), "full arms": Decimal("249"),
            "full legs": Decimal("299"), "underarms": Decimal("79"),
            "full body wax": Decimal("899"), "manicure": Decimal("349"),
            "pedicure": Decimal("449"), "women's haircut": Decimal("299"),
            "hd makeup": Decimal("1499"),
        }
        for key, price in exact.items():
            if key in title:
                return price
        if "bridal" in title:
            return Decimal("6999")
        if "keratin" in title:
            return Decimal("3499")
        if "smoothening" in title or "straightening" in title:
            return Decimal("2999")
        if "haircut" in title or "trim" in title:
            return Decimal("299")
        if "wax" in title:
            return Decimal("249")
        if "threading" in title:
            return Decimal("39")
        if "manicure" in title:
            return Decimal("349")
        if "pedicure" in title:
            return Decimal("449")
        return Decimal("499")
    if root == "Car Wash":
        return Decimal("299.00")
    if root == "Home Cleaning":
        if "bathroom" in title:
            return Decimal("499")
        if "kitchen" in title:
            return Decimal("999")
        if "sofa" in title or "upholstery" in title:
            return Decimal("399")
        if "mattress" in title:
            return Decimal("499")
        if "carpet" in title or "rug" in title:
            return Decimal("299")
        if "full home" in title:
            return Decimal("2499")
        return Decimal("499")
    # New launch services without a category-specific rule still get a
    # clearly indicative demo amount rather than being omitted from testing.
    return Decimal("199.00")


def _addon_price(root, title):
    name = title.lower()
    if root == "Beauty":
        if "thread" in name or "eyebrow" in name:
            return Decimal("39")
        if "wax" in name:
            return Decimal("149")
        return Decimal("149")
    if root == "Car Wash":
        if any(word in name for word in ("ceramic", "graphene", "engine")):
            return Decimal("499")
        return Decimal("149")
    if root == "Home Cleaning":
        return Decimal("199") if any(word in name for word in ("sofa", "seat", "stain")) else Decimal("149")
    return Decimal("99")


class Command(BaseCommand):
    help = (
        "Configure indicative Jaipur-benchmarked launch prices. Preview only by default; "
        "pass --apply to write prices. Existing non-zero prices are never overwritten."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Persist price configuration. Without this flag, all writes roll back.",
        )

    def handle(self, *args, **options):
        summary = {}
        try:
            with transaction.atomic():
                summary = self._configure()
                if not options["apply"]:
                    raise RuntimeError("AIRWAY_CATALOGUE_DRY_RUN")
        except RuntimeError as exc:
            if str(exc) != "AIRWAY_CATALOGUE_DRY_RUN":
                raise
            self.stdout.write(self.style.WARNING("DRY RUN ONLY — no database changes were saved."))
        self.stdout.write("Indicative launch price plan (INR):")
        for key, value in summary.items():
            self.stdout.write(f"  {key}: {value}")
        if options["apply"]:
            self.stdout.write(self.style.SUCCESS("Price configuration applied. Existing non-zero prices were preserved."))

    def _configure(self):
        services = [
            service for service in Service.objects.select_related("category").filter(
                is_active=True, category__is_active=True
            )
            if _root_name(service.category) in ROOT_CATEGORIES
        ]
        if not services:
            raise RuntimeError("No active launch catalogue services found.")

        counts = {
            "existing_services_reviewed": len(services),
            "variants_priced": 0,
            "standard_variants_created": 0,
            "inspection_fees_set": 0,
            "quote_services_configured_for_inspection": 0,
            "addons_priced": 0,
            "per_unit_services_priced": 0,
            "per_unit_services_still_unpriced": 0,
            "fixed_services_still_unpriced": 0,
            "existing_nonzero_prices_preserved": 0,
        }
        for service in services:
            root = _root_name(service.category)
            if service.pricing_type == Service.PricingType.QUOTE:
                quote_updates = []
                if service.booking_mode != Service.BookingMode.INSPECTION:
                    service.booking_mode = Service.BookingMode.INSPECTION
                    quote_updates.append("booking_mode")
                    counts["quote_services_configured_for_inspection"] += 1
                if service.visit_fee <= 0:
                    service.visit_fee = Decimal("149.00")
                    quote_updates.append("visit_fee")
                    counts["inspection_fees_set"] += 1
                if quote_updates:
                    service.save(update_fields=quote_updates + ["updated_at"])
            elif service.pricing_type == Service.PricingType.PER_UNIT:
                # The existing booking/cart quantity is already multiplied into
                # pricing snapshots. For per-unit services it represents the
                # measured unit count (sq ft, seat, piece, etc.).
                if not service.unit_label:
                    service.unit_label = "unit"
                    service.save(update_fields=["unit_label", "updated_at"])
                unit_label = service.unit_label.strip().lower()
                service_title = service.title.lower()
                if "mattress" in service_title:
                    unit_rate = Decimal("499.00")
                elif "sq" in unit_label or "square" in unit_label:
                    unit_rate = Decimal("15.00")
                elif "seat" in unit_label:
                    unit_rate = Decimal("199.00")
                elif "room" in unit_label:
                    unit_rate = Decimal("499.00")
                elif "piece" in unit_label or "item" in unit_label:
                    unit_rate = Decimal("199.00")
                else:
                    unit_rate = _service_base_price(root, service)
                if unit_rate <= 0:
                    unit_rate = Decimal("199.00")

                variants = list(service.variants.filter(is_active=True).order_by("sort_order", "id"))
                if not variants:
                    variant, created = ServiceVariant.objects.get_or_create(
                        service=service,
                        title=f"Standard rate per {service.unit_label or 'unit'}",
                        defaults={
                            "description": f"Indicative starting rate per {service.unit_label or 'unit'}. Enter the required quantity when booking.",
                            "mrp": _mrp(unit_rate),
                            "price": unit_rate,
                            "duration_minutes": service.duration_minutes,
                            "included_tasks": [],
                            "attributes": {},
                            "is_active": True,
                        },
                    )
                    if created:
                        counts["standard_variants_created"] += 1
                    elif variant.price <= 0 or not variant.is_active:
                        update_fields = []
                        if variant.price <= 0:
                            variant.price = unit_rate
                            variant.mrp = _mrp(unit_rate)
                            update_fields.extend(["price", "mrp"])
                        if not variant.is_active:
                            variant.is_active = True
                            update_fields.append("is_active")
                        variant.save(update_fields=update_fields + ["updated_at"])
                        counts["variants_priced"] += int("price" in update_fields)
                    else:
                        counts["existing_nonzero_prices_preserved"] += 1
                else:
                    for variant in variants:
                        if variant.price > 0:
                            counts["existing_nonzero_prices_preserved"] += 1
                            continue
                        variant.price = unit_rate
                        variant.mrp = _mrp(unit_rate)
                        variant.save(update_fields=["price", "mrp", "updated_at"])
                        counts["variants_priced"] += 1
                if service.variants.filter(is_active=True, price__gt=0).exists():
                    counts["per_unit_services_priced"] += 1
                else:
                    counts["per_unit_services_still_unpriced"] += 1
            else:
                variants = list(service.variants.filter(is_active=True).order_by("sort_order", "id"))
                if not variants:
                    price = _service_base_price(root, service)
                    if price <= 0:
                        price = Decimal("199.00")
                    if price > 0:
                        variant, created = ServiceVariant.objects.get_or_create(
                            service=service,
                            title="Standard",
                            defaults={
                                "description": "Indicative starting price for the standard scope. Confirm materials and any additional quantity before work.",
                                "mrp": _mrp(price),
                                "price": price,
                                "duration_minutes": service.duration_minutes,
                                "included_tasks": [],
                                "attributes": {},
                                "is_active": True,
                            },
                        )
                        if created:
                            counts["standard_variants_created"] += 1
                        elif variant.price <= 0 or not variant.is_active:
                            update_fields = []
                            if variant.price <= 0:
                                variant.price = price
                                variant.mrp = _mrp(price)
                                update_fields.extend(["price", "mrp"])
                            if not variant.is_active:
                                variant.is_active = True
                                update_fields.append("is_active")
                            variant.save(update_fields=update_fields + ["updated_at"])
                            counts["variants_priced"] += int("price" in update_fields)
                        else:
                            counts["existing_nonzero_prices_preserved"] += 1
                    else:
                        counts["fixed_services_still_unpriced"] += 1
                else:
                    service_has_price = False
                    for variant in variants:
                        if variant.price > 0:
                            counts["existing_nonzero_prices_preserved"] += 1
                            service_has_price = True
                            continue
                        price = _package_price(root, service.title, variant.title, variant.attributes)
                        if price <= 0 and not (
                            root == "Home Cleaning"
                            and "full home" in service.title.lower()
                        ):
                            price = _service_base_price(root, service)
                        if price <= 0:
                            price = Decimal("199.00")
                        variant.price = price
                        variant.mrp = _mrp(price)
                        variant.save(update_fields=["price", "mrp", "updated_at"])
                        counts["variants_priced"] += 1
                        service_has_price = True
                    if not service_has_price and not (
                        root == "Home Cleaning" and "full home" in service.title.lower()
                    ):
                        counts["fixed_services_still_unpriced"] += 1

                if (
                    variants
                    and root == "Home Cleaning"
                    and "full home" in service.title.lower()
                    and not service.variants.filter(is_active=True, price__gt=0).exists()
                ):
                    counts["fixed_services_still_unpriced"] += 1

            # Add-ons can still be selected on quote/inspection services; price
            # them independently of the service's base pricing model.
            for addon in service.addons.filter(is_active=True):
                if addon.price > 0:
                    counts["existing_nonzero_prices_preserved"] += 1
                    continue
                price = _addon_price(root, addon.title)
                addon.price = price
                addon.mrp = _mrp(price)
                addon.save(update_fields=["price", "mrp", "updated_at"])
                counts["addons_priced"] += 1

        return counts
