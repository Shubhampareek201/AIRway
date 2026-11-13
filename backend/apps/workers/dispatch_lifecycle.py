"""Safe reassignment and escalation when an approved worker is suspended."""
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone


def handle_worker_suspension(worker_id):
    """Reassign not-yet-started jobs; pause started work for operations review."""
    from apps.bookings.models import (
        Booking,
        BookingAssignment,
        BookingStatusHistory,
        Order,
        WorkerOffer,
    )
    from apps.notifications.models import Notification
    from apps.workers.models import WorkerProfile

    worker = WorkerProfile.objects.filter(pk=worker_id).first()
    if worker is None or worker.status == WorkerProfile.Status.APPROVED:
        return {"reassigned": 0, "escalated": 0}

    assignments = list(
        BookingAssignment.objects.filter(
            worker_id=worker_id,
            booking__status__in=(Booking.Status.ASSIGNED, Booking.Status.IN_PROGRESS),
        ).select_related("booking__customer", "booking__order_item__order")
    )
    processed_orders = set()
    reassigned = 0
    escalated = 0

    def notify_customer(booking, title, body, data):
        Notification.objects.create(
            user=booking.customer,
            type=Notification.Type.SYSTEM_ANNOUNCEMENT,
            title=title,
            body=body,
            channel=Notification.Channel.IN_APP,
            data=data,
        )
        from apps.notifications.service import send_push_notification
        transaction.on_commit(
            lambda user=booking.customer, t=title, b=body, payload=data:
                send_push_notification(
                    user, t, b, data=payload,
                    channel_id="airway_booking_updates",
                )
        )

    def notify_operations(booking, title, body, data):
        User = get_user_model()
        for staff_user in User.objects.filter(is_staff=True, is_active=True).only("id"):
            Notification.objects.get_or_create(
                user=staff_user,
                type=Notification.Type.SYSTEM_ANNOUNCEMENT,
                title=title,
                data__booking_id=booking.pk,
                defaults={
                    "body": body,
                    "channel": Notification.Channel.IN_APP,
                    "data": data,
                },
            )

    for row in assignments:
        booking_id = row.booking_id
        order_id = getattr(getattr(row.booking, "order_item", None), "order_id", None)
        if order_id:
            if order_id in processed_orders:
                continue
            processed_orders.add(order_id)
            with transaction.atomic():
                order = Order.objects.select_for_update().get(pk=order_id)
                active_items = list(
                    order.items.exclude(booking__status=Booking.Status.CANCELLED)
                    .select_related("booking")
                )
                if not active_items:
                    continue
                active_bookings = [item.booking for item in active_items]
                active_ids = [booking.pk for booking in active_bookings]
                locked_assignments = list(
                    BookingAssignment.objects.select_for_update()
                    .filter(booking_id__in=active_ids)
                    .select_related("booking")
                )
                if any(
                    assignment.started_at is not None
                    or assignment.booking.status == Booking.Status.IN_PROGRESS
                    for assignment in locked_assignments
                ):
                    for active_booking in active_bookings:
                        if active_booking.status in (Booking.Status.ASSIGNED, Booking.Status.IN_PROGRESS):
                            old_status = active_booking.status
                            active_booking.status = Booking.Status.DISPUTED
                            active_booking.save(update_fields=["status", "updated_at"])
                            BookingStatusHistory.objects.create(
                                booking=active_booking,
                                from_status=old_status,
                                to_status=Booking.Status.DISPUTED,
                                note="Worker suspended after assignment; operations review required before work continues.",
                            )
                    anchor = active_bookings[0]
                    payload = {"booking_id": anchor.pk, "order_id": order.pk, "worker_id": worker_id}
                    notify_customer(
                        anchor,
                        "Your booking needs an update",
                        "Your assigned professional is temporarily unavailable. AIRway operations is reviewing the booking and will contact you with the next step.",
                        payload,
                    )
                    notify_operations(
                        anchor,
                        "Suspended worker has started order work",
                        f"Worker #{worker_id} was suspended while order #{order.pk} had started work. Review urgently.",
                        payload,
                    )
                    escalated += len(active_bookings)
                    continue

                # A parent order is assigned as one unit. Reopen every active
                # line only when none of them has started.
                if len(locked_assignments) != len(active_bookings) or any(
                    assignment.worker_id != worker_id for assignment in locked_assignments
                ):
                    continue
                WorkerOffer.objects.filter(
                    order=order,
                    status__in=(WorkerOffer.Status.PENDING, WorkerOffer.Status.ACCEPTED),
                ).update(status=WorkerOffer.Status.WITHDRAWN, responded_at=timezone.now())
                for active_booking in active_bookings:
                    assignment = next(
                        (item for item in locked_assignments if item.booking_id == active_booking.pk),
                        None,
                    )
                    if assignment:
                        assignment.delete()
                    old_status = active_booking.status
                    active_booking.status = Booking.Status.PENDING
                    active_booking.save(update_fields=["status", "updated_at"])
                    BookingStatusHistory.objects.create(
                        booking=active_booking,
                        from_status=old_status,
                        to_status=Booking.Status.PENDING,
                        note="Assigned worker suspended before starting; service returned to dispatch.",
                    )
                order.status = (
                    Order.Status.PARTIALLY_CANCELLED
                    if order.items.filter(booking__status=Booking.Status.CANCELLED).exists()
                    else Order.Status.AWAITING_ASSIGNMENT
                )
                order.save(update_fields=["status", "updated_at"])
                anchor = active_bookings[0]
                payload = {"booking_id": anchor.pk, "order_id": order.pk, "worker_id": worker_id}
                notify_customer(
                    anchor,
                    "Finding a replacement professional",
                    "Your previously assigned professional is no longer available. Your advance remains valid and AIRway is matching a replacement.",
                    payload,
                )
            # Re-dispatch only after assignments and statuses are committed.
            from apps.bookings.dispatcher import DispatcherService
            DispatcherService.dispatch_order(order)
            reassigned += len(active_bookings)
            continue

        with transaction.atomic():
            booking = Booking.objects.select_for_update().get(pk=booking_id)
            assignment = BookingAssignment.objects.select_for_update().filter(
                booking=booking, worker_id=worker_id
            ).first()
            if assignment is None:
                continue
            if assignment.started_at is not None or booking.status == Booking.Status.IN_PROGRESS:
                old_status = booking.status
                booking.status = Booking.Status.DISPUTED
                booking.save(update_fields=["status", "updated_at"])
                BookingStatusHistory.objects.create(
                    booking=booking,
                    from_status=old_status,
                    to_status=Booking.Status.DISPUTED,
                    note="Worker suspended after starting the service; operations review required.",
                )
                payload = {"booking_id": booking.pk, "worker_id": worker_id}
                notify_customer(
                    booking,
                    "Your booking needs an update",
                    "Your assigned professional is temporarily unavailable. AIRway operations is reviewing the service and will contact you.",
                    payload,
                )
                notify_operations(
                    booking,
                    "Suspended worker has started a service",
                    f"Worker #{worker_id} was suspended while booking #{booking.pk} was in progress. Review urgently.",
                    payload,
                )
                escalated += 1
                continue

            WorkerOffer.objects.filter(
                booking=booking,
                status__in=(WorkerOffer.Status.PENDING, WorkerOffer.Status.ACCEPTED),
            ).update(status=WorkerOffer.Status.WITHDRAWN, responded_at=timezone.now())
            assignment.delete()
            old_status = booking.status
            booking.status = Booking.Status.PENDING
            booking.save(update_fields=["status", "updated_at"])
            BookingStatusHistory.objects.create(
                booking=booking,
                from_status=old_status,
                to_status=Booking.Status.PENDING,
                note="Assigned worker suspended before starting; service returned to dispatch.",
            )
            payload = {"booking_id": booking.pk, "worker_id": worker_id}
            notify_customer(
                booking,
                "Finding a replacement professional",
                "Your previously assigned professional is no longer available. Your advance remains valid and AIRway is matching a replacement.",
                payload,
            )
        from apps.bookings.dispatcher import DispatcherService
        DispatcherService.dispatch_offers(booking)
        reassigned += 1

    return {"reassigned": reassigned, "escalated": escalated}
