from django.conf import settings
from django.db import models
from simple_history.models import HistoricalRecords

from apps.bookings.models import Booking, Order
from apps.core.models import TimeStampedModel


class Payment(TimeStampedModel):
    class Method(models.TextChoices):
        COD = "cod", "Cash on Delivery"
        RAZORPAY = "razorpay", "Razorpay"
        WALLET = "wallet", "AIRway Wallet"

    class Stage(models.TextChoices):
        LEGACY = "legacy", "Legacy full payment"
        ADVANCE = "advance", "30% advance"
        BALANCE = "balance", "70% balance"

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
    order = models.ForeignKey(
        Order,
        on_delete=models.PROTECT,
        related_name="payments",
        null=True,
        blank=True,
    )
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="payments",
    )
    stage = models.CharField(max_length=20, choices=Stage.choices, default=Stage.LEGACY, db_index=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    wallet_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Amount reserved from the customer wallet for this order payment.",
    )
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
            models.UniqueConstraint(
                fields=["order", "stage"],
                condition=models.Q(order__isnull=False),
                name="unique_order_payment_stage",
            ),
            models.UniqueConstraint(
                fields=["razorpay_order_id"],
                condition=~models.Q(razorpay_order_id=""),
                name="unique_razorpay_order_id",
            ),
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


class PaymentRefund(TimeStampedModel):
    """Per-service refund ledger for order payments and legacy booking payments."""

    class Status(models.TextChoices):
        PROCESSING = "processing", "Processing"
        PENDING = "pending", "Pending"
        PROCESSED = "processed", "Processed"
        FAILED = "failed", "Failed"

    class Reason(models.TextChoices):
        CUSTOMER_CANCELLATION = "customer_cancellation", "Customer cancellation"
        PLATFORM_UNFULFILLED = "platform_unfulfilled", "AIRway unable to fulfil"

    payment = models.ForeignKey(
        Payment, on_delete=models.PROTECT, related_name="refunds"
    )
    booking = models.ForeignKey(
        Booking, on_delete=models.PROTECT, related_name="payment_refunds"
    )
    order_item = models.ForeignKey(
        "bookings.OrderItem",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="payment_refunds",
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    wallet_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    gateway_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    reason = models.CharField(max_length=32, choices=Reason.choices)
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.PROCESSING, db_index=True
    )
    gateway_refund_id = models.CharField(max_length=100, blank=True, db_index=True)
    failure_reason = models.CharField(max_length=500, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["payment", "booking"], name="unique_payment_refund_booking"
            ),
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name="payment_refund_amount_positive",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(wallet_amount__gte=0)
                    & models.Q(gateway_amount__gte=0)
                ),
                name="payment_refund_components_nonnegative",
            ),
        ]

    def __str__(self):
        return f"Refund #{self.pk} - Booking #{self.booking_id} - ₹{self.amount} ({self.status})"
