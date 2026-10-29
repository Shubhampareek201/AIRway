import razorpay
from django.conf import settings
from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.bookings.models import Booking
from .models import Payment

client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))

class CreateOrderView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        booking_id = request.data.get("booking_id")
        booking = get_object_or_404(Booking, pk=booking_id, customer=request.user)

        if booking.status != Booking.Status.PENDING:
            return Response({"detail": "Booking cannot be paid for in its current status."}, status=status.HTTP_400_BAD_REQUEST)

        amount = int(float(booking.total_amount) * 100) # Razorpay expects paise

        order_data = {
            "amount": amount,
            "currency": "INR",
            "receipt": f"booking_{booking.id}",
        }
        order = client.order.create(data=order_data)

        payment, _ = Payment.objects.update_or_create(
            booking=booking,
            defaults={
                "customer": request.user,
                "amount": booking.total_amount,
                "method": Payment.Method.RAZORPAY,
                "razorpay_order_id": order["id"],
            }
        )

        return Response({"order_id": order["id"], "amount": amount})
