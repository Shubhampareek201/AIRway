from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone

from .models import (
    Booking, BookingAddOn, BookingFormResponse, BookingStatusHistory,
    RecurringWashPlan, RecurringWashVisit,
)
from .services import check_service_available, check_slot_availability, SlotConflictError, ServiceUnavailableError


def _visit_offsets(frequency, duration_days):
    """Return day offsets anchored to visit one; twice-weekly alternates 3/4 days."""
    offsets = [0]
    if frequency == RecurringWashPlan.Frequency.DAILY:
        step = 1
    elif frequency == RecurringWashPlan.Frequency.ALTERNATE_DAY:
        step = 2
    elif frequency == RecurringWashPlan.Frequency.WEEKLY:
        step = 7
    elif frequency == RecurringWashPlan.Frequency.FORTNIGHTLY:
        step = 14
    elif frequency == RecurringWashPlan.Frequency.TWICE_WEEKLY:
        step = None
    else:
        raise ValueError(f"Unsupported recurring wash frequency: {frequency}")

    next_offset = 3
    while True:
        if step is not None:
            next_offset = offsets[-1] + step
        if next_offset >= duration_days:
            break
        offsets.append(next_offset)
        if frequency == RecurringWashPlan.Frequency.TWICE_WEEKLY:
            next_offset += 4 if len(offsets) % 2 == 0 else 3
    return offsets


@transaction.atomic
def generate_recurring_wash_visit_ledger(plan):
    """
    Create the plan's prepaid visit calendar exactly once.

    Visit one reuses the already-paid source booking. Future rows remain
    PENDING_SETUP until their real booking records have been created.
    """
    locked = RecurringWashPlan.objects.select_for_update().get(pk=plan.pk)
    existing = list(locked.visits.select_related("booking").order_by("visit_number"))
    if existing:
        return existing
    if locked.status not in (
        RecurringWashPlan.Status.PAID_PENDING_SETUP,
        RecurringWashPlan.Status.ACTIVE,
    ):
        raise ValueError("Only a paid recurring wash plan can generate visits.")
    if not locked.source_booking.scheduled_at:
        raise ValueError("The recurring plan's first visit has no confirmed appointment time.")

    first_local = timezone.localtime(locked.source_booking.scheduled_at)
    offsets = _visit_offsets(locked.frequency, locked.duration_days)
    raw_amount = (
        Decimal(locked.quoted_total) / Decimal(len(offsets))
        if offsets else Decimal("0.00")
    )
    per_visit = raw_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    allocated = Decimal("0.00")
    visits = []
    for index, offset in enumerate(offsets, start=1):
        visit_date = first_local.date() + timedelta(days=offset)
        local_naive = datetime.combine(visit_date, first_local.timetz().replace(tzinfo=None))
        scheduled_at = timezone.make_aware(local_naive, timezone.get_current_timezone())
        amount = (
            Decimal(locked.quoted_total) - allocated
            if index == len(offsets)
            else per_visit
        )
        if index < len(offsets):
            allocated += amount
        booking = locked.source_booking if index == 1 else None
        if index == 1:
            booking_status = (
                RecurringWashVisit.Status.COMPLETED
                if booking.status == Booking.Status.COMPLETED
                else RecurringWashVisit.Status.CANCELLED
                if booking.status == Booking.Status.CANCELLED
                else RecurringWashVisit.Status.BOOKED
            )
        else:
            booking_status = RecurringWashVisit.Status.PENDING_SETUP
        visits.append(RecurringWashVisit.objects.create(
            plan=locked,
            visit_number=index,
            scheduled_at=scheduled_at,
            booking=booking,
            prepaid_amount=amount,
            status=booking_status,
        ))
    return visits


@transaction.atomic
def create_pending_recurring_visit_bookings(plan):
    """
    Materialize future ledger rows as ordinary AIRway bookings.

    This is safe to retry: each visit is locked and linked to at most one
    booking. Slot conflicts leave the visit pending for the next setup pass.
    """
    locked = RecurringWashPlan.objects.select_for_update(of=("self",)).select_related(
        "source_booking", "customer", "address__zone__city", "service", "variant"
    ).get(pk=plan.pk)
    if locked.status not in (
        RecurringWashPlan.Status.PAID_PENDING_SETUP,
        RecurringWashPlan.Status.ACTIVE,
    ):
        return []

    created = []
    pending_visits = list(
        locked.visits.select_for_update()
        .filter(status=RecurringWashVisit.Status.PENDING_SETUP)
        .order_by("visit_number")
    )
    source = locked.source_booking
    for visit in pending_visits:
        if visit.booking_id:
            visit.status = RecurringWashVisit.Status.BOOKED
            visit.save(update_fields=["status", "updated_at"])
            continue

        try:
            check_service_available(locked.service, address=locked.address)
            duration = (
                locked.variant.duration_minutes
                if locked.variant_id and locked.variant.duration_minutes
                else locked.service.duration_minutes
            ) or 60
            quantity = max(int(locked.vehicle_quantity or 1), 1)
            check_slot_availability(
                service=locked.service,
                scheduled_at=visit.scheduled_at,
                duration_minutes=duration * (
                    1 if locked.service.pricing_type == "per_unit" else quantity
                ),
                booking_mode=Booking.BookingMode.SCHEDULED,
            )
        except (SlotConflictError, ServiceUnavailableError) as exc:
            visit.admin_notes = str(exc)
            visit.save(update_fields=["admin_notes", "updated_at"])
            continue

        total = Decimal(visit.prepaid_amount).quantize(Decimal("0.01"))
        subtotal = (total / Decimal("1.18")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        tax = total - subtotal
        pricing = dict(source.pricing_snapshot or {})
        pricing.update({
            "recurring_plan_id": locked.pk,
            "recurring_visit_id": visit.pk,
            "recurring_visit_number": visit.visit_number,
            "quantity": quantity,
            "subtotal": str(subtotal),
            "tax": str(tax),
            "total": str(total),
            "currency": "INR",
            "prepaid": True,
            "prepaid_amount": str(total),
        })
        booking = Booking.objects.create(
            customer=locked.customer,
            address=locked.address,
            service=locked.service,
            variant=locked.variant,
            booking_mode=Booking.BookingMode.SCHEDULED,
            scheduled_at=visit.scheduled_at,
            status=Booking.Status.PENDING,
            pricing_snapshot=pricing,
            notes=source.notes,
            customer_answers=source.customer_answers,
        )
        for addon in source.booking_addons.all():
            BookingAddOn.objects.create(
                booking=booking,
                addon=addon.addon,
                quantity=addon.quantity,
                unit_price=addon.unit_price,
                total_price=addon.total_price,
            )
        for response in source.form_responses.all():
            BookingFormResponse.objects.create(
                booking=booking,
                form_field=response.form_field,
                value=response.value,
            )
        BookingStatusHistory.objects.create(
            booking=booking,
            from_status="",
            to_status=Booking.Status.PENDING,
            changed_by=None,
            note=f"Recurring Car Wash plan #{locked.pk}, visit {visit.visit_number}; prepaid by plan.",
        )
        visit.booking = booking
        visit.status = RecurringWashVisit.Status.BOOKED
        visit.admin_notes = ""
        visit.save(update_fields=["booking", "status", "admin_notes", "updated_at"])
        created.append(booking)

    remaining = locked.visits.filter(
        status=RecurringWashVisit.Status.PENDING_SETUP
    ).exists()
    if not remaining and locked.status == RecurringWashPlan.Status.PAID_PENDING_SETUP:
        locked.status = RecurringWashPlan.Status.ACTIVE
        locked.activated_at = timezone.now()
        locked.save(update_fields=["status", "activated_at", "updated_at"])
    return created
