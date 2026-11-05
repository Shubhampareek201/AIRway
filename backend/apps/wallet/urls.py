from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    WalletViewSet,
    WalletTransactionViewSet,
    WalletBalanceView,
    WalletTransactionsView,
    WalletTopUpView,
    WalletTopUpConfirmView,
    WalletRefundView,
    WalletCreditView,
)

router = DefaultRouter()
router.register(r"", WalletViewSet, basename="wallet")
router.register(r"transactions", WalletTransactionViewSet, basename="wallet-transaction")

app_name = "wallet"

urlpatterns = [
    path("balance/", WalletBalanceView.as_view(), name="wallet-balance"),
    path("transactions/", WalletTransactionsView.as_view(), name="wallet-transactions"),
    path("top-up/", WalletTopUpView.as_view(), name="wallet-top-up"),
    path("top-up/<int:transaction_id>/confirm/", WalletTopUpConfirmView.as_view(), name="wallet-top-up-confirm"),
    path("refund/", WalletRefundView.as_view(), name="wallet-refund"),
    path("credit/", WalletCreditView.as_view(), name="wallet-credit"),
    path("", include(router.urls)),
]