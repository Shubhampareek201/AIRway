from django.conf import settings
from django.db import models
from django.db.models import F, Q, Sum
from django.utils import timezone
from simple_history.models import HistoricalRecords

from apps.catalog.models import Service, ServiceVariant, AddOn, FormField
from apps.core.models import TimeStampedModel
from apps.accounts.models import Address


class Booking(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        ASSIGNED = "assigned", "Assigned"
        IN_PROGRESS = "in_progress", "In Progress"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"
        DISPUTED = "disputed", "Disputed"

    class BookingMode(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled"
        INSPECTION = "inspection", "Inspection"
        PICKUP_DROP = "pickup_drop", "Pickup & Drop"

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="bookings",
    )
    address = models.ForeignKey(
        Address,
        on_delete=models.PROTECT,
        related_name="bookings",
    )
    service = models.ForeignKey(
        Service,
        on_delete=models.PROTECT,
        related_name="bookings",
    )
    variant = models.ForeignKey(
        ServiceVariant,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="bookings",
    )

    booking_mode = models.CharField(
        max_length=15,
        choices=BookingMode.choices,
        default=BookingMode.SCHEDULED,
    )

    scheduled_at = models.DateTimeField(
        help_text="For scheduled: service time. For inspection: visit time. For pickup_drop: pickup time."
    )
    drop_scheduled_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Only for pickup_drop: drop-off time."
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )

    pricing_snapshot = models.JSONField(
        default=dict,
        help_text="Snapshot of variant/addon prices at booking time: {variant_price, addon_prices[], total, tax, discount}"
    )

    notes = models.TextField(blank=True, help_text="Customer notes")
    customer_answers = models.JSONField(default=dict, blank=True, help_text="Category-level choices captured before service selection")
    worker_notes = models.TextField(blank=True, help_text="Worker notes during service")

    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.TextField(blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cancelled_bookings",
    )

    completed_at = models.DateTimeField(null=True, blank=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["customer", "status"]),
            models.Index(fields=["scheduled_at", "status"]),
        ]

    def __str__(self):
        return f"Booking #{self.pk} - {self.customer.phone} - {self.service.title}"

    @property
    def total_amount(self):
        return self.pricing_snapshot.get("total", 0)

    @property
    def can_cancel(self):
        return self.status in [self.Status.PENDING, self.Status.CONFIRMED, self.Status.ASSIGNED]


class BookingAddOn(TimeStampedModel):
    booking = models.ForeignKey(
        Booking,
        on_delete=models.CASCADE,
        related_name="booking_addons",
    )
    addon = models.ForeignKey(
        AddOn,
        on_delete=models.PROTECT,
        related_name="booking_addons",
    )
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["booking", "addon"], name="unique_booking_addon")
        ]

    def __str__(self):
        return f"{self.booking} - {self.addon.title} x{self.quantity}"


class BookingFormResponse(TimeStampedModel):
    booking = models.ForeignKey(
        Booking,
        on_delete=models.CASCADE,
        related_name="form_responses",
    )
    form_field = models.ForeignKey(
        FormField,
        on_delete=models.PROTECT,
        related_name="booking_responses",
    )
    value = models.JSONField(help_text="Answer value: string, number, boolean, or file URL")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["booking", "form_field"], name="unique_booking_form_response")
        ]

    def __str__(self):
        return f"{self.booking} - {self.form_field.key}: {self.value}"


class BookingStatusHistory(TimeStampedModel):
    booking = models.ForeignKey(
        Booking,
        on_delete=models.CASCADE,
        related_name="status_history",
    )
    from_status = models.CharField(max_length=20, choices=Booking.Status.choices, blank=True)
    to_status = models.CharField(max_length=20, choices=Booking.Status.choices)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="booking_status_changes",
    )
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name_plural = "Booking status histories"

    def __str__(self):
        return f"{self.booking}: {self.from_status} -> {self.to_status}"


class BookingAssignment(TimeStampedModel):
    booking = models.OneToOneField(
        Booking,
        on_delete=models.CASCADE,
        related_name="assignment",
    )
    worker = models.ForeignKey(
        "workers.WorkerProfile",
        on_delete=models.PROTECT,
        related_name="assignments",
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-assigned_at"]

    def __str__(self):
        return f"{self.booking} -> {self.worker.user.phone}"


class WorkerOffer(TimeStampedModel):
    """
    Tracks each worker's offer for a booking. One-offer-per-worker-per-booking.

    A booking is created without a BookingAssignment. Multiple WorkerOffer
    records are created for eligible workers. Only after a worker successfully
    accepts does a BookingAssignment get created with a required worker.

    The existing OneToOne booking relationship on BookingAssignment remains
    the protection against multiple final assignments.
    """
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"
        EXPIRED = "expired", "Expired"
        WITHDRAWN = "withdrawn", "Withdrawn"

    booking = models.ForeignKey(
        Booking,
        on_delete=models.CASCADE,
        related_name="worker_offers",
        help_text="For an order offer, this is the first booking line used as the offer's display anchor.",
    )
    order = models.ForeignKey(
        "Order",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="worker_offers",
        help_text="Set for a parent-order offer covering every booking line.",
    )
    batch_number = models.PositiveIntegerField(default=1)
    worker = models.ForeignKey(
        "workers.WorkerProfile",
        on_delete=models.PROTECT,
        related_name="worker_offers",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    offered_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(
        help_text="Offer expires at this time if not accepted or declined.",
    )
    responded_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["offered_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["booking", "worker"],
                name="unique_offer_per_booking_worker",
            ),
        ]

    def __str__(self):
        return f"Offer #{self.pk}: {self.worker.user.phone} -> Booking #{self.booking_id}"

class Order(TimeStampedModel):
    """Parent checkout record that groups multiple independent service bookings."""

    class Status(models.TextChoices):
        AWAITING_ASSIGNMENT = "awaiting_assignment", "Awaiting Assignment"
        AWAITING_PAYMENT = "awaiting_payment", "Awaiting Payment"
        PAID = "paid", "Paid"
        PARTIALLY_CANCELLED = "partially_cancelled", "Partially Cancelled"
        CANCELLED = "cancelled", "Cancelled"

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="service_orders",
    )
    address = models.ForeignKey(
        Address,
        on_delete=models.PROTECT,
        related_name="service_orders",
    )
    status = models.CharField(
        max_length=24,
        choices=Status.choices,
        default=Status.AWAITING_ASSIGNMENT,
        db_index=True,
    )
    currency = models.CharField(max_length=3, default="INR")
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["customer", "status"], name="book_ord_cust_stat_idx"),
            models.Index(fields=["created_at", "status"], name="book_ord_created_stat_idx"),
        ]

    def __str__(self):
        return f"Order #{self.pk} - {self.customer.phone} - ₹{self.total_amount}"


class OrderItem(TimeStampedModel):
    """Immutable checkout snapshot linking one order line to one service booking."""

    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="items")
    booking = models.OneToOneField(
        Booking,
        on_delete=models.PROTECT,
        related_name="order_item",
    )
    quantity = models.PositiveIntegerField(default=1)
    service_snapshot = models.JSONField(default=dict, blank=True)
    pricing_snapshot = models.JSONField(default=dict, blank=True)
    line_subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    line_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gte=1), name="order_item_quantity_gte_1"),
        ]

    def __str__(self):
        return f"Order #{self.order_id} - Booking #{self.booking_id}"


class CustomerCart(TimeStampedModel):
    """One active cart per customer; cart is separate from confirmed bookings."""
    customer = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="service_cart")
    address = models.ForeignKey(Address, on_delete=models.SET_NULL, null=True, blank=True, related_name="customer_carts")

    def __str__(self):
        return f"Cart - {self.customer.phone}"

    @property
    def subtotal(self):
        return sum((item.line_total for item in self.items.all()), 0)


class CartItem(TimeStampedModel):
    cart = models.ForeignKey(CustomerCart, on_delete=models.CASCADE, related_name="items")
    service = models.ForeignKey(Service, on_delete=models.PROTECT, related_name="cart_items")
    variant = models.ForeignKey(ServiceVariant, on_delete=models.PROTECT, null=True, blank=True, related_name="cart_items")
    quantity = models.PositiveIntegerField(default=1)
    addon_selections = models.JSONField(default=list, blank=True)
    form_answers = models.JSONField(default=dict, blank=True)
    category_answers = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)
    pricing_snapshot = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.service.title} x{self.quantity}"

    @property
    def line_total(self):
        from decimal import Decimal
        return Decimal(str(self.pricing_snapshot.get("line_total", "0")))


class DispatchConfiguration(TimeStampedModel):
    """Singleton Admin-controlled settings for worker priority-batch dispatch."""

    PRIORITY_RATING = "rating_desc"
    PRIORITY_ACCEPTANCE = "acceptance_desc"
    PRIORITY_RATING_ACCEPTANCE = "rating_acceptance"
    PRIORITY_CANCELLATIONS = "cancellations_asc"

    PRIORITY_CHOICES = [
        (PRIORITY_RATING, "Worker rating: highest first"),
        (PRIORITY_ACCEPTANCE, "Acceptance rate: highest first"),
        (PRIORITY_RATING_ACCEPTANCE, "Rating, then acceptance rate"),
        (PRIORITY_CANCELLATIONS, "Fewest cancellations, then rating"),
    ]

    is_enabled = models.BooleanField(default=True)
    batch_size = models.PositiveSmallIntegerField(default=5)
    max_batches = models.PositiveSmallIntegerField(default=3)
    offer_expiry_minutes = models.PositiveSmallIntegerField(default=5)
    priority_order = models.CharField(
        max_length=32,
        choices=PRIORITY_CHOICES,
        default=PRIORITY_RATING,
    )

    class Meta:
        verbose_name = "Worker dispatch configuration"
        verbose_name_plural = "Worker dispatch configuration"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Dispatch configuration cannot be deleted.")

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return "Worker dispatch configuration"


class ServiceOTP(TimeStampedModel):
    """Hashed, purpose-specific customer OTPs for service start and completion."""

    class Purpose(models.TextChoices):
        START = "start", "Service Start"
        COMPLETE = "complete", "Service Completion"

    booking = models.ForeignKey(
        Booking, on_delete=models.PROTECT, related_name="service_otps"
    )
    purpose = models.CharField(max_length=12, choices=Purpose.choices)
    code_hash = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    verified_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_sent_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["booking", "purpose", "verified_at"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self):
        return f"Booking #{self.booking_id} {self.purpose} OTP"
