from django.contrib import admin, messages
from django import forms
from django.db import transaction
from django.utils import timezone
from django.urls import reverse
from django.utils.html import format_html
from django.core.exceptions import ValidationError
from unfold.admin import ModelAdmin, TabularInline

from apps.notifications.models import Notification

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
    CustomerCampaign,
    CampaignRedemption,
    AppointmentGroup,
    DispatchConfiguration,
    BookingCompletionOTP,
    BookingStartOTPException,
    WorkerOffer,
    BookingQuote,
    BookingExtraWork,
    BookingWorkEvidence,
    RecurringWashPlan,
    RecurringWashVisit,
    BookingDispute,
    BookingDisputeHistory,
    BookingReworkProposal,
    BookingDisputeEvidence,
    BookingVariableCost,
    BookingFinanceReconciliation,
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
    can_delete = False
    exclude = ("worker",)
    readonly_fields = tuple(
        field.name for field in BookingAssignment._meta.fields if field.name != "worker"
    ) + ("worker_name_only", "worker_contact_access")
    fields = ("worker_name_only", "worker_contact_access") + tuple(
        field.name for field in BookingAssignment._meta.fields
        if field.name not in ("id", "booking", "worker")
    )

    @admin.display(description="Worker")
    def worker_name_only(self, obj):
        if obj is None:
            return "Assigned after booking dispatch."
        return obj.worker.user.name or "AIRway Professional"

    @admin.display(description="Worker phone (privacy-gated)")
    def worker_contact_access(self, obj):
        if obj is None:
            return "Available after assignment."
        from apps.workers.eligibility import worker_contact_access
        access = worker_contact_access(obj)
        return obj.worker.user.phone if access["phone_available"] else (
            "Locked until one hour before the accepted appointment."
        )

    def has_add_permission(self, request, obj=None):
        return False


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


class AppointmentGroupInline(TabularInline):
    model = AppointmentGroup
    extra = 0
    readonly_fields = ("group_number", "scheduled_at", "customer_message", "created_at")


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



@admin.register(CustomerCampaign)
class CustomerCampaignAdmin(ModelAdmin):
    list_display = ("name", "booking_sequence", "discount_type", "discount_value", "is_active", "starts_at", "ends_at", "budget_amount", "budget_reserved", "budget_spent", "remaining_budget")
    list_filter = ("is_active", "booking_sequence", "discount_type", "allow_stacking")
    search_fields = ("name", "description")
    filter_horizontal = ("eligible_services", "eligible_zones")
    readonly_fields = ("budget_reserved", "budget_spent", "created_at", "updated_at")
    fieldsets = (
        ("Campaign", {"fields": ("name", "description", "is_active", "priority", "booking_sequence")}),
        ("Discount", {"fields": ("discount_type", "discount_value", "max_discount_amount", "minimum_subtotal", "allow_stacking")}),
        ("Eligibility", {"fields": ("eligible_services", "eligible_zones", "max_redemptions_per_customer", "max_total_redemptions")}),
        ("Validity and budget", {"fields": ("starts_at", "ends_at", "budget_amount", "budget_reserved", "budget_spent")}),
    )
    @admin.display(description="Budget remaining")
    def remaining_budget(self, obj):
        return obj.remaining_budget


@admin.register(CampaignRedemption)
class CampaignRedemptionAdmin(ModelAdmin):
    list_display = ("id", "campaign", "customer", "order", "discount_amount", "status", "reserved_at", "redeemed_at")
    list_filter = ("status", "campaign")
    search_fields = ("customer__phone", "customer__name", "order__id", "campaign__name")
    readonly_fields = tuple(field.name for field in CampaignRedemption._meta.fields)
    actions = None
    def has_add_permission(self, request):
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
    inlines = [AppointmentGroupInline, OrderItemInline]


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
                Notification.objects.create(
                    user=assignment.worker.user,
                    type=Notification.Type.WORKER_OFFER_WITHDRAWN,
                    title="Service cancelled by AIRway",
                    body=f"AIRway cancelled booking #{locked.pk} because the service could not be fulfilled. This job is no longer assigned to you.",
                    channel=Notification.Channel.IN_APP,
                    data={"booking_id": locked.pk, "reason": "platform_unfulfilled"},
                )
                assignment.delete()

            appointment_group = getattr(locked, "appointment_group", None)
            if appointment_group is not None:
                # A group offer belongs to the complete shared appointment.
                # Keep it alive while any service in the group remains active;
                # withdraw it only when the whole appointment is cancelled.
                group_has_active_bookings = appointment_group.bookings.exclude(
                    status=Booking.Status.CANCELLED
                ).exists()
                if not group_has_active_bookings:
                    WorkerOffer.objects.filter(
                        appointment_group=appointment_group,
                        status__in=(WorkerOffer.Status.PENDING, WorkerOffer.Status.ACCEPTED),
                    ).update(
                        status=WorkerOffer.Status.WITHDRAWN,
                        responded_at=timezone.now(),
                    )
            else:
                WorkerOffer.objects.filter(
                    booking=locked,
                    status__in=(WorkerOffer.Status.PENDING, WorkerOffer.Status.ACCEPTED),
                ).update(
                    status=WorkerOffer.Status.WITHDRAWN,
                    responded_at=timezone.now(),
                )

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


class BookingVariableCostInline(TabularInline):
    model = BookingVariableCost
    extra = 0
    can_delete = False
    readonly_fields = ("category", "amount", "description", "reference", "created_by", "created_at", "updated_at")
    fields = readonly_fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Booking)
class BookingAdmin(ModelAdmin):
    list_display = ("id", "customer_name_only", "service", "variant", "booking_mode", "status", "actual_contribution_status", "actual_contribution", "scheduled_at", "created_at")
    list_filter = ("status", "booking_mode", "service")
    search_fields = ("customer__phone", "customer__name", "service__title")
    readonly_fields = (
        "created_at", "updated_at", "pricing_snapshot", "actual_finance_details",
        "customer_name_only", "customer_contact_access", "customer_address_access",
    )
    inlines = [BookingAddOnInline, BookingFormResponseInline, BookingAssignmentInline, BookingStatusHistoryInline, BookingVariableCostInline]
    actions = [mark_unfulfillable_and_refund]

    def get_exclude(self, request, obj=None):
        # Keep personal contact and the exact service address behind the same
        # acceptance/one-hour gate used by the worker-facing API.
        return ("customer", "address") if obj else ()

    @admin.display(description="Customer")
    def customer_name_only(self, obj):
        if obj is None:
            return "Available after booking is saved."
        return obj.customer.name or "AIRway Customer"

    def _contact_access(self, obj):
        if obj is None:
            return {"address_available": False, "phone_available": False, "contact_available_at": None}
        try:
            assignment = obj.assignment
        except BookingAssignment.DoesNotExist:
            return {"address_available": False, "phone_available": False, "contact_available_at": None}
        from apps.workers.eligibility import worker_contact_access
        return worker_contact_access(assignment)

    @admin.display(description="Customer phone (privacy-gated)")
    def customer_contact_access(self, obj):
        access = self._contact_access(obj)
        if access["phone_available"]:
            return obj.customer.phone
        return "Locked until worker accepts and the one-hour contact window opens."

    @admin.display(description="Service address (privacy-gated)")
    def customer_address_access(self, obj):
        access = self._contact_access(obj)
        if access["address_available"]:
            return obj.address.full_address
        return "Locked until the worker accepts the assignment."

    def _actual_finance_report(self, obj):
        if not hasattr(obj, "_actual_finance_report"):
            from apps.catalog.actual_finance import calculate_booking_actual_finance
            obj._actual_finance_report = calculate_booking_actual_finance(obj)
        return obj._actual_finance_report

    @admin.display(description="Actual finance status")
    def actual_contribution_status(self, obj):
        return self._actual_finance_report(obj)['status'].title()

    @admin.display(description="Partial contribution")
    def actual_contribution(self, obj):
        report = self._actual_finance_report(obj)
        value = report['partial_contribution']
        return '₹%s (partial)' % value if report['status'] != 'complete' else '₹%s'

    @admin.display(description="Actual finance reconciliation")
    def actual_finance_details(self, obj):
        report = self._actual_finance_report(obj)
        return "; ".join(report['reasons']) or "All recorded components reconciled."


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


@admin.register(BookingExtraWork)
class BookingExtraWorkAdmin(ModelAdmin):
    list_display = (
        "id", "booking", "appointment_group", "worker", "total_amount",
        "worker_payout_amount", "status", "payment_choice", "payment_status", "created_at",
    )
    list_filter = ("status", "payment_choice", "created_at")
    search_fields = ("booking__id", "booking__customer__phone", "worker__user__phone")
    readonly_fields = (
        "request_key", "booking", "appointment_group", "worker", "reason",
        "line_items", "subtotal", "worker_payout_amount", "worker_payout_snapshot",
        "tax_amount", "total_amount", "additional_duration_minutes", "status", "payment_choice", "payment_status",
        "customer_response_note", "expires_at", "responded_at",
        "approved_at", "created_at", "updated_at",
    )
    fields = readonly_fields

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(BookingQuote)
class BookingQuoteAdmin(ModelAdmin):
    list_display = ("id", "booking", "worker", "version", "status", "total_amount", "worker_payout_amount", "expires_at", "responded_at")
    list_filter = ("status", "created_at")
    search_fields = ("booking__id", "booking__customer__phone", "worker__user__phone")
    readonly_fields = tuple(field.name for field in BookingQuote._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(BookingAssignment)
class BookingAssignmentAdmin(ModelAdmin):
    list_display = ("booking", "worker_name_only", "assigned_at", "accepted_at", "started_at", "completed_at")
    search_fields = ("booking__id", "worker__user__phone")
    exclude = ("worker",)
    readonly_fields = tuple(
        field.name for field in BookingAssignment._meta.fields if field.name != "worker"
    ) + ("worker_name_only", "worker_contact_access")
    fields = ("worker_name_only", "worker_contact_access") + tuple(
        field.name for field in BookingAssignment._meta.fields
        if field.name not in ("id", "booking", "worker")
    )

    @admin.display(description="Worker")
    def worker_name_only(self, obj):
        if obj is None:
            return "Assigned after booking dispatch."
        return obj.worker.user.name or "AIRway Professional"

    @admin.display(description="Worker phone (privacy-gated)")
    def worker_contact_access(self, obj):
        if obj is None:
            return "Available after assignment."
        from apps.workers.eligibility import worker_contact_access
        access = worker_contact_access(obj)
        return obj.worker.user.phone if access["phone_available"] else (
            "Locked until one hour before the accepted appointment."
        )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(DispatchConfiguration)
class DispatchConfigurationAdmin(ModelAdmin):
    list_display = ("is_enabled", "offer_expiry_minutes", "priority_order", "late_cancellation_window_hours", "late_cancellation_fee_percent", "no_show_grace_minutes")
    fieldsets = (
        ("Dispatch control", {"fields": ("is_enabled",)}),
        ("Simultaneous worker offers", {"fields": ("offer_expiry_minutes", "priority_order")}),
        ("Customer cancellation and no-show policy", {"fields": ("late_cancellation_window_hours", "late_cancellation_fee_percent", "no_show_grace_minutes")}),
        ("Audit", {"fields": ("created_at", "updated_at")}),
    )
    readonly_fields = ("created_at", "updated_at")

    def has_add_permission(self, request):
        return not DispatchConfiguration.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False



@admin.register(BookingStartOTPException)
class BookingStartOTPExceptionAdmin(ModelAdmin):
    list_display = (
        "id", "booking", "worker_name", "status", "created_at",
        "reviewed_by", "reviewed_at",
    )
    list_filter = ("status", "created_at", "reviewed_at")
    search_fields = (
        "booking__id", "booking__customer__phone",
        "assignment__worker__user__phone", "reason",
    )
    readonly_fields = tuple(field.name for field in BookingStartOTPException._meta.fields)
    fields = readonly_fields
    actions = ("approve_service_start_exception", "reject_service_start_exception")

    @admin.display(description="Worker")
    def worker_name(self, obj):
        return obj.requested_by.user.name or "AIRway Professional"

    @admin.action(description="Approve selected OTP exceptions and start the service")
    def approve_service_start_exception(self, request, queryset):
        approved = 0
        blocked = 0
        for exception_id in queryset.filter(
            status=BookingStartOTPException.Status.PENDING
        ).values_list("pk", flat=True):
            try:
                with transaction.atomic():
                    exception = BookingStartOTPException.objects.select_for_update().get(pk=exception_id)
                    if exception.status != BookingStartOTPException.Status.PENDING:
                        continue
                    booking_ref = Booking.objects.select_related("appointment_group").get(pk=exception.booking_id)
                    if booking_ref.appointment_group_id:
                        group_ref = AppointmentGroup.objects.get(pk=booking_ref.appointment_group_id)
                        Order.objects.select_for_update().get(pk=group_ref.order_id)
                        group = AppointmentGroup.objects.select_for_update().get(pk=group_ref.pk)
                        bookings = list(
                            Booking.objects.select_for_update(of=("self",))
                            .filter(appointment_group=group)
                            .exclude(status=Booking.Status.CANCELLED)
                            .order_by("pk")
                        )
                        assignments = list(
                            BookingAssignment.objects.select_for_update()
                            .filter(booking__in=bookings)
                            .select_related("booking", "worker")
                            .order_by("booking_id")
                        )
                    else:
                        booking = Booking.objects.select_for_update(of=("self",)).get(pk=booking_ref.pk)
                        assignment = BookingAssignment.objects.select_for_update().get(pk=exception.assignment_id)
                        bookings, assignments = [booking], [assignment]

                    if (
                        len(assignments) != len(bookings)
                        or any(
                            row.booking.status not in (Booking.Status.ASSIGNED, Booking.Status.CONFIRMED)
                            or not row.accepted_at
                            or not row.arrived_at
                            or row.started_at
                            or row.worker_id != exception.assignment.worker_id
                            or row.worker.status != "approved"
                            for row in assignments
                        )
                    ):
                        blocked += 1
                        continue

                    order_item = getattr(booking_ref, "order_item", None)
                    if order_item and "payment_allocation_v1" in (order_item.order.metadata or {}):
                        from apps.payments.models import Payment
                        advance_paid = Payment.objects.filter(
                            order=order_item.order,
                            stage=Payment.Stage.ADVANCE,
                            appointment_group__isnull=True,
                            status=Payment.Status.PAID,
                        ).exists()
                        if not advance_paid:
                            blocked += 1
                            continue

                    now = timezone.now()
                    for row in assignments:
                        row.started_at = now
                        row.start_otp_hash = ""
                        row.start_otp_expires_at = now
                        row.save(update_fields=[
                            "started_at", "start_otp_hash",
                            "start_otp_expires_at", "updated_at",
                        ])
                    for active_booking in bookings:
                        old_status = active_booking.status
                        active_booking.status = Booking.Status.IN_PROGRESS
                        active_booking.save(update_fields=["status", "updated_at"])
                        BookingStatusHistory.objects.create(
                            booking=active_booking,
                            from_status=old_status,
                            to_status=Booking.Status.IN_PROGRESS,
                            changed_by=request.user,
                            note=(
                                f"Admin-approved service-start OTP exception #{exception.pk}. "
                                f"Worker reason: {exception.reason}"
                            ),
                        )
                        from apps.bookings.models import RecurringWashVisit
                        RecurringWashVisit.objects.filter(
                            booking=active_booking,
                            status=RecurringWashVisit.Status.BOOKED,
                        ).update(status=RecurringWashVisit.Status.IN_PROGRESS, updated_at=now)

                    exception.status = BookingStartOTPException.Status.APPROVED
                    exception.reviewed_by = request.user
                    exception.reviewed_at = now
                    exception.review_note = "Approved by admin after reviewing the reported OTP issue."
                    exception.save(update_fields=[
                        "status", "reviewed_by", "reviewed_at",
                        "review_note", "updated_at",
                    ])
                    Notification.objects.create(
                        user=booking_ref.customer,
                        type=Notification.Type.SYSTEM_ANNOUNCEMENT,
                        title="Service start exception approved",
                        body="AIRway Admin verified the OTP issue and approved the service start.",
                        channel=Notification.Channel.IN_APP,
                        data={"purpose": "service_start_otp_exception", "exception_id": exception.pk, "booking_id": booking_ref.pk},
                    )
                    Notification.objects.create(
                        user=exception.requested_by.user,
                        type=Notification.Type.SYSTEM_ANNOUNCEMENT,
                        title="Service start approved",
                        body="AIRway Admin approved your OTP exception request. The service is now marked In Progress.",
                        channel=Notification.Channel.IN_APP,
                        data={"purpose": "service_start_otp_exception", "exception_id": exception.pk, "booking_id": booking_ref.pk},
                    )
                    approved += 1
            except Exception:
                blocked += 1
        if blocked:
            self.message_user(
                request,
                f"Approved {approved} exception(s). {blocked} could not be approved because the appointment state changed or processing failed.",
                level=messages.WARNING,
            )
        else:
            self.message_user(
                request, f"Approved {approved} service-start exception(s).",
                level=messages.SUCCESS,
            )

    @admin.action(description="Reject selected OTP exceptions")
    def reject_service_start_exception(self, request, queryset):
        pending = queryset.filter(status=BookingStartOTPException.Status.PENDING)
        count = 0
        for exception in pending.select_related("requested_by__user", "booking__customer"):
            now = timezone.now()
            exception.status = BookingStartOTPException.Status.REJECTED
            exception.reviewed_by = request.user
            exception.reviewed_at = now
            exception.review_note = "Rejected by admin after reviewing the reported OTP issue."
            exception.save(update_fields=[
                "status", "reviewed_by", "reviewed_at",
                "review_note", "updated_at",
            ])
            Notification.objects.create(
                user=exception.requested_by.user,
                type=Notification.Type.SYSTEM_ANNOUNCEMENT,
                title="Service start exception rejected",
                body="AIRway Admin could not approve your OTP exception. Contact support before proceeding.",
                channel=Notification.Channel.IN_APP,
                data={"purpose": "service_start_otp_exception", "exception_id": exception.pk, "booking_id": exception.booking_id},
            )
            count += 1
        self.message_user(request, f"Rejected {count} service-start exception request(s).", level=messages.SUCCESS)

    def has_add_permission(self, request):
        return False

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




class BookingDisputeEvidenceInline(TabularInline):
    model = BookingDisputeEvidence
    extra = 0
    can_delete = False
    readonly_fields = ("uploaded_by", "original_name", "file_path", "note", "created_at", "updated_at")
    fields = readonly_fields


class BookingDisputeHistoryInline(TabularInline):
    model = BookingDisputeHistory
    extra = 0
    can_delete = False
    readonly_fields = ("from_status", "to_status", "changed_by", "note", "created_at")
    fields = readonly_fields

    def has_add_permission(self, request, obj=None):
        return False



class BookingReworkProposalAdminForm(forms.ModelForm):
    class Meta:
        model = BookingReworkProposal
        fields = ("dispute", "worker", "scheduled_at")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["dispute"].queryset = BookingDispute.objects.filter(
            status=BookingDispute.Status.RESOLVED,
            requested_outcome=BookingDispute.RequestedOutcome.REWORK,
            resolved_by__isnull=False,
            resolved_at__isnull=False,
            booking__booking_mode=Booking.BookingMode.SCHEDULED,
        ).exclude(
            rework_proposals__status__in=[
                BookingReworkProposal.Status.PENDING_CUSTOMER,
                BookingReworkProposal.Status.ACCEPTED,
            ]
        ).select_related("booking__service", "booking__address__zone").distinct()
        self.fields["worker"].queryset = self.fields["worker"].queryset.filter(
            status="approved",
            is_online=True,
        ).distinct()
        dispute_id = self.data.get("dispute") or self.initial.get("dispute")
        if dispute_id:
            dispute = BookingDispute.objects.filter(pk=dispute_id).select_related(
                "booking__service", "booking__address__zone"
            ).first()
            if dispute:
                self.fields["worker"].queryset = self.fields["worker"].queryset.filter(
                    worker_services__service=dispute.booking.service,
                    worker_zones__zone=dispute.booking.address.zone,
                ).distinct()

    def clean(self):
        cleaned = super().clean()
        dispute = cleaned.get("dispute")
        worker = cleaned.get("worker")
        scheduled_at = cleaned.get("scheduled_at")
        if not (dispute and worker and scheduled_at):
            return cleaned
        booking = dispute.booking
        if (
            dispute.status != BookingDispute.Status.RESOLVED
            or dispute.requested_outcome != BookingDispute.RequestedOutcome.REWORK
            or dispute.resolved_by_id is None
        ):
            self.add_error("dispute", "Only an Admin-resolved rework case can receive a recovery appointment.")
            return cleaned
        if (
            booking.booking_mode != Booking.BookingMode.SCHEDULED
            or booking.service.pricing_type == "quote"
        ):
            self.add_error(
                "dispute",
                "Automatic no-charge recovery currently supports fixed or per-unit scheduled services only.",
            )
            return cleaned
        if scheduled_at <= timezone.now():
            self.add_error("scheduled_at", "Choose a future recovery appointment time.")
            return cleaned
        from apps.bookings.dispatcher import DispatcherService
        from apps.workers.eligibility import required_worker_gender_for_booking
        duration = (
            booking.variant.duration_minutes
            if booking.variant_id and booking.variant.duration_minutes
            else booking.service.duration_minutes
        ) or 60
        try:
            required_gender = required_worker_gender_for_booking(
                booking.service, booking.customer_answers
            )
        except ValueError as exc:
            self.add_error("dispute", str(exc))
            return cleaned
        eligible = DispatcherService._get_eligible_workers(
            service=booking.service,
            zone=booking.address.zone,
            scheduled_at=scheduled_at,
            duration_minutes=duration,
            exclude_booking_id=booking.pk,
            exclude_customer_id=booking.customer_id,
            required_gender=required_gender,
            required_tasks=(booking.variant.included_tasks if booking.variant_id else []),
        )
        if not eligible.filter(pk=worker.pk).exists():
            self.add_error(
                "worker",
                "This professional is not currently eligible or available for the selected service, zone and time.",
            )
        return cleaned


@admin.register(BookingReworkProposal)
class BookingReworkProposalAdmin(ModelAdmin):
    form = BookingReworkProposalAdminForm
    list_display = ("id", "dispute", "worker", "scheduled_at", "status", "followup_booking")
    list_filter = ("status", "scheduled_at")
    search_fields = ("dispute__booking__id", "worker__user__phone")
    readonly_fields = ("status", "created_by", "responded_at", "followup_booking", "created_at", "updated_at")
    fields = ("dispute", "worker", "scheduled_at") + readonly_fields

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        dispute_id = request.GET.get("dispute")
        if dispute_id:
            initial["dispute"] = dispute_id
        return initial

    def save_model(self, request, obj, form, change):
        if change:
            raise ValidationError("A rework proposal cannot be edited after it is sent to the customer.")
        obj.created_by = request.user
        super().save_model(request, obj, form, change)
        Notification.objects.create(
            user=obj.dispute.booking.customer,
            type=Notification.Type.SYSTEM_ANNOUNCEMENT,
            title="AIRway proposed a free recovery visit",
            body=f"A no-charge recovery appointment is proposed for {timezone.localtime(obj.scheduled_at):%d %b %Y, %I:%M %p}. Review and accept it in your order details.",
            channel=Notification.Channel.IN_APP,
            data={"dispute_id": obj.dispute_id, "rework_proposal_id": obj.pk},
        )

    def has_add_permission(self, request):
        return request.user.is_staff

    def has_view_permission(self, request, obj=None):
        return request.user.is_staff

    def has_change_permission(self, request, obj=None):
        return request.user.is_staff and obj is None

    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(BookingDispute)
class BookingDisputeAdmin(ModelAdmin):
    inlines = [BookingDisputeEvidenceInline, BookingDisputeHistoryInline]
    list_display = ("id", "booking", "raised_by", "raised_by_role", "category", "status", "created_at")
    list_filter = ("status", "category", "raised_by_role", "created_at")
    search_fields = ("booking__id", "raised_by__phone", "description")
    readonly_fields = (
        "booking", "raised_by", "raised_by_role", "category", "description",
        "requested_outcome", "evidence_items", "resolved_by", "resolved_at",
        "created_at", "updated_at", "refund_history", "rework_action",
    )
    fields = readonly_fields + ("status", "resolution_note")

    @admin.display(description="Linked dispute refunds")
    def refund_history(self, obj):
        if not obj.pk:
            return "Save the dispute first."
        refunds = list(obj.payment_refunds.all())
        if refunds:
            return "; ".join(
                "Refund #" + str(item.pk) + ": ₹" + str(item.amount)
                + " (" + item.get_status_display() + ")"
                for item in refunds
            )
        if (
            obj.status == BookingDispute.Status.RESOLVED
            and obj.requested_outcome == BookingDispute.RequestedOutcome.REFUND_REVIEW
        ):
            url = reverse("admin:payments_paymentrefund_add") + "?dispute=" + str(obj.pk)
            return format_html('<a href="{}">Create linked dispute refund</a>', url)
        return "No refund linked."

    @admin.display(description="Rework scheduling")
    def rework_action(self, obj):
        if (
            obj.status != BookingDispute.Status.RESOLVED
            or obj.requested_outcome != BookingDispute.RequestedOutcome.REWORK
        ):
            return "Resolve this rework case before scheduling."
        proposal = obj.rework_proposals.order_by("-created_at").first()
        if proposal and proposal.status in (
            BookingReworkProposal.Status.PENDING_CUSTOMER,
            BookingReworkProposal.Status.ACCEPTED,
        ):
            return (
                f"Proposal #{proposal.pk}: {proposal.get_status_display()} — "
                f"{timezone.localtime(proposal.scheduled_at):%d %b %Y, %I:%M %p}"
            )
        url = reverse("admin:bookings_bookingreworkproposal_add") + "?dispute=" + str(obj.pk)
        return format_html('<a href="{}">Propose a no-charge rework appointment</a>', url)

    def save_model(self, request, obj, form, change):
        if change:
            # Serialize Admin edits against concurrent API status transitions.
            previous = BookingDispute.objects.select_for_update().get(pk=obj.pk)
            allowed = {
                BookingDispute.Status.OPEN: {
                    BookingDispute.Status.IN_REVIEW,
                    BookingDispute.Status.RESOLVED,
                    BookingDispute.Status.REJECTED,
                },
                BookingDispute.Status.IN_REVIEW: {
                    BookingDispute.Status.RESOLVED,
                    BookingDispute.Status.REJECTED,
                },
                BookingDispute.Status.RESOLVED: {BookingDispute.Status.CLOSED},
                BookingDispute.Status.REJECTED: {BookingDispute.Status.CLOSED},
            }
            if obj.status != previous.status and obj.status not in allowed.get(previous.status, set()):
                raise ValidationError("Invalid dispute status transition.")
            if obj.status in (BookingDispute.Status.RESOLVED, BookingDispute.Status.REJECTED):
                if not obj.resolution_note.strip():
                    raise ValidationError("A resolution note is required.")
                if previous.status != obj.status:
                    obj.resolved_by = request.user
                    obj.resolved_at = timezone.now()
        super().save_model(request, obj, form, change)
        if change and obj.status != previous.status:
            BookingDisputeHistory.objects.create(
                dispute=obj,
                from_status=previous.status,
                to_status=obj.status,
                changed_by=request.user,
                note=obj.resolution_note,
            )
            booking = obj.booking
            recipients = {booking.customer_id: booking.customer}
            assignment = getattr(booking, "assignment", None)
            if assignment is not None:
                recipients[assignment.worker.user_id] = assignment.worker.user
            for recipient in recipients.values():
                if recipient.pk == request.user.pk:
                    continue
                Notification.objects.create(
                    user=recipient,
                    type=Notification.Type.SYSTEM_ANNOUNCEMENT,
                    title="AIRway support updated your case",
                    body=f"Your support case for booking #{booking.pk} is now {obj.get_status_display().lower()}.",
                    channel=Notification.Channel.IN_APP,
                    data={"booking_id": booking.pk, "dispute_id": obj.pk, "status": obj.status},
                )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False




@admin.register(BookingVariableCost)
class BookingVariableCostAdmin(ModelAdmin):
    list_display = ("id", "booking", "category", "amount", "description", "created_by", "created_at")
    list_filter = ("category", "created_at")
    search_fields = ("booking__id", "description", "reference")
    readonly_fields = ("created_by", "created_at", "updated_at")
    fields = (
        "booking", "category", "amount", "description", "reference",
        "created_by", "created_at", "updated_at",
    )

    def has_add_permission(self, request):
        return request.user.is_staff

    def save_model(self, request, obj, form, change):
        if change:
            raise ValidationError("Variable cost entries are append-only. Add a correcting entry instead.")
        obj.created_by = request.user
        super().save_model(request, obj, form, change)
        BookingFinanceReconciliation.objects.filter(booking=obj.booking).update(
            other_costs_reviewed=False, reviewed_by=None, reviewed_at=None,
        )

    def has_change_permission(self, request, obj=None):
        return request.user.is_staff and obj is None

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(BookingFinanceReconciliation)
class BookingFinanceReconciliationAdmin(ModelAdmin):
    list_display = ("booking", "other_costs_reviewed", "reviewed_by", "reviewed_at", "updated_at")
    list_filter = ("other_costs_reviewed", "reviewed_at")
    search_fields = ("booking__id", "booking__customer__phone")
    readonly_fields = ("reviewed_by", "reviewed_at", "created_at", "updated_at")
    fields = ("booking", "other_costs_reviewed", "review_note") + readonly_fields

    def save_model(self, request, obj, form, change):
        if obj.other_costs_reviewed and not obj.review_note.strip():
            raise ValidationError("A review note is required to confirm reconciliation.")
        if obj.other_costs_reviewed:
            obj.reviewed_by = request.user
            obj.reviewed_at = timezone.now()
        else:
            obj.reviewed_by = None
            obj.reviewed_at = None
        super().save_model(request, obj, form, change)

    def has_add_permission(self, request):
        return request.user.is_staff

    def has_delete_permission(self, request, obj=None):
        return False
