from decimal import Decimal, InvalidOperation

from django import forms
from django.contrib import admin, messages
from django.contrib.admin.helpers import ActionForm
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.forms.models import BaseInlineFormSet
from simple_history.utils import update_change_reason
from unfold.admin import ModelAdmin, TabularInline

from .pricing import service_pricing_ready
from .models import (
    AddOn, Banner, Category, CategoryAudienceOption, CityService, FormField, Service,
    ServiceImage, ServiceVariant, ServiceInspectionRate, VehicleMake, VehicleModel,
)


class PricingBulkActionForm(ActionForm):
    pricing_reason = forms.CharField(required=False, label="Reason for price/payout change")
    new_customer_price = forms.DecimalField(required=False, min_value=0, max_digits=10, decimal_places=2, label="Set customer price")
    new_worker_payout = forms.DecimalField(required=False, min_value=0, max_digits=10, decimal_places=2, label="Set worker payout")


class PricingReasonInlineFormSet(BaseInlineFormSet):
    def save_existing(self, form, instance, commit=True):
        obj = super().save_existing(form, instance, commit=commit)
        reason = str(form.cleaned_data.get("pricing_change_reason", "")).strip()
        if commit and reason:
            update_change_reason(obj, reason)
        return obj

    def clean(self):
        super().clean()
        if any(self.errors):
            return
        for form in self.forms:
            data = getattr(form, "cleaned_data", {})
            if not data or data.get("DELETE") or not form.instance.pk:
                continue
            original = self.model.objects.filter(pk=form.instance.pk).first()
            if original is None:
                continue
            changed = any(
                getattr(original, field) != data.get(field, getattr(original, field))
                for field in ("price", "worker_payout")
            )
            if changed and not str(data.get("pricing_change_reason", "")).strip():
                raise ValidationError(
                    "A reason is required whenever customer price or worker payout changes."
                )


class PricingAuditAdminMixin:
    action_form = PricingBulkActionForm
    actions = ("bulk_update_pricing",)

    def save_model(self, request, obj, form, change):
        reason = str(getattr(obj, "pricing_change_reason", "") or "").strip()
        if change:
            original = self.model.objects.get(pk=obj.pk)
            changed = (
                original.price != obj.price
                or original.worker_payout != obj.worker_payout
            )
            if changed and not reason:
                raise ValidationError(
                    "Enter a reason for changing the customer price or worker payout."
                )
        super().save_model(request, obj, form, change)
        if change and reason:
            update_change_reason(obj, reason)

    @admin.action(description="Bulk set customer price and/or worker payout")
    def bulk_update_pricing(self, request, queryset):
        reason = str(request.POST.get("pricing_reason", "")).strip()
        price_raw = request.POST.get("new_customer_price", "")
        payout_raw = request.POST.get("new_worker_payout", "")
        if not reason or (price_raw in ("", None) and payout_raw in ("", None)):
            self.message_user(
                request,
                "Provide a reason and at least one new price or worker payout.",
                level=messages.ERROR,
            )
            return
        try:
            new_price = Decimal(price_raw) if price_raw not in ("", None) else None
            new_payout = Decimal(payout_raw) if payout_raw not in ("", None) else None
        except (InvalidOperation, TypeError, ValueError):
            self.message_user(request, "Enter valid amounts.", level=messages.ERROR)
            return

        if (new_price is not None and new_price < 0) or (new_payout is not None and new_payout < 0):
            self.message_user(request, "Prices and payouts cannot be negative.", level=messages.ERROR)
            return
        with transaction.atomic():
            rows = list(queryset.select_for_update())
            if new_price is not None and any(new_price > row.mrp for row in rows):
                self.message_user(
                    request,
                    "Bulk customer price cannot exceed the MRP of any selected item.",
                    level=messages.ERROR,
                )
                return
            updated = 0
            for obj in rows:
                changed = False
                if new_price is not None and obj.price != new_price:
                    obj.price = new_price
                    changed = True
                if new_payout is not None and obj.worker_payout != new_payout:
                    obj.worker_payout = new_payout
                    changed = True
                if changed:
                    obj.pricing_change_reason = reason
                    obj.save()
                    update_change_reason(obj, reason)
                    updated += 1
        self.message_user(
            request,
            f"Updated pricing for {updated} item(s). The reason and before/after values were recorded.",
            level=messages.SUCCESS,
        )


class CategoryAudienceOptionInline(TabularInline):
    model = CategoryAudienceOption
    extra = 0
    fields = ("audience", "title", "subtitle", "image", "image_secondary", "sort_order", "is_active")


class VariantInline(TabularInline):
    model = ServiceVariant
    extra = 0
    fields = ("title", "title_hi", "description", "included_tasks", "image", "attributes", "mrp", "price", "worker_payout", "pricing_change_reason", "duration_minutes", "sort_order", "is_active")
    formset = PricingReasonInlineFormSet
    show_change_link = True


class AddOnInline(TabularInline):
    model = AddOn
    extra = 0
    fields = ("title", "title_hi", "description", "image", "mrp", "price", "worker_payout", "pricing_change_reason", "sort_order", "is_active")
    formset = PricingReasonInlineFormSet
    show_change_link = True


class ServiceInspectionRateInline(TabularInline):
    model = ServiceInspectionRate
    extra = 0
    fields = ("title", "code", "description", "rate_type", "customer_price", "worker_payout", "pricing_change_reason", "sort_order", "is_active")


class FormFieldInline(TabularInline):
    model = FormField
    extra = 0
    fields = ("label", "key", "field_type", "options", "is_required", "visibility_rules", "sort_order", "is_active")
    show_change_link = True


class ServiceImageInline(TabularInline):
    model = ServiceImage
    extra = 0
    show_change_link = True


@admin.register(Category)
class CategoryAdmin(ModelAdmin):
    list_display = ("title", "parent", "sort_order", "is_active", "updated_at")
    list_editable = ("sort_order", "is_active")
    list_filter = ("is_active", "parent")
    search_fields = ("title", "title_hi", "slug")
    prepopulated_fields = {"slug": ("title",)}
    ordering = ("parent__title", "sort_order", "title")
    list_per_page = 30
    save_on_top = True
    inlines = [CategoryAudienceOptionInline]
    fieldsets = (
        ("Category details", {"fields": ("title", "title_hi", "slug", "parent", "image")}),
        ("Customer flow", {"fields": ("flow_steps",), "description": "Configure pre-service questions as JSON. For a choice that represents a child category, set next_category_slug (or next_category_id) on that option. The app opens that child directly, then displays its own children. Example Home Cleaning tree: Home Cleaning > Full Home > 1 BHK / 2 BHK / 3 BHK; Home Cleaning > Specific Area > Kitchen / Bathroom / Bedroom; Home Cleaning > Item > Sofa / Carpet / Mattress. Example option metadata: Full Home uses next_category_slug='full-home'; Specific Area uses next_category_slug='specific-area'; Item uses next_category_slug='item'. Use filter_children=true with child_slugs only when filtering the current category's immediate children without entering a child category."}),
        ("Display & availability", {"fields": ("sort_order", "is_active")}),
    )


@admin.register(Service)
class ServiceAdmin(ModelAdmin):
    list_display = ("title", "category", "booking_mode", "pricing_type", "audience",
                    "pricing_status", "worker_payout_status", "is_popular", "is_active", "updated_at")
    list_editable = ("is_popular", "is_active")
    list_filter = ("category", "booking_mode", "pricing_type", "audience", "is_active")
    search_fields = ("title", "title_hi", "description", "category__title")
    inlines = [VariantInline, AddOnInline, ServiceInspectionRateInline, FormFieldInline, ServiceImageInline]
    readonly_fields = ("profitability_report",)
    list_per_page = 30

    @admin.display(description="Completed booking profitability")
    def profitability_report(self, obj):
        from .actual_finance import build_service_profitability_report
        from django.utils.html import format_html, format_html_join

        def money(value):
            return "—" if value is None else f"₹{value:,.2f}"

        rows = [("All variants / service total", build_service_profitability_report(obj))]
        for variant in obj.variants.all().order_by("sort_order", "title"):
            rows.append((variant.title, build_service_profitability_report(obj, variant=variant)))
        if not rows[0][1]["booking_count"]:
            return "No completed bookings yet."
        visible = []
        for label, report in rows:
            if not report["booking_count"]:
                continue
            visible.append((
                label, report["booking_count"], report["actual_complete_count"],
                report["actual_incomplete_count"], money(report["actual_contribution_total"]),
                money(report["estimated_contribution_total"]), money(report["variance"]),
            ))
        body = format_html_join(
            "",
            "<tr><th>{}</th><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>",
            visible,
        )
        return format_html(
            "<p>All-time completed bookings. Estimates use saved booking subtotal/payout snapshots and the service's current cost assumptions. Incomplete actuals are excluded from profit/loss comparison.</p>"
            "<table><thead><tr><th>Service / variant</th><th>Completed</th><th>Finance complete</th><th>Finance incomplete</th><th>Actual contribution</th><th>Estimated contribution</th><th>Variance (comparable)</th></tr></thead><tbody>{}</tbody></table>",
            body,
        )

    def save_model(self, request, obj, form, change):
        reason = str(obj.pricing_change_reason or "").strip()
        financial_fields = (
            "visit_fee", "visit_fee_worker_payout", "tax_rate",
            "estimated_gateway_fee_percent", "discount_reserve_percent",
            "rewards_reserve_percent", "refund_reserve_percent",
            "rework_reserve_percent", "other_variable_cost_per_booking",
            "minimum_contribution_floor", "target_contribution_margin_percent",
        )
        if change:
            original = Service.objects.get(pk=obj.pk)
            if any(getattr(original, field) != getattr(obj, field) for field in financial_fields) and not reason:
                raise ValidationError("Enter a reason for changing service pricing or financial assumptions.")
        super().save_model(request, obj, form, change)
        if change and reason:
            update_change_reason(obj, reason)

    @admin.display(description="Worker payout")
    def worker_payout_status(self, obj):
        variants = obj.variants.filter(is_active=True)
        missing = variants.filter(
            models.Q(worker_payout__isnull=True) | models.Q(worker_payout__lte=0)
        ).count()
        if missing:
            return f"Configure {missing} active variant payout(s)"
        if not variants.exists() and obj.booking_mode == Service.BookingMode.INSPECTION:
            return "Configured" if obj.visit_fee_worker_payout > 0 else "Set inspection payout"
        if not variants.exists() and obj.pricing_type == Service.PricingType.QUOTE:
            return "Set quote/inspection payout"
        return "Configured" if variants.exists() else "No variant payout configured"

    @admin.display(description="Customer pricing")
    def pricing_status(self, obj):
        if service_pricing_ready(obj):
            return "Ready"
        if obj.pricing_type == "quote" and obj.booking_mode == "inspection":
            return "Set inspection fee"
        if obj.pricing_type == "per_unit":
            return "Set unit label and a priced active unit rate"
        return "Add a priced active package"
    save_on_top = True
    fieldsets = (
        ("Profitability report", {"fields": ("profitability_report",)}),
        ("Service details", {"fields": ("category", "title", "title_hi", "description", "image")}),
        ("Booking & pricing", {"fields": ("booking_mode", "pricing_type", "unit_label", "visit_fee", "visit_fee_worker_payout", "tax_rate", "duration_minutes", "buffer_minutes")}),
        ("Materials & tools", {"fields": ("material_requirements",), "description": "List the materials/tools the professional must bring for this service."}),
        ("Pricing change audit", {"fields": ("pricing_change_reason",)}),
        ("Unit economics assumptions", {"fields": (
            "estimated_gateway_fee_percent", "discount_reserve_percent",
            "rewards_reserve_percent", "refund_reserve_percent",
            "rework_reserve_percent", "other_variable_cost_per_booking",
            "minimum_contribution_floor", "target_contribution_margin_percent",
        ), "description": "All values are estimates/configuration inputs. Contribution excludes pass-through tax. Leave unset until finance has confirmed the assumption; Launch/Reprice/Hold stays unconfigured until all inputs are present."}),
        ("Customer requirements", {"fields": ("audience", "requires_female_worker")}),
        ("Visibility", {"fields": ("is_popular", "sort_order", "is_active")}),
    )


@admin.register(ServiceInspectionRate)
class ServiceInspectionRateAdmin(ModelAdmin):
    list_display = (
        "service", "title", "rate_type", "customer_price", "worker_payout",
        "estimated_contribution", "launch_recommendation", "is_active", "updated_at",
    )
    list_filter = ("service", "rate_type", "is_active")
    search_fields = ("service__title", "title", "code")
    fields = ("service", "title", "code", "description", "rate_type", "customer_price", "worker_payout", "pricing_change_reason", "sort_order", "is_active")

    @admin.display(description="Base estimated contribution")
    def estimated_contribution(self, obj):
        from .finance import calculate_estimated_contribution
        value = calculate_estimated_contribution(
            customer_price=obj.customer_price,
            worker_payout=obj.worker_payout,
            service=obj.service,
        )
        return f"₹{value}" if value is not None else "Configure assumptions"

    @admin.display(description="Base recommendation")
    def launch_recommendation(self, obj):
        from .finance import contribution_recommendation
        return contribution_recommendation(
            customer_price=obj.customer_price,
            worker_payout=obj.worker_payout,
            service=obj.service,
        )

    def save_model(self, request, obj, form, change):
        reason = str(obj.pricing_change_reason or "").strip()
        if change:
            previous = ServiceInspectionRate.objects.get(pk=obj.pk)
            if (previous.customer_price != obj.customer_price or previous.worker_payout != obj.worker_payout) and not reason:
                raise ValidationError("Enter a reason when changing the inspection customer price or worker payout.")
        super().save_model(request, obj, form, change)


@admin.register(ServiceVariant)
class RateSheetAdmin(PricingAuditAdminMixin, ModelAdmin):
    list_display = ("service", "title", "mrp", "price", "worker_payout", "estimated_contribution", "launch_recommendation", "discount", "is_active")
    list_editable = ("is_active",)
    list_filter = ("service__category", "service", "is_active")
    search_fields = ("title", "service__title")
    list_per_page = 50

    @admin.display(description="Base estimated contribution")
    def estimated_contribution(self, obj):
        from .finance import calculate_estimated_contribution
        value = calculate_estimated_contribution(
            customer_price=obj.price,
            worker_payout=obj.worker_payout,
            service=obj.service,
        )
        return f"₹{value}" if value is not None else "Configure assumptions"

    @admin.display(description="Base recommendation")
    def launch_recommendation(self, obj):
        from .finance import contribution_recommendation
        return contribution_recommendation(
            customer_price=obj.price,
            worker_payout=obj.worker_payout,
            service=obj.service,
        )

    @admin.display(description="Discount")
    def discount(self, obj):
        return f"{obj.discount_percent}% off" if obj.discount_percent else "-"


@admin.register(AddOn)
class AddOnAdmin(PricingAuditAdminMixin, ModelAdmin):
    list_display = (
        "service", "title", "mrp", "price", "worker_payout",
        "estimated_contribution", "launch_recommendation", "is_active",
    )
    list_editable = ("is_active",)
    list_filter = ("service__category", "service", "is_active")
    search_fields = ("title", "service__title")
    list_per_page = 50

    @admin.display(description="Base estimated contribution")
    def estimated_contribution(self, obj):
        from .finance import calculate_estimated_contribution
        value = calculate_estimated_contribution(
            customer_price=obj.price,
            worker_payout=obj.worker_payout,
            service=obj.service,
        )
        return f"₹{value}" if value is not None else "Configure assumptions"

    @admin.display(description="Base recommendation")
    def launch_recommendation(self, obj):
        from .finance import contribution_recommendation
        return contribution_recommendation(
            customer_price=obj.price,
            worker_payout=obj.worker_payout,
            service=obj.service,
        )


@admin.register(FormField)
class FormFieldAdmin(ModelAdmin):
    list_display = ("label", "service", "field_type", "is_required", "sort_order", "is_active")
    list_editable = ("is_required", "sort_order", "is_active")
    list_filter = ("service__category", "service", "field_type", "is_active")
    search_fields = ("label", "key", "service__title")
    list_per_page = 50


@admin.register(CityService)
class CityServiceAdmin(ModelAdmin):
    list_display = ("city", "service", "is_active", "updated_at")
    list_editable = ("is_active",)
    list_filter = ("city", "service__category", "is_active")
    search_fields = ("city__name", "service__title")
    list_per_page = 50


@admin.register(Banner)
class BannerAdmin(ModelAdmin):
    list_display = ("title", "city", "sort_order", "is_active", "starts_at", "ends_at")
    list_editable = ("sort_order", "is_active")
    list_filter = ("city", "is_active")
    search_fields = ("title",)

class VehicleModelInline(TabularInline):
    model = VehicleModel
    extra = 0
    fields = ("name", "image", "image_url", "vehicle_class", "sort_order", "is_active")
    show_change_link = True


@admin.register(VehicleMake)
class VehicleMakeAdmin(ModelAdmin):
    list_display = ("name", "vehicle_type", "sort_order", "is_active")
    list_editable = ("sort_order", "is_active")
    list_filter = ("vehicle_type", "is_active")
    search_fields = ("name",)
    inlines = [VehicleModelInline]


@admin.register(VehicleModel)
class VehicleModelAdmin(ModelAdmin):
    list_display = ("name", "make", "vehicle_class", "sort_order", "is_active")
    list_editable = ("vehicle_class", "sort_order", "is_active")
    list_filter = ("make__vehicle_type", "make", "vehicle_class", "is_active")
    search_fields = ("name", "make__name")
