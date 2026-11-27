from django.db import models

# Create your models here.
import uuid

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
    qualification = models.CharField(max_length=255, blank=True)
    equipment_details = models.TextField(blank=True)
    residential_address = models.TextField(blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    landmark = models.CharField(max_length=255, blank=True)

    upi_id = models.CharField(max_length=100, blank=True)
    commission_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Finance-configured worker commission percentage. Leave blank until agreed.",
    )

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
            models.CheckConstraint(
                condition=Q(commission_rate__isnull=True)
                | (Q(commission_rate__gte=0) & Q(commission_rate__lte=100)),
                name="worker_commission_rate_range",
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
        AADHAAR = "aadhaar", "Legacy Aadhaar"
        AADHAAR_FRONT = "aadhaar_front", "Aadhaar front"
        AADHAAR_BACK = "aadhaar_back", "Aadhaar back"
        ID = "id", "Other ID"
        PHOTO = "photo", "Photograph"
        ADDRESS_PROOF = "address_proof", "Address proof"
        QUALIFICATION = "qualification", "Qualification certificate"
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
    capabilities = models.JSONField(default=list, blank=True, help_text="Task names this worker claims to be trained to perform.")
    capabilities_verified = models.BooleanField(default=False, help_text="Set only after admin review.")
    experience_years = models.PositiveIntegerField(default=0, help_text="Worker-reported experience for this service.")

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

    class Status(models.TextChoices):
        PENDING = "pending", "Pending review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"
        EXPIRED = "expired", "Expired"

    # Existing admin-created leave rows remain effective after migration.
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.APPROVED, db_index=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="reviewed_worker_leaves",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    admin_note = models.TextField(blank=True)

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
        return f"{self.worker.user.phone} - Leave ({self.status})"


class WorkerLeaveHistory(TimeStampedModel):
    leave = models.ForeignKey(WorkerLeave, on_delete=models.PROTECT, related_name="history")
    from_status = models.CharField(max_length=12, blank=True)
    to_status = models.CharField(max_length=12, choices=WorkerLeave.Status.choices)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"Leave #{self.leave_id}: {self.to_status}"


class WorkerEarning(TimeStampedModel):
    """Per-booking earning calculation and payout state."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending settlement"
        ON_HOLD = "on_hold", "On hold"
        AVAILABLE = "available", "Available for payout"
        PAID = "paid", "Paid"

    worker = models.ForeignKey(WorkerProfile, on_delete=models.PROTECT, related_name="earnings")
    booking = models.ForeignKey("bookings.Booking", on_delete=models.PROTECT, related_name="worker_earnings")
    extra_work = models.ForeignKey("bookings.BookingExtraWork", on_delete=models.PROTECT, null=True, blank=True, related_name="worker_earnings")
    settlement_batch = models.ForeignKey(
        "workers.WorkerPayoutSettlement",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="earnings",
    )
    available_at = models.DateTimeField(
        null=True, blank=True,
        help_text="When the earning became eligible for settlement after final payment.",
    )
    payment = models.ForeignKey("payments.Payment", on_delete=models.PROTECT, null=True, blank=True, related_name="worker_earnings")
    gross_amount = models.DecimalField(max_digits=12, decimal_places=2)
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    commission_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    net_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    adjustment_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    adjustment_note = models.TextField(blank=True)
    adjusted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="worker_earning_adjustments",
    )
    adjusted_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True)
    hold_reason = models.CharField(max_length=255, blank=True)
    payout_reference = models.CharField(max_length=100, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    paid_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="worker_earning_payouts",
    )

    class Meta:
        ordering = ["-created_at"]
        permissions = [
            ("manage_worker_payouts", "Can record worker payouts"),
            ("configure_worker_commission", "Can configure worker commission rates"),
        ]
        constraints = [
            models.UniqueConstraint(fields=("booking",), condition=models.Q(extra_work__isnull=True), name="unique_worker_service_earning_per_booking"),
            models.UniqueConstraint(fields=("extra_work",), condition=models.Q(extra_work__isnull=False), name="unique_worker_earning_per_extra_work"),
            models.CheckConstraint(condition=models.Q(gross_amount__gte=0), name="worker_earning_gross_nonnegative"),
            models.CheckConstraint(condition=models.Q(net_amount__isnull=True) | models.Q(net_amount__gte=0), name="worker_earning_net_nonnegative"),
            models.CheckConstraint(
                condition=models.Q(commission_rate__isnull=True) | (
                    models.Q(commission_rate__gte=0) & models.Q(commission_rate__lte=100)
                ),
                name="worker_earning_commission_range",
            ),
        ]

    def __str__(self):
        return f"Worker earning #{self.pk} - booking #{self.booking_id} - {self.status}"


class WorkerPayoutSettlement(TimeStampedModel):
    """Weekly worker payout batch with an auditable bank/UPI settlement reference."""

    class Status(models.TextChoices):
        PENDING = "pending", "Awaiting payout"
        PAID = "paid", "Paid"

    worker = models.ForeignKey(
        WorkerProfile,
        on_delete=models.PROTECT,
        related_name="payout_settlements",
    )
    period_start = models.DateField()
    period_end = models.DateField()
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True,
    )
    payout_reference = models.CharField(max_length=120, blank=True)
    admin_note = models.TextField(blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    paid_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="worker_payout_settlements",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_worker_payout_settlements",
    )

    class Meta:
        ordering = ["-period_start", "-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(period_end__gte=F("period_start")),
                name="worker_payout_period_valid",
            ),
            models.CheckConstraint(
                condition=Q(total_amount__gt=0),
                name="worker_payout_settlement_positive",
            ),
            models.UniqueConstraint(
                fields=("worker", "period_start"),
                condition=Q(status="pending"),
                name="one_pending_worker_settlement_per_week",
            ),
        ]

    def __str__(self):
        return f"Worker #{self.worker_id} · {self.period_start}–{self.period_end} · ₹{self.total_amount}"


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


class WorkerRewardWallet(TimeStampedModel):
    """Withdrawable mission and worker-referral rewards, separate from job earnings and customer wallet."""

    worker = models.OneToOneField(
        WorkerProfile,
        on_delete=models.PROTECT,
        related_name="reward_wallet",
    )
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_earned = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_withdrawn = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    eligible_jobs_count = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(balance__gte=0), name="worker_reward_balance_nonnegative"),
            models.CheckConstraint(condition=Q(total_earned__gte=0), name="worker_reward_earned_nonnegative"),
            models.CheckConstraint(condition=Q(total_withdrawn__gte=0), name="worker_reward_withdrawn_nonnegative"),
        ]

    def __str__(self):
        return f"Worker rewards for worker #{self.worker_id}: ₹{self.balance}"


class WorkerRewardTransaction(TimeStampedModel):
    class Type(models.TextChoices):
        ELIGIBLE_JOB = "eligible_job", "Eligible completed service"
        MISSION_REWARD = "mission_reward", "Mission reward"
        REFERRAL_REWARD = "referral_reward", "Worker referral reward"
        WITHDRAWAL = "withdrawal", "Withdrawal request"
        REFUND = "refund", "Withdrawal refund"

    wallet = models.ForeignKey(
        WorkerRewardWallet,
        on_delete=models.PROTECT,
        related_name="transactions",
    )
    worker = models.ForeignKey(
        WorkerProfile,
        on_delete=models.PROTECT,
        related_name="reward_transactions",
    )
    booking = models.ForeignKey(
        "bookings.Booking",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="worker_reward_transactions",
    )
    referral = models.ForeignKey(
        "accounts.Referral",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="worker_reward_transactions",
    )
    type = models.CharField(max_length=20, choices=Type.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    milestone_jobs = models.PositiveSmallIntegerField(null=True, blank=True)
    reference_key = models.CharField(max_length=120, unique=True)
    description = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gte=0), name="worker_reward_txn_amount_nonnegative"),
        ]

    def __str__(self):
        return f"{self.worker_id} · {self.type} · ₹{self.amount}"


class WorkerRewardWithdrawal(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending review"
        APPROVED = "approved", "Approved for payout"
        REJECTED = "rejected", "Rejected"
        PAID = "paid", "Paid"

    wallet = models.ForeignKey(
        WorkerRewardWallet,
        on_delete=models.PROTECT,
        related_name="withdrawals",
    )
    worker = models.ForeignKey(
        WorkerProfile,
        on_delete=models.PROTECT,
        related_name="reward_withdrawals",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    request_key = models.CharField(max_length=120, unique=True, default=uuid.uuid4, editable=False)
    payout_upi_id = models.CharField(max_length=100)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True)
    payout_reference = models.CharField(max_length=120, blank=True)
    admin_note = models.TextField(blank=True)
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="processed_worker_reward_withdrawals",
    )
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="worker_reward_withdrawal_positive"),
        ]

    def __str__(self):
        return f"Worker reward withdrawal #{self.pk} · ₹{self.amount} · {self.status}"
