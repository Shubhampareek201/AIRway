from django.contrib import admin, messages
from django.utils import timezone
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from unfold.admin import ModelAdmin, TabularInline
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

from .models import Address, ConsentLog, CustomerVehicle, DeviceToken, Referral, User, UserRole, AccountDeletionRequest


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
    list_display = (
        "referral_type", "referrer", "referred", "reward_status", "rewarded",
        "reward_booking_id", "reward_original_service_charge", "rewarded_at", "applied_ip",
    )
    list_filter = ("reward_status", "rewarded", "created_at")
    search_fields = (
        "referrer__phone", "referrer__email", "referred__phone",
        "referred__email", "referrer__name", "referred__name",
    )
    readonly_fields = tuple(field.name for field in Referral._meta.fields)

    def has_view_permission(self, request, obj=None):
        return request.user.is_staff

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(DeviceToken, ModelAdmin)

@admin.register(CustomerVehicle)
class CustomerVehicleAdmin(ModelAdmin):
    list_display = ("user", "vehicle_type", "vehicle_model", "custom_make", "custom_model", "nickname", "is_default")
    list_filter = ("vehicle_type", "is_default")
    search_fields = ("user__phone", "user__name", "custom_make", "custom_model", "vehicle_model__name", "vehicle_model__make__name")


@admin.register(AccountDeletionRequest)
class AccountDeletionRequestAdmin(ModelAdmin):
    list_display = ("user", "status", "has_active_bookings", "has_financial_obligations", "active_booking_count", "created_at", "reviewed_at")
    list_filter = ("status", "has_active_bookings", "has_financial_obligations")
    search_fields = ("user__phone", "user__name")
    readonly_fields = ("user", "created_at", "updated_at", "has_active_bookings", "has_financial_obligations", "active_booking_count")

    def save_model(self, request, obj, form, change):
        if obj.status == AccountDeletionRequest.Status.COMPLETED:
            from .deletion import get_account_deletion_obligations
            obligations = get_account_deletion_obligations(obj.user)
            obj.has_active_bookings = obligations["has_active_bookings"]
            obj.active_booking_count = obligations["active_booking_count"]
            obj.has_financial_obligations = obligations["has_financial_obligations"]
            if obligations['has_active_bookings'] or obligations['has_financial_obligations']:
                obj.status = AccountDeletionRequest.Status.UNDER_REVIEW
                messages.error(
                    request,
                    (
                        "Resolve active bookings or disputes before closing this account."
                        if obligations["has_active_bookings"]
                        else "Settle wallet funds, pending payments or refunds before closing this account."
                    ),
                )
                super().save_model(request, obj, form, change)
                return

            user = obj.user
            old_photo = user.photo

            # Remove customer-only profile data while preserving addresses
            # referenced by historical bookings and their audit trail.
            from apps.bookings.models import Booking
            from .models import Address, CustomerVehicle, FavoriteService
            used_address_ids = Booking.objects.filter(
                customer=user,
            ).values_list("address_id", flat=True)
            Address.objects.filter(user=user).exclude(
                pk__in=used_address_ids,
            ).update(
                house_details="",
                landmark="",
                full_address="",
                latitude=None,
                longitude=None,
                zone=None,
                is_default=False,
                deleted_at=timezone.now(),
            )
            CustomerVehicle.objects.filter(user=user).delete()
            FavoriteService.objects.filter(user=user).delete()

            # Deactivate and clear the worker's live profile. Keep verified
            # identity documents for the legally required retention review.
            from apps.workers.models import WorkerDocument, WorkerProfile
            try:
                worker_profile = user.worker_profile
            except WorkerProfile.DoesNotExist:
                worker_profile = None
            if worker_profile is not None:
                worker_profile.status = WorkerProfile.Status.SUSPENDED
                worker_profile.gender = ""
                worker_profile.bio = ""
                worker_profile.qualification = ""
                worker_profile.equipment_details = ""
                worker_profile.residential_address = ""
                worker_profile.latitude = None
                worker_profile.longitude = None
                worker_profile.landmark = ""
                worker_profile.upi_id = ""
                worker_profile.is_online = False
                worker_profile.save(update_fields=[
                    "status", "gender", "bio", "qualification",
                    "equipment_details", "residential_address",
                    "latitude", "longitude", "landmark", "upi_id",
                    "is_online", "updated_at",
                ])
                for photo_document in worker_profile.documents.filter(
                    doc_type=WorkerDocument.DocumentType.PHOTO,
                ):
                    photo_file = photo_document.file
                    photo_document.delete()
                    if photo_file:
                        photo_file.delete(save=False)

            user.is_active = False
            user.set_unusable_password()
            user.phone = None
            user.firebase_uid = None
            # User.save() generates a fresh unique code, invalidating the old shared code.
            user.referral_code = ""
            user.name = ""
            user.email = ""
            user.gender = ""
            user.photo = ""
            user.devices.all().delete()
            user.save(update_fields=[
                "is_active", "password", "phone", "firebase_uid", "referral_code", "name", "email", "gender",
                "photo", "updated_at",
            ])
            if old_photo:
                old_photo.delete(save=False)
            obj.reviewed_at = timezone.now()
        elif obj.status in (
            AccountDeletionRequest.Status.REJECTED,
            AccountDeletionRequest.Status.CANCELLED,
        ):
            obj.reviewed_at = timezone.now()
        super().save_model(request, obj, form, change)
