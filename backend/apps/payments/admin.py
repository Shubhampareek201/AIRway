from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import Payment, PaymentInstallment, PaymentAttempt, PaymentRefund


@admin.register(Payment)
class PaymentAdmin(ModelAdmin):
    list_display = ("id", "customer", "booking", "order", "amount", "wallet_amount", "status", "paid_at")
    list_filter = ("status", "method", "created_at")
    search_fields = ("customer__phone", "razorpay_order_id", "razorpay_payment_id")
    readonly_fields = ("created_at", "updated_at", "paid_at", "failed_at", "raw_response")


@admin.register(PaymentInstallment)
class PaymentInstallmentAdmin(ModelAdmin):
    list_display = ("id", "payment", "kind", "amount", "wallet_amount", "status", "paid_at")
    list_filter = ("kind", "status", "created_at")
    search_fields = ("payment__customer__phone", "payment__order_id", "payment__booking_id")
    readonly_fields = ("created_at", "updated_at", "paid_at")


@admin.register(PaymentAttempt)
class PaymentAttemptAdmin(ModelAdmin):
    list_display = ("id", "installment", "attempt_number", "amount", "wallet_amount", "method", "status", "paid_at")
    list_filter = ("method", "status", "created_at")
    search_fields = ("razorpay_order_id", "razorpay_payment_id", "installment__payment__customer__phone")
    readonly_fields = ("created_at", "updated_at", "paid_at", "failed_at", "raw_response")


@admin.register(PaymentRefund)
class PaymentRefundAdmin(ModelAdmin):
    list_display = ("id", "attempt", "gateway_amount", "wallet_amount", "platform_fee", "status", "gateway_refund_id", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("idempotency_key", "gateway_refund_id", "attempt__razorpay_payment_id")
    readonly_fields = ("created_at", "updated_at", "processed_at", "raw_response")
