"""Line-level cancellation and refund accounting for split-payment parent orders."""
import logging
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.bookings.models import (
    Booking,
    BookingAssignment,
    BookingStatusHistory,
    Order,
    OrderItem,
    WorkerOffer,
)
from apps.notifications.models import Notification
from apps.wallet.models import Wallet, WalletTransaction
from .lifecycle import (
    CANCELLATION_FEE,
    PaymentLifecycleError,
    as_money,
    customer_cancellation_terms,
)
from .models import (
    BookingFinancialPlan,
    Payment,
    PaymentAllocation,
    PaymentInstallment,
    RefundRecord,
)

logger = logging.getLogger(__name__)
ZERO = Decimal("0.00")


class OrderLineCancellationError(Exception):
    """A safe business-rule rejection for parent-order line cancellation."""


def _credit_wallet_refund(record):
    """Credit the wallet component once, independently of gateway settlement."""
    if record.wallet_refund_amount <= ZERO or record.wallet_refunded_at:
        return
    wallet, _ = Wallet.objects.get_or_create(user=record.booking.customer)
    wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)
    reference = f"refund_record:{record.pk}"
    if not WalletTransaction.objects.filter(
        wallet=wallet,
        reference_id=reference,
        type=WalletTransaction.Type.REFUND,
        status=WalletTransaction.Status.COMPLETED,
    ).exists():
        wallet.balance += record.wallet_refund_amount
        wallet.save(update_fields=["balance", "updated_at"])
        WalletTransaction.objects.create(
            wallet=wallet,
            type=WalletTransaction.Type.REFUND,
            amount=record.wallet_refund_amount,
            description=f"Wallet refund for cancelled AIRway order line #{record.booking_id}",
            status=WalletTransaction.Status.COMPLETED,
            reference_id=reference,
        )
    record.wallet_refunded_at = timezone.now()
    record.save(update_fields=["wallet_refunded_at", "updated_at"])


def cancel_parent_order_line(*, order_id, booking_id, customer, reason=""):
    """Cancel one unstarted split-payment order line and reconcile its own advance.

    Gateway calls are deliberately performed after the database transaction.
    The remaining order lines retain their original snapshots and assignments.
    """
    refund_record = None
    should_dispatch = False
    response_terms = None

    with transaction.atomic():
        order = Order.objects.select_for_update().get(
            pk=order_id, customer=customer,
        )
        item = OrderItem.objects.select_for_update().select_related("booking").filter(
            order=order, booking_id=booking_id,
        ).first()
        if item is None:
            raise OrderLineCancellationError("Service line not found in this order.")

        booking = Booking.objects.select_for_update().get(pk=booking_id)
        if booking.status == Booking.Status.CANCELLED:
            raise OrderLineCancellationError("This service line is already cancelled.")
        if booking.status in (
            Booking.Status.IN_PROGRESS,
            Booking.Status.COMPLETED,
            Booking.Status.DISPUTED,
        ):
            raise OrderLineCancellationError(
                "A service cannot be cancelled after it has started. Contact AIRway support for a dispute or assistance."
            )
        if not booking.can_cancel:
            raise OrderLineCancellationError("This service cannot be cancelled in its current state.")

        assignment = BookingAssignment.objects.select_for_update().filter(
            booking=booking,
        ).first()
        if assignment and assignment.started_at:
            raise OrderLineCancellationError(
                "A service cannot be cancelled after its start OTP has been verified. You can raise a support or dispute request."
            )

        plan = BookingFinancialPlan.objects.select_for_update().filter(
            booking=booking,
        ).first()
        if plan is None:
            raise OrderLineCancellationError(
                "Partial cancellation is currently supported only for split-payment orders. Contact AIRway support for this legacy order."
            )

        plans_count = BookingFinancialPlan.objects.filter(
            booking__order_item__order=order,
        ).count()
        item_count = order.items.count()
        if plans_count != item_count:
            raise OrderLineCancellationError(
                "This order has mixed payment lifecycles and cannot be partially cancelled automatically."
            )

        payment = Payment.objects.select_for_update().filter(order=order).first()
        if payment and payment.status == Payment.Status.PENDING:
            raise OrderLineCancellationError(
                "An order payment is currently in progress. Finish or allow that payment attempt to reconcile before cancelling an individual service."
            )

        allocation = PaymentAllocation.objects.select_for_update().filter(
            installment__financial_plan=plan,
            installment__kind=PaymentInstallment.Kind.ADVANCE,
            payment__isnull=False,
        ).select_related("payment").first()

        if payment and payment.status == Payment.Status.PAID and allocation is None:
            raise OrderLineCancellationError(
                "The captured advance cannot be reconciled to this service line. AIRway support must review the payment before cancellation."
            )
        if allocation and (payment is None or payment.status != Payment.Status.PAID):
            raise OrderLineCancellationError(
                "The service advance is linked to a payment that is not in a settled state. AIRway support must reconcile it first."
            )
        if allocation and allocation.payment_id != payment.pk:
            raise OrderLineCancellationError(
                "The service advance is linked to an unexpected checkout payment."
            )

        collected = allocation.amount if allocation else ZERO
        try:
            response_terms = customer_cancellation_terms(
                booking.scheduled_at,
                collected,
                worker_accepted=bool(assignment and assignment.accepted_at),
                now=timezone.now(),
            )
        except PaymentLifecycleError as exc:
            raise OrderLineCancellationError(str(exc)) from exc

        if allocation and response_terms["refund_amount"] > ZERO:
            gross = as_money(allocation.amount)
            refund_total = min(as_money(response_terms["refund_amount"]), gross)
            fee = gross - refund_total
            # The policy fee is taken from wallet tender first. This makes the
            # two source refunds reconcile exactly to the approved net refund.
            wallet_refund = max(allocation.wallet_amount - fee, ZERO)
            remaining_fee = max(fee - allocation.wallet_amount, ZERO)
            gateway_refund = max(allocation.gateway_amount - remaining_fee, ZERO)
            if gateway_refund + wallet_refund != refund_total:
                raise OrderLineCancellationError(
                    "The captured tender allocation does not reconcile to the cancellation refund."
                )
            refund_record, created = RefundRecord.objects.get_or_create(
                idempotency_key=(
                    f"order-line-cancel:order:{order.pk}:booking:{booking.pk}:"
                    f"allocation:{allocation.pk}"
                ),
                defaults={
                    "booking": booking,
                    "payment": allocation.payment,
                    "payment_allocation": allocation,
                    "reason": RefundRecord.Reason.CUSTOMER_CANCELLATION,
                    "gross_amount": gross,
                    "platform_fee": fee,
                    "refund_amount": refund_total,
                    "gateway_refund_amount": gateway_refund,
                    "wallet_refund_amount": wallet_refund,
                    "status": (
                        RefundRecord.Status.REQUESTED
                        if gateway_refund > ZERO
                        else RefundRecord.Status.PROCESSED
                    ),
                    "requested_at": timezone.now(),
                    "processed_at": timezone.now() if gateway_refund <= ZERO else None,
                    "provider_payload": {
                        "policy": response_terms["policy"],
                        "allocation_id": allocation.pk,
                        "gateway_refund_amount": str(gateway_refund),
                        "wallet_refund_amount": str(wallet_refund),
                    },
                },
            )
            if not created:
                raise OrderLineCancellationError(
                    "A refund for this service line already exists. Refresh the order to see its latest status."
                )
            _credit_wallet_refund(refund_record)
            plan.refunded_total += refund_total
            plan.save(update_fields=["refunded_total", "updated_at"])
        elif allocation:
            # The line remains financially closed without issuing a refund.
            plan.refunded_total = plan.refunded_total or ZERO
            plan.save(update_fields=["refunded_total", "updated_at"])

        final_installment = PaymentInstallment.objects.select_for_update().filter(
            financial_plan=plan,
            kind=PaymentInstallment.Kind.FINAL_BALANCE,
        ).first()
        if final_installment and final_installment.status != PaymentInstallment.Status.PAID:
            final_installment.status = PaymentInstallment.Status.CANCELLED
            final_installment.save(update_fields=["status", "updated_at"])
        plan.state = BookingFinancialPlan.State.CANCELLED
        plan.save(update_fields=["state", "updated_at"])

        old_status = booking.status
        now = timezone.now()
        booking.status = Booking.Status.CANCELLED
        booking.cancelled_at = now
        booking.cancellation_reason = reason[:2000]
        booking.cancelled_by = customer
        booking.save(update_fields=[
            "status", "cancelled_at", "cancellation_reason",
            "cancelled_by", "updated_at",
        ])
        BookingStatusHistory.objects.create(
            booking=booking,
            from_status=old_status,
            to_status=Booking.Status.CANCELLED,
            changed_by=customer,
            note=(
                f"Customer cancelled parent-order line. Policy: {response_terms['policy']}; "
                f"collected advance: {collected}; refund: {response_terms['refund_amount']}; "
                f"platform fee: {response_terms['platform_fee']}."
            ),
        )
        Notification.objects.create(
            user=customer,
            type=Notification.Type.BOOKING_CANCELLED,
            title="Service Cancelled",
            body=f"Your {booking.service.title} service in order #{order.pk} has been cancelled.",
            channel=Notification.Channel.IN_APP,
            data={"booking_id": booking.pk, "order_id": order.pk},
        )

        # Release only this booking's assignment. Other lines keep the same
        # worker, preserving the one-worker-per-parent-order invariant.
        if assignment:
            assignment.delete()

        active_bookings = list(
            Booking.objects.filter(order_item__order=order).exclude(
                status=Booking.Status.CANCELLED,
            ).order_by("pk")
        )
        order.metadata = {**(order.metadata or {}), "partially_cancelled": True}
        if not active_bookings:
            order.status = Order.Status.CANCELLED
        else:
            active_assigned = BookingAssignment.objects.filter(
                booking__in=active_bookings,
            ).count()
            if active_assigned == len(active_bookings):
                order.status = (
                    Order.Status.IN_PROGRESS
                    if any(row.status == Booking.Status.IN_PROGRESS for row in active_bookings)
                    else Order.Status.AWAITING_SERVICE
                )
            elif payment and payment.status == Payment.Status.PAID:
                order.status = Order.Status.AWAITING_ASSIGNMENT
                should_dispatch = True
            else:
                order.status = Order.Status.AWAITING_PAYMENT
        order.save(update_fields=["status", "metadata", "updated_at"])

        # Pending offers are for the whole original order. Withdraw them before
        # dispatching a fresh offer scoped to the remaining active lines.
        WorkerOffer.objects.filter(
            order=order, status=WorkerOffer.Status.PENDING,
        ).update(status=WorkerOffer.Status.WITHDRAWN, responded_at=now)

    if should_dispatch:
        from apps.bookings.dispatcher import DispatcherService
        DispatcherService.dispatch_order(order)

    provider_error = None
    if refund_record and refund_record.gateway_refund_amount > ZERO:
        payment_id = refund_record.payment.razorpay_payment_id
        if not payment_id:
            provider_error = "Gateway refund requires manual AIRway reconciliation because the captured payment ID is unavailable."
        else:
            try:
                import razorpay
                gateway = razorpay.Client(
                    auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
                )
                result = gateway.payment.refund(
                    payment_id,
                    {
                        "amount": int(refund_record.gateway_refund_amount * 100),
                        "notes": {
                            "airway_refund_record_id": str(refund_record.pk),
                            "airway_order_id": str(order.pk),
                            "airway_booking_id": str(booking.pk),
                            "airway_policy": response_terms["policy"],
                        },
                    },
                )
                if not result.get("id"):
                    raise ValueError("Razorpay did not return a refund ID.")
                with transaction.atomic():
                    locked_refund = RefundRecord.objects.select_for_update().get(
                        pk=refund_record.pk,
                    )
                    if locked_refund.status != RefundRecord.Status.PROCESSED:
                        locked_refund.provider_refund_id = result["id"]
                        provider_status = result.get("status")
                        locked_refund.status = (
                            RefundRecord.Status.PROCESSED
                            if provider_status == "processed"
                            else RefundRecord.Status.FAILED
                            if provider_status == "failed"
                            else RefundRecord.Status.PENDING
                        )
                        if locked_refund.status == RefundRecord.Status.PROCESSED:
                            locked_refund.processed_at = timezone.now()
                        locked_refund.provider_payload = result
                        locked_refund.save(update_fields=[
                            "provider_refund_id", "status", "processed_at",
                            "provider_payload", "updated_at",
                        ])
                    refund_record = locked_refund
            except Exception as exc:
                logger.exception("Parent order line refund failed for refund %s", refund_record.pk)
                provider_error = str(exc)[:400]
                refund_record.status = RefundRecord.Status.PENDING
                refund_record.provider_payload = {
                    **(refund_record.provider_payload or {}),
                    "submission_error": provider_error,
                    "provider_outcome": "unknown; reconcile using Razorpay refund webhook/dashboard",
                }
                refund_record.save(update_fields=["status", "provider_payload", "updated_at"])

    return {
        "order_id": order.pk,
        "booking_id": booking.pk,
        "order_status": order.status,
        "booking_status": booking.status,
        "refund_id": refund_record.pk if refund_record else None,
        "refund_status": refund_record.status if refund_record else "not_refundable",
        "refund_policy": response_terms["policy"],
        "refund_amount": str(response_terms["refund_amount"]),
        "platform_fee": str(response_terms["platform_fee"]),
        "refund_message": provider_error,
    }
