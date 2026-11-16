from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone

from .models import RecurringWashPlan, RecurringWashVisit


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
    PENDING_SETUP until booking creation, slot validation and worker dispatch
    are implemented; the plan is deliberately not activated here.
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
                if booking.status == "completed"
                else RecurringWashVisit.Status.CANCELLED
                if booking.status == "cancelled"
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
