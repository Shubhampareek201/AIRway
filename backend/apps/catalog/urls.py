from django.urls import path
from .views import CategoryListView, ServiceListView, ServiceDetailView

urlpatterns = [
    path("categories/", CategoryListView.as_view(), name="category-list"),
    path("services/", ServiceListView.as_view(), name="service-list"),
    path("services/<int:pk>/", ServiceDetailView.as_view(), name="service-detail"),
]
