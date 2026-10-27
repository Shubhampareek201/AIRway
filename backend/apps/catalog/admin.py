from django.contrib import admin
from unfold.admin import ModelAdmin, StackedInline, TabularInline

from .models import (AddOn, Banner, Category, CityService, FormField, Service,
                     ServiceImage, ServiceVariant)


class VariantInline(TabularInline):
    model = ServiceVariant
    extra = 1
    fields = ("title", "title_hi", "mrp", "price", "duration_minutes", "sort_order", "is_active")


class AddOnInline(TabularInline):
    model = AddOn
    extra = 0
    fields = ("title", "title_hi", "mrp", "price", "sort_order", "is_active")


class FormFieldInline(TabularInline):
    model = FormField
    extra = 0


class ServiceImageInline(TabularInline):
    model = ServiceImage
    extra = 1


@admin.register(Category)
class CategoryAdmin(ModelAdmin):
    list_display = ("title", "parent", "sort_order", "is_active")
    list_editable = ("sort_order", "is_active")
    list_filter = ("is_active", "parent")
    search_fields = ("title", "title_hi")
    prepopulated_fields = {"slug": ("title",)}


@admin.register(Service)
class ServiceAdmin(ModelAdmin):
    list_display = ("title", "category", "booking_mode", "pricing_type", "audience",
                    "is_popular", "is_active")
    list_editable = ("is_popular", "is_active")
    list_filter = ("category", "booking_mode", "audience", "is_active")
    search_fields = ("title", "title_hi")
    inlines = [VariantInline, AddOnInline, FormFieldInline, ServiceImageInline]


@admin.register(ServiceVariant)
class RateSheetAdmin(ModelAdmin):
    """Rate Sheet: sab rates ek jagah, seedha table mein edit."""
    list_display = ("service", "title", "mrp", "price", "discount", "is_active")
    list_editable = ("mrp", "price", "is_active")
    list_filter = ("service__category", "service", "is_active")
    search_fields = ("title", "service__title")

    @admin.display(description="Discount")
    def discount(self, obj):
        return f"{obj.discount_percent}% off" if obj.discount_percent else "-"


@admin.register(AddOn)
class AddOnAdmin(ModelAdmin):
    list_display = ("service", "title", "mrp", "price", "is_active")
    list_editable = ("mrp", "price", "is_active")
    list_filter = ("service",)


@admin.register(CityService)
class CityServiceAdmin(ModelAdmin):
    list_display = ("city", "service", "is_active")
    list_editable = ("is_active",)
    list_filter = ("city", "is_active")


@admin.register(Banner)
class BannerAdmin(ModelAdmin):
    list_display = ("title", "city", "sort_order", "is_active")
    list_editable = ("sort_order", "is_active")