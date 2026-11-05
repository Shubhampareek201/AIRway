"""
Celery tasks for booking dispatch automation.
"""
import logging
from datetime import timedelta
from django.utils import timezone
from django.db import transaction

from celery import shared_task

logger = logging.getLogger(__name__)

# Configuration
BATCH_SIZE = 5
MAX_BATCHES = 3
OFFER_EXPIRY_MINUTES = 5
PAYMENT_TIMEOUT_MINUTES = 5


@shared_task
def expire_pending_offers():
    """
    Find PENDING offers whose expires_at has passed and mark them EXPIRED.
    This task is idempotent - re-running it on already expired offers is safe.
    """
    from apps.bookings.models import WorkerOffer, BookingStatusHistory
    from apps.notifications.models import Notification

    now = timezone.now()

    # Find pending offers that have expired
    expired_offers = WorkerOffer.objects.filter(
        status=WorkerOffer.Status.PENDING,
        expires_at__lt=now
    ).select_related('booking', 'worker__user')

    count = expired_offers.count()
    if count > 0:
        for offer in expired_offers:
            offer.status = WorkerOffer.Status.EXPIRED
            offer.responded_at = now
            offer.save()

            # Notify affected worker
            Notification.objects.create(
                user=offer.worker.user,
                type=Notification.Type.WORKER_OFFER_EXPIRED,
                title="Offer Expired",
                body=f"The job offer for {offer.booking.service.title} has expired.",
                channel=Notification.Channel.IN_APP,
                data={"booking_id": offer.booking.id, "offer_id": offer.id}
            )

            # Notify customer if this was the last pending offer
            has_pending = WorkerOffer.objects.filter(
                booking=offer.booking,
                status=WorkerOffer.Status.PENDING
            ).exists()
            if not has_pending:
                # Check if all offers for this booking are non-pending
                all_offers = WorkerOffer.objects.filter(booking=offer.booking).count()
                pending_offers = WorkerOffer.objects.filter(
                    booking=offer.booking,
                    status=WorkerOffer.Status.PENDING
                ).count()
                if pending_offers == 0 and all_offers > 0:
                    Notification.objects.create(
                        user=offer.booking.customer,
                        type=Notification.Type.BOOKING_OFFERS_EXPIRED,
                        title="Offers Expired",
                        body="No workers accepted your booking. We'll try again.",
                        channel=Notification.Channel.IN_APP,
                        data={"booking_id": offer.booking.id}
                    )

        logger.info(f"Expired {count} pending worker offers")
    else:
        logger.info("No pending offers to expire")

    return count


@shared_task
def retry_failed_dispatches():
    """
    Identify bookings where all current offers have expired or been declined
    and no worker is assigned. Create a new batch of offers if within retry limit.
    """
    from apps.bookings.models import Booking, WorkerOffer
    from apps.bookings.dispatcher import DispatcherService

    batch_count = 0

    # Find CONFIRMED bookings without assignment and no pending offers
    # (all previous offers expired/declined/withdrawn)
    candidate_bookings = Booking.objects.filter(
        status=Booking.Status.CONFIRMED
    ).exclude(
        assignment__isnull=False
    )

    for booking in candidate_bookings:
        # Check if all offers are non-pending
        has_pending_offers = WorkerOffer.objects.filter(
            booking=booking,
            status=WorkerOffer.Status.PENDING
        ).exists()

        if has_pending_offers:
            continue

        if booking.status != Booking.Status.CONFIRMED:
            continue

        # Count existing offers to check retry limit
        existing_offers = WorkerOffer.objects.filter(booking=booking).count()

        if existing_offers >= MAX_BATCHES * BATCH_SIZE:
            continue

        # Redispatch
        if booking.status == Booking.Status.CONFIRMED:
            offers = DispatcherService.dispatch_offers(booking, batch_size=BATCH_SIZE)
            if offers:
                batch_count += 1
                logger.info(
                    f"Redispatched booking {booking.id}: "
                    f"created {len(offers)} new offers"
                )

    logger.info(f"Retry batch: created {batch_count} new offer batches")
    return batch_count


@shared_task
def timeout_pending_payments():
    """
    Enforce payment timeout window. Mark payments as FAILED if PENDING
    past the timeout threshold.

    For ASSIGNED bookings with timeout:
    1. Mark payment as FAILED
    2. Withdraw the accepted offer
    3. Delete the BookingAssignment
    4. Revert booking to PENDING
    5. Notify customer
    6. Trigger re-dispatch for this booking

    Payment lifecycle vs Booking lifecycle:
    - PENDING payment for CONFIRMED booking: customer hasn't paid yet before worker assignment
    - PENDING payment for ASSIGNED booking: customer needs to pay after worker accepted
    - PAID payment: payment complete, booking status managed separately
    - TIMEOUT applies only to PENDING payments, never PAID
    """
    from django.conf import settings
    from apps.payments.models import Payment
    from apps.bookings.models import Booking, WorkerOffer, BookingAssignment, BookingStatusHistory
    from apps.notifications.models import Notification

    timeout_minutes = getattr(settings, 'PAYMENT_TIMEOUT_MINUTES', PAYMENT_TIMEOUT_MINUTES)
    timeout_ago = timezone.now() - timedelta(minutes=timeout_minutes)

    # Find PENDING payments that have timed out
    timed_out_payments = Payment.objects.filter(
        status=Payment.Status.PENDING,
        created_at__lt=timeout_ago
    ).select_related('booking').select_for_update()

    count = 0
    for payment in timed_out_payments:
        # Double-check status after acquiring lock
        if payment.status == Payment.Status.PAID:
            logger.info(f"Payment {payment.id} already PAID, skipping timeout")
            continue

        if payment.status != Payment.Status.PENDING:
            continue

        booking = payment.booking

        # Safety checks for booking status
        if booking.status in [Booking.Status.CANCELLED, Booking.Status.COMPLETED, Booking.Status.DISPUTED]:
            logger.info(
                f"Skipping payment {payment.id}: booking already in terminal state {booking.status}"
            )
            continue

        # Update payment to FAILED
        payment.status = Payment.Status.FAILED
        payment.failed_at = timezone.now()
        payment.save()

        # Handle ASSIGNED bookings - release worker and re-dispatch
        if booking.status == Booking.Status.ASSIGNED:
            with transaction.atomic():
                # Find and withdraw the accepted offer
                accepted_offer = WorkerOffer.objects.filter(
                    booking=booking,
                    status=WorkerOffer.Status.ACCEPTED
                ).first()

                if accepted_offer:
                    accepted_offer.status = WorkerOffer.Status.WITHDRAWN
                    accepted_offer.responded_at = timezone.now()
                    accepted_offer.save()

                    # Notify worker
                    Notification.objects.create(
                        user=accepted_offer.worker.user,
                        type=Notification.Type.WORKER_OFFER_WITHDRAWN,
                        title="Offer Withdrawn",
                        body="The job has been released due to payment timeout.",
                        channel=Notification.Channel.IN_APP,
                        data={"booking_id": booking.id}
                    )

                # Delete the assignment
                assignment = getattr(booking, 'assignment', None)
                if assignment:
                    assignment.delete()

                # Revert booking to PENDING
                old_status = booking.status
                booking.status = Booking.Status.PENDING
                booking.save(update_fields=['status'])

                BookingStatusHistory.objects.create(
                    booking=booking,
                    from_status=old_status,
                    to_status=Booking.Status.PENDING,
                    changed_by=None,
                    note="Payment timeout - worker released"
                )

                # Notify customer
                Notification.objects.create(
                    user=booking.customer,
                    type=Notification.Type.PAYMENT_TIMEOUT,
                    title="Payment Timed Out",
                    body="Your payment timed out. We're reassigning a worker.",
                    channel=Notification.Channel.IN_APP,
                    data={"booking_id": booking.id}
                )

                # Trigger re-dispatch for this booking
                from apps.bookings.dispatcher import DispatcherService

                # Count existing offers to check retry limit
                existing_offers = WorkerOffer.objects.filter(booking=booking).count()
                batch_limit = MAX_BATCHES * BATCH_SIZE

                if existing_offers < batch_limit:
                    offers = DispatcherService.dispatch_offers(booking, batch_size=BATCH_SIZE)
                    if offers:
                        logger.info(
                            f"Re-dispatched booking {booking.id} after payment timeout: "
                            f"created {len(offers)} new offers"
                        )
                    else:
                        logger.info(f"No eligible workers for re-dispatch of booking {booking.id}")
                else:
                    logger.info(
                        f"Skipping re-dispatch for booking {booking.id}: "
                        f"already has {existing_offers} offers (max {batch_limit})"
                    )

                logger.info(f"Released assignment for booking {booking.id} due to payment timeout")

        count += 1
        logger.info(
            f"Timed out payment {payment.id} for booking {booking.id}: "
            f"payment FAILED, booking now PENDING"
        )

    logger.info(f"Timeout batch: timed out {count} payments")
    return count