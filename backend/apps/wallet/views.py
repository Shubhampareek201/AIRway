from rest_framework import status, permissions, viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from django.db import transaction
from decimal import Decimal

from .models import Wallet, WalletTransaction
from .serializers import WalletSerializer, WalletTransactionSerializer, parse_amount


def get_or_create_wallet(user):
    wallet, _ = Wallet.objects.get_or_create(user=user)
    return wallet


class IsAdminUser(permissions.BasePermission):
    """Allow access only to admin users (is_staff=True)."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)


def complete_top_up_transaction(transaction_id, razorpay_payment_id=None):
    """
    Complete a pending wallet top-up transaction.
    Called by payment verification/webhook handlers.

    Returns the updated transaction or None if not found/already completed.
    """
    try:
        with transaction.atomic():
            wallet_tx = WalletTransaction.objects.select_for_update().get(
                id=transaction_id,
                type=WalletTransaction.Type.CREDIT,
                status=WalletTransaction.Status.PENDING
            )
            wallet = wallet_tx.wallet

            wallet_tx.status = WalletTransaction.Status.COMPLETED
            if razorpay_payment_id:
                wallet_tx.reference_id = razorpay_payment_id
            wallet_tx.save()

            wallet.balance += wallet_tx.amount
            wallet.save(update_fields=['balance'])

            return wallet_tx
    except WalletTransaction.DoesNotExist:
        return None


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
        if amount is None:
            return Response(
                {"detail": "A valid amount is required."},
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
            type=WalletTransaction.Type.CREDIT,
            amount=amount,
            description="Wallet top-up (pending Razorpay confirmation)",
            status=WalletTransaction.Status.PENDING,
            reference_id=request.data.get("reference_id", ""),
        )
        serializer = WalletTransactionSerializer(transaction_obj)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class WalletTopUpConfirmView(APIView):
    """Confirm a pending top-up transaction after payment verification."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, transaction_id):
        transaction_obj = complete_top_up_transaction(
            transaction_id,
            request.data.get("razorpay_payment_id")
        )
        if transaction_obj is None:
            return Response(
                {"detail": "Transaction not found or already completed."},
                status=status.HTTP_404_NOT_FOUND
            )
        serializer = WalletTransactionSerializer(transaction_obj)
        return Response(serializer.data)


class WalletRefundView(APIView):
    permission_classes = [permissions.IsAuthenticated]

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