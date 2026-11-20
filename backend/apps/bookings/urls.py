from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .extra_work import CustomerExtraWorkListView, CustomerExtraWorkDecisionView\nfrom .disputes import BookingDisputeListCreateView, BookingDisputeDetailView

from .views import (
    BookingViewSet,
    CustomerCartView,
    CustomerCartItemView,
    CustomerCheckoutView,
    CustomerOrderDetailView,
    CustomerOrderListView,
    CustomerAppointmentGroupCancelView,
    CustomerCartIssuePhotoView,
    CustomerCartFormPhotoView,
    BookingIssuePhotoView,
    BookingWorkEvidencePhotoView,
    CustomerRecurringWashPlanCancelView,
    CustomerRecurringWashVisitRescheduleView,
)

router = DefaultRouter()
router.register(r"", BookingViewSet, basename="booking")

urlpatterns = [\n    path("disputes/", BookingDisputeListCreateView.as_view(), name="booking-dispute-list-create"),\n    path("disputes/<int:dispute_id>/", BookingDisputeDetailView.as_view(), name="booking-dispute-detail"),
    path("cart/", CustomerCartView.as_view(), name="customer-cart"),
    path("cart/checkout/", CustomerCheckoutView.as_view(), name="customer-cart-checkout"),
    path("orders/", CustomerOrderListView.as_view(), name="customer-order-list"),
    path("orders/<int:order_id>/", CustomerOrderDetailView.as_view(), name="customer-order-detail"),
    path("appointment-groups/<int:group_id>/cancel/", CustomerAppointmentGroupCancelView.as_view(), name="customer-appointment-group-cancel"),
    path("<int:booking_id>/extra-work/", CustomerExtraWorkListView.as_view(), name="customer-extra-work-list"),
    path("extra-work/<int:extra_work_id>/decision/", CustomerExtraWorkDecisionView.as_view(), name="customer-extra-work-decision"),
    path("recurring-plans/<int:plan_id>/cancel/", CustomerRecurringWashPlanCancelView.as_view(), name="recurring-plan-cancel"),
    path("recurring-visits/<int:visit_id>/reschedule/", CustomerRecurringWashVisitRescheduleView.as_view(), name="recurring-visit-reschedule"),
    path("cart/items/<int:item_id>/", CustomerCartItemView.as_view(), name="customer-cart-item"),
    path("cart/items/<int:item_id>/issue-photo/", CustomerCartIssuePhotoView.as_view(), name="customer-cart-issue-photo"),
    path("cart/items/<int:item_id>/form-photos/<slug:field_key>/", CustomerCartFormPhotoView.as_view(), name="customer-cart-form-photo"),
    path("issue-photos/<int:booking_id>/", BookingIssuePhotoView.as_view(), name="booking-issue-photo"),
    path("work-evidence/<int:evidence_id>/photo/", BookingWorkEvidencePhotoView.as_view(), name="booking-work-evidence-photo"),
    path("", include(router.urls)),
]
