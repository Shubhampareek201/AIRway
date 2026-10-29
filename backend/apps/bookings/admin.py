from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from .models import (
    Booking,
    BookingAddOn,
    BookingFormResponse,
    BookingStatusHistory,
    BookingAssignment,
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