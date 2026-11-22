from django.contrib import admin
from django.db import models
from unfold.admin import ModelAdmin, TabularInline

from .pricing import service_pricing_ready
from .models import (
    AddOn, Banner, Category, CategoryAudienceOption, CityService, FormField, Service,
    ServiceImage, ServiceVariant, VehicleMake, VehicleModel,
)


class CategoryAudienceOptionInline(TabularInline):
    model = CategoryAudienceOption
    extra = 0
    fields = ("audience", "title", "subtitle", "image", "image_secondary", "sort_order", "is_active")


class VariantInline(TabularInline):
    model = ServiceVariant
    extra = 0
    fields = ("title", "title_hi", "description", "included_tasks", "image", "attributes", "mrp", "price", "worker_payout", "duration_minutes", "sort_order", "is_active")
    show_change_link = True


class AddOnInline(TabularInline):
    model = AddOn
    extra = 0
    fields = ("title", "title_hi", "description", "image", "mrp", "price", "worker_payout", "sort_order", "is_active")
    show_change_link = True


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
    inlines = [VariantInline, AddOnInline, FormFieldInline, ServiceImageInline]
    list_per_page = 30

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
        ("Service details", {"fields": ("category", "title", "title_hi", "description", "image")}),
        ("Booking & pricing", {"fields": ("booking_mode", "pricing_type", "unit_label", "visit_fee", "visit_fee_worker_payout", "tax_rate", "duration_minutes", "buffer_minutes")}),
        ("Materials & tools", {"fields": ("material_requirements",), "description": "List the materials/tools the professional must bring for this service."}),
        ("Customer requirements", {"fields": ("audience", "requires_female_worker")}),
        ("Visibility", {"fields": ("is_popular", "sort_order", "is_active")}),
    )


@admin.register(ServiceVariant)
class RateSheetAdmin(ModelAdmin):
    list_display = ("service", "title", "mrp", "price", "worker_payout", "discount", "is_active")
    list_editable = ("mrp", "price", "is_active")
    list_filter = ("service__category", "service", "is_active")
    search_fields = ("title", "service__title")
    list_per_page = 50

    @admin.display(description="Discount")
    def discount(self, obj):
        return f"{obj.discount_percent}% off" if obj.discount_percent else "-"


@admin.register(AddOn)
class AddOnAdmin(ModelAdmin):
    list_display = ("service", "title", "mrp", "price", "worker_payout", "is_active")
    list_editable = ("mrp", "price", "is_active")
    list_filter = ("service__category", "service", "is_active")
    search_fields = ("title", "service__title")
    list_per_page = 50


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
