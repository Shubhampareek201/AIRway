from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def calculate_worker_payout(*, service, variant, addon_rows, quantity, booking_mode):
    """Calculate fixed catalogue payout independently of customer selling prices."""
    try:
        quantity = int(quantity)
    except (TypeError, ValueError):
        return None
    if quantity < 1:
        return None

    payout = Decimal("0.00")
    if variant is not None:
        if variant.worker_payout is None:
            return None
        payout += Decimal(str(variant.worker_payout)) * quantity
    elif (
        service.pricing_type == service.PricingType.FIXED
        and service.variants.filter(is_active=True).exists()
    ):
        return None

    for addon, addon_quantity in addon_rows:
        try:
            addon_quantity = int(addon_quantity)
            addon_payout = Decimal(str(addon.worker_payout))
        except (TypeError, ValueError, InvalidOperation):
            return None
        if addon_quantity < 1 or not addon_payout.is_finite() or addon_payout < 0:
            return None
        payout += addon_payout * addon_quantity * quantity

    if booking_mode == "inspection":
        payout += Decimal(str(service.visit_fee_worker_payout))

    if not payout.is_finite() or payout <= 0:
        return None
    return payout.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


UNIT_ECONOMICS_ASSUMPTION_FIELDS = (
    "estimated_gateway_fee_percent",
    "discount_reserve_percent",
    "rewards_reserve_percent",
    "refund_reserve_percent",
    "rework_reserve_percent",
    "other_variable_cost_per_booking",
    "minimum_contribution_floor",
    "target_contribution_margin_percent",
)


def calculate_estimated_contribution(*, customer_price, worker_payout, service):
    """Return a projected pre-tax contribution only when every cost assumption is configured."""
    if worker_payout is None:
        return None
    values = [getattr(service, field, None) for field in UNIT_ECONOMICS_ASSUMPTION_FIELDS]
    if any(value is None for value in values):
        return None

    price = Decimal(str(customer_price))
    payout = Decimal(str(worker_payout))
    gateway_fee_percent = Decimal(str(service.estimated_gateway_fee_percent))
    reserve_percent = sum(
        (
            Decimal(str(getattr(service, field)))
            for field in (
                "discount_reserve_percent",
                "rewards_reserve_percent",
                "refund_reserve_percent",
                "rework_reserve_percent",
            )
        ),
        Decimal("0.00"),
    )
    other_cost = Decimal(str(service.other_variable_cost_per_booking))
    tax_rate = Decimal(str(service.tax_rate))
    if not price.is_finite() or price <= 0 or not payout.is_finite() or payout < 0:
        return None
    if not other_cost.is_finite() or other_cost < 0 or not tax_rate.is_finite():
        return None

    # Gateway fee is estimated on the tax-inclusive customer charge; tax itself
    # is excluded from AIRway contribution as a pass-through amount.
    gateway_gross = price + (price * tax_rate / Decimal("100"))
    gateway_fee = (gateway_gross * gateway_fee_percent / Decimal("100")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    reserve_amount = (price * reserve_percent / Decimal("100")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return (price - payout - gateway_fee - reserve_amount - other_cost).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def contribution_recommendation(*, customer_price, worker_payout, service):
    contribution = calculate_estimated_contribution(
        customer_price=customer_price,
        worker_payout=worker_payout,
        service=service,
    )
    if contribution is None:
        return "Configure assumptions"
    if contribution < 0:
        return "Hold"
    if contribution < Decimal(str(service.minimum_contribution_floor)):
        return "Reprice"
    price = Decimal(str(customer_price))
    margin = contribution * Decimal("100") / price
    if margin < Decimal(str(service.target_contribution_margin_percent)):
        return "Reprice"
    return "Launch"
