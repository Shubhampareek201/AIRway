from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from .models import (
    AddOn, Banner, Category, CityService, FormField, Service,
    ServiceImage, ServiceVariant,
)


class VariantInline(TabularInline):
    model = ServiceVariant
    extra = 0
    fields = ("title", "title_hi", "description", "image", "attributes", "mrp", "price", "duration_minutes", "sort_order", "is_active")
    show_change_link = True


class AddOnInline(TabularInline):
    model = AddOn
    extra = 0
    fields = ("title", "title_hi", "description", "mrp", "price", "sort_order", "is_active")
    show_change_link = True


class FormFieldInline(TabularInline):
    model = FormField
    extra = 0
    fields = ("label", "key", "field_type", "options", "is_required", "sort_order", "is_active")
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
    fieldsets = (
        ("Category details", {"fields": ("title", "title_hi", "slug", "parent", "image")}),
        ("Customer flow", {"fields": ("flow_steps",), "description": "Configure pre-service questions as a JSON list. Leave empty when the category only needs subcategory selection."}),
        ("Display & availability", {"fields": ("sort_order", "is_active")}),
    )


@admin.register(Service)
class ServiceAdmin(ModelAdmin):
    list_display = ("title", "category", "booking_mode", "pricing_type", "audience",
                    "is_popular", "is_active", "updated_at")
    list_editable = ("is_popular", "is_active")
    list_filter = ("category", "booking_mode", "pricing_type", "audience", "is_active")
    search_fields = ("title", "title_hi", "description", "category__title")
    inlines = [VariantInline, AddOnInline, FormFieldInline, ServiceImageInline]
    list_per_page = 30
    save_on_top = True
    fieldsets = (
        ("Service details", {"fields": ("category", "title", "title_hi", "description", "image")}),
        ("Booking & pricing", {"fields": ("booking_mode", "pricing_type", "unit_label", "visit_fee", "duration_minutes", "buffer_minutes")}),
        ("Customer requirements", {"fields": ("audience", "requires_female_worker")}),
        ("Visibility", {"fields": ("is_popular", "sort_order", "is_active")}),
    )


@admin.register(ServiceVariant)
class RateSheetAdmin(ModelAdmin):
    list_display = ("service", "title", "mrp", "price", "discount", "is_active")
    list_editable = ("mrp", "price", "is_active")
    list_filter = ("service__category", "service", "is_active")
    search_fields = ("title", "service__title")
    list_per_page = 50

    @admin.display(description="Discount")
    def discount(self, obj):
        return f"{obj.discount_percent}% off" if obj.discount_percent else "-"


@admin.register(AddOn)
class AddOnAdmin(ModelAdmin):
    list_display = ("service", "title", "mrp", "price", "is_active")
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
