from decimal import Decimal


def service_pricing_ready(service):
    """Only expose services with an honest, calculable customer price."""
    if service.pricing_type == "fixed":
        return service.variants.filter(is_active=True, price__gt=Decimal("0.00")).exists()
    if service.pricing_type == "quote":
        return service.booking_mode == "inspection" and service.visit_fee > Decimal("0.00")
    if service.pricing_type == "per_unit":
        return bool(service.unit_label) and service.variants.filter(
            is_active=True, price__gt=Decimal("0.00")
        ).exists()
    return False


def service_booking_ready(service, variant=None):
    """Check payout readiness for the exact package selected for this booking."""
    if not service_pricing_ready(service):
        return False
    # Quote/inspection jobs still use the existing quote/commission workflow.
    if service.pricing_type == "quote" or service.booking_mode == "inspection":
        return True
    if variant is None or variant.service_id != service.id or not variant.is_active:
        return False
    return (
        variant.price > Decimal("0.00")
        and variant.worker_payout is not None
        and variant.worker_payout > Decimal("0.00")
    )


def priced_service_ids(queryset):
    """Return services with a customer-facing price, independent of worker payout setup.

    Catalogue visibility must not depend on dispatch readiness. Checkout applies
    service_booking_ready() separately so a service without a configured fixed
    payout can be browsed but cannot be booked.
    """
    return {
        service.id for service in queryset.prefetch_related("variants")
        if service_pricing_ready(service)
    }
