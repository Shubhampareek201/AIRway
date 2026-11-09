from django.urls import path
from .views import CreateOrderView
from .verify_view import VerifyPaymentView, PaymentWebhookView
from .views import CreateInstallmentOrderView

urlpatterns = [
    path("installments/create-order/", CreateInstallmentOrderView.as_view(), name="installment-create-order"),
    path("create-order/", CreateOrderView.as_view(), name="create-order"),
    path("verify/", VerifyPaymentView.as_view(), name="payment-verify"),
    path("webhook/", PaymentWebhookView.as_view(), name="payment-webhook"),
]