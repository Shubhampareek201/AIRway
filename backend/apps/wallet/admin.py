from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import Wallet, WalletReservation, WalletTransaction


@admin.register(Wallet)
class WalletAdmin(ModelAdmin):
    list_display = ("user", "balance", "pending_balance", "updated_at")
    search_fields = ("user__name", "user__phone")
    readonly_fields = ("user", "balance", "pending_balance", "created_at", "updated_at")
    fields = readonly_fields

    def has_view_permission(self, request, obj=None):
        return request.user.is_staff

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(WalletTransaction)
class WalletTransactionAdmin(ModelAdmin):
    list_display = ("id", "wallet", "type", "amount", "status", "reference_id", "created_at")
    list_filter = ("type", "status", "created_at")
    search_fields = ("wallet__user__phone", "wallet__user__name", "reference_id", "razorpay_payment_id")
    readonly_fields = (
        "wallet", "type", "amount", "description", "status", "reference_id",
        "razorpay_payment_id", "created_at", "updated_at",
    )
    fields = readonly_fields

    def has_view_permission(self, request, obj=None):
        return request.user.is_staff

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(WalletReservation)
class WalletReservationAdmin(ModelAdmin):
    list_display = ("id", "wallet", "payment", "amount", "status", "captured_at", "released_at")
    list_filter = ("status", "created_at")
    search_fields = ("wallet__user__phone", "payment__razorpay_order_id")
    readonly_fields = (
        "wallet", "payment", "amount", "status", "captured_at", "released_at",
        "created_at", "updated_at",
    )
    fields = readonly_fields

    def has_view_permission(self, request, obj=None):
        return request.user.is_staff

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
