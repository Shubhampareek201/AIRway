from decimal import Decimal


def service_pricing_ready(service):
    """Only expose services with an honest, calculable customer price."""
    if service.pricing_type == "fixed":
        return service.variants.filter(is_active=True, price__gt=Decimal("0.00")).exists()
    if service.pricing_type == "quote":
        return service.booking_mode == "inspection"
    # Per-unit pricing has no unit-rate model in the current checkout snapshot.
    return False


def priced_service_ids(queryset):
    """Return IDs of services whose current pricing model can be quoted safely."""
    return {
        service.id for service in queryset.prefetch_related("variants")
        if service_pricing_ready(service)
    }
