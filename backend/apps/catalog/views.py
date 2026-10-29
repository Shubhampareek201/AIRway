from rest_framework import generics, permissions
from .models import Service
from .serializers import ServiceSerializer


class ServiceListView(generics.ListAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = ServiceSerializer

    def get_queryset(self):
        queryset = Service.objects.filter(is_active=True).select_related(
            "category"
        ).prefetch_related(
            "images", "variants", "addons", "form_fields"
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
    queryset = Service.objects.filter(is_active=True).select_related(
        "category"
    ).prefetch_related(
        "images", "variants", "addons", "form_fields"
    )