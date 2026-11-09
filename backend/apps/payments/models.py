from django.conf import settings
from django.db import models
from django.db.models import Q
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
        REFUNDED = "refunded", "Refunded"

    booking = models.OneToOneField(
        Booking, on_delete=models.PROTECT, related_name="payment",
        null=True, blank=True,
    )
    order = models.OneToOneField(
        Order, on_delete=models.PROTECT, related_name="payment",
        null=True, blank=True,
    )
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="payments",
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    wallet_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Amount reserved from the customer wallet for this order payment.",
    )
    method = models.CharField(max_length=20, choices=Method.choices, default=Method.COD)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True,
    )
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
                    (Q(booking__isnull=False) & Q(order__isnull=True))
                    | (Q(booking__isnull=True) & Q(order__isnull=False))
                ),
                name="payment_exactly_one_booking_or_order",
            ),
        ]

    def __str__(self):
        target = f"Order #{self.order_id}" if self.order_id else f"Booking #{self.booking_id}"
        return f"Payment #{self.pk} - {target} - ₹{self.amount} ({self.status})"


class BookingFinancialPlan(TimeStampedModel):
    """Immutable, versioned financial terms for one booking line.

    Existing bookings without a plan remain on the legacy payment lifecycle.
    """
    class State(models.TextChoices):
        ACTIVE = "active", "Active"
        CANCELLED = "cancelled", "Cancelled"
        CLOSED = "closed", "Closed"

    booking = models.OneToOneField(
        Booking, on_delete=models.PROTECT, related_name="financial_plan",
    )
    currency = models.CharField(max_length=3, default="INR")
    gross_total = models.DecimalField(max_digits=12, decimal_places=2)
    advance_due = models.DecimalField(max_digits=12, decimal_places=2)
    balance_due = models.DecimalField(max_digits=12, decimal_places=2)
    advance_captured = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    balance_captured = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    refunded_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    platform_fee_deducted = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    calculation_version = models.CharField(max_length=24, default="split-50-50-v1")
    pricing_snapshot = models.JSONField(default=dict)
    state = models.CharField(max_length=16, choices=State.choices, default=State.ACTIVE)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(gross_total__gte=0), name="finplan_total_nonneg"),
            models.CheckConstraint(condition=Q(advance_due__gte=0), name="finplan_adv_nonneg"),
            models.CheckConstraint(condition=Q(balance_due__gte=0), name="finplan_bal_nonneg"),
            models.CheckConstraint(condition=Q(advance_captured__gte=0), name="finplan_adv_cap_nonneg"),
            models.CheckConstraint(condition=Q(balance_captured__gte=0), name="finplan_bal_cap_nonneg"),
            models.CheckConstraint(condition=Q(refunded_total__gte=0), name="finplan_refund_nonneg"),
            models.CheckConstraint(
                condition=Q(advance_due__lte=models.F("gross_total")),
                name="finplan_adv_lte_total",
            ),
            models.CheckConstraint(
                condition=Q(balance_due__lte=models.F("gross_total")),
                name="finplan_bal_lte_total",
            ),
        ]

    def __str__(self):
        return f"Financial plan for booking #{self.booking_id} ({self.currency} {self.gross_total})"


class PaymentInstallment(TimeStampedModel):
    class Kind(models.TextChoices):
        ADVANCE = "advance", "50% Booking Advance"
        FINAL_BALANCE = "final_balance", "50% Completion Balance"

    class Status(models.TextChoices):
        NOT_DUE = "not_due", "Not Due"
        DUE = "due", "Due"
        PROCESSING = "processing", "Processing"
        PARTIALLY_PAID = "partially_paid", "Partially Paid"
        PAID = "paid", "Paid"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    financial_plan = models.ForeignKey(
        BookingFinancialPlan, on_delete=models.PROTECT, related_name="installments",
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    amount_due = models.DecimalField(max_digits=12, decimal_places=2)
    amount_captured = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.NOT_DUE, db_index=True,
    )
    due_at = models.DateTimeField(null=True, blank=True)
    settled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["financial_plan", "kind"], name="inst_plan_kind_uniq",
            ),
            models.CheckConstraint(condition=Q(amount_due__gte=0), name="inst_due_nonneg"),
            models.CheckConstraint(condition=Q(amount_captured__gte=0), name="inst_cap_nonneg"),
            models.CheckConstraint(
                condition=Q(amount_captured__lte=models.F("amount_due")),
                name="inst_cap_lte_due",
            ),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} for booking #{self.financial_plan.booking_id}"


class PaymentAttempt(TimeStampedModel):
    class Provider(models.TextChoices):
        RAZORPAY = "razorpay", "Razorpay"
        WALLET = "wallet", "AIRway Wallet"

    class Status(models.TextChoices):
        CREATED = "created", "Created"
        AUTHORIZED = "authorized", "Authorized"
        CAPTURED = "captured", "Captured"
        FAILED = "failed", "Failed"
        REFUND_PENDING = "refund_pending", "Refund Pending"
        REFUNDED = "refunded", "Refunded"

    installment = models.ForeignKey(
        PaymentInstallment, on_delete=models.PROTECT, related_name="attempts",
    )
    provider = models.CharField(max_length=16, choices=Provider.choices, default=Provider.RAZORPAY)
    idempotency_key = models.CharField(max_length=100, unique=True)
    # Full installment tender; source amounts are frozen per attempt.
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    gateway_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    wallet_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default="INR")
    provider_order_id = models.CharField(max_length=100, null=True, blank=True, unique=True)
    provider_payment_id = models.CharField(max_length=100, null=True, blank=True, unique=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.CREATED, db_index=True)
    captured_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    provider_payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="attempt_amount_positive"),
            models.CheckConstraint(
                condition=Q(amount=models.F("gateway_amount") + models.F("wallet_amount")),
                name="attempt_sources_sum",
            ),
            models.CheckConstraint(condition=Q(gateway_amount__gte=0), name="attempt_gateway_nonneg"),
            models.CheckConstraint(condition=Q(wallet_amount__gte=0), name="attempt_wallet_nonneg"),
        ]

    def __str__(self):
        return f"Attempt #{self.pk} - installment #{self.installment_id} ({self.status})"


class RefundRecord(TimeStampedModel):
    class Reason(models.TextChoices):
        CUSTOMER_CANCELLATION = "customer_cancellation", "Customer Cancellation"
        PROVIDER_UNAVAILABLE = "provider_unavailable", "Provider Unavailable"
        PLATFORM_CANCELLATION = "platform_cancellation", "Platform Cancellation"
        PAYMENT_RECONCILIATION = "payment_reconciliation", "Payment Reconciliation"
        SUPPORT_RESOLUTION = "support_resolution", "Support Resolution"

    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        PENDING = "pending", "Pending with Provider"
        PROCESSED = "processed", "Processed"
        FAILED = "failed", "Failed"

    booking = models.ForeignKey(Booking, on_delete=models.PROTECT, related_name="refund_records")
    payment_attempt = models.ForeignKey(
        PaymentAttempt, on_delete=models.PROTECT, related_name="refunds",
        null=True, blank=True,
    )
    payment = models.ForeignKey(
        Payment, on_delete=models.PROTECT, null=True, blank=True,
        related_name="refund_records",
    )
    payment_allocation = models.ForeignKey(
        "PaymentAllocation", on_delete=models.PROTECT, null=True, blank=True,
        related_name="refund_records",
    )
    idempotency_key = models.CharField(max_length=120, unique=True)
    reason = models.CharField(max_length=32, choices=Reason.choices)
    gross_amount = models.DecimalField(max_digits=12, decimal_places=2)
    platform_fee = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    refund_amount = models.DecimalField(max_digits=12, decimal_places=2)
    provider_refund_id = models.CharField(max_length=100, null=True, blank=True, unique=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.REQUESTED, db_index=True)
    requested_at = models.DateTimeField(null=True, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    provider_payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=Q(gross_amount__gte=0), name="refund_gross_nonneg"),
            models.CheckConstraint(condition=Q(platform_fee__gte=0), name="refund_fee_nonneg"),
            models.CheckConstraint(condition=Q(refund_amount__gte=0), name="refund_amt_nonneg"),
            models.CheckConstraint(
                condition=Q(refund_amount__lte=models.F("gross_amount")),
                name="refund_amt_lte_gross",
            ),
        ]

    def __str__(self):
        return f"Refund #{self.pk} - booking #{self.booking_id} ({self.status})"


class ServiceOTPChallenge(TimeStampedModel):
    class Purpose(models.TextChoices):
        START = "start", "Service Start"
        COMPLETION = "completion", "Service Completion"

    booking = models.ForeignKey(Booking, on_delete=models.PROTECT, related_name="service_otp_challenges")
    purpose = models.CharField(max_length=12, choices=Purpose.choices)
    code_hash = models.CharField(max_length=128)
    expires_at = models.DateTimeField(db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=5)
    consumed_at = models.DateTimeField(null=True, blank=True)
    invalidated_at = models.DateTimeField(null=True, blank=True)
    delivery_reference = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["booking", "purpose", "consumed_at"], name="pay_otp_booking_purpose_idx"),
        ]

    def __str__(self):
        return f"{self.get_purpose_display()} OTP challenge for booking #{self.booking_id}"

class PaymentAllocation(TimeStampedModel):
    """Allocate captured tender from a legacy Payment or an installment attempt."""

    payment = models.ForeignKey(
        Payment, on_delete=models.PROTECT, related_name="installment_allocations",
        null=True, blank=True,
    )
    payment_attempt = models.ForeignKey(
        PaymentAttempt, on_delete=models.PROTECT, related_name="allocations",
        null=True, blank=True,
    )
    installment = models.ForeignKey(
        PaymentInstallment, on_delete=models.PROTECT, related_name="payment_allocations",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    gateway_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    wallet_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        ordering = ["created_at", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["payment", "installment"], name="pay_alloc_payment_inst_uniq",
            ),
            models.UniqueConstraint(
                fields=["payment_attempt", "installment"], name="pay_alloc_attempt_inst_uniq",
            ),
            models.CheckConstraint(
                condition=(
                    (Q(payment__isnull=False) & Q(payment_attempt__isnull=True))
                    | (Q(payment__isnull=True) & Q(payment_attempt__isnull=False))
                ),
                name="pay_alloc_exactly_one_source",
            ),
            models.CheckConstraint(condition=Q(amount__gte=0), name="pay_alloc_amount_nonneg"),
            models.CheckConstraint(condition=Q(gateway_amount__gte=0), name="pay_alloc_gateway_nonneg"),
            models.CheckConstraint(condition=Q(wallet_amount__gte=0), name="pay_alloc_wallet_nonneg"),
            models.CheckConstraint(
                condition=Q(amount=models.F("gateway_amount") + models.F("wallet_amount")),
                name="pay_alloc_sources_sum",
            ),
        ]

    def __str__(self):
        return f"Payment #{self.payment_id} allocation for installment #{self.installment_id}"
