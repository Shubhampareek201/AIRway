from django.urls import path
from .views import BannerListView, CategoryListView, ServiceListView, ServiceDetailView

urlpatterns = [
    path("banners/", BannerListView.as_view(), name="banner-list"),
    path("categories/", CategoryListView.as_view(), name="category-list"),
    path("services/", ServiceListView.as_view(), name="service-list"),
    path("services/<int:pk>/", ServiceDetailView.as_view(), name="service-detail"),
]
