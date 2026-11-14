from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from apps.accounts.models import Address
from apps.catalog.models import Category, CityService, Service
from apps.catalog.pricing import service_pricing_ready
from apps.workers.models import WorkerProfile, WorkerService


LAUNCH_ROOTS = ("car-wash", "beauty", "electrical", "home-cleaning")


class Command(BaseCommand):
    help = (
        "Read-only diagnosis of why launch services are or are not visible "
        "to a customer at a selected saved address."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--address-id",
            type=int,
            required=True,
            help="Saved customer address ID to diagnose. No address data is changed.",
        )

    def handle(self, *args, **options):
        address = Address.objects.select_related("zone__city").filter(
            pk=options["address_id"],
            deleted_at__isnull=True,
        ).first()
        if address is None:
            raise CommandError("No active saved address found for that ID.")

        zone = address.zone
        city = zone.city if zone else None
        valid_location = bool(
            zone and zone.is_active and city and city.is_active
        )

        self.stdout.write(self.style.MIGRATE_HEADING("AIRway customer catalogue visibility diagnosis"))
        self.stdout.write(f"Address ID: {address.pk}")
        self.stdout.write(f"City: {city.name if city else 'NOT SET'}")
        self.stdout.write(f"Zone: {zone.name if zone else 'NOT SET'}")
        self.stdout.write(f"City active: {bool(city and city.is_active)}")
        self.stdout.write(f"Zone active: {bool(zone and zone.is_active)}")
        self.stdout.write(f"Location accepted by customer catalogue: {valid_location}")
        self.stdout.write("")

        active_categories = list(
            Category.objects.filter(is_active=True).values("id", "parent_id", "slug", "title")
        )
        children = {}
        by_id = {}
        for row in active_categories:
            by_id[row["id"]] = row
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
                category_id__in=category_ids
            ).select_related("category").prefetch_related("variants").order_by(
                "category__sort_order", "sort_order", "title"
            )

            self.stdout.write(self.style.MIGRATE_HEADING(roots[0]["title"]))
            root_visible = 0
            for service in services:
                reasons = []
                if not service.is_active:
                    reasons.append("service inactive")
                if not service.category.is_active:
                    reasons.append("category inactive")

                priced = service_pricing_ready(service)
                if not priced:
                    reasons.append("pricing not ready")

                city_hidden = bool(
                    city and CityService.objects.filter(
                        city=city, service=service, is_active=False
                    ).exists()
                )
                if city_hidden:
                    reasons.append("hidden by inactive CityService row")

                worker_count = 0
                if valid_location:
                    worker_count = WorkerService.objects.filter(
                        service=service,
                        worker__status=WorkerProfile.Status.APPROVED,
                        worker__worker_zones__zone=zone,
                        worker__worker_zones__zone__is_active=True,
                        worker__worker_zones__zone__city=city,
                        worker__worker_zones__zone__city__is_active=True,
                    ).filter(
                        Q(service__requires_female_worker=False)
                        | Q(worker__gender=WorkerProfile.Gender.FEMALE)
                    ).values("worker_id").distinct().count()

                if not valid_location:
                    reasons.append("selected address has no active city/zone")
                elif worker_count == 0:
                    reasons.append("no approved worker enrolled for this service in this zone")

                visible = (
                    service.is_active and service.category.is_active and priced
                    and not city_hidden and valid_location and worker_count > 0
                )
                if visible:
                    root_visible += 1
                    total_visible += 1

                active_variants = [v for v in service.variants.all() if v.is_active]
                priced_variants = [v for v in active_variants if v.price > 0]
                state = "VISIBLE" if visible else "HIDDEN"
                detail = "; ".join(reasons) if reasons else "all visibility checks passed"
                self.stdout.write(
                    f"  [{state}] service #{service.pk} {service.title} | "
                    f"price_ready={priced} | approved_workers_in_zone={worker_count} | "
                    f"active_variants={len(active_variants)} | priced_variants={len(priced_variants)}"
                )
                if not visible:
                    self.stdout.write(f"      Reason: {detail}")

            self.stdout.write(f"  Customer-visible services in this category: {root_visible}")
            self.stdout.write("")

        self.stdout.write(self.style.SUCCESS(
            f"Diagnosis complete. Total customer-visible launch services: {total_visible}. "
            "Read-only: no database records were changed."
        ))
