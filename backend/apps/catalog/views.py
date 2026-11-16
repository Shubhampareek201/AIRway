import json

from rest_framework import generics, permissions
from rest_framework.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import Address
from apps.workers.models import WorkerService
from .models import Banner, Category, FormField, Service, VehicleMake, VehicleModel
from .serializers import BannerSerializer, CategoryTreeSerializer, ServiceSerializer, VehicleMakeSerializer, VehicleModelSerializer
from .pricing import priced_service_ids


def _location_from_address(request):
    # Worker enrolment must see the complete active catalogue, including
    # services that do not yet have an approved worker in any zone.
    if request.query_params.get("for_worker", "").lower() == "true":
        return None

    address_id = request.query_params.get("address_id")
    if not getattr(request.user, "is_authenticated", False):
        if address_id:
            raise ValidationError({"address_id": "Sign in and select a valid saved service address."})
        return None

    addresses = Address.objects.filter(
        user=request.user,
        deleted_at__isnull=True,
        zone__isnull=False,
        zone__is_active=True,
        zone__city__is_active=True,
    ).select_related("zone__city")
    if address_id:
        address = addresses.filter(pk=address_id).first()
    else:
        address = addresses.filter(is_default=True).first() or addresses.order_by("-id").first()
    if address is None:
        if address_id:
            raise ValidationError({"address_id": "Select a valid saved service address in an active service zone."})
        return None

    return address.zone.city, address.zone


def _enrolled_service_ids():
    """
    Customer catalogue visibility depends only on a worker's service enrolment.
    Worker approval, online state, schedule, zone and city do not hide services
    during catalogue browsing or demo testing.
    """
    return set(
        WorkerService.objects.filter(
            service__is_active=True,
            service__category__is_active=True,
        ).values_list("service_id", flat=True).distinct()
    )


def _audience_service_ids(audience):
    """Return services appropriate to the selected customer catalogue audience."""
    if not audience:
        return None
    audience = audience.strip().lower()
    if audience not in ("men", "women", "both"):
        raise ValidationError({"audience": "Choose men, women or both."})
    if audience == "both":
        allowed = [Service.Audience.ALL]
    else:
        allowed = [Service.Audience.ALL, audience]
    return set(Service.objects.filter(
        is_active=True,
        category__is_active=True,
        audience__in=allowed,
    ).values_list("id", flat=True))


LAUNCH_CATEGORY_SLUGS = ("car-wash", "beauty", "electrical", "home-cleaning")


def _launch_catalogue_filter(queryset):
    """Keep launch services inside the four approved trees at any nesting depth."""
    categories = list(
        Category.objects.filter(is_active=True).values("id", "parent_id", "slug")
    )
    children_by_parent = {}
    roots = set()
    for row in categories:
        if row["parent_id"] is None and row["slug"] in LAUNCH_CATEGORY_SLUGS:
            roots.add(row["id"])
        if row["parent_id"] is not None:
            children_by_parent.setdefault(row["parent_id"], []).append(row["id"])

    visible_ids = set(roots)
    pending = list(roots)
    while pending:
        parent_id = pending.pop()
        for child_id in children_by_parent.get(parent_id, []):
            if child_id not in visible_ids:
                visible_ids.add(child_id)
                pending.append(child_id)
    return queryset.filter(category_id__in=visible_ids)


def _customer_priced_service_ids():
    """Exclude draft/zero-price fixed services and unsupported per-unit rates."""
    return priced_service_ids(
        Service.objects.filter(is_active=True, category__is_active=True)
    )


def _is_worker_catalogue_request(request):
    return request.query_params.get("for_worker", "").lower() == "true"


def _category_answers_from_request(request):
    raw = request.query_params.get("category_answers")
    if not raw:
        return {}
    try:
        answers = json.loads(raw)
    except (TypeError, ValueError):
        raise ValidationError({"category_answers": "Provide valid JSON answers."})
    if not isinstance(answers, dict):
        raise ValidationError({"category_answers": "Answers must be a JSON object."})
    return answers


def _category_answer_service_ids(answers):
    """Filter Car Wash and Electrical services using selected category answers."""
    vehicle_service_ids = None
    vehicle_kind = answers.get("vehicle_kind") if isinstance(answers, dict) else None
    if vehicle_kind not in (None, ""):
        selected = str(vehicle_kind).strip().casefold()
        if selected not in ("car", "bike"):
            raise ValidationError({"category_answers": "Choose Car or Bike."})
        root_ids = list(Category.objects.filter(
            slug="car-wash", parent__isnull=True, is_active=True
        ).values_list("id", flat=True))
        branch = Category.objects.filter(
            parent_id__in=root_ids, slug=selected, is_active=True
        ).first()
        if branch:
            car_wash_ids = set()
            pending = list(Category.objects.filter(
                parent_id__in=root_ids, is_active=True
            ).values_list("id", flat=True))
            while pending:
                category_id = pending.pop()
                if category_id in car_wash_ids:
                    continue
                car_wash_ids.add(category_id)
                pending.extend(Category.objects.filter(
                    parent_id=category_id, is_active=True
                ).values_list("id", flat=True))
            selected_branch_ids = {branch.id}
            pending = [branch.id]
            while pending:
                category_id = pending.pop()
                for child_id in Category.objects.filter(
                    parent_id=category_id, is_active=True
                ).values_list("id", flat=True):
                    if child_id not in selected_branch_ids:
                        selected_branch_ids.add(child_id)
                        pending.append(child_id)
            matching_ids = set(Service.objects.filter(
                is_active=True, category_id__in=selected_branch_ids
            ).values_list("id", flat=True))
            other_ids = set(Service.objects.filter(
                is_active=True, category__is_active=True
            ).exclude(category_id__in=car_wash_ids).values_list("id", flat=True))
            vehicle_service_ids = matching_ids | other_ids

    work_type = answers.get("work_type") if isinstance(answers, dict) else None
    if work_type in (None, ""):
        return vehicle_service_ids

    electrical_roots = list(Category.objects.filter(
        slug="electrical", parent__isnull=True, is_active=True
    ))
    if not electrical_roots:
        return vehicle_service_ids

    # Prefer the admin-authored category flow mapping. This keeps Electrical
    # filtering aligned with the exact subcategory branches shown in Flutter.
    selected = str(work_type).strip().casefold()
    mapped_slugs = set()
    for root in electrical_roots:
        for step in root.flow_steps or []:
            if not isinstance(step, dict) or step.get("key") != "work_type":
                continue
            child_slugs = step.get("child_slugs")
            if not isinstance(child_slugs, dict):
                continue
            configured = child_slugs.get(work_type)
            if configured is None:
                configured = next(
                    (value for key, value in child_slugs.items()
                     if str(key).strip().casefold() == selected),
                    None,
                )
            if isinstance(configured, list):
                mapped_slugs.update(
                    str(slug).strip().casefold()
                    for slug in configured
                    if str(slug).strip()
                )

    electrical_category_ids = set()
    pending = [root.id for root in electrical_roots]
    children_by_parent = {}
    for row in Category.objects.filter(is_active=True).values("id", "parent_id", "slug"):
        if row["parent_id"] is not None:
            children_by_parent.setdefault(row["parent_id"], []).append(row)

    while pending:
        parent_id = pending.pop()
        for child in children_by_parent.get(parent_id, []):
            child_id = child["id"]
            if child_id in electrical_category_ids:
                continue
            electrical_category_ids.add(child_id)
            pending.append(child_id)

    if mapped_slugs:
        # Include descendants of each selected branch, but not sibling branches.
        allowed_category_ids = set()
        pending = [
            row["id"]
            for root in electrical_roots
            for row in children_by_parent.get(root.id, [])
            if row["slug"].casefold() in mapped_slugs
        ]
        while pending:
            category_id = pending.pop()
            if category_id in allowed_category_ids:
                continue
            allowed_category_ids.add(category_id)
            pending.extend(
                row["id"] for row in children_by_parent.get(category_id, [])
            )
        allowed_service_ids = set(Service.objects.filter(
            is_active=True, category_id__in=allowed_category_ids
        ).values_list("id", flat=True))
    else:
        # Backward compatibility for catalogues configured with a service-level
        # FormField named work_type rather than category child_slugs.
        electrical_service_ids = set(Service.objects.filter(
            is_active=True, category_id__in=electrical_category_ids
        ).values_list("id", flat=True))
        allowed_service_ids = set()
        fields = FormField.objects.filter(
            service_id__in=electrical_service_ids,
            key="work_type",
            is_active=True,
        ).values_list("service_id", "options")
        for service_id, options in fields:
            for option in options or []:
                value = option.get("value", option.get("label")) if isinstance(option, dict) else option
                if value is not None and str(value).strip().casefold() == selected:
                    allowed_service_ids.add(service_id)
                    break

        # If neither admin mapping style is configured, do not accidentally
        # hide every Electrical service from customers.
        if not allowed_service_ids:
            allowed_service_ids = electrical_service_ids

    non_electrical_ids = set(Service.objects.filter(
        is_active=True, category__is_active=True
    ).exclude(category_id__in=electrical_category_ids).values_list("id", flat=True))
    electrical_result = non_electrical_ids | allowed_service_ids
    return electrical_result if vehicle_service_ids is None else electrical_result & vehicle_service_ids


def _visible_category_ids(service_ids):
    category_ids = set(
        Service.objects.filter(
            pk__in=service_ids,
            category__is_active=True,
        ).values_list("category_id", flat=True)
    )
    all_categories = list(
        Category.objects.filter(is_active=True).values("id", "parent_id")
    )
    parent_by_id = {row["id"]: row["parent_id"] for row in all_categories}
    visible_ids = set(category_ids)

    for category_id in list(category_ids):
        parent_id = parent_by_id.get(category_id)
        while parent_id is not None and parent_id not in visible_ids:
            visible_ids.add(parent_id)
            parent_id = parent_by_id.get(parent_id)

    return visible_ids


class CategoryListView(generics.ListAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = CategoryTreeSerializer

    def _visible_service_ids(self):
        if _is_worker_catalogue_request(self.request):
            service_ids = None
        else:
            service_ids = _enrolled_service_ids()
        # priced_only is an explicit catalogue constraint and applies to
        # customer and worker catalogue requests alike.
        if self.request.query_params.get("priced_only", "").lower() == "true":
            priced_ids = _customer_priced_service_ids()
            service_ids = priced_ids if service_ids is None else service_ids & priced_ids

        audience_ids = _audience_service_ids(self.request.query_params.get("audience"))
        if audience_ids is not None:
            service_ids = audience_ids if service_ids is None else service_ids & audience_ids

        category_answers = _category_answers_from_request(self.request)
        answer_ids = _category_answer_service_ids(category_answers)
        if answer_ids is not None:
            service_ids = answer_ids if service_ids is None else service_ids & answer_ids
        return service_ids

    def get_serializer_context(self):
        context = super().get_serializer_context()
        service_ids = self._visible_service_ids()
        context["visible_category_ids"] = (
            None if service_ids is None else _visible_category_ids(service_ids)
        )
        return context

    def get_queryset(self):
        queryset = Category.objects.filter(is_active=True, parent__isnull=True)
        service_ids = self._visible_service_ids()
        if service_ids is not None:
            queryset = queryset.filter(pk__in=_visible_category_ids(service_ids))
        if self.request.query_params.get("launch_only", "").lower() == "true":
            queryset = queryset.filter(slug__in=LAUNCH_CATEGORY_SLUGS)
        return queryset.prefetch_related("children", "audience_options", "children__audience_options")


class ServiceListView(generics.ListAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = ServiceSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["priced_only"] = (
            self.request.query_params.get("priced_only", "").lower() == "true"
        )
        context["available_service_ids"] = (
            None if _is_worker_catalogue_request(self.request) else _enrolled_service_ids()
        )
        # Do not hide package variants based on worker online state, schedule,
        # capabilities or zone while the customer browses the demo catalogue.
        context["available_variant_ids"] = None
        return context

    def get_queryset(self):
        queryset = Service.objects.filter(is_active=True, category__is_active=True).select_related(
            "category"
        ).prefetch_related(
            "images", "variants", "addons", "form_fields"
        )
        if self.request.query_params.get("launch_only", "").lower() == "true":
            queryset = _launch_catalogue_filter(queryset)
        if self.request.query_params.get("priced_only", "").lower() == "true":
            queryset = queryset.filter(pk__in=_customer_priced_service_ids())

        visible_service_ids = (
            None if _is_worker_catalogue_request(self.request) else _enrolled_service_ids()
        )
        audience_ids = _audience_service_ids(self.request.query_params.get("audience"))
        if audience_ids is not None:
            visible_service_ids = audience_ids if visible_service_ids is None else visible_service_ids & audience_ids
        if visible_service_ids is not None:
            queryset = queryset.filter(pk__in=visible_service_ids)

        category_answers = _category_answers_from_request(self.request)
        answer_service_ids = _category_answer_service_ids(category_answers)
        if answer_service_ids is not None:
            queryset = queryset.filter(pk__in=answer_service_ids)

        category_id = self.request.query_params.get("category")
        if category_id:
            queryset = queryset.filter(category_id=category_id)

        is_popular = self.request.query_params.get("is_popular")
        if is_popular and is_popular.lower() == "true":
            queryset = queryset.filter(is_popular=True)

        return queryset


class ServiceDetailView(generics.RetrieveAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = ServiceSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["priced_only"] = (
            self.request.query_params.get("priced_only", "").lower() == "true"
        )
        context["available_service_ids"] = (
            None if _is_worker_catalogue_request(self.request) else _enrolled_service_ids()
        )
        # Do not hide package variants based on worker online state, schedule,
        # capabilities or zone while the customer browses the demo catalogue.
        context["available_variant_ids"] = None
        return context

    def get_queryset(self):
        queryset = Service.objects.filter(
            is_active=True, category__is_active=True
        ).select_related("category").prefetch_related(
            "images", "variants", "addons", "form_fields"
        )
        if self.request.query_params.get("launch_only", "").lower() == "true":
            queryset = _launch_catalogue_filter(queryset)
        if (
            not _is_worker_catalogue_request(self.request)
            and self.request.query_params.get("priced_only", "").lower() == "true"
        ):
            queryset = queryset.filter(pk__in=_customer_priced_service_ids())
        visible_service_ids = (
            None if _is_worker_catalogue_request(self.request) else _enrolled_service_ids()
        )
        audience_ids = _audience_service_ids(self.request.query_params.get("audience"))
        if audience_ids is not None:
            visible_service_ids = audience_ids if visible_service_ids is None else visible_service_ids & audience_ids
        if visible_service_ids is not None:
            queryset = queryset.filter(pk__in=visible_service_ids)

        category_answers = _category_answers_from_request(self.request)
        answer_service_ids = _category_answer_service_ids(category_answers)
        if answer_service_ids is not None:
            queryset = queryset.filter(pk__in=answer_service_ids)

        return queryset


class BannerListView(generics.ListAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = BannerSerializer

    def get_queryset(self):
        now = timezone.now()
        queryset = Banner.objects.filter(is_active=True).filter(
            Q(starts_at__isnull=True) | Q(starts_at__lte=now),
            Q(ends_at__isnull=True) | Q(ends_at__gte=now),
        ).select_related("link_service", "city")

        location = _location_from_address(self.request)
        if location is None:
            queryset = queryset.filter(city__isnull=True)
        else:
            city, _zone = location
            queryset = queryset.filter(Q(city__isnull=True) | Q(city=city))

        return queryset.order_by("sort_order", "id")


class VehicleMakeListView(generics.ListAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = VehicleMakeSerializer

    def get_queryset(self):
        queryset = VehicleMake.objects.filter(is_active=True)
        vehicle_type = self.request.query_params.get("vehicle_type")
        if vehicle_type in ("car", "bike"):
            queryset = queryset.filter(vehicle_type=vehicle_type)
        vehicle_class = self.request.query_params.get("vehicle_class")
        if vehicle_class:
            queryset = queryset.filter(models__is_active=True, models__vehicle_class__iexact=vehicle_class).distinct()
        search = self.request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(name__icontains=search)
        return queryset


class VehicleModelListView(generics.ListAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = VehicleModelSerializer

    def get_queryset(self):
        queryset = VehicleModel.objects.filter(is_active=True, make__is_active=True).select_related("make")
        make_id = self.request.query_params.get("make")
        vehicle_type = self.request.query_params.get("vehicle_type")
        if make_id:
            queryset = queryset.filter(make_id=make_id)
        if vehicle_type in ("car", "bike"):
            queryset = queryset.filter(make__vehicle_type=vehicle_type)
        vehicle_class = self.request.query_params.get("vehicle_class")
        if vehicle_class:
            queryset = queryset.filter(vehicle_class__iexact=vehicle_class)
        search = self.request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(name__icontains=search)
        return queryset
