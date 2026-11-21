"""
Celery tasks for booking dispatch automation.
"""
import logging
from datetime import timedelta
from django.utils import timezone
from django.db import transaction

from celery import shared_task

logger = logging.getLogger(__name__)

# Payment timeout fallback; dispatch settings are read from Admin configuration.
PAYMENT_TIMEOUT_MINUTES = 5


@shared_task
def expire_pending_offers():
    """Expire offers and advance each exhausted order/booking to its next batch."""
    from apps.bookings.models import WorkerOffer, Order, Booking
    from apps.bookings.dispatcher import DispatcherService
    from apps.notifications.models import Notification

    now = timezone.now()
    expired = list(
        WorkerOffer.objects.filter(
            status=WorkerOffer.Status.PENDING, expires_at__lte=now
        ).select_related("booking__service", "booking__customer", "worker__user")
    )
    order_ids, booking_ids = set(), set()
    for offer in expired:
        updated = WorkerOffer.objects.filter(
            pk=offer.pk, status=WorkerOffer.Status.PENDING
        ).update(status=WorkerOffer.Status.EXPIRED, responded_at=now)
        if not updated:
            continue
        if offer.order_id:
            order_ids.add(offer.order_id)
        else:
            booking_ids.add(offer.booking_id)
        Notification.objects.create(
            user=offer.worker.user,
            type=Notification.Type.WORKER_OFFER_EXPIRED,
            title="Offer Expired",
            body=f"The job offer for {offer.booking.service.title} has expired.",
            channel=Notification.Channel.IN_APP,
            data={"booking_id": offer.booking_id, "order_id": offer.order_id, "offer_id": offer.pk},
        )

    for order_id in order_ids:
        if not WorkerOffer.objects.filter(order_id=order_id, status=WorkerOffer.Status.PENDING).exists():
            DispatcherService.dispatch_order(Order.objects.get(pk=order_id))
    for booking_id in booking_ids:
        if not WorkerOffer.objects.filter(booking_id=booking_id, order__isnull=True, status=WorkerOffer.Status.PENDING).exists():
            booking = Booking.objects.filter(pk=booking_id).first()
            if booking:
                DispatcherService.dispatch_offers(booking)
    logger.info("Expired %s worker offers; advanced %s orders and %s bookings", len(expired), len(order_ids), len(booking_ids))
    return len(expired)


@shared_task
def retry_failed_dispatches():
    """Recover eligible unassigned orders and standalone bookings using Admin limits."""
    from apps.bookings.models import Booking, Order, WorkerOffer, DispatchConfiguration
    from apps.bookings.dispatcher import DispatcherService

    config = DispatchConfiguration.get_solo()
    if not config.is_enabled:
        return 0
    dispatched = 0
    orders = Order.objects.filter(
        status__in=[Order.Status.AWAITING_ASSIGNMENT, Order.Status.PARTIALLY_CANCELLED]
    ).order_by("created_at")
    for order in orders:
        if WorkerOffer.objects.filter(order=order, status__in=[
            WorkerOffer.Status.PENDING, WorkerOffer.Status.ACCEPTED
        ]).exists():
            continue
        offers = DispatcherService.dispatch_order(order)
        if offers:
            dispatched += 1

    standalone = Booking.objects.filter(
        status__in=[Booking.Status.PENDING, Booking.Status.CONFIRMED],
        order_item__isnull=True,
    ).exclude(
        assignment__isnull=False,
    ).exclude(
        recurring_wash_visit__isnull=False,
    )
    for booking in standalone:
        if WorkerOffer.objects.filter(
            booking=booking, order__isnull=True,
            status__in=[WorkerOffer.Status.PENDING, WorkerOffer.Status.ACCEPTED],
        ).exists():
            continue
        if DispatcherService.dispatch_offers(booking):
            dispatched += 1
    logger.info("Retry dispatch: created %s new batches", dispatched)
    return dispatched


@shared_task
def timeout_pending_payments():
    """
    Mark expired booking-linked PENDING payments as FAILED.

    Lock the payment row separately from its booking. Payment.booking is
    nullable now that payments can belong to parent orders, and PostgreSQL
    cannot apply FOR UPDATE to the nullable side of an outer join.
    """
    from django.conf import settings
    from apps.payments.models import Payment
    from apps.bookings.models import Booking, WorkerOffer, BookingStatusHistory
    from apps.notifications.models import Notification

    timeout_minutes = getattr(settings, 'PAYMENT_TIMEOUT_MINUTES', PAYMENT_TIMEOUT_MINUTES)
    timeout_ago = timezone.now() - timedelta(minutes=timeout_minutes)

    payment_ids = list(
        Payment.objects.filter(
            status=Payment.Status.PENDING,
            created_at__lt=timeout_ago,
            booking__isnull=False,
        ).values_list("id", flat=True)
    )

    count = 0

    # Parent-order payments use one payment record for multiple assigned bookings.
    # Expire the wallet hold after the retry window, but keep assignments intact so
    # the customer can start a fresh payment attempt without losing selected workers.
    parent_payment_ids = list(
        Payment.objects.filter(
            status=Payment.Status.PENDING,
            updated_at__lt=timeout_ago,
            order__isnull=False,
        ).values_list("id", flat=True)
    )
    for payment_id in parent_payment_ids:
        with transaction.atomic():
            payment = Payment.objects.select_for_update().filter(
                pk=payment_id,
                status=Payment.Status.PENDING,
                updated_at__lt=timeout_ago,
                order__isnull=False,
            ).first()
            if payment is None:
                continue
            from apps.wallet.services import release_wallet_reservation
            release_wallet_reservation(
                payment,
                reason="AIRway order payment timed out; wallet funds released.",
            )
            payment.status = Payment.Status.FAILED
            payment.failed_at = timezone.now()
            payment.save(update_fields=["status", "failed_at", "updated_at"])
            stage_label = {
                "advance": "30% advance",
                "balance": "final balance",
                "legacy": "full order payment",
                "extra_work": "approved extra-work payment",
            }.get(payment.stage, "order payment")
            is_extra_work = bool(payment.extra_work_id)
            Notification.objects.create(
                user=payment.customer,
                type=Notification.Type.PAYMENT_TIMEOUT,
                title="Extra-work Payment Timed Out" if is_extra_work else "Order Payment Timed Out",
                body=(
                    f"Your {stage_label} attempt timed out. The wallet amount has been released; "
                    "your approved request is still available to retry."
                    if is_extra_work else
                    f"Your {stage_label} timed out. The wallet amount has been released; you can retry this payment stage."
                ),
                channel=Notification.Channel.IN_APP,
                data={
                    "order_id": payment.order_id,
                    "payment_id": payment.id,
                    "payment_stage": payment.stage,
                    "extra_work_id": payment.extra_work_id,
                },
            )
            count += 1
            logger.info("Timed out parent-order payment %s; wallet hold released", payment.id)

    for payment_id in payment_ids:
        with transaction.atomic():
            payment = Payment.objects.select_for_update().filter(
                pk=payment_id,
                status=Payment.Status.PENDING,
                created_at__lt=timeout_ago,
                booking__isnull=False,
            ).first()
            if payment is None:
                continue

            booking = Booking.objects.select_for_update().get(pk=payment.booking_id)
            if booking.status in [
                Booking.Status.CANCELLED,
                Booking.Status.COMPLETED,
                Booking.Status.DISPUTED,
            ]:
                logger.info(
                    f"Skipping payment {payment.id}: booking already in terminal state {booking.status}"
                )
                continue

            payment.status = Payment.Status.FAILED
            payment.failed_at = timezone.now()
            payment.save(update_fields=["status", "failed_at", "updated_at"])

            if booking.status == Booking.Status.ASSIGNED:
                accepted_offer = WorkerOffer.objects.filter(
                    booking=booking,
                    status=WorkerOffer.Status.ACCEPTED,
                ).select_related("worker__user").first()

                if accepted_offer:
                    accepted_offer.status = WorkerOffer.Status.WITHDRAWN
                    accepted_offer.responded_at = timezone.now()
                    accepted_offer.save()

                    Notification.objects.create(
                        user=accepted_offer.worker.user,
                        type=Notification.Type.WORKER_OFFER_WITHDRAWN,
                        title="Offer Withdrawn",
                        body="The job has been released due to payment timeout.",
                        channel=Notification.Channel.IN_APP,
                        data={"booking_id": booking.id},
                    )

                assignment = getattr(booking, "assignment", None)
                if assignment:
                    assignment.delete()

                old_status = booking.status
                booking.status = Booking.Status.PENDING
                booking.save(update_fields=["status"])

                BookingStatusHistory.objects.create(
                    booking=booking,
                    from_status=old_status,
                    to_status=Booking.Status.PENDING,
                    changed_by=None,
                    note="Payment timeout - worker released",
                )

                Notification.objects.create(
                    user=booking.customer,
                    type=Notification.Type.PAYMENT_TIMEOUT,
                    title="Payment Timed Out",
                    body="Your payment timed out. We're reassigning a worker.",
                    channel=Notification.Channel.IN_APP,
                    data={"booking_id": booking.id},
                )

                from apps.bookings.dispatcher import DispatcherService

                offers = DispatcherService.dispatch_offers(booking)
                if offers:
                    logger.info(
                        "Re-dispatched booking %s after payment timeout: created %s new offers",
                        booking.id, len(offers),
                    )
                else:
                    logger.info(
                        "No eligible workers or Admin dispatch limit reached for booking %s",
                        booking.id,
                    )

                logger.info(
                    f"Released assignment for booking {booking.id} due to payment timeout"
                )

            count += 1
            logger.info(
                f"Timed out payment {payment.id} for booking {booking.id}: "
                f"payment FAILED, booking now {booking.status}"
            )

    logger.info(f"Timeout batch: timed out {count} payments")
    return count



@shared_task
def setup_recurring_wash_visit_bookings():
    """Retry creation of real bookings for paid recurring wash visit rows."""
    from apps.bookings.models import RecurringWashPlan
    from apps.bookings.recurring import create_pending_recurring_visit_bookings

    plans = RecurringWashPlan.objects.filter(
        status__in=(
            RecurringWashPlan.Status.PAID_PENDING_SETUP,
            RecurringWashPlan.Status.ACTIVE,
        ),
        visits__status="pending_setup",
    ).distinct().order_by("created_at")
    created = 0
    for plan in plans.iterator():
        try:
            created += len(create_pending_recurring_visit_bookings(plan))
        except Exception:
            logger.exception("Recurring visit booking setup failed for plan %s", plan.pk)
    logger.info("Created %s recurring visit bookings", created)
    return created


@shared_task
def dispatch_due_recurring_wash_visits():
    """Offer recurring visits to workers 24 hours before their scheduled time."""
    from apps.bookings.models import Booking, RecurringWashPlan, RecurringWashVisit, WorkerOffer
    from apps.bookings.dispatcher import DispatcherService

    now = timezone.now()
    visits = RecurringWashVisit.objects.filter(
        status=RecurringWashVisit.Status.BOOKED,
        scheduled_at__gt=now,
        scheduled_at__lte=now + timedelta(hours=24),
        plan__status__in=(
            RecurringWashPlan.Status.PAID_PENDING_SETUP,
            RecurringWashPlan.Status.ACTIVE,
        ),
        booking__status__in=(Booking.Status.PENDING, Booking.Status.CONFIRMED),
    ).select_related("booking").order_by("scheduled_at")
    dispatched = 0
    for visit in visits.iterator():
        if WorkerOffer.objects.filter(
            booking=visit.booking,
            status__in=(WorkerOffer.Status.PENDING, WorkerOffer.Status.ACCEPTED),
        ).exists():
            continue
        try:
            dispatched += len(DispatcherService.dispatch_offers(visit.booking))
        except Exception:
            logger.exception("Recurring visit dispatch failed for visit %s", visit.pk)
    logger.info("Dispatched %s offers for recurring visits", dispatched)
    return dispatched


# Checkout reservation hold when a customer never starts advance payment.
UNPAID_CHECKOUT_TIMEOUT_MINUTES = 15


@shared_task
def expire_unpaid_checkouts():
    """Cancel abandoned, unpaid checkouts so their service slots are released."""
    from django.conf import settings
    from apps.bookings.models import (
        Order, Booking, BookingAssignment, BookingStatusHistory, WorkerOffer,
    )
    from apps.payments.models import Payment
    from apps.notifications.models import Notification

    timeout_minutes = max(int(getattr(
        settings, "UNPAID_CHECKOUT_TIMEOUT_MINUTES",
        UNPAID_CHECKOUT_TIMEOUT_MINUTES,
    )), 1)
    cutoff = timezone.now() - timedelta(minutes=timeout_minutes)
    order_ids = Order.objects.filter(
        status__in=(Order.Status.AWAITING_ASSIGNMENT, Order.Status.PARTIALLY_CANCELLED),
        created_at__lte=cutoff,
    ).order_by("created_at").values_list("pk", flat=True)

    expired_count = 0
    for order_id in order_ids.iterator():
        with transaction.atomic():
            order = Order.objects.select_for_update().filter(
                pk=order_id,
                status__in=(Order.Status.AWAITING_ASSIGNMENT, Order.Status.PARTIALLY_CANCELLED),
                created_at__lte=cutoff,
            ).first()
            if order is None:
                continue

            # A live gateway attempt must be resolved by the payment-timeout
            # task; a captured payment must never be cancelled by this task.
            if (
                Payment.objects.filter(
                    order=order,
                    status__in=(Payment.Status.PENDING, Payment.Status.PAID),
                ).exists()
                or Payment.objects.filter(
                    booking__order_item__order=order,
                    status__in=(Payment.Status.PENDING, Payment.Status.PAID),
                ).exists()
            ):
                continue

            bookings = list(
                Booking.objects.select_for_update().filter(
                    order_item__order=order,
                ).exclude(status=Booking.Status.CANCELLED).order_by("pk")
            )
            # Never tear down work that has progressed beyond an unpaid hold.
            if any(
                booking.status not in (Booking.Status.PENDING, Booking.Status.CONFIRMED)
                or BookingAssignment.objects.filter(booking_id=booking.pk).exists()
                for booking in bookings
            ):
                continue

            now = timezone.now()
            active_offers = WorkerOffer.objects.filter(
                booking__in=bookings,
                status__in=(WorkerOffer.Status.PENDING, WorkerOffer.Status.ACCEPTED),
            ).select_related("worker__user", "booking")
            for offer in active_offers:
                offer.status = WorkerOffer.Status.WITHDRAWN
                offer.responded_at = now
                offer.save(update_fields=["status", "responded_at", "updated_at"])
                Notification.objects.create(
                    user=offer.worker.user,
                    type=Notification.Type.WORKER_OFFER_WITHDRAWN,
                    title="Unpaid checkout expired",
                    body=f"The unpaid AIRway booking #{offer.booking_id} expired and is no longer available.",
                    channel=Notification.Channel.IN_APP,
                    data={"booking_id": offer.booking_id, "order_id": order.pk, "offer_id": offer.pk},
                )

            for booking in bookings:
                old_status = booking.status
                booking.status = Booking.Status.CANCELLED
                booking.cancelled_at = now
                booking.cancelled_by = None
                booking.cancellation_reason = "Checkout expired before advance payment was completed."
                booking.save(update_fields=[
                    "status", "cancelled_at", "cancelled_by",
                    "cancellation_reason", "updated_at",
                ])
                BookingStatusHistory.objects.create(
                    booking=booking,
                    from_status=old_status,
                    to_status=Booking.Status.CANCELLED,
                    changed_by=None,
                    note="Checkout reservation expired because advance payment was not completed within the hold window.",
                )

            order.status = Order.Status.CANCELLED
            order.save(update_fields=["status", "updated_at"])
            Notification.objects.create(
                user=order.customer,
                type=Notification.Type.BOOKING_CANCELLED,
                title="Checkout expired",
                body=(
                    f"Your AIRway checkout #{order.pk} expired because payment was not completed "
                    f"within {timeout_minutes} minutes. The reserved service time has been released. "
                    "You can create a new booking and choose an available slot."
                ),
                channel=Notification.Channel.IN_APP,
                data={
                    "order_id": order.pk,
                    "reason": "unpaid_checkout_expired",
                    "timeout_minutes": timeout_minutes,
                },
            )
            expired_count += 1

    logger.info("Expired %s unpaid AIRway checkouts", expired_count)
    return expired_count

@shared_task
def expire_past_rework_proposals():
    """Expire unanswered recovery proposals once their offered appointment time passes."""
    from apps.bookings.models import BookingReworkProposal
    from apps.notifications.models import Notification

    now = timezone.now()
    proposal_ids = list(
        BookingReworkProposal.objects.filter(
            status=BookingReworkProposal.Status.PENDING_CUSTOMER,
            scheduled_at__lte=now,
        ).values_list("pk", flat=True)[:500]
    )
    expired = 0
    for proposal_id in proposal_ids:
        with transaction.atomic():
            proposal = (
                BookingReworkProposal.objects.select_for_update()
                .select_related("dispute__booking__customer", "created_by")
                .filter(
                    pk=proposal_id,
                    status=BookingReworkProposal.Status.PENDING_CUSTOMER,
                    scheduled_at__lte=now,
                )
                .first()
            )
            if proposal is None:
                continue
            proposal.status = BookingReworkProposal.Status.EXPIRED
            proposal.responded_at = now
            proposal.save(update_fields=["status", "responded_at", "updated_at"])
            Notification.objects.create(
                user=proposal.dispute.booking.customer,
                type=Notification.Type.SYSTEM_ANNOUNCEMENT,
                title="Recovery appointment proposal expired",
                body="The proposed recovery appointment time passed before you responded. AIRway support can review and send a new proposal.",
                channel=Notification.Channel.IN_APP,
                data={"dispute_id": proposal.dispute_id, "rework_proposal_id": proposal.pk, "status": proposal.status},
            )
            if proposal.created_by_id != proposal.dispute.booking.customer_id:
                Notification.objects.create(
                    user=proposal.created_by,
                    type=Notification.Type.SYSTEM_ANNOUNCEMENT,
                    title="Recovery proposal expired",
                    body=f"The customer did not respond to recovery proposal #{proposal.pk} before its scheduled time. You can issue a new proposal if appropriate.",
                    channel=Notification.Channel.IN_APP,
                    data={"dispute_id": proposal.dispute_id, "rework_proposal_id": proposal.pk, "status": proposal.status},
                )
            expired += 1
    if expired:
        logger.info("Expired %s unanswered rework proposals", expired)
    return expired

