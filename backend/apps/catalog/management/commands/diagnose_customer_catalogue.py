from django.core.management.base import BaseCommand
from django.db.models import Count

from apps.catalog.models import Category, Service
from apps.catalog.pricing import service_pricing_ready


LAUNCH_ROOTS = ("car-wash", "beauty", "electrical", "home-cleaning")


class Command(BaseCommand):
    help = (
        "Read-only diagnosis of customer catalogue visibility. Visibility is "
        "based on active launch service + worker enrolment + usable demo price; "
        "worker status, online state, zone and selected address do not filter it."
    )

    def handle(self, *args, **options):
        active_categories = list(
            Category.objects.filter(is_active=True).values("id", "parent_id", "slug", "title")
        )
        children = {}
        for row in active_categories:
            if row["parent_id"] is not None:
                children.setdefault(row["parent_id"], []).append(row["id"])

        total_visible = 0
        for root_slug in LAUNCH_ROOTS:
            roots = [
                row for row in active_categories
                if row["parent_id"] is None and row["slug"] == root_slug
            ]
            if not roots:
                self.stdout.write(self.style.ERROR(f"[MISSING ROOT] {root_slug}"))
                continue

            category_ids = set()
            pending = [row["id"] for row in roots]
            while pending:
                current = pending.pop()
                if current in category_ids:
                    continue
                category_ids.add(current)
                pending.extend(children.get(current, []))

            services = Service.objects.filter(
                category_id__in=category_ids,
                is_active=True,
                category__is_active=True,
            ).select_related("category").prefetch_related("variants").annotate(
                worker_enrolment_count=Count("assigned_workers", distinct=True)
            ).order_by("category__sort_order", "sort_order", "title")

            self.stdout.write(self.style.MIGRATE_HEADING(roots[0]["title"]))
            root_visible = 0
            for service in services:
                priced = service_pricing_ready(service)
                worker_count = service.worker_enrolment_count
                visible = priced and worker_count > 0
                reasons = []
                if not priced:
                    reasons.append("demo pricing not ready")
                if worker_count == 0:
                    reasons.append("no worker enrolled for this service")

                active_variants = [v for v in service.variants.all() if v.is_active]
                priced_variants = [v for v in active_variants if v.price > 0]
                state = "VISIBLE" if visible else "HIDDEN"
                detail = "; ".join(reasons) if reasons else "enrolled and demo-priced"
                self.stdout.write(
                    f"  [{state}] service #{service.pk} {service.title} | "
                    f"pricing_ready={priced} | worker_enrolments={worker_count} | "
                    f"active_variants={len(active_variants)} | priced_variants={len(priced_variants)}"
                )
                if visible:
                    root_visible += 1
                    total_visible += 1
                else:
                    self.stdout.write(f"      Reason: {detail}")

            self.stdout.write(f"  Customer-visible services in this category: {root_visible}")
            self.stdout.write("")

        self.stdout.write(self.style.SUCCESS(
            f"Diagnosis complete. Total customer-visible launch services: {total_visible}. "
            "Read-only: no database records were changed."
        ))
