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
    gender = models.CharField(max_length=10, choices=Gender.choices, blank=True)
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