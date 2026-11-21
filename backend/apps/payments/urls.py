from django.urls import path
from .views import CreateOrderView, CreateExtraWorkPaymentView
from .verify_view import VerifyPaymentView, PaymentWebhookView

urlpatterns = [
    path("create-order/", CreateOrderView.as_view(), name="create-order"),
    path("extra-work/<int:extra_work_id>/create-order/", CreateExtraWorkPaymentView.as_view(), name="extra-work-create-order"),
    path("verify/", VerifyPaymentView.as_view(), name="payment-verify"),
    path("webhook/", PaymentWebhookView.as_view(), name="payment-webhook"),
]