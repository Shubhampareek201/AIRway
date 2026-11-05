from django.conf import settings
from django.db import models
from simple_history.models import HistoricalRecords

from apps.bookings.models import Booking, Order
from apps.core.models import TimeStampedModel


class Payment(TimeStampedModel):
    class Method(models.TextChoices):
        COD = "cod", "Cash on Delivery"
        RAZORPAY = "razorpay", "Razorpay"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        FAILED = "failed", "Failed"
        REFUNDED = "refunded", "Refunded"

    booking = models.OneToOneField(
        Booking,
        on_delete=models.PROTECT,
        related_name="payment",
        null=True,
        blank=True,
    )
    order = models.OneToOneField(
        Order,
        on_delete=models.PROTECT,
        related_name="payment",
        null=True,
        blank=True,
    )
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="payments",
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    method = models.CharField(max_length=20, choices=Method.choices, default=Method.COD)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)

    razorpay_order_id = models.CharField(max_length=100, blank=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True)
    razorpay_signature = models.CharField(max_length=255, blank=True)

    paid_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    raw_response = models.JSONField(default=dict, blank=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    (models.Q(booking__isnull=False) & models.Q(order__isnull=True))
                    | (models.Q(booking__isnull=True) & models.Q(order__isnull=False))
                ),
                name="payment_exactly_one_booking_or_order",
            ),
        ]

    def __str__(self):
        target = f"Order #{self.order_id}" if self.order_id else f"Booking #{self.booking_id}"
        return f"Payment #{self.pk} - {target} - ₹{self.amount} ({self.status})"