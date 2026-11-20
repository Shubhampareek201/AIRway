import uuid

from django import forms
from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.core.exceptions import PermissionDenied, ValidationError
from unfold.admin import ModelAdmin

from apps.bookings.models import BookingExtraWork, BookingDispute
from .models import Payment, PaymentRefund
from .refunds import (
    _existing_refund_components,
    _line_stage_amount,
    issue_admin_partial_refund,
)


@admin.register(Payment)
class PaymentAdmin(ModelAdmin):
    list_display = (
        "id", "order", "appointment_group", "extra_work", "customer",
        "stage", "amount", "status", "created_at",
    )
    list_filter = ("stage", "status", "created_at")
    search_fields = ("id", "order__id", "appointment_group__id", "extra_work__id", "customer__phone")
    readonly_fields = tuple(field.name for field in Payment._meta.fields)

    def has_view_permission(self, request, obj=None):
        return request.user.is_staff

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class PaymentRefundAdminForm(forms.ModelForm):
    idempotency_key = forms.UUIDField(
        initial=uuid.uuid4,
        widget=forms.HiddenInput,
    )

    class Meta:
        model = PaymentRefund
        fields = ("payment", "booking", "extra_work", "dispute", "amount", "reason", "admin_note")
        widgets = {
            "admin_note": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["payment"].queryset = Payment.objects.filter(
            status=Payment.Status.PAID
        ).select_related("customer")
        self.fields["extra_work"].queryset = BookingExtraWork.objects.filter(
            status=BookingExtraWork.Status.APPROVED,
            payment_status="paid",
        ).select_related("booking")
        self.fields["extra_work"].required = False
        self.fields["extra_work"].help_text = (
            "Choose a specific extra-work proposal to refund only that approved add-on."
        )
        self.fields["dispute"].queryset = BookingDispute.objects.filter(
            status=BookingDispute.Status.RESOLVED,
            requested_outcome=BookingDispute.RequestedOutcome.REFUND_REVIEW,
        ).select_related("booking")
        self.fields["dispute"].required = False
        self.fields["dispute"].help_text = (
            "Required for a dispute-resolution refund; the case must already be resolved by AIRway support."
        )
        self.fields["reason"].choices = [
            (PaymentRefund.Reason.ADMIN_ADJUSTMENT, "Admin partial refund"),
            (PaymentRefund.Reason.DISPUTE_RESOLUTION, "Dispute resolution"),
        ]
        self.fields["amount"] = forms.DecimalField(
            max_digits=10,
            decimal_places=2,
            min_value=0.01,
            help_text="Must not exceed the remaining captured amount for this service.",
        )
        self.fields["admin_note"].required = True
        self.fields["admin_note"].help_text = (
            "Required audit explanation. This is retained with the refund record."
        )

    def clean(self):
        cleaned = super().clean()
        payment = cleaned.get("payment")
        booking = cleaned.get("booking")
        extra_work = cleaned.get("extra_work")
        dispute = cleaned.get("dispute")
        reason = cleaned.get("reason")
        amount = cleaned.get("amount")
        key = cleaned.get("idempotency_key")
        if not (payment and booking and amount and key):
            return cleaned
        if reason == PaymentRefund.Reason.DISPUTE_RESOLUTION:
            if dispute is None:
                self.add_error("dispute", "Select the resolved dispute this refund settles.")
            elif dispute.booking_id != booking.pk:
                self.add_error("dispute", "The selected dispute does not belong to this booking.")
        elif dispute is not None:
            self.add_error("dispute", "A dispute can only be linked to a dispute-resolution refund.")
        if payment.extra_work_id:
            if extra_work is not None and extra_work.pk != payment.extra_work_id:
                self.add_error("extra_work", "Select the extra-work proposal linked to this payment.")
                return cleaned
            extra_work = payment.extra_work
            cleaned["extra_work"] = extra_work
        if extra_work is not None and extra_work.booking_id != booking.pk:
            self.add_error("extra_work", "The extra-work proposal does not belong to this booking.")
            return cleaned
        existing = PaymentRefund.objects.filter(idempotency_key=str(key)).first()
        if existing:
            if (
                existing.payment_id != payment.pk
                or existing.booking_id != booking.pk
                or existing.extra_work_id != (extra_work.pk if extra_work else None)
                or existing.dispute_id != (dispute.pk if dispute else None)
                or existing.amount != amount
            ):
                self.add_error("idempotency_key", "This request key has already been used.")
            return cleaned
        if payment.status != Payment.Status.PAID:
            self.add_error("payment", "Only captured payments can be refunded.")
            return cleaned
        if extra_work is not None and PaymentRefund.objects.filter(
            payment=payment,
            booking=booking,
            extra_work__isnull=True,
        ).exists():
            self.add_error("extra_work", "A booking-level refund already exists, so this proposal cannot be isolated safely.")
            return cleaned
        line_total, wallet_captured, gateway_captured, _ = _line_stage_amount(
            payment, booking, extra_work=extra_work
        )
        if line_total <= 0:
            self.add_error("booking", "This payment has no captured allocation for this service.")
            return cleaned
        _, refunded_wallet, refunded_gateway = _existing_refund_components(
            payment, booking, extra_work=extra_work
        )
        remaining = wallet_captured + gateway_captured - refunded_wallet - refunded_gateway
        if remaining < 0:
            self.add_error("amount", "Existing refunds exceed the captured allocation; reconciliation is required.")
        elif amount > remaining:
            self.add_error("amount", f"Maximum remaining refundable amount is ₹{remaining:.2f}.")
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.idempotency_key = str(self.cleaned_data["idempotency_key"])
        if commit:
            instance.save()
        return instance


@admin.register(PaymentRefund)
class PaymentRefundAdmin(ModelAdmin):
    form = PaymentRefundAdminForm
    list_display = (
        "id", "booking", "dispute", "extra_work", "payment", "amount", "wallet_amount",
        "gateway_amount", "reason", "status", "requested_by",
        "gateway_refund_id", "failure_summary", "created_at",
    )
    list_filter = ("status", "reason", "created_at")
    search_fields = (
        "id", "booking__id", "dispute__id", "extra_work__id", "payment__id", "gateway_refund_id",
        "booking__customer__phone", "failure_reason",
    )
    readonly_fields = (
        "payment", "booking", "dispute", "extra_work", "order_item", "amount", "wallet_amount",
        "gateway_amount", "reason", "status", "gateway_refund_id",
        "failure_reason", "processed_at", "requested_by", "admin_note",
        "idempotency_key", "created_at", "updated_at",
    )

    def get_fields(self, request, obj=None):
        if obj is None:
            return ("payment", "booking", "dispute", "extra_work", "amount", "reason", "admin_note", "idempotency_key")
        return self.readonly_fields

    def get_readonly_fields(self, request, obj=None):
        return () if obj is None else self.readonly_fields

    @admin.display(description="Gateway / reconciliation note")
    def failure_summary(self, obj):
        return obj.failure_reason[:100] if obj.failure_reason else "—"

    def has_view_permission(self, request, obj=None):
        return request.user.is_staff

    def has_add_permission(self, request):
        return request.user.is_superuser or request.user.has_perm(
            "payments.issue_partial_paymentrefund"
        )

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        try:
            return super().changeform_view(request, object_id, form_url, extra_context)
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
            return HttpResponseRedirect(request.path)

    def save_model(self, request, obj, form, change):
        if change:
            raise PermissionDenied("Refund records are immutable.")
        try:
            refund = issue_admin_partial_refund(
                payment=obj.payment,
                booking=obj.booking,
                amount=obj.amount,
                requested_by=request.user,
                admin_note=obj.admin_note,
                idempotency_key=obj.idempotency_key,
                reason=obj.reason,
                extra_work=obj.extra_work,
                dispute=obj.dispute,
            )
        except ValueError as exc:
            raise ValidationError(str(exc))
        obj.pk = refund.pk
        obj.status = refund.status
        obj.wallet_amount = refund.wallet_amount
        obj.gateway_amount = refund.gateway_amount
        obj.gateway_refund_id = refund.gateway_refund_id
        obj.failure_reason = refund.failure_reason
        obj.processed_at = refund.processed_at
        obj.requested_by = refund.requested_by
        messages.add_message(
            request,
            messages.SUCCESS if refund.status == PaymentRefund.Status.PROCESSED else messages.WARNING,
            f"Refund #{refund.pk} recorded: ₹{refund.amount} ({refund.get_status_display()}).",
        )
