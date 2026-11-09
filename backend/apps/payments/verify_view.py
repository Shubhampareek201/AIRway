import hmac
import hashlib
import json
import logging
from decimal import Decimal
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from apps.bookings.models import Booking, BookingStatusHistory, Order
from apps.notifications.models import Notification
from .models import Payment

logger = logging.getLogger(__name__)


def _refund_late_capture_for_cancelled_booking(
    payment, razorpay_payment_id, razorpay_order_id, source,
):
    """Refund a captured advance if its booking was cancelled before capture arrived."""
    if not payment.booking_id:
        return None

    from .models import RefundRecord
    with transaction.atomic():
        # Keep the same booking -> payment lock order as customer cancellation.
        booking = Booking.objects.select_for_update().filter(
            pk=payment.booking_id,
        ).first()
        locked_payment = Payment.objects.select_for_update().get(pk=payment.pk)
        if locked_payment.status in (Payment.Status.PAID, Payment.Status.REFUNDED):
            return Response({
                "detail": "Payment already settled.",
                "status": locked_payment.status,
                "payment_id": locked_payment.pk,
            })
        if booking is None or booking.status != Booking.Status.CANCELLED:
            return None

        now = timezone.now()
        locked_payment.status = Payment.Status.PAID
        locked_payment.razorpay_payment_id = razorpay_payment_id
        locked_payment.razorpay_signature = "verified"
        locked_payment.paid_at = now
        locked_payment.raw_response = {
            "razorpay_order_id": razorpay_order_id,
            "razorpay_payment_id": razorpay_payment_id,
            "captured_after_booking_cancellation": True,
            "source": source,
            "captured_at": now.isoformat(),
        }
        locked_payment.save(update_fields=[
            "status", "razorpay_payment_id", "razorpay_signature",
            "paid_at", "raw_response", "updated_at",
        ])
        refund_record, created = RefundRecord.objects.get_or_create(
            idempotency_key=f"late-capture-cancelled-booking:{locked_payment.pk}:{razorpay_payment_id}",
            defaults={
                "booking": booking,
                "payment": locked_payment,
                "reason": RefundRecord.Reason.PAYMENT_RECONCILIATION,
                "gross_amount": locked_payment.amount,
                "platform_fee": Decimal("0.00"),
                "refund_amount": locked_payment.amount,
                "gateway_refund_amount": locked_payment.amount,
                "wallet_refund_amount": Decimal("0.00"),
                "status": (
                    RefundRecord.Status.REQUESTED
                    if locked_payment.amount > 0
                    else RefundRecord.Status.PROCESSED
                ),
                "requested_at": now,
                "processed_at": now if locked_payment.amount <= 0 else None,
                "provider_payload": {
                    "reason": "Razorpay capture arrived after customer cancellation.",
                },
            },
        )

    if not created or refund_record.refund_amount <= 0:
        return Response({
            "detail": "Late payment was reconciled against the cancelled booking.",
            "status": Payment.Status.PAID,
            "payment_id": payment.pk,
            "refund_id": refund_record.pk,
            "refund_status": refund_record.status,
        }, status=status.HTTP_200_OK)

    try:
        if not razorpay_payment_id:
            raise ValueError("Captured payment has no Razorpay payment ID.")
        import razorpay
        gateway = razorpay.Client(
            auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
        )
        provider_refund = gateway.payment.refund(
            razorpay_payment_id,
            {
                "amount": int(refund_record.refund_amount * 100),
                "notes": {
                    "airway_refund_record_id": str(refund_record.pk),
                    "airway_booking_id": str(booking.pk),
                    "reason": "Late capture after booking cancellation",
                },
            },
        )
        if not provider_refund.get("id"):
            raise ValueError("Razorpay did not return a refund ID.")
        from .installment_service import _persist_refund_submission
        refund_record = _persist_refund_submission(
            record_id=refund_record.pk,
            provider_refund=provider_refund,
        )
    except Exception as exc:
        logger.exception(
            "Late-capture refund submission failed for cancelled booking %s",
            booking.pk,
        )
        from .installment_service import _persist_refund_submission
        refund_record = _persist_refund_submission(
            record_id=refund_record.pk,
            submission_error=exc,
        )
    return Response({
        "detail": "Payment was captured after the booking was cancelled; AIRway initiated full reconciliation refund.",
        "status": Payment.Status.PAID,
        "payment_id": payment.pk,
        "refund_id": refund_record.pk,
        "refund_status": refund_record.status,
    }, status=status.HTTP_200_OK)


def _process_verified_payment(
    payment, razorpay_payment_id, razorpay_order_id, customer, source
):
    """
    Process a verified payment. Called by both checkout verification
    and webhook handlers.
    """
    late_capture_response = _refund_late_capture_for_cancelled_booking(
        payment, razorpay_payment_id, razorpay_order_id, source,
    )
    if late_capture_response is not None:
        return late_capture_response

    # Idempotency check: skip if already processed
    if payment.status in [Payment.Status.PAID, Payment.Status.REFUNDED]:
        logger.info(
            "Payment %s already settled with status %s; skipping re-process",
            payment.id, payment.status,
        )
        return Response({
            "detail": "Payment already settled.",
            "status": payment.status,
            "payment_id": payment.id,
        })

    with transaction.atomic():
        payment = Payment.objects.select_for_update().get(pk=payment.pk)
        if payment.status in [Payment.Status.PAID, Payment.Status.REFUNDED]:
            return Response({
                "detail": "Payment already settled.",
                "status": payment.status,
                "payment_id": payment.id,
            })

        if payment.order_id and payment.wallet_amount > 0:
            from apps.wallet.services import capture_wallet_reservation

            try:
                captured_reservation = capture_wallet_reservation(
                    payment,
                    razorpay_payment_id=razorpay_payment_id,
                )
                if (
                    captured_reservation is None
                    or captured_reservation.status != "captured"
                ):
                    raise ValueError("Wallet reservation is missing or not captured.")
            except ValueError as exc:
                logger.error(
                    "Cannot settle wallet component for payment %s: %s",
                    payment.id, exc,
                )
                # Razorpay has already captured the external component, but
                # the released wallet funds may no longer be available. Refund
                # the captured gateway amount rather than marking an underpaid
                # order as paid.
                if not razorpay_payment_id or payment.amount <= 0:
                    return Response(
                        {
                            "detail": "Wallet funds are unavailable for payment reconciliation.",
                            "status": payment.status,
                            "payment_id": payment.id,
                        },
                        status=status.HTTP_409_CONFLICT,
                    )
                try:
                    import razorpay

                    gateway = razorpay.Client(
                        auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
                    )
                    gateway_payment = gateway.payment.fetch(razorpay_payment_id)
                    expected_refund_paise = int(payment.amount * 100)
                    already_refunded_paise = int(gateway_payment.get("amount_refunded", 0))
                    remaining_refund_paise = expected_refund_paise - already_refunded_paise
                    if remaining_refund_paise > 0:
                        refund = gateway.payment.refund(
                            razorpay_payment_id,
                            {
                                "amount": remaining_refund_paise,
                                "notes": {
                                    "airway_payment_id": str(payment.id),
                                    "reason": "Wallet reservation expired before payment capture",
                                },
                            },
                        )
                    else:
                        refund = {"status": "already_refunded"}
                except Exception:
                    logger.exception(
                        "Automatic Razorpay refund failed for late payment %s",
                        payment.id,
                    )
                    return Response(
                        {
                            "detail": "Payment was captured but automatic refund could not be confirmed. AIRway support will reconcile it.",
                            "status": payment.status,
                            "payment_id": payment.id,
                        },
                        status=status.HTTP_502_BAD_GATEWAY,
                    )

                payment.status = Payment.Status.REFUNDED
                payment.failed_at = timezone.now()
                payment.raw_response = {
                    "razorpay_order_id": razorpay_order_id,
                    "razorpay_payment_id": razorpay_payment_id,
                    "automatic_refund": refund,
                    "reason": "Wallet reservation expired and released funds were unavailable.",
                    "refunded_at": timezone.now().isoformat(),
                    "source": source,
                }
                payment.save(
                    update_fields=["status", "failed_at", "raw_response", "updated_at"]
                )
                Notification.objects.create(
                    user=payment.customer,
                    type=Notification.Type.SYSTEM_ANNOUNCEMENT,
                    title="Payment Refunded",
                    body="Your late payment was automatically refunded because the reserved wallet amount was no longer available. You can retry checkout.",
                    channel=Notification.Channel.IN_APP,
                    data={
                        "order_id": payment.order_id,
                        "payment_id": payment.id,
                        "refund_id": refund.get("id") if isinstance(refund, dict) else None,
                    },
                )
                logger.warning(
                    "Late Razorpay payment %s was refunded because wallet funds were unavailable",
                    payment.id,
                )
                return Response(
                    {
                        "detail": "The late payment was refunded because the wallet reservation had expired.",
                        "status": payment.status,
                        "payment_id": payment.id,
                        "airway_order_id": payment.order_id,
                    },
                    status=status.HTTP_200_OK,
                )

        payment.status = Payment.Status.PAID
        payment.razorpay_payment_id = razorpay_payment_id
        payment.razorpay_signature = "verified"
        payment.paid_at = timezone.now()
        payment.raw_response = {
            "razorpay_order_id": razorpay_order_id,
            "razorpay_payment_id": razorpay_payment_id,
            "verified_at": timezone.now().isoformat(),
            "source": source,
        }
        payment.save()

        # New single-booking advances use the same line-level ledger and
        # dispatch gate as parent orders. Historical bookings remain unchanged.
        if payment.booking_id:
            from .models import (
                BookingFinancialPlan, PaymentInstallment, PaymentAllocation,
            )
            plan = BookingFinancialPlan.objects.select_for_update().filter(
                booking_id=payment.booking_id
            ).first()
            if plan:
                installment = PaymentInstallment.objects.select_for_update().get(
                    financial_plan=plan,
                    kind=PaymentInstallment.Kind.ADVANCE,
                )
                if installment.status != PaymentInstallment.Status.PAID:
                    if payment.amount != installment.amount_due:
                        raise ValueError("Captured payment does not equal the booking advance.")
                    PaymentAllocation.objects.create(
                        payment=payment,
                        installment=installment,
                        amount=installment.amount_due,
                        gateway_amount=installment.amount_due,
                        wallet_amount=0,
                    )
                    installment.amount_captured = installment.amount_due
                    installment.status = PaymentInstallment.Status.PAID
                    installment.settled_at = timezone.now()
                    installment.save(update_fields=[
                        "amount_captured", "status", "settled_at", "updated_at"
                    ])
                    plan.advance_captured = installment.amount_due
                    plan.save(update_fields=["advance_captured", "updated_at"])
                booking = Booking.objects.select_for_update().get(pk=payment.booking_id)
                if booking.status not in (Booking.Status.PENDING, Booking.Status.CONFIRMED):
                    raise ValueError("Booking is no longer eligible for dispatch after payment.")
                def dispatch_paid_booking(booking_id):
                    from apps.bookings.dispatcher import DispatcherService
                    paid_booking = Booking.objects.get(pk=booking_id)
                    DispatcherService.dispatch_offers(paid_booking)
                transaction.on_commit(
                    lambda booking_id=booking.pk: dispatch_paid_booking(booking_id)
                )
                Notification.objects.create(
                    user=payment.customer,
                    type=Notification.Type.PAYMENT_SUCCESS,
                    title="Booking advance received",
                    body=f"Your 50% booking advance for booking #{booking.pk} was received. We are finding an eligible professional.",
                    channel=Notification.Channel.IN_APP,
                    data={"booking_id": booking.pk, "payment_id": payment.id},
                )
                return Response({
                    "detail": "Booking advance captured. Worker dispatch has been queued.",
                    "status": payment.status,
                    "payment_id": payment.id,
                    "booking_id": booking.pk,
                    "advance_amount": str(installment.amount_due),
                    "razorpay_payment_id": razorpay_payment_id,
                }, status=status.HTTP_200_OK)

        # New split-payment orders settle line-level advance installments
        # before any worker offer is created. Legacy orders keep the path below.
        if payment.order_id:
            from .models import (
                BookingFinancialPlan, PaymentInstallment, PaymentAllocation,
            )
            from decimal import Decimal

            parent_order = Order.objects.select_for_update().get(pk=payment.order_id)
            order_items = list(
                parent_order.items.exclude(booking__status=Booking.Status.CANCELLED)
                .select_related("booking").order_by("id")
            )
            plans = [
                BookingFinancialPlan.objects.select_for_update().filter(
                    booking_id=item.booking_id
                ).first()
                for item in order_items
            ]
            if not order_items:
                raise ValueError("This order has no active service lines to settle.")
            if order_items and all(plans):
                if parent_order.status != Order.Status.AWAITING_PAYMENT:
                    raise ValueError("Split-payment order is not awaiting its advance.")
                installments = []
                for plan in plans:
                    installment = PaymentInstallment.objects.select_for_update().get(
                        financial_plan=plan,
                        kind=PaymentInstallment.Kind.ADVANCE,
                    )
                    if installment.status == PaymentInstallment.Status.PAID:
                        raise ValueError("An advance installment was already settled by another payment.")
                    if installment.amount_due <= 0:
                        raise ValueError("Zero-value advances cannot be settled through this payment.")
                    installments.append((plan, installment))

                total_advance = sum(
                    (row.amount_due for _, row in installments), Decimal("0.00")
                )
                wallet_remaining = payment.wallet_amount
                gateway_remaining = payment.amount
                if total_advance != wallet_remaining + gateway_remaining:
                    raise ValueError("Captured tender does not equal the order's aggregate advance.")
                for plan, installment in installments:
                    wallet_part = min(installment.amount_due, wallet_remaining)
                    wallet_remaining -= wallet_part
                    gateway_part = installment.amount_due - wallet_part
                    if gateway_part > gateway_remaining:
                        raise ValueError("Payment allocation exceeds the captured gateway amount.")
                    gateway_remaining -= gateway_part
                    PaymentAllocation.objects.create(
                        payment=payment,
                        installment=installment,
                        amount=installment.amount_due,
                        gateway_amount=gateway_part,
                        wallet_amount=wallet_part,
                    )
                    installment.amount_captured = installment.amount_due
                    installment.status = PaymentInstallment.Status.PAID
                    installment.settled_at = timezone.now()
                    installment.save(update_fields=[
                        "amount_captured", "status", "settled_at", "updated_at"
                    ])
                    plan.advance_captured = installment.amount_due
                    plan.save(update_fields=["advance_captured", "updated_at"])

                if wallet_remaining != 0 or gateway_remaining != 0:
                    raise ValueError("Aggregate advance allocation did not reconcile exactly.")

                parent_order.status = Order.Status.AWAITING_ASSIGNMENT
                parent_order.save(update_fields=["status", "updated_at"])
                booking_ids = [item.booking_id for item in order_items]
                Notification.objects.create(
                    user=payment.customer,
                    type=Notification.Type.PAYMENT_SUCCESS,
                    title="Booking advance received",
                    body=f"Your 50% booking advance for AIRway order #{parent_order.id} was received. We are finding an eligible professional.",
                    channel=Notification.Channel.IN_APP,
                    data={"order_id": parent_order.id, "payment_id": payment.id, "booking_ids": booking_ids},
                )
                def dispatch_paid_order(order_id):
                    from apps.bookings.dispatcher import DispatcherService
                    paid_order = Order.objects.get(pk=order_id)
                    DispatcherService.dispatch_order(paid_order)
                transaction.on_commit(lambda order_id=parent_order.id: dispatch_paid_order(order_id))
                return Response({
                    "detail": "Booking advance captured and allocated. Worker dispatch has been queued.",
                    "status": payment.status,
                    "payment_id": payment.id,
                    "airway_order_id": parent_order.id,
                    "booking_ids": booking_ids,
                    "advance_total": str(total_advance),
                    "razorpay_payment_id": razorpay_payment_id,
                }, status=status.HTTP_200_OK)

        # Parent-order payment: legacy full-payment settlement.
        if payment.order_id:
            parent_order = Order.objects.select_for_update().get(pk=payment.order_id)
            order_bookings = list(
                parent_order.items.select_related("booking").order_by("id")
            )
            for order_item in order_bookings:
                booking = order_item.booking
                if booking.status == Booking.Status.ASSIGNED:
                    old_status = booking.status
                    booking.status = Booking.Status.CONFIRMED
                    booking.save(update_fields=["status", "updated_at"])
                    BookingStatusHistory.objects.create(
                        booking=booking,
                        from_status=old_status,
                        to_status=Booking.Status.CONFIRMED,
                        changed_by=payment.customer,
                        note=f"Parent order #{parent_order.id} payment confirmed via {source}.",
                    )
                elif booking.status == Booking.Status.PENDING:
                    old_status = booking.status
                    booking.status = Booking.Status.CONFIRMED
                    booking.save(update_fields=["status", "updated_at"])
                    BookingStatusHistory.objects.create(
                        booking=booking,
                        from_status=old_status,
                        to_status=Booking.Status.CONFIRMED,
                        changed_by=payment.customer,
                        note=f"Late parent order #{parent_order.id} payment received.",
                    )
                    from apps.bookings.dispatcher import DispatcherService
                    DispatcherService.dispatch_offers(booking)

            parent_order.status = Order.Status.PAID
            parent_order.save(update_fields=["status", "updated_at"])
            Notification.objects.create(
                user=payment.customer,
                type=Notification.Type.PAYMENT_SUCCESS,
                title="Payment Successful",
                body=f"Payment for AIRway order #{parent_order.id} was successful.",
                channel=Notification.Channel.IN_APP,
                data={
                    "order_id": parent_order.id,
                    "payment_id": payment.id,
                    "booking_ids": [row.booking_id for row in order_bookings],
                },
            )
            logger.info(
                "Parent order payment %s verified for order %s",
                payment.id, parent_order.id,
            )
            return Response(
                {
                    "detail": "Order payment verified successfully.",
                    "status": payment.status,
                    "payment_id": payment.id,
                    "airway_order_id": parent_order.id,
                    "booking_ids": [row.booking_id for row in order_bookings],
                    "razorpay_payment_id": razorpay_payment_id,
                    "paid_at": payment.paid_at.isoformat() if payment.paid_at else None,
                },
                status=status.HTTP_200_OK,
            )

        booking = payment.booking
        notification_created = False

        # Handle booking status transition based on current state
        if booking.status == Booking.Status.ASSIGNED:
            # Normal flow: worker accepted, payment confirmed
            old_status = booking.status
            booking.status = Booking.Status.CONFIRMED
            booking.save(update_fields=["status"])
            BookingStatusHistory.objects.create(
                booking=booking,
                from_status=old_status,
                to_status=Booking.Status.CONFIRMED,
                changed_by=payment.customer,
                note="Payment confirmed via Razorpay webhook",
            )
            logger.info(
                f"Booking {payment.booking_id} status updated from {old_status} to CONFIRMED"
            )

        elif booking.status == Booking.Status.PENDING:
            # Q12 Late webhook scenario: timeout already released worker
            # Payment was captured after timeout released the assignment
            old_status = booking.status
            booking.status = Booking.Status.CONFIRMED
            booking.save(update_fields=["status"])
            BookingStatusHistory.objects.create(
                booking=booking,
                from_status=old_status,
                to_status=Booking.Status.CONFIRMED,
                changed_by=payment.customer,
                note="Late payment webhook - booking confirmed after timeout release",
            )

            # Trigger fresh dispatch for this booking (slot may be taken, will find next)
            from apps.bookings.dispatcher import DispatcherService

            offers = DispatcherService.dispatch_offers(booking)
            if offers:
                logger.info(
                    f"Q12: Re-dispatched booking {booking.id} after late webhook: {len(offers)} offers created"
                )

            # Notify customer about late payment
            Notification.objects.create(
                user=booking.customer,
                type=Notification.Type.PAYMENT_SUCCESS,
                title="Payment Confirmed",
                body="Your payment was received after timeout. A new worker is being assigned.",
                channel=Notification.Channel.IN_APP,
                data={
                    "booking_id": booking.id,
                    "payment_id": payment.id,
                    "late_webhook": True,
                    "re_dispatch": len(offers) > 0,
                },
            )
            notification_created = True

            logger.info(
                f"Booking {payment.booking_id} Q12 late webhook handled: "
                f"payment PAID, dispatch triggered, {len(offers)} offers"
            )

        else:
            # Booking in unexpected state (e.g., COMPLETED, CANCELLED)
            logger.warning(
                f"Payment {payment.id} PAID but booking {payment.booking_id} in state {booking.status}"
            )

        # Create payment success notification for normal flow (skip if already created for Q12)
        if booking.status == Booking.Status.CONFIRMED and not notification_created:
            Notification.objects.create(
                user=payment.customer,
                type=Notification.Type.PAYMENT_SUCCESS,
                title="Payment Successful",
                body=f"Your booking #{payment.booking_id} is now confirmed!",
                channel=Notification.Channel.IN_APP,
                data={"booking_id": payment.booking_id, "payment_id": payment.id},
            )

    logger.info(
        f"Payment {payment.id} verified for booking {payment.booking_id}: "
        f"PAID at {payment.paid_at}"
    )

    return Response(
        {
            "detail": "Payment verified successfully.",
            "status": payment.status,
            "payment_id": payment.id,
            "razorpay_payment_id": razorpay_payment_id,
            "paid_at": payment.paid_at.isoformat() if payment.paid_at else None,
        },
        status=status.HTTP_200_OK,
    )


class VerifyPaymentView(APIView):
    """
    Verify Razorpay checkout payment signatures and handle webhooks.
    Supports both customer-initiated verification and server-to-server webhooks.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        razorpay_order_id = request.data.get("razorpay_order_id")
        razorpay_payment_id = request.data.get("razorpay_payment_id")
        razorpay_signature = request.data.get("razorpay_signature")

        if not all([razorpay_order_id, razorpay_payment_id, razorpay_signature]):
            return Response(
                {"detail": "Missing required payment verification fields."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        payment = get_object_or_404(
            Payment,
            razorpay_order_id=razorpay_order_id,
            customer=request.user,
        )

        # Verify HMAC signature for checkout response
        message = f"{razorpay_order_id}|{razorpay_payment_id}"
        expected_signature = hmac.new(
            settings.RAZORPAY_KEY_SECRET.encode(),
            message.encode(),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(expected_signature, razorpay_signature):
            # A bad checkout callback is not proof that the Razorpay order
            # itself failed. Keep parent-order reservations available for retry.
            if not payment.order_id:
                payment.status = Payment.Status.FAILED
                payment.failed_at = timezone.now()
                payment.save(update_fields=["status", "failed_at", "updated_at"])
            payment.raw_response = {
                "error": "Signature verification failed",
                "razorpay_order_id": razorpay_order_id,
                "razorpay_payment_id": razorpay_payment_id,
            }
            payment.save(update_fields=["raw_response", "updated_at"])
            logger.warning(
                f"Payment verification failed for booking {payment.booking_id}: "
                f"order_id={razorpay_order_id}"
            )
            return Response(
                {"detail": "Payment signature verification failed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return _process_verified_payment(
            payment=payment,
            razorpay_payment_id=razorpay_payment_id,
            razorpay_order_id=razorpay_order_id,
            customer=request.user,
            source="checkout"
        )


class PaymentWebhookView(APIView):
    """
    Razorpay webhook endpoint for server-to-server payment notifications.
    This endpoint is called by Razorpay when payment events occur.

    SECURITY: Webhook endpoint does not require authentication as it's
    called by Razorpay servers. Signature verification is mandatory.
    """
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        # Get the webhook signature from headers
        signature = request.META.get('HTTP_X_RAZORPAY_SIGNATURE')
        if not signature:
            logger.warning("Webhook called without signature header")
            return Response(
                {"detail": "Missing Razorpay signature"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get raw request body for signature verification
        # Important: must use raw body, not parsed JSON
        raw_body = request.body
        if not raw_body:
            logger.warning("Webhook called with empty body")
            return Response(
                {"detail": "Empty webhook body"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Verify webhook signature using webhook secret
        webhook_secret = getattr(settings, 'RAZORPAY_WEBHOOK_SECRET', None)
        if not webhook_secret:
            logger.error("RAZORPAY_WEBHOOK_SECRET not configured")
            return Response(
                {"detail": "Webhook configuration error"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        expected_signature = hmac.new(
            webhook_secret.encode(),
            raw_body,
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(expected_signature, signature):
            logger.warning(
                f"Webhook signature verification failed. "
                f"Expected: {expected_signature[:16]}..., Got: {signature[:16]}..."
            )
            return Response(
                {"detail": "Invalid webhook signature"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Parse the webhook payload
        try:
            payload = json.loads(raw_body.decode('utf-8'))
        except json.JSONDecodeError as e:
            logger.error(f"Webhook JSON parse error: {e}")
            return Response(
                {"detail": "Invalid JSON in webhook payload"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Extract event details
        event_type = payload.get('event')
        payment_id = payload.get('payload', {}).get('payment', {}).get('entity', {}).get('id')
        order_id = payload.get('payload', {}).get('payment', {}).get('entity', {}).get('order_id')

        logger.info(f"Webhook received: event={event_type}, payment_id={payment_id}, order_id={order_id}")

        # Reconcile refund lifecycle events independently of payment events.
        if event_type in ("refund.created", "refund.processed", "refund.failed"):
            refund_entity = payload.get("payload", {}).get("refund", {}).get("entity", {})
            provider_refund_id = refund_entity.get("id")
            if provider_refund_id:
                from .models import PaymentAttempt, RefundRecord
                refund_notes = refund_entity.get("notes") or {}
                record_id = refund_notes.get("airway_refund_record_id")
                with transaction.atomic():
                    refund_query = RefundRecord.objects.select_for_update()
                    refund_record = refund_query.filter(
                        provider_refund_id=provider_refund_id
                    ).first()
                    if refund_record is None and record_id:
                        refund_record = refund_query.filter(pk=record_id).first()
                    if refund_record:
                        # The signed webhook must still reconcile to the exact
                        # tender and original payment recorded by AIRway.
                        expected_payment_id = (
                            refund_record.payment.razorpay_payment_id
                            if refund_record.payment_id
                            else refund_record.payment_attempt.provider_payment_id
                            if refund_record.payment_attempt_id
                            else None
                        )
                        received_payment_id = refund_entity.get("payment_id")
                        received_amount = refund_entity.get("amount")
                        try:
                            amount_matches = (
                                received_amount is not None
                                and int(received_amount)
                                == int(refund_record.gateway_refund_amount * 100)
                            )
                        except (TypeError, ValueError):
                            amount_matches = False
                        if (
                            not expected_payment_id
                            or str(received_payment_id or "") != str(expected_payment_id)
                            or not amount_matches
                        ):
                            logger.error(
                                "Refund webhook does not match AIRway ledger: "
                                "refund_record=%s provider_refund_id=%s",
                                refund_record.pk, provider_refund_id,
                            )
                            refund_record = None
                    if refund_record:
                        # Lock the refund and linked attempt in one transaction.
                        # Duplicate/out-of-order events must not regress a processed refund.
                        if refund_record.status != RefundRecord.Status.PROCESSED:
                            if event_type == "refund.processed":
                                refund_record.status = RefundRecord.Status.PROCESSED
                                refund_record.processed_at = timezone.now()
                            elif event_type == "refund.failed":
                                refund_record.status = RefundRecord.Status.FAILED
                            else:
                                refund_record.status = RefundRecord.Status.PENDING
                        refund_record.provider_payload = payload
                        if provider_refund_id and not refund_record.provider_refund_id:
                            refund_record.provider_refund_id = provider_refund_id
                        refund_record.save(update_fields=[
                            "status", "processed_at", "provider_payload",
                            "provider_refund_id", "updated_at"
                        ])
                        if refund_record.payment_attempt_id:
                            attempt = PaymentAttempt.objects.select_for_update().filter(
                                pk=refund_record.payment_attempt_id,
                            ).first()
                            if attempt and attempt.status != PaymentAttempt.Status.CAPTURED:
                                refund_states = list(
                                    RefundRecord.objects.filter(
                                        payment_attempt=attempt,
                                    ).values_list("status", flat=True)
                                )
                                if any(state in (
                                    RefundRecord.Status.REQUESTED,
                                    RefundRecord.Status.PENDING,
                                ) for state in refund_states):
                                    attempt.status = PaymentAttempt.Status.REFUND_PENDING
                                elif any(state == RefundRecord.Status.FAILED for state in refund_states):
                                    attempt.status = PaymentAttempt.Status.FAILED
                                elif refund_states and all(
                                    state == RefundRecord.Status.PROCESSED for state in refund_states
                                ):
                                    attempt.status = PaymentAttempt.Status.REFUNDED
                                attempt.save(update_fields=["status", "updated_at"])
                    else:
                        logger.warning(
                            "Refund webhook references unknown AIRway refund: %s",
                            provider_refund_id,
                        )
            return Response({"status": "ok"})

        # Installment attempts are separate from legacy Payment rows: one
        # immutable provider order belongs to one booking-line installment.
        if event_type in ("payment.captured", "payment.authorized", "payment.failed", "payment.canceled"):
            from .models import PaymentAttempt, RefundRecord
            from .installment_service import (
                InstallmentPaymentError,
                mark_final_balance_attempt_failed,
                refund_late_final_capture,
                refund_duplicate_final_capture,
                refund_mismatched_final_capture,
                settle_final_balance_attempt,
            )
            attempt = None
            if order_id:
                attempt = PaymentAttempt.objects.filter(provider_order_id=order_id).first()
            if attempt is None and payment_id:
                attempt = PaymentAttempt.objects.filter(provider_payment_id=payment_id).first()
            if attempt is not None:
                entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
                if order_id != attempt.provider_order_id:
                    return Response({"detail": "Razorpay order ID mismatch."}, status=status.HTTP_400_BAD_REQUEST)
                if event_type == "payment.authorized":
                    if attempt.status == PaymentAttempt.Status.CREATED:
                        attempt.status = PaymentAttempt.Status.AUTHORIZED
                        attempt.provider_payment_id = payment_id or None
                        attempt.provider_payload = payload
                        attempt.save(update_fields=["status", "provider_payment_id", "provider_payload", "updated_at"])
                    return Response({"status": "ok"})
                if event_type in ("payment.failed", "payment.canceled"):
                    try:
                        mark_final_balance_attempt_failed(
                            attempt_id=attempt.pk, provider_order_id=order_id, payload=payload,
                        )
                    except InstallmentPaymentError as exc:
                        return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
                    return Response({"status": "ok"})
                amount_paise = entity.get("amount")
                currency = entity.get("currency")
                if not payment_id or not isinstance(amount_paise, int) or not currency:
                    return Response({"detail": "Captured event is missing payment ID, amount, or currency."}, status=status.HTTP_400_BAD_REQUEST)
                if currency.upper() != attempt.currency:
                    return Response({"detail": "Currency mismatch requires manual provider reconciliation."}, status=status.HTTP_400_BAD_REQUEST)
                if amount_paise != int(attempt.gateway_amount * 100):
                    try:
                        refund_record = refund_mismatched_final_capture(
                            attempt_id=attempt.pk,
                            razorpay_payment_id=payment_id,
                            provider_order_id=order_id,
                            amount_paise=amount_paise,
                            currency=currency,
                            payload=payload,
                        )
                    except InstallmentPaymentError as exc:
                        logger.exception("Mismatched final-payment capture needs reconciliation for attempt %s", attempt.pk)
                        return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
                    return Response({
                        "status": "ok",
                        "reconciled": "mismatched_capture_refund",
                        "refund_status": refund_record.status,
                    })
                try:
                    if (
                        attempt.status in (PaymentAttempt.Status.REFUND_PENDING, PaymentAttempt.Status.REFUNDED)
                        and RefundRecord.objects.filter(
                            payment_attempt=attempt,
                            idempotency_key=f"late-final-capture:attempt:{attempt.pk}:{payment_id}",
                        ).exists()
                    ):
                        return Response({"status": "ok", "reconciled": "already_refunded"})
                    if attempt.status in (PaymentAttempt.Status.REFUND_PENDING, PaymentAttempt.Status.REFUNDED):
                        refund_late_final_capture(
                            attempt_id=attempt.pk,
                            razorpay_payment_id=payment_id,
                            provider_order_id=order_id,
                            payload=payload,
                        )
                        return Response({"status": "ok", "reconciled": "additional_late_capture_refund"})
                    if (
                        attempt.status == PaymentAttempt.Status.CAPTURED
                        and attempt.provider_payment_id != payment_id
                    ):
                        refund_duplicate_final_capture(
                            attempt_id=attempt.pk,
                            razorpay_payment_id=payment_id,
                            provider_order_id=order_id,
                            payload=payload,
                        )
                        return Response({"status": "ok", "reconciled": "duplicate_capture_refund"})
                    if attempt.status == PaymentAttempt.Status.FAILED:
                        refund_late_final_capture(
                            attempt_id=attempt.pk,
                            razorpay_payment_id=payment_id,
                            provider_order_id=order_id,
                            payload=payload,
                        )
                        return Response({"status": "ok", "reconciled": "late_capture_refund"})
                    settle_final_balance_attempt(
                        attempt_id=attempt.pk,
                        razorpay_payment_id=payment_id,
                        provider_order_id=order_id,
                        amount_paise=amount_paise,
                        currency=currency,
                        source="webhook",
                    )
                except InstallmentPaymentError as exc:
                    attempt.refresh_from_db()
                    if (
                        attempt.status == PaymentAttempt.Status.CAPTURED
                        and attempt.provider_payment_id != payment_id
                    ):
                        refund_duplicate_final_capture(
                            attempt_id=attempt.pk,
                            razorpay_payment_id=payment_id,
                            provider_order_id=order_id,
                            payload=payload,
                        )
                        return Response({"status": "ok", "reconciled": "concurrent_duplicate_capture_refund"})
                    logger.exception("Final-balance webhook reconciliation failed for attempt %s", attempt.pk)
                    return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
                return Response({"status": "ok"})

        # Handle payment.captured event (Razorpay uses 'payment.captured' for successful payments)
        if event_type in ('payment.captured', 'payment.authorized'):
            # Get the payment record by order_id or payment_id
            payment = None
            try:
                if order_id:
                    payment = Payment.objects.get(razorpay_order_id=order_id)
                elif payment_id:
                    payment = Payment.objects.get(razorpay_payment_id=payment_id)
            except Payment.DoesNotExist:
                # Wallet top-ups use their own ledger rather than a Booking
                # Payment row. Only captured events may settle wallet funds.
                if event_type == "payment.captured" and order_id:
                    from apps.wallet.models import WalletTransaction
                    from apps.wallet.views import complete_top_up_transaction

                    wallet_top_up = WalletTransaction.objects.filter(
                        reference_id=order_id,
                        type=WalletTransaction.Type.CREDIT,
                        status=WalletTransaction.Status.PENDING,
                    ).first()
                    if wallet_top_up is not None:
                        payment_entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
                        razorpay_amount = payment_entity.get("amount")
                        razorpay_currency = payment_entity.get("currency", "").upper()
                        expected_amount_paise = int(wallet_top_up.amount * 100)

                        if razorpay_amount != expected_amount_paise:
                            logger.warning(
                                "Wallet top-up webhook amount mismatch for transaction %s",
                                wallet_top_up.id,
                            )
                            return Response({"detail": "Amount mismatch"}, status=status.HTTP_400_BAD_REQUEST)
                        if razorpay_currency != "INR":
                            logger.warning(
                                "Wallet top-up webhook currency mismatch for transaction %s",
                                wallet_top_up.id,
                            )
                            return Response({"detail": "Currency mismatch"}, status=status.HTTP_400_BAD_REQUEST)

                        completed = complete_top_up_transaction(
                            wallet_top_up.id,
                            razorpay_payment_id=payment_id,
                            razorpay_order_id=order_id,
                        )
                        if completed is not None:
                            Notification.objects.create(
                                user=completed.wallet.user,
                                type=Notification.Type.PAYMENT_SUCCESS,
                                title="Wallet Top-up Successful",
                                body=f"₹{completed.amount} has been added to your AIRway wallet.",
                                channel=Notification.Channel.IN_APP,
                                data={
                                    "wallet_transaction_id": completed.id,
                                    "razorpay_payment_id": payment_id,
                                },
                            )
                        return Response({"status": "ok"})

                logger.warning(f"Payment not found for webhook: payment_id={payment_id}, order_id={order_id}")
                return Response({"status": "ok"})  # Idempotent: don't fail on unknown payment

            # Idempotency: if already processed, skip
            if payment.status == Payment.Status.PAID:
                logger.info(f"Webhook: payment {payment.id} already processed (PAID)")
                return Response({"status": "ok"})

            # Extract payment entity for amount/currency validation
            payment_entity = payload.get('payload', {}).get('payment', {}).get('entity', {})
            razorpay_amount = payment_entity.get('amount')  # in paise
            razorpay_currency = payment_entity.get('currency', '').upper()

            # Validate amount matches (convert to paise for comparison)
            expected_amount_paise = int(float(payment.amount) * 100)
            if razorpay_amount is not None and razorpay_amount != expected_amount_paise:
                logger.warning(
                    f"Webhook amount mismatch for payment {payment.id}: "
                    f"expected {expected_amount_paise} paise, got {razorpay_amount} paise"
                )
                return Response(
                    {"detail": "Amount mismatch"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Validate currency
            if razorpay_currency and razorpay_currency != 'INR':
                logger.warning(
                    f"Webhook currency mismatch for payment {payment.id}: "
                    f"expected INR, got {razorpay_currency}"
                )
                return Response(
                    {"detail": "Currency mismatch"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Process the payment - verify and mark as PAID
            return _process_verified_payment(
                payment=payment,
                razorpay_payment_id=payment_id,
                razorpay_order_id=payment.razorpay_order_id,
                customer=payment.customer,
                source="webhook"
            )

        elif event_type == 'payment.failed':
            # Handle failed payment
            payment = None
            try:
                if order_id:
                    payment = Payment.objects.get(razorpay_order_id=order_id)
                elif payment_id:
                    payment = Payment.objects.get(razorpay_payment_id=payment_id)
            except Payment.DoesNotExist:
                logger.warning(f"Payment not found for webhook (failed): payment_id={payment_id}, order_id={order_id}")
                return Response({"status": "ok"})

            if payment.status not in [Payment.Status.PAID, Payment.Status.REFUNDED]:
                if payment.order_id:
                    # A failed attempt can be retried against the same Razorpay order.
                    # Keep the parent payment and wallet reservation pending.
                    payment.raw_response = payload
                    payment.save(update_fields=["raw_response", "updated_at"])
                    logger.info("Order payment %s attempt failed; reservation retained for retry", payment.id)
                else:
                    payment.status = Payment.Status.FAILED
                    payment.failed_at = timezone.now()
                    payment.raw_response = payload
                    payment.save()
                    logger.info(f"Payment {payment.id} marked as FAILED via webhook")
            else:
                logger.info(f"Payment {payment.id} already PAID, not marking as FAILED")

            return Response({"status": "ok"})

        elif event_type == 'payment.canceled':
            # Handle canceled payment
            payment = None
            try:
                if order_id:
                    payment = Payment.objects.get(razorpay_order_id=order_id)
                elif payment_id:
                    payment = Payment.objects.get(razorpay_payment_id=payment_id)
            except Payment.DoesNotExist:
                logger.warning(f"Payment not found for webhook (canceled): payment_id={payment_id}, order_id={order_id}")
                return Response({"status": "ok"})

            if payment.status not in [Payment.Status.PAID, Payment.Status.REFUNDED]:
                if payment.order_id:
                    payment.raw_response = payload
                    payment.save(update_fields=["raw_response", "updated_at"])
                    logger.info("Order payment %s attempt canceled; reservation retained for retry", payment.id)
                else:
                    payment.status = Payment.Status.FAILED
                    payment.failed_at = timezone.now()
                    payment.raw_response = payload
                    payment.save()
                    logger.info(f"Payment {payment.id} marked as FAILED (canceled)")

            return Response({"status": "ok"})

        # Return OK for unrecognized events (idempotency)
        logger.info(f"Webhook event {event_type} received but not processed")
        return Response({"status": "ok"})