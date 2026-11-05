import razorpay
import logging
from django.conf import settings
from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db import transaction, IntegrityError

from apps.bookings.models import Booking
from .models import Payment

logger = logging.getLogger(__name__)

client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


def create_or_get_payment(booking, customer, trigger_source="api"):
    """
    Create or retrieve an existing Payment record with Razorpay order.

    This function is idempotent - if a payment already exists for the booking,
    it returns the existing payment/order. If Razorpay order creation fails,
    raises an exception.

    This function should be called OUTSIDE of a database transaction to avoid
    long-running transactions that include network calls to Razorpay.

    Args:
        booking: Booking instance (must be ASSIGNED or PENDING status)
        customer: User instance (the booking customer)
        trigger_source: String indicating what triggered the payment creation
                       (e.g., "worker_accept", "checkout", "webhook")

    Returns:
        tuple: (Payment instance, razorpay_order_id, already_existed boolean)

    Raises:
        ValueError: If booking status is not PENDING or ASSIGNED
        Exception: If Razorpay order creation fails
    """
    if booking.status not in [Booking.Status.PENDING, Booking.Status.ASSIGNED]:
        raise ValueError(
            f"Booking cannot have payment created in {booking.get_status_display()} state."
        )

    # Try to get existing payment first (fast path)
    try:
        existing_payment = Payment.objects.get(booking=booking)
        if existing_payment.razorpay_order_id:
            logger.info(
                f"Payment already exists for booking {booking.id}: "
                f"payment_id={existing_payment.id}, order_id={existing_payment.razorpay_order_id}"
            )
            return existing_payment, existing_payment.razorpay_order_id, True
        # Payment exists but no order ID - need to create
    except Payment.DoesNotExist:
        existing_payment = None

    # Create Razorpay order OUTSIDE of any transaction
    amount_paise = int(float(booking.total_amount) * 100)

    try:
        order_data = {
            "amount": amount_paise,
            "currency": "INR",
            "receipt": f"booking_{booking.id}_{timezone.now().strftime('%Y%m%d%H%M%S')}",
        }
        razorpay_order = client.order.create(data=order_data)
        razorpay_order_id = razorpay_order["id"]
    except Exception as e:
        logger.error(
            f"Failed to create Razorpay order for booking {booking.id}: {e}"
        )
        raise

    # Now create the Payment record in a transaction to handle race conditions
    try:
        with transaction.atomic():
            payment = Payment.objects.create(
                booking=booking,
                customer=customer,
                amount=booking.total_amount,
                method=Payment.Method.RAZORPAY,
                razorpay_order_id=razorpay_order_id,
                status=Payment.Status.PENDING,
            )
    except IntegrityError:
        # Race condition: another request created payment first
        # Fetch the existing payment
        payment = Payment.objects.get(booking=booking)
        if payment.razorpay_order_id:
            # Another request already has an order
            logger.info(f"Payment already created by concurrent request for booking {booking.id}")
            return payment, payment.razorpay_order_id, True
        else:
            # This payment was created without an order (shouldn't happen)
            # Use the order we just created
            payment.razorpay_order_id = razorpay_order_id
            payment.save(update_fields=["razorpay_order_id"])

    logger.info(
        f"Created Razorpay order for booking {booking.id}: "
        f"order_id={razorpay_order_id}, payment_id={payment.id}, trigger={trigger_source}"
    )

    return payment, razorpay_order_id, False


class CreateOrderView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        booking_id = request.data.get("booking_id")
        if not booking_id:
            return Response(
                {"detail": "booking_id is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate booking in transaction
        with transaction.atomic():
            try:
                booking = Booking.objects.select_for_update().get(
                    pk=booking_id,
                    customer=request.user
                )
            except Booking.DoesNotExist:
                return Response(
                    {"detail": "Booking not found or access denied."},
                    status=status.HTTP_404_NOT_FOUND
                )

        # Create payment OUTSIDE transaction (Razorpay API call)
        try:
            payment, order_id, already_existed = create_or_get_payment(
                booking=booking,
                customer=request.user,
                trigger_source="checkout"
            )
        except ValueError as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Payment creation failed: {e}")
            return Response(
                {"detail": "Failed to create payment order. Please try again."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        amount_paise = int(float(booking.total_amount) * 100)

        if already_existed:
            return Response({
                "order_id": order_id,
                "amount": amount_paise,
                "payment_exists": True,
            })

        return Response({"order_id": order_id, "amount": amount_paise})
