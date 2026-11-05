from rest_framework import generics, permissions
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Address
from .models import Category, CityService, Service
from .serializers import CategoryTreeSerializer, ServiceSerializer


def _city_from_address(request):
    address_id = request.query_params.get("address_id")
    if not address_id:
        return None
    address = Address.objects.filter(
        pk=address_id,
        user=request.user,
        deleted_at__isnull=True,
        zone__isnull=False,
    ).select_related("zone__city").first()
    if address is None:
        raise ValidationError({"address_id": "Select a valid saved service address."})
    if not address.zone.city.is_active:
        raise ValidationError({"address_id": "Services are not available in this city yet."})
    return address.zone.city


def _city_service_ids(city):
    if city is None:
        return None
    return CityService.objects.filter(
        city=city, is_active=True, service__is_active=True
    ).values_list("service_id", flat=True)


class CategoryListView(generics.ListAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = CategoryTreeSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        city = _city_from_address(self.request)
        if city is None:
            context["visible_category_ids"] = None
            return context

        service_ids = _city_service_ids(city)
        visible_ids = set(
            Service.objects.filter(
                pk__in=service_ids,
                category__is_active=True,
            ).values_list("category_id", flat=True)
        )
        all_categories = list(
            Category.objects.filter(is_active=True).values("id", "parent_id")
        )
        parent_by_id = {row["id"]: row["parent_id"] for row in all_categories}
        for category_id in list(visible_ids):
            parent_id = parent_by_id.get(category_id)
            while parent_id is not None:
                visible_ids.add(parent_id)
                parent_id = parent_by_id.get(parent_id)
        context["visible_category_ids"] = visible_ids
        return context

    def get_queryset(self):
        city = _city_from_address(self.request)
        queryset = Category.objects.filter(is_active=True, parent__isnull=True)
        if city is not None:
            service_ids = _city_service_ids(city)
            available_category_ids = set(
                Service.objects.filter(
                    pk__in=service_ids,
                    category__is_active=True,
                ).values_list("category_id", flat=True)
            )
            # Include each active ancestor so nested category paths remain navigable.
            all_categories = list(Category.objects.filter(is_active=True).values("id", "parent_id"))
            parent_by_id = {row["id"]: row["parent_id"] for row in all_categories}
            visible_ids = set(available_category_ids)
            for category_id in list(available_category_ids):
                parent_id = parent_by_id.get(category_id)
                while parent_id is not None and parent_id not in visible_ids:
                    visible_ids.add(parent_id)
                    parent_id = parent_by_id.get(parent_id)
            queryset = queryset.filter(id__in=visible_ids)
        return queryset.prefetch_related("children")


class ServiceListView(generics.ListAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = ServiceSerializer

    def get_queryset(self):
        queryset = Service.objects.filter(is_active=True, category__is_active=True).select_related(
            "category"
        ).prefetch_related(
            "images", "variants", "addons", "form_fields"
        )

        city = _city_from_address(self.request)
        if city is not None:
            queryset = queryset.filter(
                pk__in=_city_service_ids(city)
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

    def get_queryset(self):
        queryset = Service.objects.filter(
            is_active=True, category__is_active=True
        ).select_related("category").prefetch_related(
            "images", "variants", "addons", "form_fields"
        )
        city = _city_from_address(self.request)
        if city is not None:
            queryset = queryset.filter(pk__in=_city_service_ids(city))
        return queryset
