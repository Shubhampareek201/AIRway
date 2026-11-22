from decimal import Decimal

from django.db.models import Q


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


def service_booking_ready(service):
    """Require a real worker payout for fixed-price jobs before customer checkout."""
    if not service_pricing_ready(service):
        return False
    # Quote/inspection jobs still use the existing quote/commission workflow.
    if service.pricing_type == "quote" or service.booking_mode == "inspection":
        return True
    variants = service.variants.filter(is_active=True)
    return variants.exists() and not variants.filter(
        Q(worker_payout__isnull=True) | Q(worker_payout__lte=Decimal("0.00"))
    ).exists()


def priced_service_ids(queryset):
    """Return IDs of services that have both a customer price and dispatchable payout."""
    return {
        service.id for service in queryset.prefetch_related("variants")
        if service_booking_ready(service)
    }
