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

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        FAILED = "failed", "Failed"
        PARTIALLY_PAID = "partially_paid", "Partially Paid"
        REFUND_PENDING = "refund_pending", "Refund Pending"
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

class PaymentInstallment(TimeStampedModel):
    """A separately collectible part of one booking/order total."""

    class Kind(models.TextChoices):
        ADVANCE = "advance", "Booking Advance"
        BALANCE = "balance", "Completion Balance"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"

    payment = models.ForeignKey(
        Payment, on_delete=models.PROTECT, related_name="installments"
    )
    kind = models.CharField(max_length=16, choices=Kind.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    wallet_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(fields=["payment", "kind"], name="uniq_pay_inst_kind"),
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="pay_inst_amt_pos"),
            models.CheckConstraint(condition=models.Q(wallet_amount__gte=0), name="pay_inst_wallet_nonneg"),
        ]

    def __str__(self):
        return f"Payment #{self.payment_id} {self.kind} ₹{self.amount} ({self.status})"


class PaymentAttempt(TimeStampedModel):
    """One Razorpay/wallet attempt for an advance or completion-balance installment."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        FAILED = "failed", "Failed"
        REFUNDED = "refunded", "Refunded"

    installment = models.ForeignKey(
        PaymentInstallment, on_delete=models.PROTECT, related_name="attempts"
    )
    attempt_number = models.PositiveIntegerField()
    amount = models.DecimalField(
        max_digits=12, decimal_places=2,
        help_text="Gateway amount only; wallet contribution is stored separately.",
    )
    wallet_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    method = models.CharField(max_length=20, choices=Payment.Method.choices, default=Payment.Method.RAZORPAY)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    razorpay_order_id = models.CharField(max_length=100, blank=True, null=True, unique=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True, null=True, unique=True)
    razorpay_signature = models.CharField(max_length=255, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    raw_response = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["attempt_number"]
        constraints = [
            models.UniqueConstraint(fields=["installment", "attempt_number"], name="uniq_inst_attempt_no"),
            models.CheckConstraint(condition=models.Q(amount__gte=0), name="pay_attempt_amt_nonneg"),
            models.CheckConstraint(condition=models.Q(wallet_amount__gte=0), name="pay_attempt_wallet_nonneg"),
        ]

    def __str__(self):
        return f"{self.installment} attempt {self.attempt_number}"


class PaymentRefund(TimeStampedModel):
    """Refund ledger entry; gateway refunds remain pending until Razorpay confirms processing."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSED = "processed", "Processed"
        FAILED = "failed", "Failed"

    attempt = models.ForeignKey(PaymentAttempt, on_delete=models.PROTECT, related_name="refunds")
    idempotency_key = models.CharField(max_length=120, unique=True)
    gateway_refund_id = models.CharField(max_length=100, blank=True, db_index=True)
    gateway_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    wallet_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    platform_fee = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    reason = models.CharField(max_length=255, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    raw_response = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=models.Q(gateway_amount__gte=0), name="pay_refund_gateway_nonneg"),
            models.CheckConstraint(condition=models.Q(wallet_amount__gte=0), name="pay_refund_wallet_nonneg"),
            models.CheckConstraint(condition=models.Q(platform_fee__gte=0), name="pay_refund_fee_nonneg"),
        ]

    def __str__(self):
        return f"Refund for attempt #{self.attempt_id}: ₹{self.gateway_amount + self.wallet_amount} ({self.status})"
