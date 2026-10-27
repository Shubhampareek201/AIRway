from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from .models import AppSetting, City, Zone


class ZoneInline(TabularInline):
    model = Zone
    extra = 1


@admin.register(City)
class CityAdmin(ModelAdmin):
    list_display = ("name", "state", "is_active")
    list_editable = ("is_active",)
    search_fields = ("name",)
    inlines = [ZoneInline]


@admin.register(Zone)
class ZoneAdmin(ModelAdmin):
    list_display = ("name", "city", "is_active")
    list_filter = ("city", "is_active")
    search_fields = ("name",)


@admin.register(AppSetting)
class AppSettingAdmin(ModelAdmin):
    list_display = ("key", "value", "description")
    search_fields = ("key",)