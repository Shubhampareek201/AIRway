from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    BookingViewSet,
    CustomerCartView,
    CustomerCartItemView,
    CustomerCheckoutView,
    CustomerOrderDetailView,
    CustomerOrderListView,
    CustomerCartIssuePhotoView,
    CustomerCartFormPhotoView,
    BookingIssuePhotoView,
)

router = DefaultRouter()
router.register(r"", BookingViewSet, basename="booking")

urlpatterns = [
    path("cart/", CustomerCartView.as_view(), name="customer-cart"),
    path("cart/checkout/", CustomerCheckoutView.as_view(), name="customer-cart-checkout"),
    path("orders/", CustomerOrderListView.as_view(), name="customer-order-list"),
    path("orders/<int:order_id>/", CustomerOrderDetailView.as_view(), name="customer-order-detail"),
    path("cart/items/<int:item_id>/", CustomerCartItemView.as_view(), name="customer-cart-item"),
    path("cart/items/<int:item_id>/issue-photo/", CustomerCartIssuePhotoView.as_view(), name="customer-cart-issue-photo"),
    path("cart/items/<int:item_id>/form-photos/<slug:field_key>/", CustomerCartFormPhotoView.as_view(), name="customer-cart-form-photo"),
    path("issue-photos/<int:booking_id>/", BookingIssuePhotoView.as_view(), name="booking-issue-photo"),
    path("", include(router.urls)),
]
