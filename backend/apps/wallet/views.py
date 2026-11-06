import hashlib
import hmac
import logging
from decimal import Decimal

import razorpay
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import status, permissions, viewsets
from rest_framework.views import APIView
from rest_framework.response import Response

from .models import Wallet, WalletTransaction
from .serializers import WalletSerializer, WalletTransactionSerializer, parse_amount

logger = logging.getLogger(__name__)
razorpay_client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


def get_or_create_wallet(user):
    wallet, _ = Wallet.objects.get_or_create(user=user)
    return wallet


class IsAdminUser(permissions.BasePermission):
    """Allow access only to admin users (is_staff=True)."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)


def complete_top_up_transaction(
    transaction_id,
    razorpay_payment_id=None,
    user=None,
    razorpay_order_id=None,
):
    """
    Atomically credit a pending top-up once. Customer-initiated completion is
    scoped to the authenticated wallet owner and the server-stored Razorpay
    order ID. Webhooks may omit user because their signature is verified first.
    """
    with transaction.atomic():
        queryset = WalletTransaction.objects.select_for_update().filter(
            id=transaction_id,
            type=WalletTransaction.Type.CREDIT,
            status=WalletTransaction.Status.PENDING,
        )
        if user is not None:
            queryset = queryset.filter(wallet__user=user)
        if razorpay_order_id:
            queryset = queryset.filter(reference_id=razorpay_order_id)

        wallet_tx = queryset.first()
        if wallet_tx is None:
            return None

        wallet = Wallet.objects.select_for_update().get(pk=wallet_tx.wallet_id)
        wallet_tx.status = WalletTransaction.Status.COMPLETED
        if razorpay_payment_id:
            wallet_tx.razorpay_payment_id = razorpay_payment_id
        wallet_tx.save(update_fields=[
            "status", "razorpay_payment_id", "updated_at"
        ])

        wallet.balance += wallet_tx.amount
        wallet.save(update_fields=["balance", "updated_at"])
        return wallet_tx


class WalletViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Wallet.objects.filter(user=self.request.user)

    def list(self, request):
        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        serializer = WalletSerializer(wallet, context={"request": request})
        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        try:
            wallet = Wallet.objects.get(pk=pk, user=request.user)
        except Wallet.DoesNotExist:
            return Response(
                {"detail": "Wallet not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = WalletSerializer(wallet, context={"request": request})
        return Response(serializer.data)


class WalletTransactionViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def list(self, request):
        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        qs = wallet.transactions.all().order_by("-created_at")
        serializer = WalletTransactionSerializer(qs, many=True)
        return Response(serializer.data)


class WalletBalanceView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        serializer = WalletSerializer(wallet, context={"request": request})
        return Response(serializer.data)


class WalletTransactionsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        qs = wallet.transactions.all().order_by("-created_at")
        serializer = WalletTransactionSerializer(qs, many=True)
        return Response(serializer.data)


class WalletTopUpView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        amount = parse_amount(request.data.get("amount"))
        if amount is None or amount <= 0:
            return Response(
                {"detail": "A valid amount greater than zero is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        normalized_amount = amount.quantize(Decimal("0.01"))
        if normalized_amount != amount:
            return Response(
                {"detail": "Amount can have at most two decimal places."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        amount_paise = int(normalized_amount * 100)
        try:
            razorpay_order = razorpay_client.order.create(data={
                "amount": amount_paise,
                "currency": "INR",
                "receipt": f"wallet_{request.user.id}_{timezone.now().strftime('%Y%m%d%H%M%S%f')}",
                "notes": {"customer_id": str(request.user.id), "purpose": "wallet_top_up"},
            })
        except Exception:
            logger.exception("Razorpay wallet top-up order creation failed for user %s", request.user.id)
            return Response(
                {"detail": "Unable to start wallet top-up. Please try again."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        transaction_obj = WalletTransaction.objects.create(
            wallet=wallet,
            type=WalletTransaction.Type.CREDIT,
            amount=normalized_amount,
            description="Wallet top-up (awaiting Razorpay confirmation)",
            status=WalletTransaction.Status.PENDING,
            reference_id=razorpay_order["id"],
        )
        return Response({
            **WalletTransactionSerializer(transaction_obj).data,
            "order_id": razorpay_order["id"],
            "amount": amount_paise,
            "currency": "INR",
            "key_id": settings.RAZORPAY_KEY_ID,
        }, status=status.HTTP_201_CREATED)


class WalletTopUpConfirmView(APIView):
    """Verify Razorpay checkout signature before crediting the customer's wallet."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, transaction_id):
        razorpay_order_id = request.data.get("razorpay_order_id")
        razorpay_payment_id = request.data.get("razorpay_payment_id")
        razorpay_signature = request.data.get("razorpay_signature")
        if not all([razorpay_order_id, razorpay_payment_id, razorpay_signature]):
            return Response(
                {"detail": "razorpay_order_id, razorpay_payment_id and razorpay_signature are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        wallet_tx = WalletTransaction.objects.filter(
            id=transaction_id,
            wallet__user=request.user,
            type=WalletTransaction.Type.CREDIT,
            status=WalletTransaction.Status.PENDING,
            reference_id=razorpay_order_id,
        ).first()
        if wallet_tx is None:
            return Response(
                {"detail": "Pending top-up not found for this account and Razorpay order."},
                status=status.HTTP_404_NOT_FOUND,
            )

        message = f"{razorpay_order_id}|{razorpay_payment_id}"
        expected_signature = hmac.new(
            settings.RAZORPAY_KEY_SECRET.encode(),
            message.encode(),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected_signature, razorpay_signature):
            return Response(
                {"detail": "Wallet top-up payment signature verification failed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        transaction_obj = complete_top_up_transaction(
            transaction_id,
            razorpay_payment_id=razorpay_payment_id,
            user=request.user,
            razorpay_order_id=razorpay_order_id,
        )
        if transaction_obj is None:
            return Response(
                {"detail": "Top-up is already completed or no longer available."},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(WalletTransactionSerializer(transaction_obj).data)


class WalletRefundView(APIView):
    # A customer must never be able to mint wallet credit by submitting an
    # arbitrary booking ID and amount. Refunds are currently admin-reviewed.
    permission_classes = [IsAdminUser]

    def post(self, request):
        booking_id = request.data.get("booking_id")
        amount = parse_amount(request.data.get("amount"))
        reason = request.data.get("reason", "Refund for cancelled booking")

        if not booking_id or amount is None:
            return Response(
                {"detail": "booking_id and a valid amount are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if amount <= 0:
            return Response(
                {"detail": "Amount must be greater than zero."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        transaction_obj = WalletTransaction.objects.create(
            wallet=wallet,
            type=WalletTransaction.Type.REFUND,
            amount=amount,
            description=reason,
            status=WalletTransaction.Status.COMPLETED,
            reference_id=str(booking_id),
        )
        wallet.balance += amount
        wallet.save()
        serializer = WalletTransactionSerializer(transaction_obj)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class WalletCreditView(APIView):
    """Internal endpoint used by worker earnings / incentives services. Admin-only access."""
    permission_classes = [IsAdminUser]

    def post(self, request):
        user_id = request.data.get("user_id")
        amount = parse_amount(request.data.get("amount"))
        description = request.data.get("description", "Wallet credit")
        reference_id = request.data.get("reference_id", "")

        if not user_id or amount is None:
            return Response(
                {"detail": "user_id and a valid amount are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if amount <= 0:
            return Response(
                {"detail": "Amount must be greater than zero."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from django.contrib.auth import get_user_model
        User = get_user_model()
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return Response(
                {"detail": "User not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        wallet, _ = Wallet.objects.get_or_create(user=user)
        transaction_obj = WalletTransaction.objects.create(
            wallet=wallet,
            type=WalletTransaction.Type.CREDIT,
            amount=amount,
            description=description,
            status=WalletTransaction.Status.COMPLETED,
            reference_id=reference_id,
        )
        wallet.balance += amount
        wallet.save()
        serializer = WalletTransactionSerializer(transaction_obj)
        return Response(serializer.data, status=status.HTTP_201_CREATED)