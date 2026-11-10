"""Safe reassignment when an accepted split-payment worker cannot fulfil a job."""
import logging
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.bookings.models import (
    Booking, BookingAssignment, BookingStatusHistory, Order, OrderItem, WorkerOffer,
)
from apps.notifications.models import Notification
from apps.payments.models import (
    BookingFinancialPlan, PaymentAllocation, PaymentInstallment, RefundRecord,
)

logger = logging.getLogger(__name__)


class WorkerUnavailabilityError(Exception):
    """Expected lifecycle rejection for an invalid worker-unavailability request."""


def release_split_payment_assignment(*, assignment_id, worker_user, reason):
    """Atomically release a pre-start assignment and re-dispatch using existing rules.

    Parent orders are released as a unit so the same-worker/all-lines invariant
    remains intact. Captured advances and financial plans are deliberately kept.
    """
    item_ref = OrderItem.objects.filter(booking__assignment__pk=assignment_id).values(
        "order_id", "booking_id"
    ).first()
    order_id = item_ref["order_id"] if item_ref else None

    with transaction.atomic():
        order = None
        if order_id:
            order = Order.objects.select_for_update().get(pk=order_id)

        assignment_ref = BookingAssignment.objects.select_related(
            "booking", "worker__user"
        ).get(pk=assignment_id)
        if assignment_ref.worker.user_id != worker_user.pk:
            raise WorkerUnavailabilityError("This assignment does not belong to you.")

        booking_ids = (
            list(
                OrderItem.objects.filter(order_id=order_id)
                .exclude(booking__status=Booking.Status.CANCELLED)
                .order_by("booking_id")
                .values_list("booking_id", flat=True)
            )
            if order_id else [assignment_ref.booking_id]
        )
        bookings = list(
            Booking.objects.select_for_update()
            .filter(pk__in=booking_ids)
            .select_related("service")
            .order_by("pk")
        )
        assignments = list(
            BookingAssignment.objects.select_for_update()
            .filter(booking_id__in=booking_ids)
            .select_related("worker__user", "booking")
            .order_by("booking_id")
        )

        if not bookings or len(assignments) != len(bookings):
            raise WorkerUnavailabilityError(
                "The complete assignment could not be verified. Contact AIRway support."
            )
        if any(
            assignment.worker_id != assignment_ref.worker_id
            or not assignment.accepted_at
            or assignment.started_at
            for assignment in assignments
        ):
            raise WorkerUnavailabilityError(
                "This order is no longer eligible for automatic reassignment."
            )
        if any(
            booking.status != Booking.Status.ASSIGNED
            or not BookingFinancialPlan.objects.filter(booking=booking).exists()
            for booking in bookings
        ):
            raise WorkerUnavailabilityError(
                "Only accepted, not-yet-started split-payment jobs can use this action."
            )

        now = timezone.now()
        old_statuses = {booking.pk: booking.status for booking in bookings}
        for booking in bookings:
            booking.status = Booking.Status.CONFIRMED
            booking.save(update_fields=["status", "updated_at"])
            BookingStatusHistory.objects.create(
                booking=booking,
                from_status=old_statuses[booking.pk],
                to_status=Booking.Status.CONFIRMED,
                changed_by=worker_user,
                note=f"Accepted worker reported unable to fulfil before start OTP. Reason: {reason[:500]}",
            )

        offer_scope = (
            WorkerOffer.objects.filter(order_id=order_id)
            if order_id
            else WorkerOffer.objects.filter(
                booking_id=booking_ids[0], order__isnull=True,
            )
        )
        offer_scope.filter(
            status__in=[WorkerOffer.Status.ACCEPTED, WorkerOffer.Status.PENDING],
        ).update(status=WorkerOffer.Status.WITHDRAWN, responded_at=now)

        BookingAssignment.objects.filter(pk__in=[row.pk for row in assignments]).delete()

        if order:
            order.status = Order.Status.AWAITING_ASSIGNMENT
            order.save(update_fields=["status", "updated_at"])

        for booking in bookings:
            Notification.objects.create(
                user=booking.customer,
                type=Notification.Type.WORKER_UNAVAILABLE,
                title="Finding Another Professional",
                body="Your professional is unavailable. AIRway is arranging another eligible professional; your payment remains protected.",
                channel=Notification.Channel.IN_APP,
                data={
                    "booking_id": booking.pk,
                    "order_id": order.pk if order else None,
                    "reason": "worker_unavailable",
                },
            )

    dispatch_pending = False
    dispatch_error = False
    try:
        from apps.bookings.dispatcher import DispatcherService
        if order:
            offers = DispatcherService.dispatch_order(order)
        else:
            offers = DispatcherService.dispatch_offers(bookings[0])
        dispatch_pending = not bool(offers)
    except Exception:
        dispatch_pending = True
        dispatch_error = True
        logger.exception(
            "Re-dispatch failed after worker unavailability for assignment %s",
            assignment_id,
        )

    # Only the configured maximum number of completed offer batches is a
    # terminal dispatch outcome. No eligible worker right now, disabled
    # dispatch, and transient errors remain retryable and must not trigger a
    # premature customer cancellation/refund.
    if not dispatch_error and _configured_batches_exhausted(
        order_id=order_id, booking_ids=booking_ids,
    ):
        refund_status = _cancel_unfulfillable_bookings(
            order_id=order_id,
            booking_ids=booking_ids,
            worker_user=worker_user,
            reason=reason,
        )
        if refund_status:
            return {
                "detail": (
                    "No eligible professional accepted within the configured dispatch batches. "
                    "The service was cancelled and the full captured advance is recorded for refund."
                ),
                "status": "cancelled",
                "booking_ids": booking_ids,
                "order_id": order_id,
                "dispatch_pending": False,
                "refund_status": refund_status,
            }
        return {
            "detail": "No eligible professional accepted within the configured dispatch batches. AIRway could not safely reconcile the captured payment; support review is required before the service can be closed.",
            "status": "awaiting_assignment",
            "booking_ids": booking_ids,
            "order_id": order_id,
            "dispatch_pending": True,
            "refund_status": "reconciliation_required",
        }

    return {
        "detail": "Assignment released. AIRway is looking for another eligible professional.",
        "status": "awaiting_assignment",
        "booking_ids": booking_ids,
        "order_id": order_id,
        "dispatch_pending": dispatch_pending,
    }


def _configured_batches_exhausted(*, order_id, booking_ids):
    from django.db.models import Max
    from apps.bookings.models import DispatchAttempt, DispatchConfiguration

    config = DispatchConfiguration.get_solo()
    if not config.is_enabled:
        return False
    max_batches = max(int(config.max_batches or 1), 1)
    offers = (
        WorkerOffer.objects.filter(order_id=order_id)
        if order_id
        else WorkerOffer.objects.filter(
            booking_id=booking_ids[0], order__isnull=True,
        )
    )
    if offers.filter(status__in=[WorkerOffer.Status.PENDING, WorkerOffer.Status.ACCEPTED]).exists():
        return False
    attempts = (
        DispatchAttempt.objects.filter(order_id=order_id)
        if order_id
        else DispatchAttempt.objects.filter(booking_id=booking_ids[0])
    )
    last_offer_batch = offers.aggregate(value=Max("batch_number"))["value"] or 0
    last_attempt_batch = attempts.aggregate(value=Max("batch_number"))["value"] or 0
    return max(last_offer_batch, last_attempt_batch) >= max_batches


def finalize_exhausted_dispatch(*, order_id=None, booking_id=None):
    """Finalize a split-payment target after its configured dispatch batches end."""
    if order_id:
        booking_ids = list(
            OrderItem.objects.filter(order_id=order_id)
            .exclude(booking__status=Booking.Status.CANCELLED)
            .order_by("booking_id")
            .values_list("booking_id", flat=True)
        )
    elif booking_id:
        booking_ids = [booking_id]
    else:
        return None
    if not booking_ids or not _configured_batches_exhausted(
        order_id=order_id, booking_ids=booking_ids,
    ):
        return None
    if BookingFinancialPlan.objects.filter(booking_id__in=booking_ids).count() != len(booking_ids):
        return None
    return _cancel_unfulfillable_bookings(
        order_id=order_id,
        booking_ids=booking_ids,
        worker_user=None,
        reason="No eligible professional accepted within the configured dispatch batches.",
    )


def _cancel_unfulfillable_bookings(*, order_id, booking_ids, worker_user, reason):
    """Cancel all affected lines and create full, source-reconciled refunds."""
    from apps.bookings.models import BookingStatusHistory
    from apps.notifications.models import Notification
    from apps.payments.order_cancellation import _credit_wallet_refund

    created_refunds = []
    refund_record_ids = []
    with transaction.atomic():
        order = (
            Order.objects.select_for_update().get(pk=order_id)
            if order_id else None
        )
        bookings = list(
            Booking.objects.select_for_update().filter(pk__in=booking_ids).order_by("pk")
        )
        if len(bookings) != len(booking_ids) or any(
            booking.status not in (Booking.Status.PENDING, Booking.Status.CONFIRMED)
            or BookingAssignment.objects.filter(booking=booking).exists()
            for booking in bookings
        ):
            return False

        plans = {
            plan.booking_id: plan
            for plan in BookingFinancialPlan.objects.select_for_update().filter(
                booking_id__in=booking_ids,
            ).order_by("booking_id")
        }
        if len(plans) != len(booking_ids):
            _notify_refund_reconciliation_required(
                booking_ids=booking_ids,
                order_id=order_id,
                detail="A split-payment financial plan is missing during platform unavailability refund.",
            )
            return False

        allocations = list(
            PaymentAllocation.objects.select_for_update(of=("self",)).filter(
                installment__financial_plan__booking_id__in=booking_ids,
                installment__kind=PaymentInstallment.Kind.ADVANCE,
            ).select_related(
                "installment__financial_plan__booking",
                "payment",
                "payment_attempt",
            ).order_by("pk")
        )
        allocation_totals = {booking_id: Decimal("0.00") for booking_id in booking_ids}
        for allocation in allocations:
            allocation_totals[allocation.installment.financial_plan.booking_id] += allocation.amount

        # Captured advance money must reconcile to immutable allocations before
        # any terminal state is committed. Otherwise support must investigate.
        for booking_id, plan in plans.items():
            if allocation_totals[booking_id] != plan.advance_captured:
                detail = (
                    f"Booking {booking_id}: captured advance {plan.advance_captured} "
                    f"does not match allocated tender {allocation_totals[booking_id]}."
                )
                logger.error("Cannot auto-refund unavailable booking %s: %s", booking_id, detail)
                _notify_refund_reconciliation_required(
                    booking_ids=[booking_id],
                    order_id=order_id,
                    detail=detail,
                )
                return False

        # Preflight every line before writing any refund or wallet ledger entry.
        # A conflict on one line must not leave earlier lines partially refunded.
        for allocation in allocations:
            booking = allocation.installment.financial_plan.booking
            refund_key = f"worker-unavailable:booking:{booking.pk}:allocation:{allocation.pk}"
            conflicting_refund = RefundRecord.objects.filter(
                payment_allocation=allocation,
            ).exclude(idempotency_key=refund_key).exists()
            if conflicting_refund:
                detail = (
                    f"Booking {booking.pk} advance allocation {allocation.pk} already has "
                    "a refund record from another lifecycle."
                )
                logger.error("Cannot auto-refund unavailable booking: %s", detail)
                _notify_refund_reconciliation_required(
                    booking_ids=[booking.pk],
                    order_id=order_id,
                    detail=detail,
                )
                return False

        for allocation in allocations:
            booking = allocation.installment.financial_plan.booking
            refund_key = f"worker-unavailable:booking:{booking.pk}:allocation:{allocation.pk}"
            gateway_amount = allocation.gateway_amount
            wallet_amount = allocation.wallet_amount
            amount = allocation.amount
            record, created = RefundRecord.objects.get_or_create(
                idempotency_key=refund_key,
                defaults={
                    "booking": booking,
                    "payment": allocation.payment,
                    "payment_attempt": allocation.payment_attempt,
                    "payment_allocation": allocation,
                    "reason": RefundRecord.Reason.PROVIDER_UNAVAILABLE,
                    "gross_amount": amount,
                    "platform_fee": Decimal("0.00"),
                    "refund_amount": amount,
                    "gateway_refund_amount": gateway_amount,
                    "wallet_refund_amount": wallet_amount,
                    "status": (
                        RefundRecord.Status.REQUESTED
                        if gateway_amount > 0 else RefundRecord.Status.PROCESSED
                    ),
                    "requested_at": timezone.now(),
                    "processed_at": timezone.now() if gateway_amount <= 0 else None,
                    "provider_payload": {
                        "policy": "platform_unavailable_full_refund",
                        "worker_id": (
                            getattr(worker_user, "worker_profile", None).pk
                            if worker_user is not None and hasattr(worker_user, "worker_profile")
                            else None
                        ),
                        "allocation_id": allocation.pk,
                    },
                },
            )
            if not created and (
                record.refund_amount != amount
                or record.gateway_refund_amount != gateway_amount
                or record.wallet_refund_amount != wallet_amount
                or record.payment_allocation_id != allocation.pk
            ):
                raise WorkerUnavailabilityError(
                    "An existing refund record conflicts with the captured allocation. Contact AIRway support."
                )
            refund_record_ids.append(record.pk)
            _credit_wallet_refund(record)
            if gateway_amount > 0 and record.status != RefundRecord.Status.PROCESSED:
                payment_id = (
                    allocation.payment.razorpay_payment_id
                    if allocation.payment_id
                    else allocation.payment_attempt.provider_payment_id
                )
                if not payment_id:
                    record.status = RefundRecord.Status.PENDING
                    record.provider_payload = {
                        **(record.provider_payload or {}),
                        "reconciliation_required": "Captured gateway payment ID is missing.",
                    }
                    record.save(update_fields=["status", "provider_payload", "updated_at"])
                elif created:
                    created_refunds.append((
                        record.pk, payment_id, int(gateway_amount * 100),
                        allocation.payment_attempt_id,
                    ))

        for booking in bookings:
            plan = plans[booking.pk]
            plan.refunded_total += allocation_totals[booking.pk]
            plan.state = BookingFinancialPlan.State.CANCELLED
            plan.save(update_fields=["refunded_total", "state", "updated_at"])
            PaymentInstallment.objects.filter(
                financial_plan=plan,
                kind=PaymentInstallment.Kind.FINAL_BALANCE,
            ).exclude(status=PaymentInstallment.Status.PAID).update(
                status=PaymentInstallment.Status.CANCELLED,
            )
            old_status = booking.status
            booking.status = Booking.Status.CANCELLED
            booking.cancelled_at = timezone.now()
            booking.cancelled_by = worker_user
            booking.cancellation_reason = (
                f"Platform cancellation: no eligible professional accepted within configured dispatch batches. "
                f"Worker report: {reason[:400]}"
            )
            booking.save(update_fields=[
                "status", "cancelled_at", "cancelled_by",
                "cancellation_reason", "updated_at",
            ])
            BookingStatusHistory.objects.create(
                booking=booking,
                from_status=old_status,
                to_status=Booking.Status.CANCELLED,
                changed_by=worker_user,
                note="Platform cancellation after configured dispatch batches exhausted; full advance refund initiated.",
            )
            Notification.objects.create(
                user=booking.customer,
                type=Notification.Type.BOOKING_CANCELLED,
                title="Service Cancelled — Full Refund",
                body="AIRway could not find an eligible professional. Your captured booking advance is being fully refunded; no cancellation fee was deducted.",
                channel=Notification.Channel.IN_APP,
                data={"booking_id": booking.pk, "order_id": order_id, "refund_policy": "platform_unavailable_full_refund"},
            )

        if order:
            order.status = Order.Status.CANCELLED
            order.metadata = {
                **(order.metadata or {}),
                "fully_cancelled": True,
                "cancellation_reason": "dispatch_batches_exhausted",
                "refund_policy": "platform_unavailable_full_refund",
            }
            order.save(update_fields=["status", "metadata", "updated_at"])

    # Submit gateway refunds after the cancellation/refund ledger transaction.
    # Separate provider submission from local persistence: if Razorpay accepted
    # a refund but our DB write fails, reconciliation must discover it by notes;
    # we must never reinterpret that as a safe reason to submit another refund.
    for record_id, payment_id, amount_paise, attempt_id in created_refunds:
        try:
            import razorpay
            gateway = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
            provider_refund = gateway.payment.refund(
                payment_id,
                {
                    "amount": amount_paise,
                    "notes": {
                        "airway_refund_record_id": str(record_id),
                        "reason": "Platform unable to fulfil before service start",
                    },
                },
            )
            if not provider_refund.get("id"):
                raise ValueError("Razorpay did not return a refund ID.")
        except Exception as exc:
            logger.exception("Platform unavailability refund submission failed for record %s", record_id)
            try:
                from apps.payments.installment_service import _persist_refund_submission
                _persist_refund_submission(
                    record_id=record_id,
                    submission_error=exc,
                    attempt_id=attempt_id,
                )
            except Exception:
                # Keep the durable REQUESTED record for read-only provider
                # reconciliation if even local error persistence is unavailable.
                logger.exception(
                    "Could not persist refund submission failure for record %s; reconciliation is required",
                    record_id,
                )
            continue

        try:
            from apps.payments.installment_service import _persist_refund_submission
            _persist_refund_submission(
                record_id=record_id,
                provider_refund=provider_refund,
                attempt_id=attempt_id,
            )
        except Exception:
            # The gateway may already have accepted the refund. Leave the
            # durable record unresolved so reconcile_refund_record can locate
            # the provider refund by airway_refund_record_id notes.
            logger.exception(
                "Razorpay refund submitted but AIRway could not persist response for record %s",
                record_id,
            )
    unresolved = RefundRecord.objects.filter(
        pk__in=refund_record_ids,
        status__in=[
            RefundRecord.Status.REQUESTED,
            RefundRecord.Status.PENDING,
            RefundRecord.Status.FAILED,
        ],
    ).exists()
    if unresolved:
        _notify_refund_reconciliation_required(
            booking_ids=booking_ids,
            order_id=order_id,
            detail=(
                "Platform-unavailability refund records remain pending or failed. "
                "Reconcile the gateway outcome before any manual retry."
            ),
        )
    return "pending_reconciliation" if unresolved else "processed"



def _notify_refund_reconciliation_required(*, booking_ids, order_id, detail):
    """Create an in-app operations alert without exposing payment data to workers."""
    from django.contrib.auth import get_user_model
    from apps.notifications.models import Notification

    staff_users = get_user_model().objects.filter(is_staff=True, is_active=True)
    notifications = [
        Notification(
            user=user,
            type=Notification.Type.SYSTEM_ANNOUNCEMENT,
            title="Platform refund reconciliation required",
            body=detail[:1000],
            channel=Notification.Channel.IN_APP,
            data={
                "event": "worker_unavailability_refund_reconciliation",
                "order_id": order_id,
                "booking_ids": list(booking_ids),
            },
        )
        for user in staff_users
    ]
    if notifications:
        Notification.objects.bulk_create(notifications)
