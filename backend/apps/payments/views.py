import razorpay
import logging
from decimal import Decimal, InvalidOperation
from django.conf import settings
from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db import transaction, IntegrityError

from apps.bookings.models import Booking, Order
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


def create_or_get_order_payment(
    order,
    customer,
    wallet_amount=Decimal("0.00"),
    trigger_source="checkout",
    stage=Payment.Stage.ADVANCE,
):
    """Create or retrieve an idempotent advance or balance payment for an order."""
    try:
        requested = Decimal(str(wallet_amount))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Provide a valid wallet amount.")
    if not requested.is_finite() or requested < 0 or requested.quantize(Decimal("0.01")) != requested:
        raise ValueError("Wallet amount must be non-negative and have at most two decimal places.")
    if order.customer_id != customer.id:
        raise ValueError("Order not found or access denied.")
    if stage not in (Payment.Stage.LEGACY, Payment.Stage.ADVANCE, Payment.Stage.BALANCE):
        raise ValueError("Unsupported order payment stage.")

    items = list(order.items.select_related("booking").order_by("id"))
    if not items:
        raise ValueError("This order has no service bookings.")

    # Keep a deterministic per-service allocation in the order snapshot. The
    # last line receives the rounding remainder so allocations always sum.
    allocation_key = "payment_allocation_v1"
    allocation = order.metadata.get(allocation_key) if isinstance(order.metadata, dict) else None
    if stage != Payment.Stage.LEGACY and not allocation:
        from decimal import ROUND_HALF_UP
        advance_percentage = Decimal(str(getattr(settings, "ORDER_ADVANCE_PERCENTAGE", 30)))
        advance_total = (order.total_amount * advance_percentage / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        balance_total = order.total_amount - advance_total
        advance_rows, balance_rows = [], []
        allocated_advance = Decimal("0.00")
        allocated_balance = Decimal("0.00")
        for index, item in enumerate(items):
            if index == len(items) - 1:
                advance_line = advance_total - allocated_advance
                balance_line = balance_total - allocated_balance
            else:
                ratio = item.line_total / order.total_amount if order.total_amount else Decimal("0")
                advance_line = (advance_total * ratio).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                balance_line = item.line_total - advance_line
                allocated_advance += advance_line
                allocated_balance += balance_line
            advance_rows.append({"order_item_id": item.id, "booking_id": item.booking_id, "amount": str(advance_line)})
            balance_rows.append({"order_item_id": item.id, "booking_id": item.booking_id, "amount": str(balance_line)})
        allocation = {
            "percentage": str(advance_percentage),
            "advance_total": str(advance_total),
            "balance_total": str(balance_total),
            "advance": advance_rows,
            "balance": balance_rows,
        }
        order.metadata = {**(order.metadata or {}), allocation_key: allocation}
        order.save(update_fields=["metadata", "updated_at"])

    active_items = [item for item in items if item.booking.status != Booking.Status.CANCELLED]
    if stage in (Payment.Stage.ADVANCE, Payment.Stage.BALANCE):
        if not active_items:
            raise ValueError("There are no active services remaining to pay for.")
        allocation_rows = allocation.get(
            "advance" if stage == Payment.Stage.ADVANCE else "balance", []
        )
        stage_total = sum(
            (
                Decimal(str(next(
                    (row.get("amount", "0") for row in allocation_rows
                     if row.get("order_item_id") == item.id),
                    "0",
                )))
                for item in active_items
            ),
            Decimal("0.00"),
        )
    else:
        stage_total = order.total_amount
    if stage == Payment.Stage.LEGACY:
        # Idempotent retries must still succeed after the first payment has
        # advanced the order out of AWAITING_PAYMENT (including wallet-only
        # payments, which have no Razorpay order ID).
        paid = Payment.objects.filter(
            order=order,
            stage=Payment.Stage.LEGACY,
            status=Payment.Status.PAID,
        ).first()
        if paid:
            return paid, paid.razorpay_order_id, True
        if order.status != Order.Status.AWAITING_PAYMENT or any(
            item.booking.status != Booking.Status.ASSIGNED for item in items
        ):
            raise ValueError("Legacy full payment is available only for an assigned order awaiting payment.")
    elif stage == Payment.Stage.ADVANCE:
        if Payment.objects.filter(order=order, stage=Payment.Stage.ADVANCE, status=Payment.Status.PAID).exists():
            paid = Payment.objects.get(order=order, stage=Payment.Stage.ADVANCE, status=Payment.Status.PAID)
            return paid, paid.razorpay_order_id, True
        if order.status not in (Order.Status.AWAITING_ASSIGNMENT, Order.Status.AWAITING_PAYMENT, Order.Status.PARTIALLY_CANCELLED):
            raise ValueError("This order is not eligible for an advance payment.")
    else:
        if not Payment.objects.filter(order=order, stage=Payment.Stage.ADVANCE, status=Payment.Status.PAID).exists():
            raise ValueError("The advance payment must be completed first.")
        if any(item.booking.status != Booking.Status.COMPLETED for item in active_items):
            raise ValueError("Final balance is available only after every active service is completed and verified.")
        if Payment.objects.filter(order=order, stage=Payment.Stage.BALANCE, status=Payment.Status.PAID).exists():
            paid = Payment.objects.get(order=order, stage=Payment.Stage.BALANCE, status=Payment.Status.PAID)
            return paid, paid.razorpay_order_id, True

    if stage_total <= 0:
        raise ValueError("Payment amount must be greater than zero.")
    if requested > stage_total:
        raise ValueError("Wallet amount cannot exceed the amount due for this payment stage.")
    if requested > 0 and order.currency != "INR":
        raise ValueError("AIRway wallet can only be used for INR orders.")

    gateway_order_created = False
    with transaction.atomic():
        locked_order = Order.objects.select_for_update().get(pk=order.pk, customer=customer)
        payment = Payment.objects.select_for_update().filter(
            order=locked_order, stage=stage
        ).first()
        # Check the settled record before validating the pre-payment order
        # state: successful retries naturally arrive after the order changed.
        if payment and payment.status == Payment.Status.PAID:
            return payment, payment.razorpay_order_id, True

        if stage in (Payment.Stage.ADVANCE, Payment.Stage.BALANCE):
            locked_allocation = (locked_order.metadata or {}).get(allocation_key, {})
            locked_rows = locked_allocation.get(
                "advance" if stage == Payment.Stage.ADVANCE else "balance", []
            )
            locked_items = list(locked_order.items.select_related("booking"))
            locked_active_items = [
                item for item in locked_items
                if item.booking.status != Booking.Status.CANCELLED
            ]
            locked_stage_total = sum(
                (
                    Decimal(str(next(
                        (row.get("amount", "0") for row in locked_rows
                         if row.get("order_item_id") == item.id),
                        "0",
                    )))
                    for item in locked_active_items
                ),
                Decimal("0.00"),
            )
            if locked_stage_total != stage_total:
                raise ValueError("The order changed while checkout was starting. Refresh the order and retry.")
            if stage == Payment.Stage.BALANCE and (
                not locked_active_items
                or any(item.booking.status != Booking.Status.COMPLETED for item in locked_active_items)
            ):
                raise ValueError("Final balance is available only after every active service is completed and verified.")
        elif stage == Payment.Stage.LEGACY:
            locked_items = list(locked_order.items.select_related("booking"))
            if locked_order.status != Order.Status.AWAITING_PAYMENT or any(
                item.booking.status != Booking.Status.ASSIGNED for item in locked_items
            ):
                raise ValueError("Legacy full payment is no longer available for this order.")

        if (
            payment
            and payment.wallet_amount != requested
            and payment.status not in (Payment.Status.FAILED, Payment.Status.REFUNDED)
        ):
            raise ValueError("A payment attempt already exists with a different wallet amount.")
        expected_gateway_amount = stage_total - requested
        if (
            payment
            and payment.razorpay_order_id
            and payment.status in (Payment.Status.PENDING, Payment.Status.FAILED)
            and payment.amount != expected_gateway_amount
        ):
            raise ValueError(
                "A previous Razorpay attempt has a different amount and is still reconciling. Please wait before retrying this payment stage."
            )
        if payment is None:
            payment = Payment.objects.create(
                order=locked_order,
                customer=customer,
                stage=stage,
                amount=stage_total - requested,
                wallet_amount=requested,
                method=Payment.Method.WALLET if requested == stage_total else Payment.Method.RAZORPAY,
                status=Payment.Status.PENDING,
            )
        elif payment.status in (Payment.Status.FAILED, Payment.Status.REFUNDED):
            was_refunded = payment.status == Payment.Status.REFUNDED
            payment.status = Payment.Status.PENDING
            payment.failed_at = None
            payment.amount = stage_total - requested
            payment.wallet_amount = requested
            fields = ["status", "failed_at", "amount", "wallet_amount", "updated_at"]
            if was_refunded:
                payment.razorpay_order_id = ""
                payment.razorpay_payment_id = ""
                payment.razorpay_signature = ""
                payment.raw_response = {}
                fields += ["razorpay_order_id", "razorpay_payment_id", "razorpay_signature", "raw_response"]
            payment.save(update_fields=fields)
        # Persist the exact captured wallet/gateway split per service line.
        # This snapshot is immutable evidence for later partial cancellations.
        from decimal import ROUND_HALF_UP
        if stage in (Payment.Stage.ADVANCE, Payment.Stage.BALANCE):
            line_values = []
            for active_item in locked_active_items:
                line_value = Decimal(str(next(
                    (row.get("amount", "0") for row in locked_rows
                     if row.get("order_item_id") == active_item.id),
                    "0",
                )))
                if line_value > 0:
                    line_values.append((active_item, line_value))
        else:
            line_values = [(item, item.line_total) for item in locked_items if item.line_total > 0]
        service_rows = []
        wallet_allocated = Decimal("0.00")
        for index, (active_item, line_value) in enumerate(line_values):
            if index == len(line_values) - 1:
                wallet_line = requested - wallet_allocated
            else:
                wallet_line = (requested * line_value / stage_total).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                wallet_line = min(
                    wallet_line,
                    max(Decimal("0.00"), requested - wallet_allocated),
                )
                wallet_allocated += wallet_line
            wallet_line = max(Decimal("0.00"), min(wallet_line, line_value))
            service_rows.append({
                "order_item_id": active_item.id,
                "booking_id": active_item.booking_id,
                "total": str(line_value),
                "wallet_amount": str(wallet_line),
                "gateway_amount": str(line_value - wallet_line),
            })
        payment.raw_response = {
            **(payment.raw_response or {}),
            "service_allocation_v1": service_rows,
        }
        payment.save(update_fields=["raw_response", "updated_at"])

        if requested > 0:
            from apps.wallet.services import reserve_wallet_amount
            reserve_wallet_amount(payment, requested)

        # Create the Razorpay order while holding the parent-order lock. This
        # prevents concurrent checkout taps from creating multiple gateway
        # orders for the same stage record.
        if payment.amount > 0 and not payment.razorpay_order_id:
            gateway_order = client.order.create(data={
                "amount": int(payment.amount * 100),
                "currency": locked_order.currency,
                "receipt": f"airway_{stage}_{locked_order.id}_{payment.id}",
                "notes": {
                    "airway_order_id": str(locked_order.id),
                    "payment_stage": stage,
                    "customer_id": str(customer.id),
                    "wallet_amount": str(payment.wallet_amount),
                },
            })
            payment.razorpay_order_id = gateway_order["id"]
            payment.save(update_fields=["razorpay_order_id", "updated_at"])
            gateway_order_created = True

    if payment.amount == 0:
        from .verify_view import _process_verified_payment
        result = _process_verified_payment(payment, "", "", customer, "wallet")
        if getattr(result, "status_code", 500) >= 400:
            raise ValueError("Wallet payment could not be completed. Please retry.")
        payment.refresh_from_db()
        return payment, "", False

    if payment.razorpay_order_id:
        if gateway_order_created:
            logger.info("Created %s payment for order %s (payment %s, %s)", stage, locked_order.id, payment.id, trigger_source)
        return payment, payment.razorpay_order_id, not gateway_order_created
    raise ValueError("Razorpay order could not be initialized. Please retry.")


class CreateOrderView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        parent_order_id = request.data.get("order_id")
        booking_id = request.data.get("booking_id")

        if parent_order_id:
            try:
                parent_order = Order.objects.get(pk=parent_order_id, customer=request.user)
            except Order.DoesNotExist:
                return Response({"detail": "Order not found or access denied."}, status=status.HTTP_404_NOT_FOUND)
            try:
                raw_wallet_amount = request.data.get("wallet_amount", "0.00")
                requested_stage = request.data.get("stage")
                if not requested_stage:
                    # New checkout orders always start with the 30% advance.
                    # Preserve the legacy full-settlement path only for orders
                    # that were already assigned before staged checkout existed.
                    legacy_assigned_order = (
                        parent_order.status == Order.Status.AWAITING_PAYMENT
                        and parent_order.items.exclude(
                            booking__status=Booking.Status.CANCELLED
                        ).exists()
                        and not parent_order.items.exclude(
                            booking__status__in=(
                                Booking.Status.ASSIGNED,
                                Booking.Status.CANCELLED,
                            )
                        ).exists()
                        and not (parent_order.metadata or {}).get("payment_allocation_v1")
                    )
                    requested_stage = (
                        Payment.Stage.LEGACY if legacy_assigned_order
                        else Payment.Stage.ADVANCE
                    )
                if requested_stage == Payment.Stage.LEGACY:
                    legacy_assigned_order = (
                        parent_order.status == Order.Status.AWAITING_PAYMENT
                        and parent_order.items.exclude(
                            booking__status=Booking.Status.CANCELLED
                        ).exists()
                        and not parent_order.items.exclude(
                            booking__status__in=(
                                Booking.Status.ASSIGNED,
                                Booking.Status.CANCELLED,
                            )
                        ).exists()
                        and not (parent_order.metadata or {}).get("payment_allocation_v1")
                    )
                    if not legacy_assigned_order:
                        return Response(
                            {"detail": "Full payment is available only to previously assigned legacy orders. New bookings require a 30% advance before worker dispatch."},
                            status=status.HTTP_400_BAD_REQUEST,
                        )
                if requested_stage not in (
                    Payment.Stage.LEGACY, Payment.Stage.ADVANCE, Payment.Stage.BALANCE
                ):
                    return Response({"detail": "stage must be 'legacy', 'advance' or 'balance'."}, status=status.HTTP_400_BAD_REQUEST)
                payment, razorpay_order_id, already_existed = create_or_get_order_payment(
                    order=parent_order,
                    customer=request.user,
                    wallet_amount=raw_wallet_amount,
                    trigger_source="checkout",
                    stage=requested_stage,
                )
            except ValueError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
            except Exception:
                logger.exception("Order payment creation failed for order %s", parent_order.id)
                return Response({"detail": "Failed to create payment order. Please try again."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            response_data = {
                "order_id": razorpay_order_id,
                "amount": int(payment.amount * 100),
                "total_amount": str(parent_order.total_amount),
                "payment_stage": payment.stage,
                "stage_amount": str(payment.amount + payment.wallet_amount),
                "wallet_amount": str(payment.wallet_amount),
                "currency": parent_order.currency,
                "payment_exists": already_existed,
                "fully_paid_by_wallet": payment.status == Payment.Status.PAID and payment.method == Payment.Method.WALLET,
                "already_paid": payment.status == Payment.Status.PAID,
                "payment_status": payment.status,
                "airway_order_id": parent_order.id,
                "payment_id": payment.id,
            }
            if razorpay_order_id:
                response_data["key_id"] = settings.RAZORPAY_KEY_ID
            return Response(response_data)

        if not booking_id:
            return Response(
                {"detail": "Provide order_id for a multi-service order or booking_id for a single booking."},
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            try:
                booking = Booking.objects.select_for_update().select_related(
                    "address", "service", "variant"
                ).get(pk=booking_id, customer=request.user)
            except Booking.DoesNotExist:
                return Response(
                    {"detail": "Booking not found or access denied."},
                    status=status.HTTP_404_NOT_FOUND
                )
            from apps.bookings.models import OrderItem
            order_item = OrderItem.objects.filter(booking=booking).select_related("order").first()
            if order_item:
                parent_order = order_item.order
            else:
                # Convert pre-existing legacy bookings once; all new attempts
                # use the same 30% advance / 70% post-completion balance flow.
                snapshot = booking.pricing_snapshot or {}
                subtotal = Decimal(str(snapshot.get("subtotal", booking.total_amount)))
                tax = Decimal(str(snapshot.get("tax", "0")))
                parent_order = Order.objects.create(
                    customer=request.user, address=booking.address,
                    subtotal=subtotal, tax_amount=tax,
                    total_amount=Decimal(str(booking.total_amount)),
                    metadata={"checkout_source": "legacy_single_booking_migration"},
                )
                OrderItem.objects.create(
                    order=parent_order, booking=booking,
                    quantity=max(int(snapshot.get("quantity", 1) or 1), 1),
                    service_snapshot={
                        "service_id": booking.service_id,
                        "service_title": booking.service.title,
                        "variant_id": booking.variant_id,
                        "variant_title": booking.variant.title if booking.variant_id else "",
                    },
                    pricing_snapshot=snapshot, line_subtotal=subtotal,
                    tax_amount=tax, line_total=Decimal(str(booking.total_amount)),
                )

        payment_stage = Payment.Stage.ADVANCE
        if (
            not order_item
            and booking.status == Booking.Status.ASSIGNED
            and getattr(booking, "assignment", None) is not None
        ):
            # Preserve settlement for an already assigned booking from the
            # pre-staged-payment release. This exception is never used for new
            # pending bookings.
            parent_order.status = Order.Status.AWAITING_PAYMENT
            parent_order.save(update_fields=["status", "updated_at"])
            payment_stage = Payment.Stage.LEGACY

        try:
            payment, order_id, already_existed = create_or_get_order_payment(
                order=parent_order, customer=request.user,
                wallet_amount=request.data.get("wallet_amount", "0.00"),
                trigger_source="single_booking_checkout",
                stage=payment_stage,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception("Single booking advance payment creation failed")
            return Response(
                {"detail": "Failed to create advance payment order. Please try again."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        response_data = {
            "order_id": order_id, "amount": int(payment.amount * 100),
            "total_amount": str(parent_order.total_amount),
            "payment_stage": payment.stage,
            "stage_amount": str(payment.amount + payment.wallet_amount),
            "wallet_amount": str(payment.wallet_amount),
            "currency": parent_order.currency,
            "payment_exists": already_existed,
            "fully_paid_by_wallet": payment.status == Payment.Status.PAID and payment.method == Payment.Method.WALLET,
            "already_paid": payment.status == Payment.Status.PAID,
            "payment_status": payment.status,
            "airway_order_id": parent_order.pk, "payment_id": payment.pk,
        }
        if order_id:
            response_data["key_id"] = settings.RAZORPAY_KEY_ID
        return Response(response_data)
