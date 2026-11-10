"""Safe reassignment when an accepted split-payment worker cannot fulfil a job."""
import logging

from django.db import transaction
from django.utils import timezone

from apps.bookings.models import (
    Booking, BookingAssignment, BookingStatusHistory, Order, OrderItem, WorkerOffer,
)
from apps.notifications.models import Notification
from apps.payments.models import BookingFinancialPlan

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

        WorkerOffer.objects.filter(
            order_id=order_id if order_id else None,
            booking_id__in=booking_ids,
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
    try:
        from apps.bookings.dispatcher import DispatcherService
        if order:
            offers = DispatcherService.dispatch_order(order)
        else:
            offers = DispatcherService.dispatch_offers(bookings[0])
        dispatch_pending = not bool(offers)
    except Exception:
        dispatch_pending = True
        logger.exception(
            "Re-dispatch failed after worker unavailability for assignment %s",
            assignment_id,
        )

    return {
        "detail": "Assignment released. AIRway is looking for another eligible professional.",
        "status": "awaiting_assignment",
        "booking_ids": booking_ids,
        "order_id": order_id,
        "dispatch_pending": dispatch_pending,
    }
