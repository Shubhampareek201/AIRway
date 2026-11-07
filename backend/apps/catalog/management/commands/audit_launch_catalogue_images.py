from collections import Counter
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


def fallback_group(title):
    """Broad title intent classification; this does not verify photo content."""
    value = title.lower()
    groups = (
        ("Fan", ("fan",)),
        ("Lighting", ("chandelier", "ceiling light", "wall light", "tube light",
                      "panel light", "strip light", "decorative light", "outdoor light",
                      "lighting", "light", "bulb", "led")),
        ("Switch / wiring / electrical repair", ("switch", "socket", "plug", "wiring",
                                                   "short circuit", "mcb", "fuse",
                                                   "electrician", "electrical")),
        ("Inverter / UPS", ("inverter", "ups", "battery backup")),
        ("Geyser / water heater", ("geyser", "water heater")),
        ("Sofa / upholstery", ("sofa", "upholstery", "cushion", "chair cleaning")),
        ("Kitchen / appliance", ("kitchen", "chimney", "refrigerator", "fridge",
                                  "microwave", "oven")),
        ("Bathroom", ("bathroom", "toilet", "washbasin", "sanitary")),
        ("Window / glass", ("window", "glass")),
        ("Mattress / bedroom", ("mattress", "bedroom", "bed cleaning")),
        ("Carpet / rug", ("carpet", "rug")),
        ("Floor / tile / outdoor", ("floor", "tile", "marble", "grout", "terrace",
                                     "balcony", "outdoor")),
        ("Garden", ("garden", "plant", "lawn")),
        ("Full-home cleaning", ("full home", "deep home", "move-in", "move-out",
                                 "home cleaning", "house cleaning", "general cleaning",
                                 "dusting", "maid")),
    )
    for label, terms in groups:
        if any(term in value for term in terms):
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

                group = fallback_group(service.title)
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
