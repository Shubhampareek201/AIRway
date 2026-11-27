from django.conf import settings
from django.db import models
from django.db.models import F, Q, Sum
import uuid
from simple_history.models import HistoricalRecords

from apps.catalog.models import Service, ServiceVariant, AddOn, FormField
from apps.core.models import TimeStampedModel
from apps.accounts.models import Address
from apps.core.models import Zone


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
        help_text="Appointment grouping for multi-service orders; null for legacy standalone bookings.",
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
        help_text="Customer-facing immutable price snapshot: variant/addon prices, subtotal, tax and total.",
    )
    worker_payout_snapshot = models.JSONField(
        default=dict,
        blank=True,
        help_text="Private immutable worker payout and required-material snapshot; never expose through customer serializers.",
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


class BookingExtraWork(TimeStampedModel):
    """Immutable worker proposal for additional work during an active appointment."""

    class Status(models.TextChoices):
        PENDING_CUSTOMER = "pending_customer", "Awaiting customer decision"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        EXPIRED = "expired", "Expired"
        CANCELLED = "cancelled", "Cancelled"

    class PaymentChoice(models.TextChoices):
        SEPARATE = "separate", "Separate payment"
        ADD_TO_BALANCE = "add_to_balance", "Add to appointment balance"

    request_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    booking = models.ForeignKey(
        Booking, on_delete=models.PROTECT, related_name="extra_work_requests"
    )
    appointment_group = models.ForeignKey(
        "AppointmentGroup", on_delete=models.PROTECT, null=True, blank=True,
        related_name="extra_work_requests",
    )
    worker = models.ForeignKey(
        "workers.WorkerProfile", on_delete=models.PROTECT,
        related_name="extra_work_requests",
    )
    reason = models.CharField(max_length=500)
    line_items = models.JSONField(
        default=list,
        help_text="Immutable item snapshot: description, quantity, unit price and line total.",
    )
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    worker_payout_amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Worker's immutable payout snapshot for this customer-approved extra-work scope.",
    )
    worker_payout_snapshot = models.JSONField(
        default=dict, blank=True,
        help_text="Calculation inputs captured when the extra-work proposal was created.",
    )
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    additional_duration_minutes = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(
        max_length=24, choices=Status.choices,
        default=Status.PENDING_CUSTOMER, db_index=True,
    )
    payment_choice = models.CharField(
        max_length=24, choices=PaymentChoice.choices, blank=True,
    )
    payment_status = models.CharField(
        max_length=16,
        choices=[("not_due", "Not due"), ("pending", "Pending payment"), ("paid", "Paid")],
        default="not_due",
        db_index=True,
    )
    customer_response_note = models.CharField(max_length=1000, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["booking", "status"]),
            models.Index(fields=["appointment_group", "status"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(subtotal__gt=0),
                name="extra_work_subtotal_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(total_amount__gt=0),
                name="extra_work_total_positive",
            ),
            models.UniqueConstraint(
                fields=["booking"],
                condition=models.Q(status="pending_customer"),
                name="one_pending_extra_work_per_booking",
            ),
        ]

    def __str__(self):
        return f"Extra work #{self.pk} for booking #{self.booking_id} ({self.status})"


class BookingQuote(TimeStampedModel):
    """Worker-submitted inspection estimate requiring explicit customer approval."""

    class Status(models.TextChoices):
        PENDING_ADMIN = "pending_admin", "Awaiting AIRway payout approval"
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
    worker_payout_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    payout_approval_note = models.TextField(blank=True)
    payout_approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="approved_booking_quote_payouts")
    payout_approved_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.PENDING_CUSTOMER, db_index=True)
    customer_response_note = models.TextField(blank=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    repair_started_at = models.DateTimeField(null=True, blank=True, help_text="Set only after the customer has paid the accepted inspection estimate.")

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
    location_sharing_enabled = models.BooleanField(
        default=False,
        help_text="Worker-controlled permission to share foreground GPS with the customer during the 30-minute pre-appointment window and active job.",
    )
    arrival_requested_at = models.DateTimeField(null=True, blank=True)
    arrival_verified_at = models.DateTimeField(null=True, blank=True)
    arrival_otp_hash = models.CharField(max_length=256, blank=True)
    arrival_otp_expires_at = models.DateTimeField(null=True, blank=True)
    arrival_otp_attempts = models.PositiveSmallIntegerField(default=0)
    arrival_otp_last_sent_at = models.DateTimeField(null=True, blank=True)

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
    appointment_group = models.ForeignKey(
        "AppointmentGroup",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="worker_offers",
        help_text="Set for a single-worker offer covering every service in one appointment group.",
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
            models.UniqueConstraint(
                fields=["appointment_group", "worker"],
                condition=Q(appointment_group__isnull=False),
                name="unique_group_offer_worker",
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



class CustomerCampaign(TimeStampedModel):
    """Admin-managed customer discount campaign; budget counters are reserved atomically at checkout."""
    class BookingSequence(models.TextChoices):
        FIRST = "first", "First paid booking"
        SECOND = "second", "Second paid booking"
        ANY = "any", "Any eligible paid booking"
    class DiscountType(models.TextChoices):
        FIXED = "fixed", "Fixed amount"
        PERCENTAGE = "percentage", "Percentage"
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=False)
    booking_sequence = models.CharField(max_length=12, choices=BookingSequence.choices, default=BookingSequence.ANY)
    discount_type = models.CharField(max_length=12, choices=DiscountType.choices, default=DiscountType.FIXED)
    discount_value = models.DecimalField(max_digits=10, decimal_places=2)
    max_discount_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    minimum_subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    budget_amount = models.DecimalField(max_digits=14, decimal_places=2)
    budget_reserved = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    budget_spent = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    max_redemptions_per_customer = models.PositiveIntegerField(default=1)
    max_total_redemptions = models.PositiveIntegerField(null=True, blank=True)
    allow_stacking = models.BooleanField(default=False)
    priority = models.PositiveIntegerField(default=100)
    eligible_services = models.ManyToManyField(Service, blank=True, related_name="discount_campaigns")
    eligible_zones = models.ManyToManyField(Zone, blank=True, related_name="discount_campaigns")
    class Meta:
        ordering = ["priority", "-created_at"]
        constraints = [
            models.CheckConstraint(condition=Q(discount_value__gt=0), name="campaign_discount_value_positive"),
            models.CheckConstraint(condition=Q(minimum_subtotal__gte=0), name="campaign_min_subtotal_nonneg"),
            models.CheckConstraint(condition=Q(budget_amount__gt=0), name="campaign_budget_positive"),
            models.CheckConstraint(condition=Q(budget_reserved__gte=0) & Q(budget_spent__gte=0), name="campaign_budget_counters_nonneg"),
            models.CheckConstraint(condition=Q(budget_reserved__lte=F("budget_amount") - F("budget_spent")), name="campaign_budget_within_limit"),
            models.CheckConstraint(condition=Q(max_discount_amount__isnull=True) | Q(max_discount_amount__gt=0), name="campaign_discount_cap_positive"),
            models.CheckConstraint(condition=Q(max_redemptions_per_customer__gte=1), name="campaign_customer_limit_positive"),
            models.CheckConstraint(condition=Q(max_total_redemptions__isnull=True) | Q(max_total_redemptions__gte=1), name="campaign_total_limit_positive"),
        ]
    def clean(self):
        super().clean()
        from django.core.exceptions import ValidationError
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValidationError({"ends_at": "End time must be after the start time."})
        if self.discount_type == self.DiscountType.PERCENTAGE and self.discount_value > 100:
            raise ValidationError({"discount_value": "Percentage discount cannot exceed 100%."})
        if self.budget_amount is not None and self.budget_reserved + self.budget_spent > self.budget_amount:
            raise ValidationError("Reserved plus spent campaign budget cannot exceed the campaign budget.")
    @property
    def remaining_budget(self):
        return self.budget_amount - self.budget_reserved - self.budget_spent
    def __str__(self):
        return self.name


class CampaignRedemption(TimeStampedModel):
    """Order-level campaign claim with a retained reservation/redemption audit trail."""
    class Status(models.TextChoices):
        RESERVED = "reserved", "Reserved"
        REDEEMED = "redeemed", "Redeemed"
        RELEASED = "released", "Released"
        REFUNDED = "refunded", "Refunded"
    campaign = models.ForeignKey(CustomerCampaign, on_delete=models.PROTECT, related_name="redemptions")
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="campaign_redemptions")
    order = models.ForeignKey("Order", on_delete=models.PROTECT, related_name="campaign_redemptions")
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.RESERVED, db_index=True)
    reserved_at = models.DateTimeField(auto_now_add=True)
    redeemed_at = models.DateTimeField(null=True, blank=True)
    released_at = models.DateTimeField(null=True, blank=True)
    release_reason = models.CharField(max_length=160, blank=True)
    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["campaign", "order"], name="unique_campaign_redemption_per_order"),
            models.CheckConstraint(condition=Q(discount_amount__gt=0), name="campaign_redemption_amount_positive"),
        ]
    def __str__(self):
        return f"{self.campaign} / Order #{self.order_id} / ₹{self.discount_amount} ({self.status})"


class AppointmentGroup(TimeStampedModel):
    """A customer-facing appointment containing one or more compatible services."""

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="appointment_groups",
    )
    group_number = models.PositiveSmallIntegerField()
    scheduled_at = models.DateTimeField()
    customer_message = models.CharField(
        max_length=500,
        blank=True,
        help_text="One optional message shared with the worker handling this appointment.",
    )

    class Meta:
        ordering = ["group_number", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["order", "group_number"],
                name="unique_order_appointment_group_number",
            ),
        ]

    def __str__(self):
        return f"Order #{self.order_id} - Appointment {self.group_number}"



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
    offer_expiry_minutes = models.PositiveSmallIntegerField(default=30)
    late_cancellation_window_hours = models.PositiveSmallIntegerField(
        default=0,
        help_text="Hours before the appointment when the late-cancellation fee applies. Zero disables the fee.",
    )
    late_cancellation_fee_percent = models.PositiveSmallIntegerField(
        default=30,
        help_text="Percentage retained from the captured advance payment for late customer cancellations.",
    )
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


class BookingDispute(TimeStampedModel):
    """Auditable customer/worker case linked to one service booking."""

    class Category(models.TextChoices):
        SERVICE_QUALITY = "service_quality", "Service quality"
        DAMAGE = "damage", "Property or item damage"
        PAYMENT = "payment", "Payment or refund"
        WORKER_CONDUCT = "worker_conduct", "Professional conduct"
        CUSTOMER_CONDUCT = "customer_conduct", "Customer conduct"
        SAFETY = "safety", "Safety concern"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        IN_REVIEW = "in_review", "In review"
        RESOLVED = "resolved", "Resolved"
        REJECTED = "rejected", "Rejected"
        CLOSED = "closed", "Closed"

    class RequestedOutcome(models.TextChoices):
        REFUND_REVIEW = "refund_review", "Refund review"
        REWORK = "rework", "Rework or service recovery"
        INVESTIGATION = "investigation", "Investigation"
        OTHER = "other", "Other"

    booking = models.ForeignKey(Booking, on_delete=models.PROTECT, related_name="disputes")
    raised_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="raised_booking_disputes"
    )
    raised_by_role = models.CharField(max_length=12, choices=[("customer", "Customer"), ("worker", "Worker")])
    category = models.CharField(max_length=24, choices=Category.choices)
    description = models.TextField(max_length=5000)
    requested_outcome = models.CharField(max_length=24, choices=RequestedOutcome.choices)
    evidence_items = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN, db_index=True)
    resolution_note = models.TextField(blank=True, max_length=5000)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="resolved_booking_disputes",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "created_at"], name="booking_dispute_status_idx")]
        constraints = [
            models.UniqueConstraint(
                fields=["booking"],
                condition=models.Q(status__in=["open", "in_review"]),
                name="one_active_dispute_per_booking",
            ),
        ]

    def __str__(self):
        return f"Dispute #{self.pk} for booking #{self.booking_id} ({self.status})"


class BookingDisputeHistory(TimeStampedModel):
    """Append-only audit trail for every dispute status transition."""

    dispute = models.ForeignKey(
        BookingDispute, on_delete=models.PROTECT, related_name="status_history"
    )
    from_status = models.CharField(max_length=16, blank=True)
    to_status = models.CharField(max_length=16, choices=BookingDispute.Status.choices)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="booking_dispute_status_changes",
    )
    note = models.TextField(blank=True, max_length=5000)

    class Meta:
        ordering = ["created_at", "pk"]

    def __str__(self):
        return f"Dispute #{self.dispute_id}: {self.from_status or 'created'} → {self.to_status}"


class BookingDisputeEvidence(TimeStampedModel):
    """Private evidence file attached to a booking dispute."""

    dispute = models.ForeignKey(
        BookingDispute, on_delete=models.PROTECT, related_name="evidence"
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="uploaded_dispute_evidence",
    )
    file_path = models.CharField(max_length=500)
    original_name = models.CharField(max_length=255, blank=True)
    note = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"Evidence #{self.pk} for dispute #{self.dispute_id}"


class BookingReworkProposal(TimeStampedModel):
    """Admin-approved, no-charge follow-up visit offered to a customer after a rework dispute."""

    class Status(models.TextChoices):
        PENDING_CUSTOMER = "pending_customer", "Awaiting customer decision"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"
        EXPIRED = "expired", "Expired"
        CANCELLED = "cancelled", "Cancelled by customer"

    dispute = models.ForeignKey(
        BookingDispute, on_delete=models.PROTECT, related_name="rework_proposals"
    )
    worker = models.ForeignKey(
        "workers.WorkerProfile", on_delete=models.PROTECT, related_name="rework_proposals"
    )
    scheduled_at = models.DateTimeField()
    status = models.CharField(
        max_length=24, choices=Status.choices,
        default=Status.PENDING_CUSTOMER, db_index=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="created_booking_rework_proposals",
    )
    responded_at = models.DateTimeField(null=True, blank=True)
    followup_booking = models.OneToOneField(
        Booking, on_delete=models.PROTECT, null=True, blank=True,
        related_name="rework_source",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "scheduled_at"], name="rework_status_slot_idx")]
        constraints = [
            models.UniqueConstraint(
                fields=["dispute"],
                condition=models.Q(status="pending_customer"),
                name="one_pending_rework_proposal_per_dispute",
            ),
        ]

    def __str__(self):
        return f"Rework proposal for dispute #{self.dispute_id} ({self.status})"



class BookingVariableCost(TimeStampedModel):
    """Append-only, booking-attributed variable operating expense."""
    class Category(models.TextChoices):
        TRAVEL = "travel", "Travel"
        MATERIALS = "materials", "Materials"
        PAYMENT = "payment", "Payment processing"
        SUPPORT = "support", "Customer support"
        REWORK = "rework", "Rework / service recovery"
        OTHER = "other", "Other"

    booking = models.ForeignKey(Booking, on_delete=models.PROTECT, related_name="variable_costs")
    category = models.CharField(max_length=20, choices=Category.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.CharField(max_length=500)
    reference = models.CharField(max_length=120, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="recorded_booking_variable_costs")

    class Meta:
        ordering = ["created_at", "pk"]
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name="booking_variable_cost_positive")]

    def __str__(self):
        return f"{self.get_category_display()} ₹{self.amount} for booking #{self.booking_id}"


class BookingFinanceReconciliation(TimeStampedModel):
    """Finance review confirming that all other variable costs were considered."""
    booking = models.OneToOneField(Booking, on_delete=models.PROTECT, related_name="finance_reconciliation")
    other_costs_reviewed = models.BooleanField(default=False)
    review_note = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="booking_finance_reviews")
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"Finance reconciliation for booking #{self.booking_id}"
