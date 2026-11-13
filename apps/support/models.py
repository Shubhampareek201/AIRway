from django.conf import settings
from django.db import models

class SupportTicket(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        IN_PROGRESS = "in_progress", "In Progress"
        WAITING_CUSTOMER = "waiting_customer", "Waiting for Customer"
        RESOLVED = "resolved", "Resolved"
        CLOSED = "closed", "Closed"
    class Category(models.TextChoices):
        PAYMENT = "payment", "Payment and Refund"
        BOOKING = "booking", "Booking Problem"
        SERVICE = "service", "Service Quality"
        ACCOUNT = "account", "Account and Profile"
        SAFETY = "safety", "Safety Concern"
        WORKER = "worker", "Worker or Customer Issue"
        OTHER = "other", "Other"
    ticket_number = models.CharField(max_length=20, unique=True, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="support_tickets")
    category = models.CharField(max_length=20, choices=Category.choices)
    subject = models.CharField(max_length=160)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.OPEN, db_index=True)
    booking_id = models.PositiveBigIntegerField(null=True, blank=True, db_index=True)
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_support_tickets")
    last_message_at = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ["-last_message_at", "-pk"]
        indexes = [models.Index(fields=["status", "last_message_at"]), models.Index(fields=["user", "status"])]
    def save(self, *args, **kwargs):
        if not self.ticket_number:
            super().save(*args, **kwargs)
            self.ticket_number = f"AW-{self.created_at:%y%m}-{self.pk:06d}"
            return super().save(update_fields=["ticket_number"])
        return super().save(*args, **kwargs)
    def __str__(self):
        return f"{self.ticket_number} - {self.subject}"

class SupportMessage(models.Model):
    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="support_messages")
    message = models.TextField(max_length=5000)
    attachment = models.FileField(upload_to="support/%Y/%m/", null=True, blank=True)
    is_internal_note = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["created_at", "pk"]
