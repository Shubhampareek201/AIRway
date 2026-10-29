from rest_framework import serializers
from .models import Payment

class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ["id", "booking", "amount", "method", "status", "razorpay_order_id", "paid_at"]
        read_only_fields = ["status", "razorpay_order_id", "paid_at"]

class RazorpayOrderSerializer(serializers.Serializer):
    booking_id = serializers.IntegerField()
