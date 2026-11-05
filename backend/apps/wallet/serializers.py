from decimal import Decimal, InvalidOperation

from rest_framework import serializers
from .models import Wallet, WalletTransaction


def parse_amount(value):
    """Convert request amount to Decimal, or None if invalid."""
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


class WalletTransactionSerializer(serializers.ModelSerializer):
    type_display = serializers.CharField(source="get_type_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = WalletTransaction
        fields = [
            "id",
            "type",
            "type_display",
            "amount",
            "description",
            "status",
            "status_display",
            "reference_id",
            "created_at",
        ]
        read_only_fields = ["id", "created_at", "type_display", "status_display"]


class WalletSerializer(serializers.ModelSerializer):
    transactions = serializers.SerializerMethodField()
    pending_balance = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )

    class Meta:
        model = Wallet
        fields = [
            "id",
            "balance",
            "pending_balance",
            "transactions",
            "created_at",
        ]
        read_only_fields = ["id", "balance", "created_at"]

    def get_transactions(self, obj):
        qs = obj.transactions.all().order_by("-created_at")[:20]
        return WalletTransactionSerializer(qs, many=True, context=self.context).data