from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.db.models import Q

from apps.payments.models import Payment, PaymentRefund
from apps.workers.models import WorkerEarning, WorkerRewardTransaction

CENT = Decimal('0.01')
ZERO = Decimal('0.00')

def _decimal(value):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return result if result.is_finite() else None

def _money(value):
    return value.quantize(CENT, rounding=ROUND_HALF_UP)

def _booking_payment_allocation(payment, booking):
    if payment.booking_id == booking.pk and not payment.order_id:
        return payment.amount + payment.wallet_amount, payment.amount, True
    rows = (payment.raw_response or {}).get('service_allocation_v1')
    if not isinstance(rows, list):
        return ZERO, ZERO, False
    matching = [row for row in rows if isinstance(row, dict) and str(row.get('booking_id')) == str(booking.pk) and row.get('allocation_type') != 'extra_work']
    if not matching:
        return ZERO, ZERO, True
    gross = ZERO
    gateway = ZERO
    for row in matching:
        row_gross = _decimal(row.get('total'))
        row_gateway = _decimal(row.get('gateway_amount'))
        if row_gross is None or row_gateway is None or row_gross < 0 or row_gateway < 0:
            return ZERO, ZERO, False
        gross += row_gross
        gateway += row_gateway
    return gross, gateway, True

def _booking_other_variable_cost_total(booking):
    from apps.bookings.models import BookingVariableCost
    values = BookingVariableCost.objects.filter(booking=booking).values_list("amount", flat=True)
    return sum((_decimal(value) or ZERO for value in values), ZERO)


def _booking_other_costs_reviewed(booking):
    from apps.bookings.models import BookingFinanceReconciliation
    reconciliation = BookingFinanceReconciliation.objects.filter(booking=booking).first()
    return bool(
        reconciliation is not None
        and reconciliation.other_costs_reviewed
        and reconciliation.reviewed_at is not None
    )


def calculate_booking_actual_finance(booking):
    from apps.bookings.models import OrderItem
    from apps.accounts.models import Referral
    from apps.wallet.models import WalletTransaction
    reasons = []
    item = OrderItem.objects.select_related('order').filter(booking=booking).first()
    pricing = booking.pricing_snapshot or {}
    subtotal = _decimal(item.line_subtotal if item is not None else pricing.get('subtotal'))
    tax = _decimal(item.tax_amount if item is not None else pricing.get('tax', pricing.get('tax_amount')))
    line_total = _decimal(item.line_total if item is not None else pricing.get('total'))
    if subtotal is None or subtotal < 0:
        reasons.append('Customer service subtotal is unavailable')
        subtotal = ZERO
    if tax is None or tax < 0:
        reasons.append('Service tax snapshot is unavailable')
        tax = ZERO
    if line_total is None or line_total <= 0:
        line_total = subtotal + tax
    discount = ZERO
    if item is not None and item.order.discount_amount:
        order_subtotal = _decimal(item.order.subtotal) or ZERO
        if order_subtotal > 0:
            discount = _money(_decimal(item.order.discount_amount) * subtotal / order_subtotal)
    elif item is None:
        reasons.append('Legacy booking discount allocation is unavailable')
    payments = Payment.objects.filter(status=Payment.Status.PAID).filter(Q(booking=booking) | Q(order__items__booking=booking)).distinct()
    if not payments.exists():
        reasons.append('No captured payment is linked to this booking')
    gateway_fee = ZERO
    gateway_fee_tax = ZERO
    gateway_fee_known = True
    for payment in payments:
        gross_allocation, gateway_allocation, allocation_known = _booking_payment_allocation(payment, booking)
        if not allocation_known:
            reasons.append('Payment #%s service allocation is unavailable' % payment.pk)
            continue
        if gross_allocation <= 0:
            continue
        if gateway_allocation <= 0 or payment.method != Payment.Method.RAZORPAY:
            continue
        if payment.gateway_fee_amount is None or payment.gateway_fee_tax_amount is None:
            if gateway_allocation > 0:
                gateway_fee_known = False
                reasons.append('Payment #%s actual gateway fee is not recorded' % payment.pk)
            continue
        payment_gateway_total = _decimal(payment.amount)
        if payment_gateway_total is None or payment_gateway_total <= 0:
            continue
        ratio = min(gateway_allocation / payment_gateway_total, Decimal('1'))
        gateway_fee += payment.gateway_fee_amount * ratio
        gateway_fee_tax += payment.gateway_fee_tax_amount * ratio
    refunds = PaymentRefund.objects.filter(booking=booking, status=PaymentRefund.Status.PROCESSED, extra_work__isnull=True)
    refunded_gross = sum((_decimal(value) or ZERO for value in refunds.values_list('amount', flat=True)), ZERO)
    refunded_service_revenue = _money(refunded_gross * subtotal / line_total) if line_total > 0 else ZERO
    earning = WorkerEarning.objects.filter(booking=booking, extra_work__isnull=True).order_by('-updated_at', '-pk').first()
    worker_payout = _decimal(earning.net_amount) if earning is not None else None
    if worker_payout is None or worker_payout < 0:
        reasons.append('Worker earning/payout snapshot is not available')
        worker_payout = ZERO
    if WorkerEarning.objects.filter(booking=booking, extra_work__isnull=False).exists():
        reasons.append('Separately quoted extra-work revenue and payout are not included')
    mission_rewards = sum((_decimal(amount) or ZERO for amount in WorkerRewardTransaction.objects.filter(booking=booking, type=WorkerRewardTransaction.Type.MISSION_REWARD).values_list('amount', flat=True)), ZERO)
    if earning is not None:
        mission_events = WorkerRewardTransaction.objects.filter(
            worker_id=earning.worker_id,
            type=WorkerRewardTransaction.Type.MISSION_REWARD,
            booking__isnull=True,
            milestone_jobs__isnull=False,
        ).order_by('created_at')
        for event in mission_events:
            milestone = event.milestone_jobs or 0
            if milestone <= 0:
                continue
            eligible_ids = list(
                WorkerRewardTransaction.objects.filter(
                    worker_id=earning.worker_id,
                    type=WorkerRewardTransaction.Type.ELIGIBLE_JOB,
                    created_at__lte=event.created_at,
                ).order_by('-created_at').values_list('booking_id', flat=True)[:milestone]
            )
            if booking.pk in eligible_ids:
                mission_rewards += (_decimal(event.amount) or ZERO) / Decimal(milestone)
    from apps.bookings.models import BookingReworkProposal
    rework_payout = ZERO
    proposals = BookingReworkProposal.objects.filter(
        dispute__booking=booking,
        followup_booking__isnull=False,
    ).select_related('followup_booking')
    for proposal in proposals:
        followup_earning = WorkerEarning.objects.filter(
            booking=proposal.followup_booking,
            extra_work__isnull=True,
        ).order_by('-updated_at', '-pk').first()
        if followup_earning and followup_earning.net_amount is not None:
            rework_payout += followup_earning.net_amount
    customer_reward_cost = ZERO
    referral = Referral.objects.filter(referred=booking.customer, rewarded=True).first()
    first_completed_booking_id = booking.customer.bookings.filter(status='completed').order_by('completed_at', 'pk').values_list('pk', flat=True).first()
    if referral is not None and first_completed_booking_id == booking.pk:
        referral_keys = ['referral:%s:referrer' % referral.pk, 'referral:%s:referred:first-service' % referral.pk]
        customer_reward_cost = sum((_decimal(amount) or ZERO for amount in WalletTransaction.objects.filter(wallet__user_id__in=[referral.referrer_id, referral.referred_id], type=WalletTransaction.Type.CASHBACK, status=WalletTransaction.Status.COMPLETED, reference_id__in=referral_keys).values_list('amount', flat=True)), ZERO)
    unallocated_cashback = WalletTransaction.objects.filter(wallet__user=booking.customer, type=WalletTransaction.Type.CASHBACK, status=WalletTransaction.Status.COMPLETED).exclude(reference_id__startswith='referral:').exists()
    if unallocated_cashback:
        reasons.append('Non-referral customer wallet rewards are not attributed to a booking')
    other_variable_costs = _booking_other_variable_cost_total(booking)
    if not _booking_other_costs_reviewed(booking):
        reasons.append('Other variable operating expenses have not been reviewed by Finance')
    if not gateway_fee_known:
        gateway_fee = None
        gateway_fee_tax = None
    partial = subtotal - discount - refunded_service_revenue - worker_payout - mission_rewards - rework_payout - customer_reward_cost - other_variable_costs
    if gateway_fee is not None and gateway_fee_tax is not None:
        partial -= gateway_fee + gateway_fee_tax
    return {
        'status': 'complete' if not reasons else 'incomplete',
        'subtotal': _money(subtotal), 'tax': _money(tax), 'discount': _money(discount),
        'refunded_gross': _money(refunded_gross), 'refunded_service_revenue': _money(refunded_service_revenue),
        'worker_payout': _money(worker_payout),
        'gateway_fee': _money(gateway_fee) if gateway_fee is not None else None,
        'gateway_fee_tax': _money(gateway_fee_tax) if gateway_fee_tax is not None else None,
        'mission_rewards': _money(mission_rewards), 'rework_payout': _money(rework_payout), 'customer_reward_cost': _money(customer_reward_cost), 'other_variable_costs': _money(other_variable_costs), 'partial_contribution': _money(partial),
        'reasons': list(dict.fromkeys(reasons)),
    }

def _finalize_profitability_summary(result):
    for key in ("actual_contribution_total", "estimated_contribution_total",
                "comparable_actual_total", "comparable_estimated_total"):
        result[key] = _money(result[key])
    if result["estimated_count"]:
        result["estimated_average"] = _money(
            result["estimated_contribution_total"] / result["estimated_count"]
        )
        result["variance"] = _money(
            result["comparable_actual_total"] - result["comparable_estimated_total"]
        )
    if result["actual_complete_count"]:
        result["actual_average"] = _money(
            result["actual_contribution_total"] / result["actual_complete_count"]
        )
    if (
        result["booking_count"] > 0
        and result["actual_complete_count"] == result["booking_count"]
        and result["estimated_count"] == result["booking_count"]
    ):
        result["profitability_status"] = (
            "Profitable" if result["actual_contribution_total"] > ZERO
            else "Loss-making" if result["actual_contribution_total"] < ZERO
            else "Break-even"
        )
    else:
        result["profitability_status"] = "Insufficient data"
    return result


def summarize_service_profitability(bookings, service=None):
    """Summarize completed bookings using each booking's own service assumptions."""
    from apps.catalog.finance import calculate_estimated_contribution

    result = {
        "booking_count": 0,
        "actual_complete_count": 0,
        "actual_incomplete_count": 0,
        "estimated_count": 0,
        "actual_contribution_total": ZERO,
        "estimated_contribution_total": ZERO,
        "comparable_actual_total": ZERO,
        "comparable_estimated_total": ZERO,
        "variance": None,
        "actual_average": None,
        "estimated_average": None,
    }
    for booking in bookings:
        result["booking_count"] += 1
        actual = calculate_booking_actual_finance(booking)
        if actual["status"] != "complete":
            result["actual_incomplete_count"] += 1
            continue
        result["actual_complete_count"] += 1
        result["actual_contribution_total"] += actual["partial_contribution"]

        pricing = booking.pricing_snapshot or {}
        payout_snapshot = booking.worker_payout_snapshot or {}
        estimate_service = service or booking.service
        estimated = calculate_estimated_contribution(
            customer_price=pricing.get("subtotal"),
            worker_payout=payout_snapshot.get("total"),
            service=estimate_service,
        ) if pricing.get("subtotal") is not None and payout_snapshot.get("total") is not None else None
        if estimated is None:
            continue
        result["estimated_count"] += 1
        result["estimated_contribution_total"] += estimated
        result["comparable_actual_total"] += actual["partial_contribution"]
        result["comparable_estimated_total"] += estimated

    return _finalize_profitability_summary(result)


def combine_profitability_summaries(summaries):
    """Combine service summaries without recalculating bookings or mixing assumptions."""
    combined = {
        "booking_count": 0,
        "actual_complete_count": 0,
        "actual_incomplete_count": 0,
        "estimated_count": 0,
        "actual_contribution_total": ZERO,
        "estimated_contribution_total": ZERO,
        "comparable_actual_total": ZERO,
        "comparable_estimated_total": ZERO,
        "variance": None,
        "actual_average": None,
        "estimated_average": None,
    }
    for summary in summaries:
        for key in (
            "booking_count", "actual_complete_count", "actual_incomplete_count",
            "estimated_count", "actual_contribution_total", "estimated_contribution_total",
            "comparable_actual_total", "comparable_estimated_total",
        ):
            combined[key] += summary[key]
    return _finalize_profitability_summary(combined)


def build_service_profitability_report(service, variant=None, start_date=None, end_date=None):
    """Return completed-booking profitability for a service/package and date range."""
    from apps.bookings.models import Booking

    bookings = Booking.objects.filter(
        service=service, status=Booking.Status.COMPLETED
    ).select_related("service", "variant").order_by("pk")
    if variant is not None:
        bookings = bookings.filter(variant=variant)
    if start_date:
        bookings = bookings.filter(completed_at__date__gte=start_date)
    if end_date:
        bookings = bookings.filter(completed_at__date__lte=end_date)
    return summarize_service_profitability(bookings, service=service)
