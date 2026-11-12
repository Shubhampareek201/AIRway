from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import Payment, PaymentRefund


@admin.register(PaymentRefund)
class PaymentRefundAdmin(ModelAdmin):
    list_display = (
        "id", "booking", "payment", "amount", "wallet_amount",
        "gateway_amount", "reason", "status", "gateway_refund_id", "created_at",
    )
    list_filter = ("status", "reason", "created_at")
    search_fields = (
        "id", "booking__id", "payment__id", "gateway_refund_id",
        "booking__customer__phone",
    )
    readonly_fields = (
        "payment", "booking", "order_item", "amount", "wallet_amount",
        "gateway_amount", "reason", "status", "gateway_refund_id",
        "failure_reason", "processed_at", "created_at", "updated_at",
    )

    def has_view_permission(self, request, obj=None):
        return request.user.is_staff

    def has_view_permission(self, request, obj=None):
        return request.user.is_staff

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Payment)
class PaymentAdmin(ModelAdmin):
    list_display = (
        "id", "customer", "order", "booking", "stage", "amount",
        "wallet_amount", "method", "status", "paid_at", "created_at",
    )
    list_filter = ("status", "stage", "method", "created_at")
    search_fields = (
        "id", "customer__phone", "customer__name",
        "razorpay_order_id", "razorpay_payment_id",
    )
    readonly_fields = (
        "booking", "order", "customer", "stage", "amount", "wallet_amount",
        "method", "status", "razorpay_order_id", "razorpay_payment_id",
        "razorpay_signature", "paid_at", "failed_at", "raw_response",
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
