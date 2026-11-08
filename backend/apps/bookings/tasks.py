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
    orders = Order.objects.filter(status=Order.Status.AWAITING_ASSIGNMENT).order_by("created_at")
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
    ).exclude(assignment__isnull=False)
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
            Notification.objects.create(
                user=payment.customer,
                type=Notification.Type.PAYMENT_TIMEOUT,
                title="Order Payment Timed Out",
                body="Your payment timed out. The wallet amount has been released; you can retry checkout.",
                channel=Notification.Channel.IN_APP,
                data={"order_id": payment.order_id, "payment_id": payment.id},
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
