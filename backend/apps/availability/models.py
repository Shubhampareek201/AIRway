from django.conf import settings
from django.db import models
from django.db.models import F, Q

from apps.core.models import TimeStampedModel


class WorkerAvailability(TimeStampedModel):
    """Worker's working hours per weekday (Mon=0 .. Sun=6)."""

    class Weekday(models.IntegerChoices):
        MONDAY = 0, "Monday"
        TUESDAY = 1, "Tuesday"
        WEDNESDAY = 2, "Wednesday"
        THURSDAY = 3, "Thursday"
        FRIDAY = 4, "Friday"
        SATURDAY = 5, "Saturday"
        SUNDAY = 6, "Sunday"

    worker = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="availability",
    )
    weekday = models.IntegerField(choices=Weekday.choices)
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["weekday", "start_time"]
        constraints = [
            models.CheckConstraint(condition=Q(end_time__gt=F("start_time")), name="avail_valid_hours"),
            models.UniqueConstraint(fields=["worker", "weekday"], name="unique_worker_availability_day"),
        ]

    def __str__(self):
        return f"{self.worker.phone} - {self.get_weekday_display()} {self.start_time} - {self.end_time}"


class WorkerBlockedSlot(TimeStampedModel):
    """Ad-hoc blocked window (holiday, emergency, etc.) for a worker."""

    worker = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="blocked_slots",
    )
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    reason = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["start_at"]
        constraints = [
            models.CheckConstraint(condition=Q(end_at__gt=F("start_at")), name="blocked_slot_valid_range"),
        ]

    def __str__(self):
        return f"{self.worker.phone} - blocked {self.start_at} -> {self.end_at}"