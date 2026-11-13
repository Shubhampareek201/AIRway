from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class City(TimeStampedModel):
    name = models.CharField(max_length=100, unique=True)
    state = models.CharField(max_length=100, default="Rajasthan")
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "cities"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Zone(TimeStampedModel):
    """City ke andar area/colony. Worker aur matching isi se hoti hai."""
    city = models.ForeignKey(City, on_delete=models.PROTECT, related_name="zones")
    name = models.CharField(max_length=100)
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )

    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )
    coverage_radius_meters = models.PositiveIntegerField(
        default=5000,
        help_text="Legacy radius fallback. Polygon coverage takes precedence when configured.",
    )
    coverage_polygon = models.JSONField(
        null=True,
        blank=True,
        help_text="GeoJSON Polygon geometry: {\"type\": \"Polygon\", \"coordinates\": [[[longitude, latitude], ...]]}.",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["city", "name"]
        constraints = [
            models.UniqueConstraint(fields=["city", "name"], name="unique_zone_per_city")
        ]

    def __str__(self):
        return f"{self.name}, {self.city.name}"


class AppSetting(TimeStampedModel):
    """Admin se badalne wali settings: working hours, commission, urgent fee, etc."""
    key = models.CharField(max_length=100, unique=True)
    value = models.CharField(max_length=500)
    description = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["key"]

    def __str__(self):
        return f"{self.key} = {self.value}"

    @classmethod
    def get(cls, key, default=None):
        obj = cls.objects.filter(key=key).first()
        return obj.value if obj else default