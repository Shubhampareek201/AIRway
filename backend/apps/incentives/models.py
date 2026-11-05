from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel
from apps.catalog.models import Category
from apps.workers.models import WorkerProfile


class IncentiveProgram(TimeStampedModel):
    """Admin-defined bonus program: complete N jobs in a category window and earn."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        EXPIRED = "expired", "Expired"

    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    service_categories = models.ManyToManyField(
        Category,
        related_name="incentive_programs",
        blank=True,
        help_text="Categories whose completed jobs count toward this program.",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True
    )
    start_date = models.DateTimeField(null=True, blank=True)
    end_date = models.DateTimeField(null=True, blank=True)
    max_rewards = models.PositiveIntegerField(
        default=0, help_text="Max bonus awards per worker (0 = unlimited)."
    )
    repeat_allowed = models.BooleanField(
        default=False, help_text="Whether a worker can earn the bonus more than once."
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Incentive Program"
        verbose_name_plural = "Incentive Programs"

    def __str__(self):
        return self.name


class Milestone(TimeStampedModel):
    """A threshold within a program: complete `required_jobs` and get `bonus_amount`."""

    program = models.ForeignKey(
        IncentiveProgram,
        on_delete=models.CASCADE,
        related_name="milestones",
    )
    required_jobs = models.PositiveIntegerField()
    bonus_amount = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ["required_jobs"]
        constraints = [
            models.UniqueConstraint(
                fields=["program", "required_jobs"],
                name="unique_milestone_per_program",
            ),
            models.CheckConstraint(
                condition=models.Q(required_jobs__gte=1),
                name="milestone_required_jobs_positive",
            ),
        ]

    def __str__(self):
        return f"{self.program.name} - {self.required_jobs} jobs - ₹{self.bonus_amount}"


class IncentiveProgress(TimeStampedModel):
    """Per-worker progress snapshot for a program, recomputed on completed bookings."""

    worker = models.ForeignKey(
        WorkerProfile,
        on_delete=models.CASCADE,
        related_name="incentive_progress",
    )
    program = models.ForeignKey(
        IncentiveProgram,
        on_delete=models.CASCADE,
        related_name="progress",
    )
    eligible_jobs_count = models.PositiveIntegerField(default=0)
    last_updated = models.DateTimeField(auto_now=True)
    awards_count = models.PositiveIntegerField(
        default=0, help_text="How many times this worker was already rewarded."
    )

    class Meta:
        ordering = ["-last_updated"]
        constraints = [
            models.UniqueConstraint(
                fields=["worker", "program"], name="unique_worker_program_progress"
            ),
        ]

    def __str__(self):
        return f"{self.worker.user.phone} - {self.program.name} ({self.eligible_jobs_count})"