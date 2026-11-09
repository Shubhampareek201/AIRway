import hashlib
import hmac
import logging

import razorpay
from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .installment_service import (
    InstallmentPaymentError,
    create_final_balance_attempt,
    settle_final_balance_attempt,
)
from .models import PaymentAttempt

logger = logging.getLogger(__name__)


class CreateFinalBalancePaymentView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        booking_id = request.data.get("booking_id")
        if not booking_id:
            return Response({"detail": "Provide booking_id."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            attempt, existed = create_final_balance_attempt(
                booking_id=booking_id,
                customer=request.user,
                wallet_amount=request.data.get("wallet_amount", "0.00"),
            )
        except InstallmentPaymentError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception("Could not create final-balance attempt for booking %s", booking_id)
            return Response(
                {"detail": "Could not initialize final payment. Please retry."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        installment = attempt.installment
        response = {
            "attempt_id": attempt.pk,
            "booking_id": installment.financial_plan.booking_id,
            "installment": installment.kind,
            "amount": int(attempt.gateway_amount * 100),
            "total_tender": str(attempt.amount),
            "wallet_amount": str(attempt.wallet_amount),
            "currency": attempt.currency,
            "payment_status": attempt.status,
            "payment_exists": existed,
            "already_paid": attempt.status == PaymentAttempt.Status.CAPTURED,
            "remaining_balance": str(installment.amount_due - installment.amount_captured),
            "order_id": attempt.provider_order_id or "",
        }
        if attempt.gateway_amount > 0 and attempt.provider_order_id:
            response["key_id"] = settings.RAZORPAY_KEY_ID
        return Response(response)


class VerifyInstallmentPaymentView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        order_id = request.data.get("razorpay_order_id")
        payment_id = request.data.get("razorpay_payment_id")
        signature = request.data.get("razorpay_signature")
        if not all((order_id, payment_id, signature)):
            return Response(
                {"detail": "Missing Razorpay verification fields."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        attempt = get_object_or_404(
            PaymentAttempt.objects.select_related("installment__financial_plan__booking"),
            provider_order_id=order_id,
            installment__financial_plan__booking__customer=request.user,
        )
        message = f"{order_id}|{payment_id}"
        expected = hmac.new(
            settings.RAZORPAY_KEY_SECRET.encode(),
            message.encode(),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            return Response(
                {"detail": "Payment signature verification failed."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            gateway = razorpay.Client(
                auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
            )
            provider_payment = gateway.payment.fetch(payment_id)
        except Exception:
            logger.exception("Could not fetch Razorpay payment for attempt %s", attempt.pk)
            return Response(
                {"detail": "Payment status could not be confirmed with Razorpay. Refresh shortly."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        if provider_payment.get("order_id") != order_id:
            return Response({"detail": "Razorpay payment belongs to a different order."}, status=status.HTTP_400_BAD_REQUEST)
        if provider_payment.get("status") != "captured" or not provider_payment.get("captured"):
            return Response(
                {"detail": "Payment is not captured yet. The final balance remains due."},
                status=status.HTTP_409_CONFLICT,
            )
        if provider_payment.get("amount") != int(attempt.gateway_amount * 100):
            return Response({"detail": "Captured amount mismatch."}, status=status.HTTP_400_BAD_REQUEST)
        if (provider_payment.get("currency") or "").upper() != attempt.currency:
            return Response({"detail": "Captured currency mismatch."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            settled = settle_final_balance_attempt(
                attempt_id=attempt.pk,
                razorpay_payment_id=payment_id,
                provider_order_id=order_id,
                amount_paise=provider_payment["amount"],
                currency=provider_payment["currency"],
                source="checkout",
            )
        except InstallmentPaymentError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response({
            "detail": "Final payment captured and allocated.",
            "attempt_id": settled.pk,
            "status": settled.status,
            "booking_id": attempt.installment.financial_plan.booking_id,
        })
