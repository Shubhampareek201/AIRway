from collections import Counter

from django.core.management.base import BaseCommand
from apps.catalog.models import Category, Service
from apps.catalog.pricing import service_pricing_ready


class Command(BaseCommand):
    help = "Read-only audit of AIRway's four launch catalogues, audience tags and customer pricing."

    def handle(self, *args, **options):
        roots = Category.objects.filter(
            parent__isnull=True,
            slug__in=("car-wash", "beauty", "electrical", "home-cleaning"),
        ).order_by("sort_order", "title")

        total = 0
        ready = 0
        for root in roots:
            self.stdout.write(self.style.MIGRATE_HEADING(f"\n{root.title}"))
            category_ids = {root.id}
            frontier = [root.id]
            while frontier:
                child_ids = list(Category.objects.filter(
                    parent_id__in=frontier, is_active=True
                ).values_list("id", flat=True))
                category_ids.update(child_ids)
                frontier = child_ids
            services = Service.objects.filter(
                category_id__in=category_ids,
            ).select_related("category").prefetch_related("variants")
            duplicate_titles = Counter(s.title.strip().casefold() for s in services)
            for service in services.order_by("category__sort_order", "category__title", "sort_order", "title"):
                total += 1
                is_ready = service_pricing_ready(service)
                ready += int(is_ready)
                active_packages = [v for v in service.variants.all() if v.is_active]
                priced_packages = [v for v in active_packages if v.price > 0]
                duplicate = duplicate_titles[service.title.strip().casefold()] > 1
                status = "READY" if is_ready else "NEEDS PRICE / PRICING MODEL"
                self.stdout.write(
                    f"  [{status}] {service.category.title} | {service.title} "
                    f"| audience={service.audience} | type={service.pricing_type} "
                    f"| packages={len(active_packages)} | priced={len(priced_packages)}"
                    f"{' | DUPLICATE TITLE' if duplicate else ''}"
                )

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"Catalogue audit complete: {total} services; {ready} pricing-ready; "
                f"{total - ready} require admin pricing/configuration. No records changed."
            )
        )
