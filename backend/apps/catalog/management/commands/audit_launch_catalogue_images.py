from collections import Counter
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from django.core.management.base import BaseCommand

from apps.catalog.models import Category, Service


LAUNCH_ROOTS = ("car-wash", "beauty", "electrical", "home-cleaning")


def image_field_state(field):
    """Return (state, URL) without assuming the storage backend is local."""
    try:
        name = field.name
        if not name:
            return "MISSING", ""
        url = field.url
    except (ValueError, AttributeError, NotImplementedError):
        return "MISSING", ""

    try:
        if not field.storage.exists(name):
            return "FILE MISSING", url
    except (OSError, NotImplementedError):
        # Remote storages may not support exists consistently.
        pass
    return "PRESENT", url


def fallback_group(title, root_title="", category_title=""):
    """Classify a service using its catalogue context before its title.

    This is an audit hint only; it does not establish that a photo depicts the job.
    """
    value = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
    words = set(value.split())
    root = root_title.lower().strip()
    category = category_title.lower().strip()

    # The catalogue branch is stronger evidence than ambiguous words such as
    # "wash", "wax", "light", or "highlights" in a service title.
    if root == "car wash":
        if "monthly" in words or "plan" in words:
            return "Car wash plan"
        if "interior" in words:
            return "Car interior cleaning"
        if "engine" in words:
            return "Engine bay detailing"
        return "Car care"

    if root == "beauty":
        if category == "facial & skin care":
            return "Facial / skin care"
        if category == "grooming & massage":
            return "Massage / spa" if words & {"massage", "spa"} else "Hair / grooming"
        if category == "hair services":
            return "Massage / spa" if "massage" in words else "Hair / grooming"
        if category == "makeup & occasion styling":
            return "Hair / grooming" if words & {"hairstyle", "hairstyling"} else "Makeup / occasion styling"
        if category == "manicure & pedicure":
            return "Nail care"
        if category == "threading":
            return "Threading"
        if category == "waxing":
            return "Waxing"
        if category == "beauty":
            return "Beauty / salon service"

    if root == "home cleaning":
        if "balcony" in category or "terrace" in category:
            return "Balcony / terrace cleaning"
        if "living room" in category:
            return "Living room cleaning"
        if "bathroom" in category:
            return "Bathroom"
        if "bedroom" in category or "mattress" in category:
            return "Mattress / bedroom"
        if "carpet" in category:
            return "Carpet / rug"
        if "floor" in category:
            return "Floor / tile"
        if "home" in category:
            return "Full-home cleaning"
        if "garden" in category:
            return "Garden"
        if "kitchen" in category:
            return "Kitchen / appliance"
        if "sofa" in category or "upholstery" in category:
            return "Sofa / upholstery"
        if "window" in category or "glass" in category:
            return "Window / glass"
        return "Home cleaning"

    if root == "electrical":
        if "fan" in category:
            return "Fan"
        if "lighting" in category:
            return "Lighting"
        if "switch" in category or "socket" in category:
            return "Switch / socket"
        if "wiring" in category:
            return "Wiring / electrical repair"
        if "inverter" in category or "ups" in category:
            return "Inverter / UPS"
        if "geyser" in category:
            return "Geyser / water heater"
        if "inspection" in category or "setup" in category:
            return "Electrical inspection / setup"

    # Context-free fallback for services outside the launch catalogue.
    groups = (
        ("Fan", {"fan"}),
        ("Lighting", {"chandelier", "lighting", "light", "bulb", "led"}),
        ("Switch / socket", {"switch", "socket", "plug"}),
        ("Wiring / electrical repair", {"wiring", "electrician", "electrical", "mcb", "fuse"}),
        ("Inverter / UPS", {"inverter", "ups", "battery"}),
        ("Geyser / water heater", {"geyser"}),
        ("Facial / skin care", {"facial", "bleaching", "cleanup"}),
        ("Massage / spa", {"massage", "spa"}),
        ("Hair / grooming", {"beard", "shave", "haircut", "hair", "hairstyle", "styling"}),
        ("Nail care", {"nail", "manicure", "pedicure", "polish"}),
        ("Threading", {"threading", "eyebrow"}),
        ("Waxing", {"wax", "underarms", "bikini"}),
        ("Makeup / occasion styling", {"makeup", "bridal", "engagement", "saree"}),
        ("Car care", {"car", "vehicle", "detailing", "coating", "polishing", "paint"}),
    )
    for label, terms in groups:
        if words & terms:
            return label
    return "NO TITLE RULE"


def check_remote_url(url, timeout):
    """Check an absolute HTTP(S) image URL. Relative media URLs are not probed."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return "NOT REMOTE URL"
    request = Request(url, method="HEAD", headers={"User-Agent": "AIRway-image-audit/1.0"})
    try:
        with urlopen(request, timeout=timeout) as response:
            return f"HTTP {response.status}"
    except HTTPError as exc:
        # Some image hosts reject HEAD; retry with a small ranged GET.
        if exc.code not in (403, 405, 501):
            return f"HTTP {exc.code}"
    except (URLError, TimeoutError, OSError):
        pass

    request = Request(
        url, headers={"Range": "bytes=0-0", "User-Agent": "AIRway-image-audit/1.0"}
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return f"HTTP {response.status}"
    except HTTPError as exc:
        return f"HTTP {exc.code}"
    except (URLError, TimeoutError, OSError) as exc:
        return f"UNREACHABLE: {exc.__class__.__name__}"


class Command(BaseCommand):
    help = (
        "Audit launch-catalogue service images for missing uploads, missing storage "
        "files, duplicate assignments and unmatched titles. Optional remote URL checks "
        "verify reachability only, not visual relevance."
    )

    def add_arguments(self, parser):
        parser.add_argument("--all", action="store_true",
                            help="Include inactive services.")
        parser.add_argument("--check-urls", action="store_true",
                            help="Probe absolute HTTP(S) image URLs (may take time).")
        parser.add_argument("--timeout", type=float, default=8.0,
                            help="Timeout per remote image URL in seconds (default: 8).")

    def handle(self, *args, **options):
        include_inactive = options["all"]
        check_urls = options["check_urls"]
        timeout = options["timeout"]
        roots = list(
            Category.objects.filter(parent__isnull=True, slug__in=LAUNCH_ROOTS)
            .order_by("sort_order", "title")
        )
        found = {root.slug for root in roots}
        missing_roots = [slug for slug in LAUNCH_ROOTS if slug not in found]

        self.stdout.write("\nAIRway launch catalogue image audit")
        self.stdout.write("=" * 76)
        if missing_roots:
            self.stderr.write(self.style.ERROR(
                "Missing launch root categories: " + ", ".join(missing_roots)
            ))

        totals = Counter()
        image_urls = Counter()
        remote_results = {}
        unmatched = []

        for root in roots:
            category_ids = [root.id]
            category_ids.extend(
                Category.objects.filter(parent=root).values_list("id", flat=True)
            )
            services = Service.objects.filter(category_id__in=category_ids)
            if not include_inactive:
                services = services.filter(is_active=True)
            services = services.select_related("category").prefetch_related("images")
            services = services.order_by("category__title", "sort_order", "title")

            self.stdout.write(f"\n[{root.title}]")
            for service in services:
                totals["services"] += 1
                fields = [("service", service.image)]
                fields.extend(("gallery", item.image) for item in service.images.all())

                present = []
                broken_storage = []
                for kind, field in fields:
                    state, url = image_field_state(field)
                    if state == "PRESENT":
                        present.append((kind, url))
                        if url:
                            image_urls[url] += 1
                    elif state == "FILE MISSING":
                        broken_storage.append(url)
                        totals["storage_missing"] += 1

                if present:
                    totals["services_with_image"] += 1
                    image_status = f"{len(present)} image(s) present"
                else:
                    totals["services_missing_image"] += 1
                    image_status = "MISSING ADMIN IMAGE/GALLERY"

                if broken_storage:
                    image_status += f"; {len(broken_storage)} storage file(s) missing"

                group = fallback_group(service.title, root.title, service.category.title)
                if group == "NO TITLE RULE":
                    unmatched.append(
                        f"{root.title} > {service.category.title} > {service.title}"
                    )

                self.stdout.write(
                    f"  - {service.category.title} / {service.title} | "
                    f"{image_status} | title group: {group}"
                )

                if check_urls:
                    for kind, url in present:
                        if url not in remote_results:
                            remote_results[url] = check_remote_url(url, timeout)
                        self.stdout.write(
                            f"      {kind} URL: {remote_results[url]} | {url}"
                        )

        duplicates = [(url, count) for url, count in image_urls.items() if count > 1]
        self.stdout.write("\n" + "=" * 76)
        self.stdout.write(f"Services checked: {totals['services']}")
        self.stdout.write(f"Services with Admin image/gallery: {totals['services_with_image']}")
        self.stdout.write(f"Services missing Admin image/gallery: {totals['services_missing_image']}")
        self.stdout.write(f"Referenced storage files missing: {totals['storage_missing']}")
        self.stdout.write(f"Duplicate image URLs: {len(duplicates)}")
        for url, count in duplicates:
            self.stdout.write(self.style.WARNING(f"  DUPLICATE x{count}: {url}"))
        self.stdout.write(f"Titles without a classification rule: {len(unmatched)}")
        for item in unmatched:
            self.stdout.write(self.style.WARNING(f"  NO TITLE RULE: {item}"))

        if check_urls:
            bad = [
                (url, result) for url, result in remote_results.items()
                if not result.startswith("HTTP 2")
            ]
            self.stdout.write(f"Unique remote URLs checked: {len(remote_results)}")
            self.stdout.write(f"Remote URLs not returning 2xx: {len(bad)}")
            for url, result in bad:
                self.stdout.write(self.style.ERROR(f"  {result}: {url}"))

        self.stdout.write(self.style.WARNING(
            "NOTE: URL/storage checks do not recognize image subjects. "
            "A reachable photo may still be wrong for its service title. "
            "Title groups are classification hints, not proof of visual relevance."
        ))
