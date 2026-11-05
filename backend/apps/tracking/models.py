from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class WorkerLocation(TimeStampedModel):
    """Latest known location of a worker."""
    worker = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="locations",
    )
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    accuracy = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    heading = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    speed = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["worker"]),
        ]

    def __str__(self):
        return f"{self.worker.phone} - {self.latitude}, {self.longitude}"


class LocationEvent(TimeStampedModel):
    """Historical location events for tracking worker journey."""
    worker = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="location_events",
    )
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    event_type = models.CharField(max_length=50, default="update")
    booking_id = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["worker", "created_at"]),
        ]

    def __str__(self):
        return f"{self.worker.phone} - {self.event_type} - {self.created_at}"