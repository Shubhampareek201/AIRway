from django.db import models

from apps.core.models import TimeStampedModel


class PricingRule(TimeStampedModel):
    """Admin-configurable pricing rules."""
    service = models.ForeignKey(
        "catalog.Service",
        on_delete=models.CASCADE,
        related_name="pricing_rules",
        null=True, blank=True,
    )
    category = models.ForeignKey(
        "catalog.Category",
        on_delete=models.CASCADE,
        related_name="pricing_rules",
        null=True, blank=True,
    )
    name = models.CharField(max_length=200)
    base_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    visit_fee = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    duration_minutes = models.PositiveIntegerField(default=60)
    buffer_minutes = models.PositiveIntegerField(default=30)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class CommissionRule(TimeStampedModel):
    """Platform commission rules."""
    name = models.CharField(max_length=200)
    commission_percent = models.DecimalField(max_digits=5, decimal_places=2, default=20)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class ServiceQuestion(TimeStampedModel):
    """Dynamic questions for services."""
    service = models.ForeignKey(
        "catalog.Service",
        on_delete=models.CASCADE,
        related_name="questions",
    )
    key = models.SlugField(help_text="Unique key for the question")
    label = models.CharField(max_length=200)
    label_hi = models.CharField(max_length=200, blank=True)
    field_type = models.CharField(max_length=20, default="text")
    options_data = models.JSONField(default=list, blank=True)
    is_required = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order"]
        constraints = [
            models.UniqueConstraint(fields=["service", "key"], name="unique_question_per_service"),
        ]

    def __str__(self):
        return self.label


class ServiceQuestionOption(TimeStampedModel):
    """Options for select-type questions."""
    question = models.ForeignKey(
        ServiceQuestion,
        on_delete=models.CASCADE,
        related_name="option_items",
    )
    value = models.CharField(max_length=100)
    label = models.CharField(max_length=200)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order"]

    def __str__(self):
        return self.label