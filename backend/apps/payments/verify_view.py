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


def _process_verified_payment(
    payment, razorpay_payment_id, razorpay_order_id, customer, source
):
    """
    Process a verified payment. Called by both checkout verification
    and webhook handlers.
    """
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

        if payment.order_id and payment.stage in (Payment.Stage.ADVANCE, Payment.Stage.BALANCE):
            staged_order = Order.objects.select_for_update().get(pk=payment.order_id)
            allocation = (staged_order.metadata or {}).get("payment_allocation_v1", {})
            stage_rows = allocation.get(
                "advance" if payment.stage == Payment.Stage.ADVANCE else "balance", []
            )
            active_ids = set(
                staged_order.items.exclude(booking__status=Booking.Status.CANCELLED)
                .values_list("id", flat=True)
            )
            expected_stage_total = sum(
                (
                    Decimal(str(row.get("amount", "0")))
                    for row in stage_rows
                    if row.get("order_item_id") in active_ids
                ),
                Decimal("0.00"),
            )
            captured_stage_total = payment.amount + payment.wallet_amount
            if captured_stage_total != expected_stage_total:
                logger.warning(
                    "Captured payment %s no longer matches active %s allocation (%s vs %s); reversing",
                    payment.pk, payment.stage, captured_stage_total, expected_stage_total,
                )
                try:
                    refund = {"status": "wallet_only"}
                    if payment.amount > 0:
                        if not razorpay_payment_id:
                            raise ValueError("Captured Razorpay payment ID is missing for reversal.")
                        import razorpay
                        gateway = razorpay.Client(
                            auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
                        )
                        gateway_payment = gateway.payment.fetch(razorpay_payment_id)
                        remaining = int(payment.amount * 100) - int(gateway_payment.get("amount_refunded", 0))
                        if remaining > 0:
                            refund = gateway.payment.refund(
                                razorpay_payment_id,
                                {
                                    "amount": remaining,
                                    "notes": {
                                        "airway_payment_id": str(payment.pk),
                                        "reason": "Order service allocation changed before payment capture",
                                    },
                                },
                            )
                        else:
                            refund = {"status": "already_refunded"}
                    if payment.wallet_amount > 0:
                        from apps.wallet.services import release_wallet_reservation
                        release_wallet_reservation(
                            payment,
                            reason="Payment reversed because active service allocation changed.",
                        )
                    payment.razorpay_payment_id = razorpay_payment_id
                    payment.status = Payment.Status.REFUNDED
                    payment.failed_at = timezone.now()
                    payment.raw_response = {
                        **(payment.raw_response or {}),
                        "automatic_refund": refund,
                        "expected_stage_total": str(expected_stage_total),
                        "captured_stage_total": str(captured_stage_total),
                        "reason": "Payment attempt no longer matched active service allocations.",
                        "refunded_at": timezone.now().isoformat(),
                        "source": source,
                    }
                    payment.save(update_fields=["razorpay_payment_id", "status", "failed_at", "raw_response", "updated_at"])
                    Notification.objects.create(
                        user=payment.customer,
                        type=Notification.Type.SYSTEM_ANNOUNCEMENT,
                        title="Payment reversed",
                        body="Your payment was reversed because the active services in your order changed before payment completed. Please review the updated order and retry.",
                        channel=Notification.Channel.IN_APP,
                        data={"order_id": payment.order_id, "payment_id": payment.pk},
                    )
                    return Response(
                        {"detail": "Payment reversed because the active service allocation changed.", "status": payment.status, "payment_id": payment.pk},
                        status=status.HTTP_200_OK,
                    )
                except Exception:
                    logger.exception("Could not reverse stale staged payment %s", payment.pk)
                    return Response(
                        {"detail": "Payment was captured but automatic reversal could not be confirmed. AIRway support must reconcile it.", "payment_id": payment.pk},
                        status=status.HTTP_502_BAD_GATEWAY,
                    )

        if payment.order_id and payment.stage == Payment.Stage.BALANCE:
            balance_order = Order.objects.select_for_update().get(pk=payment.order_id)
            active_balance_items = balance_order.items.exclude(
                booking__status=Booking.Status.CANCELLED
            )
            if (
                not active_balance_items.exists()
                or active_balance_items.exclude(
                    booking__status=Booking.Status.COMPLETED
                ).exists()
            ):
                logger.error("Balance payment %s captured before all bookings were verified complete", payment.pk)
                try:
                    refund = {"status": "wallet_only"}
                    if razorpay_payment_id and payment.amount > 0:
                        import razorpay
                        gateway = razorpay.Client(
                            auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
                        )
                        gateway_payment = gateway.payment.fetch(razorpay_payment_id)
                        remaining = int(payment.amount * 100) - int(gateway_payment.get("amount_refunded", 0))
                        if remaining > 0:
                            refund = gateway.payment.refund(
                                razorpay_payment_id,
                                {
                                    "amount": remaining,
                                    "notes": {
                                        "airway_payment_id": str(payment.pk),
                                        "reason": "Balance captured before all service completions were verified",
                                    },
                                },
                            )
                        else:
                            refund = {"status": "already_refunded"}
                    if payment.wallet_amount > 0:
                        from apps.wallet.services import release_wallet_reservation
                        release_wallet_reservation(
                            payment,
                            reason="Balance payment reversed because service completion was not verified.",
                        )
                    payment.razorpay_payment_id = razorpay_payment_id
                    payment.status = Payment.Status.REFUNDED
                    payment.failed_at = timezone.now()
                    payment.raw_response = {
                        **(payment.raw_response or {}),
                        "automatic_refund": refund,
                        "reason": "Service completion was not verified at balance capture.",
                        "refunded_at": timezone.now().isoformat(),
                        "source": source,
                    }
                    payment.save(update_fields=["razorpay_payment_id", "status", "failed_at", "raw_response", "updated_at"])
                    Notification.objects.create(
                        user=payment.customer,
                        type=Notification.Type.SYSTEM_ANNOUNCEMENT,
                        title="Balance payment reversed",
                        body="Your final payment was reversed because all service completions were not verified. AIRway support will follow up if the gateway refund is still processing.",
                        channel=Notification.Channel.IN_APP,
                        data={"order_id": payment.order_id, "payment_id": payment.pk},
                    )
                    return Response(
                        {"detail": "Balance payment was reversed because service completion was not verified.", "status": payment.status, "payment_id": payment.pk},
                        status=status.HTTP_200_OK,
                    )
                except Exception:
                    logger.exception("Could not automatically reverse premature balance capture %s", payment.pk)
                    return Response(
                        {"detail": "Payment was captured but automatic reversal could not be confirmed. AIRway support must reconcile it.", "payment_id": payment.pk},
                        status=status.HTTP_502_BAD_GATEWAY,
                    )

        if payment.order_id and payment.stage == Payment.Stage.ADVANCE:
            advance_order = Order.objects.select_for_update().get(pk=payment.order_id)
            has_active_services = advance_order.items.exclude(
                booking__status=Booking.Status.CANCELLED
            ).exists()
            if advance_order.status == Order.Status.CANCELLED or not has_active_services:
                try:
                    refund = {"status": "wallet_only"}
                    if razorpay_payment_id and payment.amount > 0:
                        import razorpay
                        gateway = razorpay.Client(
                            auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
                        )
                        gateway_payment = gateway.payment.fetch(razorpay_payment_id)
                        remaining = int(payment.amount * 100) - int(gateway_payment.get("amount_refunded", 0))
                        if remaining > 0:
                            refund = gateway.payment.refund(
                                razorpay_payment_id,
                                {
                                    "amount": remaining,
                                    "notes": {
                                        "airway_payment_id": str(payment.pk),
                                        "reason": "Order cancelled before advance settlement",
                                    },
                                },
                            )
                        else:
                            refund = {"status": "already_refunded"}
                    elif payment.amount > 0:
                        raise ValueError("Captured Razorpay payment ID is missing for refund.")
                    if payment.wallet_amount > 0:
                        from apps.wallet.services import release_wallet_reservation
                        release_wallet_reservation(
                            payment,
                            reason="Order cancelled before advance settlement.",
                        )
                    payment.razorpay_payment_id = razorpay_payment_id
                    payment.status = Payment.Status.REFUNDED
                    payment.failed_at = timezone.now()
                    payment.raw_response = {
                        **(payment.raw_response or {}),
                        "automatic_refund": refund,
                        "reason": "Order was cancelled before worker dispatch.",
                        "refunded_at": timezone.now().isoformat(),
                        "source": source,
                    }
                    payment.save(update_fields=["razorpay_payment_id", "status", "failed_at", "raw_response", "updated_at"])
                    Notification.objects.create(
                        user=payment.customer,
                        type=Notification.Type.SYSTEM_ANNOUNCEMENT,
                        title="Advance payment refunded",
                        body="Your advance payment was reversed because the order had no active services remaining.",
                        channel=Notification.Channel.IN_APP,
                        data={"order_id": payment.order_id, "payment_id": payment.pk},
                    )
                    return Response(
                        {"detail": "Advance payment was reversed because the order was cancelled.", "status": payment.status, "payment_id": payment.pk},
                        status=status.HTTP_200_OK,
                    )
                except Exception:
                    logger.exception("Could not automatically refund advance for cancelled order %s", payment.order_id)
                    return Response(
                        {"detail": "Advance payment was captured but automatic refund could not be confirmed. AIRway support must reconcile it.", "payment_id": payment.pk},
                        status=status.HTTP_502_BAD_GATEWAY,
                    )

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

                payment.razorpay_payment_id = razorpay_payment_id
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
                    update_fields=["razorpay_payment_id", "status", "failed_at", "raw_response", "updated_at"]
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
            **(payment.raw_response or {}),
            "razorpay_order_id": razorpay_order_id,
            "razorpay_payment_id": razorpay_payment_id,
            "verified_at": timezone.now().isoformat(),
            "source": source,
        }
        payment.save()

        # Parent-order staged settlement. Advance capture unlocks dispatch;
        # balance capture closes the order. Neither stage marks the order paid
        # prematurely.
        if payment.order_id:
            parent_order = Order.objects.select_for_update().get(pk=payment.order_id)
            order_items = list(parent_order.items.select_related("booking").order_by("id"))
            if payment.stage == Payment.Stage.ADVANCE:
                if parent_order.status not in (
                    Order.Status.AWAITING_ASSIGNMENT,
                    Order.Status.AWAITING_PAYMENT,
                    Order.Status.PARTIALLY_CANCELLED,
                ):
                    logger.warning("Advance payment %s captured for order in state %s", payment.pk, parent_order.status)
                else:
                    if parent_order.status != Order.Status.PARTIALLY_CANCELLED:
                        parent_order.status = Order.Status.AWAITING_ASSIGNMENT
                        parent_order.save(update_fields=["status", "updated_at"])
                    from apps.bookings.dispatcher import DispatcherService
                    DispatcherService.dispatch_order(parent_order)
                message = f"Your 30% advance for AIRway order #{parent_order.id} was received. We are arranging your services."
            elif payment.stage == Payment.Stage.BALANCE:
                active_order_items = [
                    row for row in order_items
                    if row.booking.status != Booking.Status.CANCELLED
                ]
                if (
                    not active_order_items
                    or any(
                        row.booking.status != Booking.Status.COMPLETED
                        for row in active_order_items
                    )
                ):
                    logger.error("Balance payment %s captured before all active services completed", payment.pk)
                    return Response({"detail": "Captured payment requires reconciliation: all active services must be complete.", "payment_id": payment.pk}, status=status.HTTP_409_CONFLICT)
                parent_order.status = (
                    Order.Status.PARTIALLY_CANCELLED
                    if any(row.booking.status == Booking.Status.CANCELLED for row in order_items)
                    else Order.Status.PAID
                )
                parent_order.save(update_fields=["status", "updated_at"])
                message = f"Final balance for AIRway order #{parent_order.id} was received. Thank you."
            else:
                # Preserve the old full-payment transition for orders created
                # before staged checkout was introduced.
                for order_item in order_items:
                    booking = order_item.booking
                    if booking.status in (Booking.Status.ASSIGNED, Booking.Status.PENDING):
                        old_status = booking.status
                        booking.status = Booking.Status.CONFIRMED
                        booking.save(update_fields=["status", "updated_at"])
                        BookingStatusHistory.objects.create(
                            booking=booking,
                            from_status=old_status,
                            to_status=Booking.Status.CONFIRMED,
                            changed_by=payment.customer,
                            note=f"Legacy parent order #{parent_order.id} payment confirmed via {source}.",
                        )
                        if old_status == Booking.Status.PENDING:
                            from apps.bookings.dispatcher import DispatcherService
                            DispatcherService.dispatch_offers(booking)
                parent_order.status = Order.Status.PAID
                parent_order.save(update_fields=["status", "updated_at"])
                message = f"Payment for AIRway order #{parent_order.id} was successful."

            Notification.objects.create(
                user=payment.customer,
                type=Notification.Type.PAYMENT_SUCCESS,
                title="Payment Successful",
                body=message,
                channel=Notification.Channel.IN_APP,
                data={
                    "order_id": parent_order.id,
                    "payment_id": payment.id,
                    "payment_stage": payment.stage,
                    "booking_ids": [row.booking_id for row in order_items],
                },
            )
            logger.info("Order payment stage %s verified for order %s", payment.stage, parent_order.id)
            return Response({
                "detail": message,
                "status": payment.status,
                "payment_id": payment.id,
                "payment_stage": payment.stage,
                "airway_order_id": parent_order.id,
                "booking_ids": [row.booking_id for row in order_items],
                "razorpay_payment_id": razorpay_payment_id,
                "paid_at": payment.paid_at.isoformat() if payment.paid_at else None,
            }, status=status.HTTP_200_OK)

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

        # A valid checkout HMAC proves the callback payload was signed, but
        # fetching the payment also verifies the captured amount and gateway
        # order against the current attempt (important after retries/adjustments).
        if payment.amount > 0:
            try:
                import razorpay
                gateway = razorpay.Client(
                    auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
                )
                gateway_payment = gateway.payment.fetch(razorpay_payment_id)
                gateway_order_matches = gateway_payment.get("order_id") == razorpay_order_id
                gateway_amount_matches = int(gateway_payment.get("amount", -1)) == int(payment.amount * 100)
                expected_currency = payment.order.currency if payment.order_id else "INR"
                gateway_currency_matches = gateway_payment.get("currency") == expected_currency
                gateway_is_captured = gateway_payment.get("status") == "captured"
                if not (gateway_order_matches and gateway_amount_matches and gateway_currency_matches and gateway_is_captured):
                    logger.warning(
                        "Razorpay payment %s does not match payment attempt %s",
                        razorpay_payment_id, payment.pk,
                    )
                    if gateway_order_matches and gateway_is_captured and (
                        not gateway_amount_matches or not gateway_currency_matches
                    ):
                        actual_amount = int(gateway_payment.get("amount", 0))
                        already_refunded = int(gateway_payment.get("amount_refunded", 0))
                        remaining = max(actual_amount - already_refunded, 0)
                        if remaining > 0:
                            refund = gateway.payment.refund(
                                razorpay_payment_id,
                                {
                                    "amount": remaining,
                                    "notes": {
                                        "airway_payment_id": str(payment.pk),
                                        "reason": "Captured amount did not match current payment attempt",
                                    },
                                },
                            )
                        else:
                            refund = {"status": "already_refunded"}
                        payment.razorpay_payment_id = razorpay_payment_id
                        payment.status = Payment.Status.REFUNDED
                        payment.failed_at = timezone.now()
                        payment.raw_response = {
                            **(payment.raw_response or {}),
                            "automatic_refund": refund,
                            "gateway_amount": actual_amount,
                            "expected_amount": int(payment.amount * 100),
                            "reason": "Razorpay capture did not match payment attempt.",
                        }
                        payment.save(update_fields=["razorpay_payment_id", "status", "failed_at", "raw_response", "updated_at"])
                        Notification.objects.create(
                            user=payment.customer,
                            type=Notification.Type.SYSTEM_ANNOUNCEMENT,
                            title="Payment reversed",
                            body="A payment amount did not match the current order total and was automatically reversed. Please review your order and try again.",
                            channel=Notification.Channel.IN_APP,
                            data={"payment_id": payment.pk, "order_id": payment.order_id},
                        )
                        return Response(
                            {"detail": "Mismatched captured payment was reversed.", "status": payment.status},
                            status=status.HTTP_200_OK,
                        )
                    return Response(
                        {"detail": "Gateway payment details do not match this payment attempt."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            except Exception:
                logger.exception("Could not confirm Razorpay payment details for %s", payment.pk)
                return Response(
                    {"detail": "Could not confirm payment with Razorpay. Please retry shortly."},
                    status=status.HTTP_502_BAD_GATEWAY,
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

        # Handle payment.captured event (Razorpay uses 'payment.captured' for successful payments)
        if event_type == 'payment.captured':
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

            # Validate amount/currency. A captured mismatch is refunded rather
            # than ignored, so stale attempts cannot leave an untracked charge.
            expected_amount_paise = int(payment.amount * 100)
            expected_currency = payment.order.currency if payment.order_id else "INR"
            amount_matches = razorpay_amount == expected_amount_paise
            currency_matches = not razorpay_currency or razorpay_currency == expected_currency
            if not amount_matches or not currency_matches:
                logger.warning(
                    "Webhook mismatch for payment %s: expected %s %s, received %s %s",
                    payment.id, expected_amount_paise, expected_currency,
                    razorpay_amount, razorpay_currency,
                )
                if (
                    payment_entity.get("status") == "captured"
                    and order_id == payment.razorpay_order_id
                    and razorpay_amount
                ):
                    try:
                        import razorpay
                        gateway = razorpay.Client(
                            auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
                        )
                        gateway_payment = gateway.payment.fetch(payment_id)
                        remaining = int(gateway_payment.get("amount", razorpay_amount)) - int(
                            gateway_payment.get("amount_refunded", 0)
                        )
                        refund = gateway.payment.refund(
                            payment_id,
                            {
                                "amount": remaining,
                                "notes": {
                                    "airway_payment_id": str(payment.id),
                                    "reason": "Webhook capture did not match the current payment attempt",
                                },
                            },
                        ) if remaining > 0 else {"status": "already_refunded"}
                        if payment.wallet_amount > 0:
                            from apps.wallet.services import release_wallet_reservation
                            release_wallet_reservation(
                                payment,
                                reason="Stale payment attempt reversed after webhook validation.",
                            )
                        payment.razorpay_payment_id = payment_id
                        payment.status = Payment.Status.REFUNDED
                        payment.failed_at = timezone.now()
                        payment.raw_response = {
                            **(payment.raw_response or {}),
                            "automatic_refund": refund,
                            "gateway_amount": razorpay_amount,
                            "expected_amount": expected_amount_paise,
                            "reason": "Webhook capture did not match payment attempt.",
                        }
                        payment.save(update_fields=["razorpay_payment_id", "status", "failed_at", "raw_response", "updated_at"])
                        Notification.objects.create(
                            user=payment.customer,
                            type=Notification.Type.SYSTEM_ANNOUNCEMENT,
                            title="Payment reversed",
                            body="A captured payment did not match the current order amount and was automatically reversed. Please review your order.",
                            channel=Notification.Channel.IN_APP,
                            data={"payment_id": payment.id, "order_id": payment.order_id},
                        )
                        return Response({"status": "ok", "detail": "Mismatched capture reversed."})
                    except Exception:
                        logger.exception("Failed to refund mismatched webhook capture for payment %s", payment.id)
                        return Response(
                            {"detail": "Captured payment mismatch requires reconciliation."},
                            status=status.HTTP_502_BAD_GATEWAY,
                        )
                return Response(
                    {"detail": "Amount or currency mismatch"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Process the payment - verify and mark as PAID
            return _process_verified_payment(
                payment=payment,
                razorpay_payment_id=payment_id,
                razorpay_order_id=payment.razorpay_order_id,
                customer=payment.customer,
                source="webhook"
            )

        elif event_type in ("refund.processed", "refund.failed"):
            refund_entity = payload.get("payload", {}).get("refund", {}).get("entity", {})
            gateway_refund_id = refund_entity.get("id")
            if gateway_refund_id:
                from .refunds import reconcile_gateway_refund

                refund = reconcile_gateway_refund(
                    gateway_refund_id,
                    event_type,
                    refund_entity.get("status", ""),
                )
                if refund is not None:
                    payment = refund.payment
                    payment.raw_response = {
                        **(payment.raw_response or {}),
                        "last_gateway_refund_event": {
                            "event": event_type,
                            "refund_id": gateway_refund_id,
                            "status": refund_entity.get("status"),
                            "amount": refund_entity.get("amount"),
                            "updated_at": timezone.now().isoformat(),
                        },
                    }
                    payment.save(update_fields=["raw_response", "updated_at"])
            return Response({"status": "ok"})

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
                    payment.raw_response = {
                        **(payment.raw_response or {}),
                        "last_gateway_attempt_event": payload,
                    }
                    payment.save(update_fields=["raw_response", "updated_at"])
                    logger.info("Order payment %s attempt failed; reservation retained for retry", payment.id)
                else:
                    payment.status = Payment.Status.FAILED
                    payment.failed_at = timezone.now()
                    payment.raw_response = {
                        **(payment.raw_response or {}),
                        "last_gateway_attempt_event": payload,
                    }
                    payment.save(update_fields=["status", "failed_at", "raw_response", "updated_at"])
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