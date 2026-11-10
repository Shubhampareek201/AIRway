from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel


class Notification(TimeStampedModel):
    class Type(models.TextChoices):
        BOOKING_CONFIRMED = "booking_confirmed", "Booking Confirmed"
        BOOKING_ASSIGNED = "booking_assigned", "Worker Assigned"
        WORKER_UNAVAILABLE = "worker_unavailable", "Worker Unavailable"
        BOOKING_STARTED = "booking_started", "Service Started"
        BOOKING_COMPLETED = "booking_completed", "Service Completed"
        BOOKING_CANCELLED = "booking_cancelled", "Booking Cancelled"
        BOOKING_OFFERS_EXPIRED = "booking_offers_expired", "Offers Expired"
        PAYMENT_SUCCESS = "payment_success", "Payment Success"
        FINAL_PAYMENT_DUE = "final_payment_due", "Final Payment Due"
        PAYMENT_TIMEOUT = "payment_timeout", "Payment Timeout"
        WALLET_CREDIT = "wallet_credit", "Wallet Credited"
        REFERRAL_REWARD = "referral_reward", "Referral Reward"
        WORKER_BONUS = "worker_bonus", "Worker Bonus"
        SYSTEM_ANNOUNCEMENT = "system_announcement", "System Announcement"
        WORKER_OFFER = "worker_offer", "Job Offer"
        WORKER_OFFER_WITHDRAWN = "worker_offer_withdrawn", "Offer Withdrawn"
        WORKER_OFFER_EXPIRED = "worker_offer_expired", "Offer Expired"
        WORKER_APPLICATION_SUBMITTED = "worker_application_submitted", "Worker Application Submitted"
        WORKER_APPLICATION_APPROVED = "worker_application_approved", "Worker Application Approved"
        WORKER_APPLICATION_REJECTED = "worker_application_rejected", "Worker Application Rejected"

    class Channel(models.TextChoices):
        IN_APP = "in_app", "In-App"
        PUSH = "push", "Push Notification"
        SMS = "sms", "SMS"
        EMAIL = "email", "Email"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    type = models.CharField(max_length=30, choices=Type.choices)
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    channel = models.CharField(max_length=20, choices=Channel.choices, default=Channel.IN_APP)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    data = models.JSONField(default=dict, blank=True, help_text="Extra payload: booking_id, worker_id, etc.")

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "is_read"]),
        ]

    def __str__(self):
        return f"{self.user.phone} - {self.title}"

    def mark_read(self):
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save()