import json
from datetime import datetime, timezone
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.catalog.models import (
    AddOn,
    Category,
    CityService,
    FormField,
    Service,
    ServiceVariant,
)
from apps.workers.models import WorkerService


LAUNCH_ROOT_SLUGS = ("beauty", "car-wash", "electrical", "home-cleaning")


def image_name(field_file):
    return field_file.name if field_file and field_file.name else None


class Command(BaseCommand):
    help = (
        "Export the AIRway launch service catalogue and configuration as JSON. "
        "Read-only: this command only performs database SELECT queries."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            required=True,
            help="JSON output path, e.g. launch_booking_catalogue_audit.json",
        )

    def handle(self, *args, **options):
        output_path = Path(options["output"]).expanduser()
        if output_path.exists():
            raise CommandError(
                f"Refusing to overwrite existing file: {output_path}. "
                "Choose a new --output filename."
            )

        categories = list(
            Category.objects.all().only(
                "id", "parent_id", "title", "title_hi", "slug",
                "flow_steps", "sort_order", "is_active", "image"
            ).order_by("sort_order", "title")
        )
        children_by_parent = {}
        for category in categories:
            children_by_parent.setdefault(category.parent_id, []).append(category)

        roots = [
            category for category in categories
            if category.parent_id is None and category.slug in LAUNCH_ROOT_SLUGS
        ]
        if not roots:
            raise CommandError(
                "No launch root categories found. Expected slugs: "
                + ", ".join(LAUNCH_ROOT_SLUGS)
            )

        selected_categories = {}
        root_category_ids = {}
        for root in roots:
            stack = [root]
            root_ids = []
            while stack:
                current = stack.pop()
                if current.id in selected_categories:
                    continue
                selected_categories[current.id] = current
                root_ids.append(current.id)
                stack.extend(reversed(children_by_parent.get(current.id, [])))
            root_category_ids[root.slug] = root_ids

        services = list(
            Service.objects.filter(category_id__in=selected_categories.keys())
            .select_related("category")
            .order_by("category__sort_order", "category__title", "sort_order", "title")
        )
        service_ids = [service.id for service in services]

        variants_by_service = {}
        for item in ServiceVariant.objects.filter(service_id__in=service_ids).order_by(
            "service_id", "sort_order", "price", "title"
        ):
            variants_by_service.setdefault(item.service_id, []).append({
                "id": item.id,
                "title": item.title,
                "title_hi": item.title_hi,
                "description": item.description,
                "price": str(item.price),
                "mrp": str(item.mrp),
                "is_active": item.is_active,
                "duration_minutes": item.duration_minutes,
                "attributes": item.attributes,
                "included_tasks": item.included_tasks,
                "image": image_name(item.image),
                "sort_order": item.sort_order,
            })

        addons_by_service = {}
        for item in AddOn.objects.filter(service_id__in=service_ids).order_by(
            "service_id", "sort_order", "price", "title"
        ):
            addons_by_service.setdefault(item.service_id, []).append({
                "id": item.id,
                "title": item.title,
                "title_hi": item.title_hi,
                "description": item.description,
                "price": str(item.price),
                "mrp": str(item.mrp),
                "is_active": item.is_active,
                "image": image_name(item.image),
                "sort_order": item.sort_order,
            })

        fields_by_service = {}
        for item in FormField.objects.filter(service_id__in=service_ids).order_by(
            "service_id", "sort_order", "id"
        ):
            fields_by_service.setdefault(item.service_id, []).append({
                "id": item.id,
                "key": item.key,
                "label": item.label,
                "label_hi": item.label_hi,
                "field_type": item.field_type,
                "options": item.options,
                "is_active": item.is_active,
                "is_required": item.is_required,
                "sort_order": item.sort_order,
            })

        city_services_by_service = {}
        for item in CityService.objects.filter(service_id__in=service_ids).select_related(
            "city"
        ).order_by("service_id", "city__name"):
            city_services_by_service.setdefault(item.service_id, []).append({
                "city": item.city.name,
                "city_is_active": item.city.is_active,
                "is_active": item.is_active,
            })

        worker_counts = {}
        worker_rows = WorkerService.objects.filter(
            service_id__in=service_ids
        ).values_list(
            "service_id", "worker__status", "worker__is_online"
        )
        for service_id, status, is_online in worker_rows:
            counts = worker_counts.setdefault(
                service_id, {"mapped_total": 0, "approved": 0, "approved_online": 0}
            )
            counts["mapped_total"] += 1
            if status == "approved":
                counts["approved"] += 1
                if is_online:
                    counts["approved_online"] += 1

        category_data = []
        for category in sorted(
            selected_categories.values(),
            key=lambda c: (c.sort_order, c.title.lower())
        ):
            category_data.append({
                "id": category.id,
                "parent_id": category.parent_id,
                "title": category.title,
                "title_hi": category.title_hi,
                "slug": category.slug,
                "is_active": category.is_active,
                "sort_order": category.sort_order,
                "flow_steps": category.flow_steps,
                "image": image_name(category.image),
            })

        service_data = []
        for service in services:
            service_data.append({
                "id": service.id,
                "category_id": service.category_id,
                "category_title": service.category.title,
                "category_slug": service.category.slug,
                "title": service.title,
                "title_hi": service.title_hi,
                "description": service.description,
                "is_active": service.is_active,
                "is_popular": service.is_popular,
                "sort_order": service.sort_order,
                "image": image_name(service.image),
                "gallery_images": [
                    image_name(img.image)
                    for img in service.images.all()
                    if image_name(img.image)
                ],
                "booking_mode": service.booking_mode,
                "pricing_type": service.pricing_type,
                "unit_label": service.unit_label,
                "visit_fee": str(service.visit_fee),
                "duration_minutes": service.duration_minutes,
                "buffer_minutes": service.buffer_minutes,
                "audience": service.audience,
                "requires_female_worker": service.requires_female_worker,
                "variants": variants_by_service.get(service.id, []),
                "addons": addons_by_service.get(service.id, []),
                "form_fields": fields_by_service.get(service.id, []),
                "city_availability": city_services_by_service.get(service.id, []),
                "worker_counts": worker_counts.get(
                    service.id,
                    {"mapped_total": 0, "approved": 0, "approved_online": 0},
                ),
            })

        payload = {
            "export_type": "airway_launch_booking_catalogue_audit",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "read_only": True,
            "launch_root_slugs_expected": list(LAUNCH_ROOT_SLUGS),
            "launch_roots_found": [
                {"id": root.id, "title": root.title, "slug": root.slug, "is_active": root.is_active}
                for root in roots
            ],
            "counts": {
                "categories_in_launch_trees": len(category_data),
                "services_in_launch_trees": len(service_data),
                "active_services": sum(1 for s in services if s.is_active),
                "inactive_services": sum(1 for s in services if not s.is_active),
            },
            "categories": category_data,
            "services": service_data,
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        self.stdout.write(self.style.SUCCESS(
            f"Read-only catalogue export created: {output_path.resolve()}"
        ))
        self.stdout.write(
            f"Categories: {len(category_data)} | Services: {len(service_data)} "
            f"| Active services: {payload['counts']['active_services']}"
        )
        self.stdout.write(
            "No customer data, worker names, phone numbers, addresses, credentials, "
            "or payment data are exported."
        )
