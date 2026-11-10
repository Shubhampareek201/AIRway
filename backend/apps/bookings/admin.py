from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from .models import (
    Booking,
    BookingAddOn,
    BookingFormResponse,
    BookingStatusHistory,
    BookingAssignment,
    CustomerCart,
    CartItem,
    Order,
    OrderItem,
    DispatchConfiguration,
    DispatchAttempt,
)


class BookingAddOnInline(TabularInline):
    model = BookingAddOn
    extra = 0
    readonly_fields = ("unit_price", "total_price")


class BookingFormResponseInline(TabularInline):
    model = BookingFormResponse
    extra = 0
    readonly_fields = ("form_field", "value")


class BookingStatusHistoryInline(TabularInline):
    model = BookingStatusHistory
    extra = 0
    readonly_fields = ("from_status", "to_status", "changed_by", "note", "created_at")


class BookingAssignmentInline(TabularInline):
    model = BookingAssignment
    extra = 0


class CartItemInline(TabularInline):
    model = CartItem
    extra = 0
    readonly_fields = ('pricing_snapshot', 'created_at', 'updated_at')


@admin.register(CustomerCart)
class CustomerCartAdmin(ModelAdmin):
    list_display = ('customer', 'address', 'updated_at')
    search_fields = ('customer__phone', 'customer__name')
    list_filter = ('address__zone__city',)
    readonly_fields = ('created_at', 'updated_at')
    inlines = [CartItemInline]


class OrderItemInline(TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = (
        "booking", "quantity", "service_snapshot", "pricing_snapshot",
        "line_subtotal", "tax_amount", "line_total", "created_at",
    )


@admin.register(Order)
class OrderAdmin(ModelAdmin):
    list_display = ("id", "customer", "status", "total_amount", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("customer__phone", "customer__name", "id")
    readonly_fields = (
        "created_at", "updated_at", "subtotal", "tax_amount",
        "discount_amount", "total_amount", "metadata",
    )
    inlines = [OrderItemInline]


@admin.register(Booking)
class BookingAdmin(ModelAdmin):
    list_display = ("id", "customer", "service", "variant", "booking_mode", "status", "scheduled_at", "created_at")
    list_filter = ("status", "booking_mode", "service")
    search_fields = ("customer__phone", "customer__name", "service__title")
    readonly_fields = ("created_at", "updated_at", "pricing_snapshot")
    inlines = [BookingAddOnInline, BookingFormResponseInline, BookingAssignmentInline, BookingStatusHistoryInline]


@admin.register(BookingAssignment)
class BookingAssignmentAdmin(ModelAdmin):
    list_display = ("booking", "worker", "assigned_at", "accepted_at", "started_at", "completed_at")
    search_fields = ("booking__id", "worker__user__phone")

@admin.register(DispatchConfiguration)
class DispatchConfigurationAdmin(ModelAdmin):
    list_display = ("is_enabled", "batch_size", "max_batches", "offer_expiry_minutes", "priority_order")
    fieldsets = (
        ("Dispatch control", {"fields": ("is_enabled",)}),
        ("Priority batches", {"fields": ("batch_size", "max_batches", "offer_expiry_minutes", "priority_order")}),
        ("Audit", {"fields": ("created_at", "updated_at")}),
    )
    readonly_fields = ("created_at", "updated_at")

    def has_add_permission(self, request):
        return not DispatchConfiguration.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False



@admin.register(DispatchAttempt)
class DispatchAttemptAdmin(ModelAdmin):
    list_display = (
        "id", "order", "booking", "batch_number",
        "candidate_count", "status", "retry_after", "created_at",
    )
    list_filter = ("status", "created_at")
    search_fields = ("order__id", "booking__id")
    readonly_fields = (
        "order", "booking", "batch_number", "candidate_count",
        "status", "retry_after", "details", "created_at", "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.is_staff

    def has_delete_permission(self, request, obj=None):
        return False
