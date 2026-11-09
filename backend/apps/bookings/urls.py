from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    BookingViewSet,
    CustomerCartView,
    CustomerCartItemView,
    CustomerCheckoutView,
    CustomerOrderDetailView,
    CustomerOrderCancelView,
    CustomerOrderListView,
)

router = DefaultRouter()
router.register(r"", BookingViewSet, basename="booking")

urlpatterns = [
    path("cart/", CustomerCartView.as_view(), name="customer-cart"),
    path("cart/checkout/", CustomerCheckoutView.as_view(), name="customer-cart-checkout"),
    path("orders/", CustomerOrderListView.as_view(), name="customer-order-list"),
    path("orders/<int:order_id>/", CustomerOrderDetailView.as_view(), name="customer-order-detail"),
    path("orders/<int:order_id>/cancel/", CustomerOrderCancelView.as_view(), name="customer-order-cancel"),
    path("cart/items/<int:item_id>/", CustomerCartItemView.as_view(), name="customer-cart-item"),
    path("", include(router.urls)),
]
