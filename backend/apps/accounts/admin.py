from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from unfold.admin import ModelAdmin, TabularInline
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

from .models import Address, ConsentLog, DeviceToken, Referral, User, UserRole


class UserRoleInline(TabularInline):
    model = UserRole
    extra = 0


class AddressInline(TabularInline):
    model = Address
    extra = 0
    fields = ("label", "house_details", "landmark", "zone", "is_default")


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm

    list_display = ("phone", "name", "active_mode", "is_active", "is_staff", "created_at")
    list_filter = ("active_mode", "is_active", "is_staff", "gender")
    search_fields = ("phone", "name", "email", "referral_code")
    ordering = ("-created_at",)
    inlines = [UserRoleInline, AddressInline]

    fieldsets = (
        (None, {"fields": ("phone", "password")}),
        ("Profile", {"fields": ("name", "email", "gender", "photo", "language", "active_mode", "referral_code")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("phone", "name", "password1", "password2")}),
    )
    readonly_fields = ("referral_code",)


@admin.register(ConsentLog)
class ConsentLogAdmin(ModelAdmin):
    list_display = ("user", "document", "version", "created_at")
    list_filter = ("document", "version")
    search_fields = ("user__phone",)


@admin.register(Referral)
class ReferralAdmin(ModelAdmin):
    list_display = ("referrer", "referred", "rewarded", "rewarded_at")
    list_filter = ("rewarded",)


admin.site.register(DeviceToken, ModelAdmin)