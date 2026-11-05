from django.db import models

# Create your models here.
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from apps.core.models import TimeStampedModel, Zone
from apps.catalog.models import Service


class WorkerProfile(TimeStampedModel):

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        SUSPENDED = "suspended", "Suspended"

    class Gender(models.TextChoices):
        MALE = "male", "Male"
        FEMALE = "female", "Female"
        OTHER = "other", "Other"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="worker_profile",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )

    gender = models.CharField(
        max_length=10,
        choices=Gender.choices,
        blank=True,
    )

    experience_years = models.PositiveIntegerField(default=0)
    bio = models.TextField(blank=True)

    upi_id = models.CharField(max_length=100, blank=True)

    is_online = models.BooleanField(default=False)

    rating_avg = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=0,
    )
    rating_count = models.PositiveIntegerField(default=0)

    acceptance_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
    )

    cancellation_count = models.PositiveIntegerField(default=0)

    rejection_reason = models.TextField(blank=True)

    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_workers",
    )

    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(rating_avg__gte=0) & Q(rating_avg__lte=5),
                name="worker_rating_range",
            ),
            models.CheckConstraint(
                condition=Q(acceptance_rate__gte=0)
                & Q(acceptance_rate__lte=100),
                name="worker_acceptance_range",
            ),
        ]

    def __str__(self):
        return f"{self.user.phone} - {self.status}"

    def save(self, *args, **kwargs):
        if self.status != self.Status.APPROVED:
            self.is_online = False
        super().save(*args, **kwargs)


class WorkerDocument(TimeStampedModel):

    class DocumentType(models.TextChoices):
        AADHAAR = "aadhaar", "Aadhaar"
        ID = "id", "Other ID"
        PHOTO = "photo", "Photograph"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        VERIFIED = "verified", "Verified"
        REJECTED = "rejected", "Rejected"

    worker = models.ForeignKey(
        WorkerProfile,
        on_delete=models.CASCADE,
        related_name="documents",
    )

    doc_type = models.CharField(
        max_length=20,
        choices=DocumentType.choices,
    )

    file = models.FileField(upload_to="worker_documents/")

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )

    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_worker_documents",
    )

    def __str__(self):
        return f"{self.worker.user.phone} - {self.doc_type}"


class WorkerService(TimeStampedModel):

    worker = models.ForeignKey(
        WorkerProfile,
        on_delete=models.CASCADE,
        related_name="worker_services",
    )

    service = models.ForeignKey(
        Service,
        on_delete=models.PROTECT,
        related_name="assigned_workers",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["worker", "service"],
                name="unique_worker_service",
            )
        ]

    def __str__(self):
        return f"{self.worker.user.phone} - {self.service}"


class WorkerZone(TimeStampedModel):

    worker = models.ForeignKey(
        WorkerProfile,
        on_delete=models.CASCADE,
        related_name="worker_zones",
    )

    zone = models.ForeignKey(
        Zone,
        on_delete=models.PROTECT,
        related_name="assigned_workers",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["worker", "zone"],
                name="unique_worker_zone",
            )
        ]

    def __str__(self):
        return f"{self.worker.user.phone} - {self.zone}"


class WorkerSchedule(TimeStampedModel):

    class Weekday(models.IntegerChoices):
        MONDAY = 0, "Monday"
        TUESDAY = 1, "Tuesday"
        WEDNESDAY = 2, "Wednesday"
        THURSDAY = 3, "Thursday"
        FRIDAY = 4, "Friday"
        SATURDAY = 5, "Saturday"
        SUNDAY = 6, "Sunday"

    worker = models.ForeignKey(
        WorkerProfile,
        on_delete=models.CASCADE,
        related_name="schedules",
    )

    weekday = models.IntegerField(choices=Weekday.choices)

    start_time = models.TimeField()
    end_time = models.TimeField()

    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["weekday", "start_time"]
        constraints = [
            models.CheckConstraint(
                condition=Q(end_time__gt=F("start_time")),
                name="worker_schedule_valid_hours",
            ),
            models.UniqueConstraint(
                fields=["worker", "weekday", "start_time"],
                name="unique_worker_schedule_start",
            ),
        ]

    def clean(self):
        super().clean()
        if (
            self.start_time is not None
            and self.end_time is not None
            and self.start_time >= self.end_time
        ):
            raise ValidationError({
                "end_time": "End time must be after start time."
            })

    def __str__(self):
        return f"{self.worker.user.phone} - {self.get_weekday_display()}"


class WorkerLeave(TimeStampedModel):

    worker = models.ForeignKey(
        WorkerProfile,
        on_delete=models.CASCADE,
        related_name="leaves",
    )

    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    reason = models.TextField(blank=True)

    class Meta:
        ordering = ["-start_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(end_at__gt=F("start_at")),
                name="worker_leave_valid_period",
            )
        ]

    def clean(self):
        super().clean()
        if (
            self.start_at is not None
            and self.end_at is not None
            and self.start_at >= self.end_at
        ):
            raise ValidationError({
                "end_at": "End date must be after start date."
            })

    def __str__(self):
        return f"{self.worker.user.phone} - Leave"

class WorkerJobStreak(TimeStampedModel):
    """Tracks milestone bonuses awarded to workers for completed job streaks."""

    worker = models.ForeignKey(
        WorkerProfile,
        on_delete=models.CASCADE,
        related_name="job_streaks",
    )

    jobs_completed = models.PositiveIntegerField(
        help_text="Number of completed jobs at time of bonus",
    )
    bonus_amount = models.DecimalField(max_digits=10, decimal_places=2)
    awarded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-awarded_at"]
        constraints = [
            models.UniqueConstraint(
                fields=("worker", "jobs_completed"),
                name="unique_worker_streak_per_threshold",
            ),
        ]

    def __str__(self):
        return f"{self.worker.user.phone} - {self.jobs_completed} jobs"
