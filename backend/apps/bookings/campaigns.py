"""Read-only customer campaign eligibility and discount calculation."""
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_UP

from django.db.models import Count, Q
from django.utils import timezone

from apps.bookings.models import CampaignRedemption, CustomerCampaign
from apps.catalog.finance import calculate_estimated_contribution
from apps.payments.models import Payment


CENT = Decimal("0.01")
ZERO = Decimal("0.00")
COUNTED_REDEMPTION_STATUSES = (
    CampaignRedemption.Status.RESERVED,
    CampaignRedemption.Status.REDEEMED,
    CampaignRedemption.Status.REFUNDED,
)


def _money(value):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not amount.is_finite():
        return None
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def _paid_order_count(customer):
    """Count distinct orders with a successfully paid 30% advance."""
    return (
        Payment.objects.filter(
            customer=customer,
            order__isnull=False,
            stage=Payment.Stage.ADVANCE,
            status=Payment.Status.PAID,
        )
        .exclude(order__status="cancelled")
        .values("order_id")
        .distinct()
        .count()
    )


def _campaign_sequence_matches(campaign, paid_order_count):
    if campaign.booking_sequence == CustomerCampaign.BookingSequence.FIRST:
        return paid_order_count == 0
    if campaign.booking_sequence == CustomerCampaign.BookingSequence.SECOND:
        return paid_order_count == 1
    return campaign.booking_sequence == CustomerCampaign.BookingSequence.ANY


def _eligible_lines(campaign, lines, zone):
    service_ids = set(campaign.eligible_services.values_list("id", flat=True))
    zone_ids = set(campaign.eligible_zones.values_list("id", flat=True))
    if zone_ids and (zone is None or zone.pk not in zone_ids):
        return []
    if not service_ids:
        return list(lines)
    return [line for line in lines if line["service"].pk in service_ids]


def _allocate_discount(lines, discount):
    """Allocate a rounded discount proportionally, with the final cent on the last line."""
    subtotal = sum((line["remaining"] for line in lines), ZERO)
    if subtotal <= ZERO or discount <= ZERO:
        return {}
    allocation = {}
    assigned = ZERO
    for index, line in enumerate(lines):
        if index == len(lines) - 1:
            amount = discount - assigned
        else:
            amount = (discount * line["remaining"] / subtotal).quantize(
                CENT, rounding=ROUND_HALF_UP
            )
            amount = min(amount, line["remaining"])
            assigned += amount
        if amount < ZERO or amount > line["remaining"]:
            return {}
        allocation[line["key"]] = amount
    return allocation


def _contribution_floor_passes(lines, allocation, previous_discounts):
    """Fail closed if finance assumptions are missing or a service misses its floor."""
    for line in lines:
        discount = previous_discounts.get(line["key"], ZERO) + allocation.get(
            line["key"], ZERO
        )
        discounted_price = line["subtotal"] - discount
        contribution = calculate_estimated_contribution(
            customer_price=discounted_price,
            worker_payout=line["worker_payout"],
            service=line["service"],
        )
        floor = line["service"].minimum_contribution_floor
        if contribution is None or floor is None:
            return False
        if contribution < Decimal(str(floor)):
            return False
    return True


def evaluate_customer_campaigns(*, customer, zone, lines, now=None):
    """Calculate eligible discounts without reserving budget or creating redemptions.

    Each line must contain a unique key, service, subtotal and worker_payout.
    Checkout must re-evaluate under database locks before creating reservations.
    """
    now = now or timezone.now()
    normalized_lines = []
    seen_keys = set()
    for line in lines:
        if not isinstance(line, dict) or not {"key", "service", "subtotal", "worker_payout"} <= set(line):
            return {"discount_amount": ZERO, "line_discounts": {}, "applied_campaigns": []}
        key = str(line["key"])
        subtotal = _money(line["subtotal"])
        payout = _money(line["worker_payout"])
        if key in seen_keys or subtotal is None or subtotal <= ZERO or payout is None or payout < ZERO:
            return {"discount_amount": ZERO, "line_discounts": {}, "applied_campaigns": []}
        seen_keys.add(key)
        normalized_lines.append({
            "key": key,
            "service": line["service"],
            "subtotal": subtotal,
            "remaining": subtotal,
            "worker_payout": payout,
        })

    order_subtotal = sum((line["subtotal"] for line in normalized_lines), ZERO)
    if not normalized_lines or order_subtotal <= ZERO:
        return {"discount_amount": ZERO, "line_discounts": {}, "applied_campaigns": []}

    paid_count = _paid_order_count(customer)
    redemption_counts = dict(
        CampaignRedemption.objects.filter(
            customer=customer,
            status__in=COUNTED_REDEMPTION_STATUSES,
        )
        .values("campaign_id")
        .annotate(total=Count("id"))
        .values_list("campaign_id", "total")
    )
    candidates = CustomerCampaign.objects.filter(is_active=True).filter(
        (Q(starts_at__isnull=True) | Q(starts_at__lte=now))
        & (Q(ends_at__isnull=True) | Q(ends_at__gt=now))
    ).order_by("priority", "-created_at")

    total_discounts = {line["key"]: ZERO for line in normalized_lines}
    applied = []
    for campaign in candidates:
        if not _campaign_sequence_matches(campaign, paid_count):
            continue
        if redemption_counts.get(campaign.pk, 0) >= campaign.max_redemptions_per_customer:
            continue
        if (
            campaign.max_total_redemptions is not None
            and campaign.redemptions.filter(status__in=COUNTED_REDEMPTION_STATUSES).count()
            >= campaign.max_total_redemptions
        ):
            continue
        if campaign.remaining_budget <= ZERO or order_subtotal < campaign.minimum_subtotal:
            continue
        if applied and (
            not campaign.allow_stacking
            or any(not item["allow_stacking"] for item in applied)
        ):
            continue

        eligible = _eligible_lines(campaign, normalized_lines, zone)
        eligible = [line for line in eligible if line["remaining"] > ZERO]
        if not eligible:
            continue
        eligible_subtotal = sum((line["remaining"] for line in eligible), ZERO)
        if campaign.discount_type == CustomerCampaign.DiscountType.PERCENTAGE:
            discount = (eligible_subtotal * campaign.discount_value / Decimal("100")).quantize(
                CENT, rounding=ROUND_HALF_UP
            )
        else:
            discount = _money(campaign.discount_value)
        if discount is None:
            continue
        if campaign.max_discount_amount is not None:
            discount = min(discount, campaign.max_discount_amount)
        discount = min(discount, eligible_subtotal, campaign.remaining_budget)
        if discount <= ZERO:
            continue

        allocation = _allocate_discount(eligible, discount)
        if not allocation or not _contribution_floor_passes(
            eligible, allocation, total_discounts
        ):
            continue

        for line in normalized_lines:
            amount = allocation.get(line["key"], ZERO)
            total_discounts[line["key"]] += amount
            line["remaining"] -= amount
        applied.append({
            "campaign_id": campaign.pk,
            "name": campaign.name,
            "discount_amount": discount,
            "allow_stacking": campaign.allow_stacking,
        })
        if not campaign.allow_stacking:
            break

    return {
        "discount_amount": sum(total_discounts.values(), ZERO).quantize(CENT),
        "line_discounts": total_discounts,
        "applied_campaigns": applied,
    }



def reserve_customer_campaigns(*, customer, order, zone, lines, now=None):
    """Lock customer/campaign rows, re-evaluate, and reserve budget for this order.

    Call only inside the checkout transaction. Locking the customer serializes
    first/second-booking claims; locking campaigns serializes shared budgets.
    """
    from django.db import transaction

    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError("Campaign reservations require an active checkout transaction.")

    customer.__class__.objects.select_for_update().get(pk=customer.pk)
    locked_campaigns = list(
        CustomerCampaign.objects.select_for_update()
        .filter(is_active=True)
        .order_by("pk")
    )
    result = evaluate_customer_campaigns(
        customer=customer,
        zone=zone,
        lines=lines,
        now=now,
    )
    campaigns_by_id = {campaign.pk: campaign for campaign in locked_campaigns}
    for applied in result["applied_campaigns"]:
        campaign = campaigns_by_id.get(applied["campaign_id"])
        amount = applied["discount_amount"]
        if campaign is None or amount <= ZERO or amount > campaign.remaining_budget:
            raise RuntimeError("Campaign budget changed during checkout reservation.")
        campaign.budget_reserved += amount
        campaign.save(update_fields=["budget_reserved", "updated_at"])
        CampaignRedemption.objects.create(
            campaign=campaign,
            customer=customer,
            order=order,
            discount_amount=amount,
            status=CampaignRedemption.Status.RESERVED,
        )
    return result



def redeem_customer_campaigns_for_order(*, order, now=None):
    """Convert reserved campaign budget to spent after a verified advance payment."""
    from django.db import transaction

    now = now or timezone.now()
    transitioned = 0
    with transaction.atomic():
        redemptions = list(
            CampaignRedemption.objects.select_for_update()
            .filter(order=order, status=CampaignRedemption.Status.RESERVED)
            .order_by("campaign_id", "pk")
        )
        for redemption in redemptions:
            campaign = CustomerCampaign.objects.select_for_update().get(
                pk=redemption.campaign_id
            )
            amount = redemption.discount_amount
            if campaign.budget_reserved < amount:
                raise RuntimeError("Campaign reserved budget is inconsistent with its redemption.")
            campaign.budget_reserved -= amount
            campaign.budget_spent += amount
            campaign.save(update_fields=["budget_reserved", "budget_spent", "updated_at"])
            redemption.status = CampaignRedemption.Status.REDEEMED
            redemption.redeemed_at = now
            redemption.save(update_fields=["status", "redeemed_at", "updated_at"])
            transitioned += 1
    return transitioned


def release_customer_campaigns_for_order(*, order, reason, now=None):
    """Release reserved campaign budget when an order is cancelled before advance capture."""
    from django.db import transaction

    now = now or timezone.now()
    reason = str(reason or "Order cancelled before advance payment.")[:160]
    transitioned = 0
    with transaction.atomic():
        redemptions = list(
            CampaignRedemption.objects.select_for_update()
            .filter(order=order, status=CampaignRedemption.Status.RESERVED)
            .order_by("campaign_id", "pk")
        )
        for redemption in redemptions:
            campaign = CustomerCampaign.objects.select_for_update().get(
                pk=redemption.campaign_id
            )
            amount = redemption.discount_amount
            if campaign.budget_reserved < amount:
                raise RuntimeError("Campaign reserved budget is inconsistent with its redemption.")
            campaign.budget_reserved -= amount
            campaign.save(update_fields=["budget_reserved", "updated_at"])
            redemption.status = CampaignRedemption.Status.RELEASED
            redemption.released_at = now
            redemption.release_reason = reason
            redemption.save(update_fields=[
                "status", "released_at", "release_reason", "updated_at"
            ])
            transitioned += 1
    return transitioned
