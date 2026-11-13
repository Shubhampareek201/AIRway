from rest_framework import generics, permissions
from rest_framework.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import Address
from apps.workers.eligibility import eligible_worker_profiles
from apps.workers.models import WorkerProfile, WorkerService
from .models import Banner, Category, CityService, Service
from .serializers import BannerSerializer, CategoryTreeSerializer, ServiceSerializer


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


def _city_service_ids(city, zone=None):
    """
    CityService is an explicit city-level opt-out: an inactive row hides that
    service in the selected city. The customer catalogue applies this city
    publication rule together with the eligible-worker service filter.
    """
    if city is None:
        return None

    hidden_ids = set(
        CityService.objects.filter(
            city=city,
            is_active=False,
        ).values_list("service_id", flat=True)
    )
    active_ids = set(
        Service.objects.filter(
            is_active=True,
            category__is_active=True,
        ).values_list("id", flat=True)
    )
    return active_ids - hidden_ids

def _enrolled_service_ids(city, zone=None):
    """
    Services visible to customers are based on approved worker enrolments
    in the selected zone, not on whether a worker happens to be online
    or scheduled at the moment the catalogue is opened.
    """
    if city is None:
        return None

    links = WorkerService.objects.filter(
        worker__status=WorkerProfile.Status.APPROVED,
        worker__worker_zones__zone__city=city,
        worker__worker_zones__zone__is_active=True,
        worker__worker_zones__zone__city__is_active=True,
        service__is_active=True,
        service__category__is_active=True,
    )
    if zone is not None:
        links = links.filter(worker__worker_zones__zone=zone)

    links = links.filter(
        Q(service__requires_female_worker=False)
        | Q(worker__gender=WorkerProfile.Gender.FEMALE)
    )
    return set(links.values_list("service_id", flat=True).distinct())


def _available_service_ids(city, zone=None):
    if city is None:
        return None
    eligible_workers = eligible_worker_profiles(city=city, zone=zone)
    service_links = WorkerService.objects.filter(
        worker__in=eligible_workers,
        service__is_active=True,
        service__category__is_active=True,
    ).filter(
        Q(service__requires_female_worker=False)
        | Q(worker__gender=WorkerProfile.Gender.FEMALE)
    )
    return set(service_links.values_list("service_id", flat=True).distinct())


def _available_variant_ids(city, zone=None):
    if city is None:
        return None
    eligible_workers = eligible_worker_profiles(city=city, zone=zone)
    links = WorkerService.objects.filter(
        worker__in=eligible_workers,
        service__is_active=True,
        service__category__is_active=True,
    ).filter(
        Q(service__requires_female_worker=False)
        | Q(worker__gender=WorkerProfile.Gender.FEMALE)
    ).select_related("service").prefetch_related("service__variants")
    available = set()
    for link in links:
        skills = {str(task).strip() for task in (link.capabilities or []) if str(task).strip()}
        for variant in link.service.variants.filter(is_active=True):
            required = {str(task).strip() for task in (variant.included_tasks or []) if str(task).strip()}
            if required and (
                not link.capabilities_verified or not required.issubset(skills)
            ):
                continue
            available.add(variant.pk)
    return available


LAUNCH_CATEGORY_SLUGS = ("car-wash", "beauty", "electrical", "home-cleaning")


def _launch_catalogue_filter(queryset):
    """Keep the mobile launch catalogue inside its four approved root trees."""
    return queryset.filter(
        Q(category__slug__in=LAUNCH_CATEGORY_SLUGS, category__parent__isnull=True)
        | Q(category__parent__slug__in=LAUNCH_CATEGORY_SLUGS,
            category__parent__parent__isnull=True)
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
        else:
            service_ids = _enrolled_service_ids(*location)
            context["visible_category_ids"] = _visible_category_ids(service_ids)
        return context

    def get_queryset(self):
        queryset = Category.objects.filter(
            is_active=True,
            parent__isnull=True,
        )
        location = _location_from_address(self.request)
        if location is not None:
            visible_ids = _visible_category_ids(_enrolled_service_ids(*location))
            queryset = queryset.filter(pk__in=visible_ids)
        if self.request.query_params.get("launch_only", "").lower() == "true":
            queryset = queryset.filter(slug__in=LAUNCH_CATEGORY_SLUGS)
        return queryset.prefetch_related("children", "audience_options", "children__audience_options")


class ServiceListView(generics.ListAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = ServiceSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        location = _location_from_address(self.request)
        if location is None:
            context["available_service_ids"] = None
        else:
            city, zone = location
            context["available_service_ids"] = (
                _enrolled_service_ids(city, zone=zone)
                & _city_service_ids(city, zone=zone)
            )
        context["available_variant_ids"] = (
            None if location is None else _available_variant_ids(*location)
        )
        return context

    def get_queryset(self):
        queryset = Service.objects.filter(is_active=True, category__is_active=True).select_related(
            "category"
        ).prefetch_related(
            "images", "variants", "addons", "form_fields"
        )
        if self.request.query_params.get("launch_only", "").lower() == "true":
            queryset = _launch_catalogue_filter(queryset)

        location = _location_from_address(self.request)
        if location is not None:
            city, zone = location
            visible_service_ids = _enrolled_service_ids(city, zone=zone)
            visible_service_ids &= _city_service_ids(city, zone=zone)
            queryset = queryset.filter(pk__in=visible_service_ids)

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
        if location is None:
            context["available_service_ids"] = None
        else:
            city, zone = location
            context["available_service_ids"] = (
                _enrolled_service_ids(city, zone=zone)
                & _city_service_ids(city, zone=zone)
            )
        context["available_variant_ids"] = (
            None if location is None else _available_variant_ids(*location)
        )
        return context

    def get_queryset(self):
        queryset = Service.objects.filter(
            is_active=True, category__is_active=True
        ).select_related("category").prefetch_related(
            "images", "variants", "addons", "form_fields"
        )
        if self.request.query_params.get("launch_only", "").lower() == "true":
            queryset = _launch_catalogue_filter(queryset)
        location = _location_from_address(self.request)
        if location is not None:
            city, zone = location
            visible_service_ids = _enrolled_service_ids(city, zone=zone)
            visible_service_ids &= _city_service_ids(city, zone=zone)
            queryset = queryset.filter(pk__in=visible_service_ids)

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
