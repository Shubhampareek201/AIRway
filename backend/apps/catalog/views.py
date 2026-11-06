from rest_framework import generics, permissions
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Address
from apps.workers.eligibility import eligible_worker_profiles
from .models import Category, CityService, Service
from .serializers import CategoryTreeSerializer, ServiceSerializer


def _location_from_address(request):
    address_id = request.query_params.get("address_id")
    if not address_id:
        return None

    address = Address.objects.filter(
        pk=address_id,
        user=request.user,
        deleted_at__isnull=True,
        zone__isnull=False,
        zone__is_active=True,
        zone__city__is_active=True,
    ).select_related("zone__city").first()
    if address is None:
        raise ValidationError({"address_id": "Select a valid saved service address in an active service zone."})

    return address.zone.city, address.zone


def _city_service_ids(city, zone=None):
    """
    Return city-enabled services that have at least one approved, online,
    service-skilled worker with an active schedule in the requested area.
    If a zone is supplied, serviceability is checked for that exact zone.
    """
    if city is None:
        return None

    # Catalogue visibility is based on city configuration, not live worker
    # availability. Customers should still see services with no worker online.
    return CityService.objects.filter(
        city=city,
        is_active=True,
        service__is_active=True,
        service__category__is_active=True,
    ).values_list("service_id", flat=True)


def _available_service_ids(city, zone=None):
    if city is None:
        return None
    return set(
        eligible_worker_profiles(city=city, zone=zone)
        .values_list("worker_services__service_id", flat=True)
        .distinct()
    )


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

    def get_serializer_context(self):
        context = super().get_serializer_context()
        location = _location_from_address(self.request)
        if location is None:
            context["visible_category_ids"] = None
            return context

        city, zone = location
        context["visible_category_ids"] = _visible_category_ids(
            _city_service_ids(city, zone=zone)
        )
        return context

    def get_queryset(self):
        location = _location_from_address(self.request)
        queryset = Category.objects.filter(is_active=True, parent__isnull=True)
        if location is not None:
            city, zone = location
            visible_ids = _visible_category_ids(
                _city_service_ids(city, zone=zone)
            )
            queryset = queryset.filter(id__in=visible_ids)
        return queryset.prefetch_related("children")


class ServiceListView(generics.ListAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = ServiceSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        location = _location_from_address(self.request)
        context["available_service_ids"] = (
            None if location is None else _available_service_ids(*location)
        )
        return context

    def get_queryset(self):
        queryset = Service.objects.filter(is_active=True, category__is_active=True).select_related(
            "category"
        ).prefetch_related(
            "images", "variants", "addons", "form_fields"
        )

        location = _location_from_address(self.request)
        if location is not None:
            city, zone = location
            queryset = queryset.filter(
                pk__in=_city_service_ids(city, zone=zone)
            )

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
        location = _location_from_address(self.request)
        context["available_service_ids"] = (
            None if location is None else _available_service_ids(*location)
        )
        return context

    def get_queryset(self):
        queryset = Service.objects.filter(
            is_active=True, category__is_active=True
        ).select_related("category").prefetch_related(
            "images", "variants", "addons", "form_fields"
        )
        location = _location_from_address(self.request)
        if location is not None:
            city, zone = location
            queryset = queryset.filter(pk__in=_city_service_ids(city, zone=zone))
        return queryset
