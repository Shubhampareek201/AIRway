from django.urls import path
from .views import CreateOrderView
from .installment_views import CreateFinalBalancePaymentView, VerifyInstallmentPaymentView
from .verify_view import VerifyPaymentView, PaymentWebhookView

urlpatterns = [
    path("create-order/", CreateOrderView.as_view(), name="create-order"),
    path("verify/", VerifyPaymentView.as_view(), name="payment-verify"),
    path("webhook/", PaymentWebhookView.as_view(), name="payment-webhook"),
    path("final-balance/create-order/", CreateFinalBalancePaymentView.as_view(), name="final-balance-create-order"),
    path("final-balance/verify/", VerifyInstallmentPaymentView.as_view(), name="final-balance-verify"),
]