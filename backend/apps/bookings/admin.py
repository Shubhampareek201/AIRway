from django.contrib import admin, messages
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
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
    AppointmentGroup,
    OrderItem,
    DispatchConfiguration,
    BookingCompletionOTP,
    WorkerOffer,
    BookingQuote,
    BookingWorkEvidence,
    RecurringWashPlan,
    RecurringWashVisit,
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
        "booking", "scheduled_service_time", "quantity", "service_snapshot", "pricing_snapshot",
        "line_subtotal", "tax_amount", "line_total", "created_at",
    )

    @admin.display(description="Service schedule")
    def scheduled_service_time(self, obj):
        booking = getattr(obj, "booking", None)
        if booking is None or booking.scheduled_at is None:
            return "Not scheduled"
        scheduled = timezone.localtime(booking.scheduled_at).strftime("%d %b %Y, %I:%M %p")
        if booking.drop_scheduled_at:
            drop = timezone.localtime(booking.drop_scheduled_at).strftime("%d %b %Y, %I:%M %p")
            return f"Service: {scheduled} | Drop-off: {drop}"
        return scheduled


@admin.register(AppointmentGroup)
class AppointmentGroupAdmin(ModelAdmin):
    list_display = (
        "id", "order", "category_title_snapshot", "scheduled_at",
        "customer_message", "created_at",
    )
    list_filter = ("category_slug_snapshot", "scheduled_at")
    search_fields = ("order__id", "category_title_snapshot", "customer_message")
    readonly_fields = (
        "order", "root_category", "category_slug_snapshot",
        "category_title_snapshot", "scheduled_at", "customer_message",
        "created_at", "updated_at",
    )
    fields = readonly_fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


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


@admin.register(BookingWorkEvidence)
class BookingWorkEvidenceAdmin(ModelAdmin):
    list_display = ("id", "booking", "worker", "stage", "created_at")
    list_filter = ("stage", "created_at")
    search_fields = ("booking__id", "booking__customer__phone", "worker__user__phone")
    readonly_fields = ("booking", "worker", "stage", "image_path", "note", "created_at", "updated_at")
    fields = readonly_fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(BookingQuote)
class BookingQuoteAdmin(ModelAdmin):
    list_display = (
        "id", "booking", "worker", "version", "status",
        "total_amount", "expires_at", "responded_at",
    )
    list_filter = ("status", "created_at")
    search_fields = ("booking__id", "booking__customer__phone", "worker__user__phone")
    readonly_fields = (
        "booking", "worker", "version", "line_items", "labour_amount",
        "material_amount", "other_amount", "tax_amount", "total_amount",
        "notes", "status", "customer_response_note", "expires_at",
        "responded_at", "created_at", "updated_at",
    )
    fields = readonly_fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(BookingAssignment)
class BookingAssignmentAdmin(ModelAdmin):
    list_display = ("booking", "worker", "assigned_at", "accepted_at", "started_at", "completed_at")
    search_fields = ("booking__id", "worker__user__phone")

@admin.register(DispatchConfiguration)
class DispatchConfigurationAdmin(ModelAdmin):
    list_display = ("is_enabled", "offer_expiry_minutes", "priority_order")
    fieldsets = (
        ("Dispatch control", {"fields": ("is_enabled",)}),
        ("Simultaneous worker offers", {"fields": ("offer_expiry_minutes", "priority_order")}),
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


class RecurringWashVisitInline(TabularInline):
    model = RecurringWashVisit
    extra = 0
    can_delete = False
    readonly_fields = (
        "visit_number", "booking", "prepaid_amount",
        "status", "created_at", "updated_at",
    )
    fields = (
        "visit_number", "scheduled_at", "booking", "prepaid_amount",
        "status", "admin_notes", "created_at", "updated_at",
    )

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(RecurringWashPlan)
class RecurringWashPlanAdmin(ModelAdmin):
    list_display = (
        "id", "customer", "service", "vehicle_type", "vehicle_quantity",
        "frequency", "starts_on", "ends_on", "quoted_total", "status",
    )
    list_filter = ("status", "frequency", "starts_on")
    search_fields = ("customer__phone", "customer__name", "vehicle_type", "order__id")
    readonly_fields = (
        "order", "source_booking", "customer", "address", "service", "variant",
        "frequency", "duration_days", "starts_on", "ends_on",
        "preferred_time_window", "vehicle_type", "vehicle_quantity",
        "quoted_total", "plan_snapshot", "quote_accepted_at", "activated_at",
        "paused_at", "cancelled_at", "status", "created_at", "updated_at",
    )
    fields = readonly_fields + ("admin_notes",)
    inlines = [RecurringWashVisitInline]
    actions = ["retry_pending_visit_setup"]

    @admin.action(description="Retry setup for pending recurring visits")
    def retry_pending_visit_setup(self, request, queryset):
        from apps.bookings.recurring import create_pending_recurring_visit_bookings

        created = 0
        failed = 0
        for plan in queryset:
            try:
                created += len(create_pending_recurring_visit_bookings(plan))
                failed += plan.visits.filter(status=RecurringWashVisit.Status.PENDING_SETUP).count()
            except Exception:
                failed += 1
        if failed:
            self.message_user(
                request,
                f"Created {created} booking(s). {failed} visit(s) still need schedule resolution; see each visit's Admin notes.",
                level=messages.WARNING,
            )
        else:
            self.message_user(
                request,
                f"Recurring setup complete: {created} booking(s) created.",
                level=messages.SUCCESS,
            )

    def save_formset(self, request, form, formset, change):
        instances = formset.save()
        if formset.model is RecurringWashVisit:
            from apps.bookings.services import (
                check_service_available, check_slot_availability,
                SlotConflictError, ServiceUnavailableError,
            )

            for visit in instances:
                if not visit.booking_id or visit.booking.scheduled_at == visit.scheduled_at:
                    continue
                booking = visit.booking
                if (
                    booking.status not in (Booking.Status.PENDING, Booking.Status.CONFIRMED)
                    or hasattr(booking, "assignment")
                ):
                    raise ValidationError(
                        "An assigned, started, completed or cancelled visit cannot be rescheduled from this Admin inline."
                    )
                if visit.scheduled_at <= timezone.now():
                    raise ValidationError("Choose a future date and time for this recurring visit.")
                duration = (
                    booking.variant.duration_minutes
                    if booking.variant_id and booking.variant.duration_minutes
                    else booking.service.duration_minutes
                ) or 60
                quantity = max(int((booking.pricing_snapshot or {}).get("quantity", 1) or 1), 1)
                try:
                    check_service_available(booking.service, address=booking.address)
                    check_slot_availability(
                        service=booking.service,
                        scheduled_at=visit.scheduled_at,
                        duration_minutes=duration * (
                            1 if booking.service.pricing_type == "per_unit" else quantity
                        ),
                        booking_mode=booking.booking_mode,
                        drop_scheduled_at=(
                            booking.drop_scheduled_at
                            if booking.booking_mode == Booking.BookingMode.PICKUP_DROP
                            else None
                        ),
                    )
                except (SlotConflictError, ServiceUnavailableError) as exc:
                    raise ValidationError(str(exc)) from exc
                WorkerOffer.objects.filter(
                    booking=booking,
                    status__in=(
                        WorkerOffer.Status.PENDING,
                        WorkerOffer.Status.ACCEPTED,
                        WorkerOffer.Status.DECLINED,
                        WorkerOffer.Status.EXPIRED,
                    ),
                ).update(
                    status=WorkerOffer.Status.WITHDRAWN,
                    responded_at=timezone.now(),
                )
                booking.scheduled_at = visit.scheduled_at
                booking.save(update_fields=["scheduled_at", "updated_at"])


