from django.contrib import admin, messages
from django.db import transaction
from django.utils import timezone
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
    BookingCompletionOTP,
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


@admin.action(description="Mark AIRway unable to fulfil and issue full service refund")
def mark_unfulfillable_and_refund(modeladmin, request, queryset):
    from apps.payments.models import PaymentRefund
    from apps.payments.refunds import request_booking_refunds

    cancelled = 0
    for booking in queryset.select_related("customer").prefetch_related("order_item"):
        with transaction.atomic():
            locked = Booking.objects.select_for_update().get(pk=booking.pk)
            if locked.status in (Booking.Status.CANCELLED, Booking.Status.COMPLETED):
                continue
            old_status = locked.status
            locked.status = Booking.Status.CANCELLED
            locked.cancelled_at = timezone.now()
            locked.cancelled_by = request.user
            locked.cancellation_reason = "AIRway unable to fulfil this service."
            locked.save(update_fields=[
                "status", "cancelled_at", "cancelled_by",
                "cancellation_reason", "updated_at",
            ])
            BookingStatusHistory.objects.create(
                booking=locked,
                from_status=old_status,
                to_status=Booking.Status.CANCELLED,
                changed_by=request.user,
                note="Cancelled by AIRway: unable to fulfil. Full service refund initiated.",
            )
            assignment = getattr(locked, "assignment", None)
            if assignment:
                assignment.delete()

            order_item = getattr(locked, "order_item", None)
            if order_item:
                order = Order.objects.select_for_update().get(pk=order_item.order_id)
                active_remaining = order.items.exclude(
                    booking__status=Booking.Status.CANCELLED
                ).exists()
                order.status = (
                    Order.Status.PARTIALLY_CANCELLED
                    if active_remaining else Order.Status.CANCELLED
                )
                order.save(update_fields=["status", "updated_at"])
                if not active_remaining:
                    WorkerOffer.objects.filter(
                        order=order, status=WorkerOffer.Status.PENDING
                    ).update(
                        status=WorkerOffer.Status.WITHDRAWN,
                        responded_at=timezone.now(),
                    )
                else:
                    WorkerOffer.objects.filter(
                        order=order, status=WorkerOffer.Status.PENDING
                    ).update(
                        status=WorkerOffer.Status.WITHDRAWN,
                        responded_at=timezone.now(),
                    )
                    from apps.bookings.dispatcher import DispatcherService
                    DispatcherService.dispatch_order(order)
            else:
                WorkerOffer.objects.filter(
                    booking=locked, status=WorkerOffer.Status.PENDING
                ).update(
                    status=WorkerOffer.Status.EXPIRED,
                    responded_at=timezone.now(),
                )

            transaction.on_commit(
                lambda booking_id=locked.pk: _issue_platform_refund(booking_id)
            )
            cancelled += 1

    modeladmin.message_user(
        request,
        f"{cancelled} service(s) cancelled. Full refunds have been initiated where payments were captured.",
        level=messages.SUCCESS if cancelled else messages.WARNING,
    )


def _issue_platform_refund(booking_id):
    import logging
    from apps.payments.models import PaymentRefund
    from apps.payments.refunds import request_booking_refunds

    try:
        booking = Booking.objects.get(pk=booking_id)
        request_booking_refunds(
            booking,
            reason=PaymentRefund.Reason.PLATFORM_UNFULFILLED,
        )
    except Exception:
        logging.getLogger(__name__).exception(
            "Could not initiate platform cancellation refund for booking %s",
            booking_id,
        )


@admin.register(Booking)
class BookingAdmin(ModelAdmin):
    list_display = ("id", "customer", "service", "variant", "booking_mode", "status", "scheduled_at", "created_at")
    list_filter = ("status", "booking_mode", "service")
    search_fields = ("customer__phone", "customer__name", "service__title")
    readonly_fields = ("created_at", "updated_at", "pricing_snapshot")
    inlines = [BookingAddOnInline, BookingFormResponseInline, BookingAssignmentInline, BookingStatusHistoryInline]
    actions = [mark_unfulfillable_and_refund]


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



@admin.register(BookingCompletionOTP)
class BookingCompletionOTPAdmin(ModelAdmin):
    list_display = ("booking", "expires_at", "attempts", "verified_at", "created_at")
    list_filter = ("verified_at", "expires_at")
    search_fields = ("booking__id", "booking__customer__phone")
    readonly_fields = (
        "booking", "expires_at", "attempts", "last_sent_at",
        "verified_at", "created_at", "updated_at",
    )
    fields = readonly_fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
