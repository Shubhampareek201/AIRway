from django.contrib import admin

from .models import (
    BookingFinancialPlan,
    Payment,
    PaymentAttempt,
    PaymentAllocation,
    PaymentInstallment,
    RefundRecord,
    ServiceOTPChallenge,
)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("id", "customer", "booking", "order", "amount", "method", "status", "created_at")
    list_filter = ("status", "method", "created_at")
    search_fields = ("id", "razorpay_order_id", "razorpay_payment_id", "customer__phone")
    readonly_fields = tuple(field.name for field in Payment._meta.fields)

    def has_add_permission(self, request):
        return False


class ReadOnlyLedgerAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(BookingFinancialPlan)
class BookingFinancialPlanAdmin(ReadOnlyLedgerAdmin):
    list_display = ("id", "booking", "gross_total", "advance_due", "balance_due", "advance_captured", "balance_captured", "state")
    list_filter = ("state", "currency", "calculation_version")
    search_fields = ("booking__id", "booking__customer__phone")
    readonly_fields = tuple(field.name for field in BookingFinancialPlan._meta.fields)


@admin.register(PaymentInstallment)
class PaymentInstallmentAdmin(ReadOnlyLedgerAdmin):
    list_display = ("id", "financial_plan", "kind", "amount_due", "amount_captured", "status", "due_at", "settled_at")
    list_filter = ("kind", "status")
    search_fields = ("financial_plan__booking__id",)


@admin.register(PaymentAttempt)
class PaymentAttemptAdmin(ReadOnlyLedgerAdmin):
    list_display = ("id", "installment", "provider", "amount", "gateway_amount", "wallet_amount", "currency", "status", "captured_at", "created_at")
    list_filter = ("provider", "status", "currency")
    search_fields = ("provider_order_id", "provider_payment_id", "idempotency_key")


@admin.register(PaymentAllocation)
class PaymentAllocationAdmin(ReadOnlyLedgerAdmin):
    list_display = (
        "id", "payment", "payment_attempt", "installment",
        "amount", "gateway_amount", "wallet_amount", "created_at",
    )
    search_fields = (
        "payment__id", "payment_attempt__id",
        "installment__financial_plan__booking__id",
    )


@admin.register(RefundRecord)
class RefundRecordAdmin(ReadOnlyLedgerAdmin):
    list_display = ("id", "booking", "reason", "gross_amount", "platform_fee", "refund_amount", "status", "requested_at", "processed_at")
    list_filter = ("reason", "status")
    search_fields = ("provider_refund_id", "idempotency_key", "booking__id")


@admin.register(ServiceOTPChallenge)
class ServiceOTPChallengeAdmin(ReadOnlyLedgerAdmin):
    list_display = ("id", "booking", "purpose", "expires_at", "attempts", "max_attempts", "consumed_at", "invalidated_at")
    list_filter = ("purpose", "expires_at")
    search_fields = ("booking__id",)
    # Never expose the password hash, plaintext OTP, or delivery payload in admin.
    exclude = ("code_hash", "delivery_reference")
