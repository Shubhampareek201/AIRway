from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import Payment, PaymentRefund


@admin.register(Payment)
class PaymentAdmin(ModelAdmin):
    list_display = (
        "id", "order", "appointment_group", "customer",
        "stage", "amount", "status", "created_at",
    )
    list_filter = ("stage", "status", "created_at")
    search_fields = ("id", "order__id", "appointment_group__id", "customer__phone")
    readonly_fields = tuple(field.name for field in Payment._meta.fields)

    def has_view_permission(self, request, obj=None):
        return request.user.is_staff

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PaymentRefund)
class PaymentRefundAdmin(ModelAdmin):
    list_display = (
        "id", "booking", "payment", "amount", "wallet_amount",
        "gateway_amount", "reason", "status", "gateway_refund_id", "failure_summary", "created_at",
    )
    list_filter = ("status", "reason", "created_at")
    search_fields = (
        "id", "booking__id", "payment__id", "gateway_refund_id",
        "booking__customer__phone", "failure_reason",
    )
    readonly_fields = (
        "payment", "booking", "order_item", "amount", "wallet_amount",
        "gateway_amount", "reason", "status", "gateway_refund_id",
        "failure_reason", "processed_at", "created_at", "updated_at",
    )

    @admin.display(description="Gateway / reconciliation note")
    def failure_summary(self, obj):
        return obj.failure_reason[:100] if obj.failure_reason else "—"

    def has_view_permission(self, request, obj=None):
        return request.user.is_staff

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
