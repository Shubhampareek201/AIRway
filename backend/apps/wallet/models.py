from django.conf import settings
from django.db import models
from simple_history.models import HistoricalRecords

from apps.core.models import TimeStampedModel


class Wallet(TimeStampedModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="wallet",
    )
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    pending_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.phone} - ₹{self.balance}"

    def deposit(self, amount, description=""):
        WalletTransaction.objects.create(
            wallet=self,
            type=WalletTransaction.Type.CREDIT,
            amount=amount,
            description=description,
        )
        self.balance += amount
        self.save()

    def debit(self, amount, description=""):
        WalletTransaction.objects.create(
            wallet=self,
            type=WalletTransaction.Type.DEBIT,
            amount=amount,
            description=description,
        )
        self.balance -= amount
        self.save()


class WalletTransaction(TimeStampedModel):
    class Type(models.TextChoices):
        CREDIT = "credit", "Credit"
        DEBIT = "debit", "Debit"
        REFUND = "refund", "Refund"
        CASHBACK = "cashback", "Cashback"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    wallet = models.ForeignKey(
        Wallet,
        on_delete=models.CASCADE,
        related_name="transactions",
    )
    type = models.CharField(max_length=20, choices=Type.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.COMPLETED)
    reference_id = models.CharField(max_length=100, blank=True, help_text="Booking ID / Razorpay order ID / Referral reward ID")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.wallet.user.phone} - {self.type} - ₹{self.amount}"