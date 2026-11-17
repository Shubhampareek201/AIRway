import secrets

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.validators import RegexValidator
from django.db import models

from apps.core.models import TimeStampedModel, Zone


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, phone, password=None, **extra):
        if not phone:
            raise ValueError("Phone number zaroori hai")
        user = self.model(phone=phone, **extra)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()  # customer/worker OTP se login karenge
        user.save(using=self._db)
        return user

    def create_superuser(self, phone, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)

        if extra.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")

        if extra.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        if not password:
            raise ValueError("Superuser must have a password.")

        return self.create_user(phone, password, **extra)


phone_validator = RegexValidator(
    regex=r"^\+91[6-9]\d{9}$",
    message="Phone number must be in format +919876543210",
)


class User(AbstractBaseUser, PermissionsMixin, TimeStampedModel):
    class Gender(models.TextChoices):
        MALE = "male", "Male"
        FEMALE = "female", "Female"
        OTHER = "other", "Other"
        PREFER_NOT_TO_SAY = "prefer_not_to_say", "Prefer not to say"

    class Language(models.TextChoices):
        HINDI = "hi", "Hindi"
        ENGLISH = "en", "English"

    class Mode(models.TextChoices):
        CUSTOMER = "customer", "Customer"
        WORKER = "worker", "Worker"

    phone = models.CharField(
        max_length=15,
        blank=True,
        null=True,
        unique=True,
        validators=[phone_validator],
    )
    name = models.CharField(max_length=150, blank=True)
    email = models.EmailField(blank=True)
    gender = models.CharField(max_length=20, choices=Gender.choices, blank=True)
    photo = models.ImageField(upload_to="users/", blank=True)
    language = models.CharField(max_length=2, choices=Language.choices, default=Language.HINDI)
    active_mode = models.CharField(max_length=10, choices=Mode.choices, default=Mode.CUSTOMER)
    referral_code = models.CharField(max_length=12, unique=True, blank=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)  # admin panel access

    USERNAME_FIELD = "phone"
    REQUIRED_FIELDS = []
    objects = UserManager()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name or 'User'} ({self.phone})"

    def save(self, *args, **kwargs):
        if not self.referral_code:
            while True:
                code = "AIR" + secrets.token_hex(3).upper()
                if not User.objects.filter(referral_code=code).exists():
                    self.referral_code = code
                    break
        super().save(*args, **kwargs)


class UserRole(TimeStampedModel):
    class Role(models.TextChoices):
        CUSTOMER = "customer", "Customer"
        WORKER = "worker", "Worker"
        ADMIN = "admin", "Admin"
        STAFF = "staff", "Staff"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="roles")
    role = models.CharField(max_length=10, choices=Role.choices)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "role"], name="unique_user_role")]

    def __str__(self):
        return f"{self.user.phone} - {self.role}"


class ConsentLog(TimeStampedModel):
    """Kisne kaunsi policy ka kaunsa version kab accept kiya."""
    class Document(models.TextChoices):
        TERMS = "terms", "Terms & Conditions"
        PRIVACY = "privacy", "Privacy Policy"
        WORKER_TERMS = "worker_terms", "Worker Terms"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="consents")
    document = models.CharField(max_length=20, choices=Document.choices)
    version = models.CharField(max_length=20)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    def __str__(self):
        return f"{self.user.phone} - {self.document} v{self.version}"


class Address(TimeStampedModel):
    class Label(models.TextChoices):
        HOME = "home", "Home"
        WORK = "work", "Work"
        OTHER = "other", "Other"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="addresses")
    label = models.CharField(max_length=10, choices=Label.choices, default=Label.HOME)
    house_details = models.CharField(max_length=255, help_text="Flat / house no. / floor")
    landmark = models.CharField(max_length=255, help_text="Rawatbhata mein landmark zaroori hai")
    full_address = models.TextField(help_text="Map se aaya poora address")
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    zone = models.ForeignKey(Zone, on_delete=models.SET_NULL, null=True, blank=True)
    is_default = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)  # soft delete

    class Meta:
        verbose_name_plural = "addresses"

    def __str__(self):
        return f"{self.label} - {self.user.phone}"


class DeviceToken(TimeStampedModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="devices")
    token = models.CharField(max_length=512, unique=True)
    platform = models.CharField(max_length=10, default="android")

    def __str__(self):
        return f"{self.user.phone} - {self.platform}"


class Referral(TimeStampedModel):
    referrer = models.ForeignKey(User, on_delete=models.CASCADE, related_name="referrals_made")
    referred = models.OneToOneField(User, on_delete=models.CASCADE, related_name="referred_by")
    rewarded = models.BooleanField(default=False)  # pehli booking complete hone par True
    rewarded_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.referrer.phone} -> {self.referred.phone}"

class FavoriteService(TimeStampedModel):
    """A customer-owned bookmark for an active catalogue service."""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="favorite_services",
    )
    service = models.ForeignKey(
        "catalog.Service",
        on_delete=models.CASCADE,
        related_name="favorited_by",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "service"],
                name="unique_user_favorite_service",
            )
        ]

    def __str__(self):
        return f"{self.user_id} favorites service {self.service_id}"


class CustomerVehicle(TimeStampedModel):
    class VehicleType(models.TextChoices):
        CAR = "car", "Car"
        BIKE = "bike", "Bike"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="saved_vehicles")
    vehicle_type = models.CharField(max_length=10, choices=VehicleType.choices)
    vehicle_model = models.ForeignKey(
        "catalog.VehicleModel", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="customer_vehicles"
    )
    custom_make = models.CharField(max_length=100, blank=True)
    custom_model = models.CharField(max_length=120, blank=True)
    vehicle_class = models.CharField(max_length=40, blank=True)
    nickname = models.CharField(max_length=60, blank=True)
    is_default = models.BooleanField(default=False)

    class Meta:
        ordering = ["-is_default", "-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user"], condition=models.Q(is_default=True),
                name="one_default_vehicle_per_customer",
            )
        ]

    def clean(self):
        super().clean()
        if self.vehicle_model_id and self.vehicle_model.make.vehicle_type != self.vehicle_type:
            from django.core.exceptions import ValidationError
            raise ValidationError({"vehicle_model": "Selected model does not match vehicle type."})

    def __str__(self):
        return self.nickname or self.custom_model or str(self.vehicle_model or self.get_vehicle_type_display())




class AccountDeletionRequest(TimeStampedModel):
    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        UNDER_REVIEW = "under_review", "Under review"
        REJECTED = "rejected", "Rejected"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    user = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="account_deletion_requests",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.REQUESTED,
        db_index=True,
    )
    reason = models.TextField(blank=True)
    has_active_bookings = models.BooleanField(default=False)
    active_booking_count = models.PositiveIntegerField(default=0)
    admin_notes = models.TextField(blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "status"]),
        ]

    def __str__(self):
        return f"Deletion request #{self.pk} for user {self.user_id} ({self.status})"
