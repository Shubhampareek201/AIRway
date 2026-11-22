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
