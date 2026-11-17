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
    list_display = ("referrer", "referred", "rewarded", "rewarded_at")
    list_filter = ("rewarded",)


admin.site.register(DeviceToken, ModelAdmin)

@admin.register(CustomerVehicle)
class CustomerVehicleAdmin(ModelAdmin):
    list_display = ("user", "vehicle_type", "vehicle_model", "custom_make", "custom_model", "nickname", "is_default")
    list_filter = ("vehicle_type", "is_default")
    search_fields = ("user__phone", "user__name", "custom_make", "custom_model", "vehicle_model__name", "vehicle_model__make__name")


@admin.register(AccountDeletionRequest)
class AccountDeletionRequestAdmin(ModelAdmin):
    list_display = ("user", "status", "has_active_bookings", "has_financial_obligations", "active_booking_count", "created_at", "reviewed_at")
    list_filter = ("status", "has_active_bookings")
    search_fields = ("user__phone", "user__name")
    readonly_fields = ("user", "created_at", "updated_at", "has_active_bookings", "has_financial_obligations", "active_booking_count")

    def save_model(self, request, obj, form, change):
        if obj.status == AccountDeletionRequest.Status.COMPLETED:
            from apps.bookings.models import Booking, BookingAssignment
            active_statuses = (
                Booking.Status.PENDING,
                Booking.Status.CONFIRMED,
                Booking.Status.ASSIGNED,
                Booking.Status.IN_PROGRESS,
                Booking.Status.DISPUTED,
            )
            active_ids = set(
                obj.user.bookings.filter(status__in=active_statuses)
                .values_list("id", flat=True)
            )
            try:
                worker_profile = obj.user.worker_profile
            except Exception:
                worker_profile = None
            if worker_profile is not None:
                active_ids.update(
                    BookingAssignment.objects.filter(
                        worker=worker_profile,
                        booking__status__in=active_statuses,
                    ).values_list("booking_id", flat=True)
                )
            wallet = getattr(obj.user, "wallet", None)
            has_financial_obligations = bool(
                wallet and (
                    wallet.balance > 0
                    or wallet.pending_balance > 0
                    or wallet.reservations.filter(status="reserved").exists()
                )
            )
            from apps.payments.models import Payment, PaymentRefund
            has_financial_obligations = has_financial_obligations or Payment.objects.filter(
                customer=obj.user,
                status=Payment.Status.PENDING,
            ).exists() or PaymentRefund.objects.filter(
                payment__customer=obj.user,
                status__in=(PaymentRefund.Status.PROCESSING, PaymentRefund.Status.PENDING),
            ).exists()
            obj.has_active_bookings = bool(active_ids)
            obj.active_booking_count = len(active_ids)
            obj.has_financial_obligations = has_financial_obligations
            if active_ids or has_financial_obligations:
                obj.status = AccountDeletionRequest.Status.UNDER_REVIEW
                messages.error(
                    request,
                    (
                        "Resolve active bookings or disputes before closing this account."
                        if active_ids
                        else "Settle the wallet balance and reservations before closing this account."
                    ),
                )
                super().save_model(request, obj, form, change)
                return

            user = obj.user
            old_photo = user.photo
            user.is_active = False
            user.set_unusable_password()
            user.phone = None
            user.firebase_uid = None
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
