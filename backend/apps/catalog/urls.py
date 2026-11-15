from django.urls import path
from .views import BannerListView, CategoryListView, ServiceListView, ServiceDetailView, VehicleMakeListView, VehicleModelListView

urlpatterns = [
    path("banners/", BannerListView.as_view(), name="banner-list"),\n    path("vehicle-makes/", VehicleMakeListView.as_view(), name="vehicle-make-list"),\n    path("vehicle-models/", VehicleModelListView.as_view(), name="vehicle-model-list"),
    path("categories/", CategoryListView.as_view(), name="category-list"),
    path("services/", ServiceListView.as_view(), name="service-list"),
    path("services/<int:pk>/", ServiceDetailView.as_view(), name="service-detail"),
]
