from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import BookingViewSet, CustomerCartView, CustomerCartItemView

router = DefaultRouter()
router.register(r"", BookingViewSet, basename="booking")

urlpatterns = [
    path("cart/", CustomerCartView.as_view(), name="customer-cart"),
    path("cart/items/<int:item_id>/", CustomerCartItemView.as_view(), name="customer-cart-item"),
    path("", include(router.urls)),
]
