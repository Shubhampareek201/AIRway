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