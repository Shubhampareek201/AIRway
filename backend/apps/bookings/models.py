from django.conf import settings
from django.db import models
from django.db.models import F, Q, Sum
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
    appointment_group = models.ForeignKey(
        "AppointmentGroup",
        on_delete=models.SET_NULL,
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
        recurring_plan = getattr(self, "recurring_wash_plan", None)
        if recurring_plan and recurring_plan.status in (
            RecurringWashPlan.Status.PAID_PENDING_SETUP,
            RecurringWashPlan.Status.ACTIVE,
            RecurringWashPlan.Status.PAUSED,
        ):
            return False
        return self.status in [self.Status.PENDING, self.Status.CONFIRMED, self.Status.ASSIGNED]


class BookingWorkEvidence(TimeStampedModel):
    """Private before/after work photos uploaded by the assigned professional."""

    class Stage(models.TextChoices):
        BEFORE = "before", "Before work"
        AFTER = "after", "After work"

    booking = models.ForeignKey(
        Booking, on_delete=models.PROTECT, related_name="work_evidence"
    )
    worker = models.ForeignKey(
        "workers.WorkerProfile", on_delete=models.PROTECT, related_name="work_evidence"
    )
    stage = models.CharField(max_length=8, choices=Stage.choices, db_index=True)
    image_path = models.CharField(max_length=500)
    note = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["booking", "stage"], name="booking_evidence_stage_idx")]

    def __str__(self):
        return f"{self.get_stage_display()} evidence for booking #{self.booking_id}"


class BookingQuote(TimeStampedModel):
    """Worker-submitted inspection estimate requiring explicit customer approval."""

    class Status(models.TextChoices):
        PENDING_CUSTOMER = "pending_customer", "Awaiting customer approval"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"
        SUPERSEDED = "superseded", "Superseded by a revised quote"

    booking = models.ForeignKey(
        Booking, on_delete=models.PROTECT, related_name="quotes"
    )
    worker = models.ForeignKey(
        "workers.WorkerProfile", on_delete=models.PROTECT, related_name="booking_quotes"
    )
    version = models.PositiveIntegerField(default=1)
    line_items = models.JSONField(
        default=list,
        help_text="Worker estimate rows: labour, material or other with description, quantity and unit price.",
    )
    labour_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    material_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    other_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    status = models.CharField(
        max_length=24, choices=Status.choices,
        default=Status.PENDING_CUSTOMER, db_index=True,
    )
    customer_response_note = models.TextField(blank=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-version", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["booking", "version"], name="unique_booking_quote_version"
            ),
            models.UniqueConstraint(
                fields=["booking"],
                condition=models.Q(status="pending_customer"),
                name="one_pending_quote_per_booking",
            ),
        ]

    def __str__(self):
        return f"Quote v{self.version} for booking #{self.booking_id} ({self.status})"


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
    # Only the latest foreground GPS sample is retained for active-job tracking.
    live_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    live_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    live_accuracy_m = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    live_location_updated_at = models.DateTimeField(null=True, blank=True)

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
        help_text="Set for a legacy parent-order offer covering every booking line.",
    )
    appointment_group = models.ForeignKey(
        "AppointmentGroup",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="worker_offers",
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
        PARTIALLY_ASSIGNED = "partially_assigned", "Partially Assigned"
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


class AppointmentGroup(TimeStampedModel):
    """One coordinated appointment for services under the same root category in an order."""

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="appointment_groups",
    )
    root_category = models.ForeignKey(
        "catalog.Category",
        on_delete=models.PROTECT,
        related_name="appointment_groups",
    )
    category_slug_snapshot = models.SlugField(max_length=100)
    category_title_snapshot = models.CharField(max_length=150)
    scheduled_at = models.DateTimeField()
    customer_message = models.CharField(max_length=500, blank=True)
    arrival_otp = models.CharField(max_length=6, blank=True)
    arrival_otp_expires_at = models.DateTimeField(null=True, blank=True)
    arrival_otp_verified_at = models.DateTimeField(null=True, blank=True)
    arrival_otp_attempts = models.PositiveSmallIntegerField(default=0)
    arrival_otp_locked_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["scheduled_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["order", "root_category"],
                name="unique_order_root_appointment_group",
            )
        ]
        indexes = [
            models.Index(
                fields=["order", "scheduled_at"],
                name="appt_group_order_time_idx",
            )
        ]

    def __str__(self):
        return f"{self.category_title_snapshot} appointment for Order #{self.order_id}"


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
    schedule_mode = models.CharField(max_length=24, default="separate")
    group_messages = models.JSONField(default=dict, blank=True)

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
    schedule_data = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.service.title} x{self.quantity}"

    @property
    def line_total(self):
        from decimal import Decimal
        return Decimal(str(self.pricing_snapshot.get("line_total", "0")))


class DispatchConfiguration(TimeStampedModel):
    """Singleton Admin-controlled settings for simultaneous worker-offer dispatch."""

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



class BookingCompletionOTP(TimeStampedModel):
    """Hashed, expiring one-time code shared by the customer with the worker."""

    booking = models.OneToOneField(
        Booking,
        on_delete=models.CASCADE,
        related_name="completion_otp",
    )
    code_hash = models.CharField(max_length=256)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    last_sent_at = models.DateTimeField()
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["expires_at", "verified_at"], name="booking_otp_exp_idx"),
        ]

    def __str__(self):
        return f"Completion OTP for booking #{self.booking_id}"


class RecurringWashPlan(TimeStampedModel):
    """Customer's quoted recurring car-wash agreement, linked to its inspection order."""

    class Frequency(models.TextChoices):
        DAILY = "daily", "Daily"
        ALTERNATE_DAY = "alternate_day", "Alternate day"
        TWICE_WEEKLY = "twice_weekly", "Twice a week"
        WEEKLY = "weekly", "Weekly"
        FORTNIGHTLY = "fortnightly", "Fortnightly"

    class Status(models.TextChoices):
        AWAITING_QUOTE = "awaiting_quote", "Awaiting quote"
        AWAITING_PAYMENT = "awaiting_payment", "Awaiting payment"
        PAID_PENDING_SETUP = "paid_pending_setup", "Paid - schedule setup pending"
        ACTIVE = "active", "Active"
        PAUSED = "paused", "Paused"
        CANCELLED = "cancelled", "Cancelled"
        COMPLETED = "completed", "Completed"

    class TimeWindow(models.TextChoices):
        MORNING = "Morning", "Morning"
        AFTERNOON = "Afternoon", "Afternoon"
        EVENING = "Evening", "Evening"

    order = models.OneToOneField(
        Order, on_delete=models.PROTECT, related_name="recurring_wash_plan"
    )
    source_booking = models.OneToOneField(
        Booking, on_delete=models.PROTECT, related_name="recurring_wash_plan"
    )
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="recurring_wash_plans",
    )
    address = models.ForeignKey(
        Address, on_delete=models.PROTECT, related_name="recurring_wash_plans"
    )
    service = models.ForeignKey(
        Service, on_delete=models.PROTECT, related_name="recurring_wash_plans"
    )
    variant = models.ForeignKey(
        ServiceVariant, on_delete=models.PROTECT, null=True, blank=True,
        related_name="recurring_wash_plans",
    )
    frequency = models.CharField(max_length=20, choices=Frequency.choices)
    duration_days = models.PositiveSmallIntegerField()
    starts_on = models.DateField()
    ends_on = models.DateField()
    preferred_time_window = models.CharField(
        max_length=12, choices=TimeWindow.choices, blank=True
    )
    vehicle_type = models.CharField(max_length=40)
    vehicle_quantity = models.PositiveSmallIntegerField(default=1)
    quoted_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(
        max_length=20, choices=Status.choices,
        default=Status.AWAITING_QUOTE, db_index=True,
    )
    plan_snapshot = models.JSONField(default=dict, blank=True)
    quote_accepted_at = models.DateTimeField(null=True, blank=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    paused_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    admin_notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "starts_on"], name="wash_plan_status_start_idx"),
            models.Index(fields=["customer", "status"], name="wash_plan_customer_status_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(vehicle_quantity__gte=1),
                name="wash_plan_vehicle_qty_gte_1",
            ),
            models.CheckConstraint(
                condition=models.Q(ends_on__gte=models.F("starts_on")),
                name="wash_plan_end_after_start",
            ),
        ]

    def __str__(self):
        return f"Recurring wash plan #{self.pk} for order #{self.order_id}"


class RecurringWashVisit(TimeStampedModel):
    """One prepaid occurrence in a recurring wash plan's visit ledger."""

    class Status(models.TextChoices):
        PENDING_SETUP = "pending_setup", "Pending booking setup"
        BOOKED = "booked", "Booking created"
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"
        SKIPPED = "skipped", "Skipped"

    plan = models.ForeignKey(
        RecurringWashPlan, on_delete=models.PROTECT, related_name="visits"
    )
    visit_number = models.PositiveSmallIntegerField()
    scheduled_at = models.DateTimeField(db_index=True)
    booking = models.OneToOneField(
        Booking, on_delete=models.PROTECT, null=True, blank=True,
        related_name="recurring_wash_visit",
    )
    prepaid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(
        max_length=20, choices=Status.choices,
        default=Status.PENDING_SETUP, db_index=True,
    )
    admin_notes = models.TextField(blank=True)

    class Meta:
        ordering = ["scheduled_at", "visit_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["plan", "visit_number"],
                name="unique_wash_plan_visit_number",
            ),
            models.UniqueConstraint(
                fields=["plan", "scheduled_at"],
                name="unique_wash_plan_visit_time",
            ),
            models.CheckConstraint(
                condition=models.Q(visit_number__gte=1),
                name="wash_visit_number_gte_1",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "scheduled_at"], name="wash_visit_status_time_idx"),
        ]

    def __str__(self):
        return f"Plan #{self.plan_id} visit {self.visit_number} ({self.status})"
