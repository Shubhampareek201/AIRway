def get_account_deletion_obligations(user):
    """Return current booking and financial blockers before an account is closed."""
    from apps.bookings.models import Booking, BookingAssignment
    from apps.payments.models import Payment, PaymentRefund
    from apps.workers.models import WorkerProfile
    from apps.wallet.models import Wallet

    active_statuses = (
        Booking.Status.PENDING,
        Booking.Status.CONFIRMED,
        Booking.Status.ASSIGNED,
        Booking.Status.IN_PROGRESS,
        Booking.Status.DISPUTED,
    )
    active_booking_ids = set(
        user.bookings.filter(status__in=active_statuses).values_list("id", flat=True)
    )

    try:
        worker_profile = user.worker_profile
    except WorkerProfile.DoesNotExist:
        worker_profile = None
    if worker_profile is not None:
        active_booking_ids.update(
            BookingAssignment.objects.filter(
                worker=worker_profile,
                booking__status__in=active_statuses,
            ).values_list("booking_id", flat=True)
        )

    # Query afresh: request.user may carry a cached reverse OneToOne wallet
    # instance whose balance predates a payment/refund update in this request.
    wallet = Wallet.objects.filter(user_id=user.pk).first()
    has_financial_obligations = bool(
        wallet and (
            wallet.balance > 0
            or wallet.pending_balance > 0
            or wallet.reservations.filter(status="reserved").exists()
        )
    )
    has_financial_obligations = has_financial_obligations or Payment.objects.filter(
        customer=user,
        status=Payment.Status.PENDING,
    ).exists() or PaymentRefund.objects.filter(
        payment__customer=user,
        status__in=(PaymentRefund.Status.PROCESSING, PaymentRefund.Status.PENDING),
    ).exists()

    return {
        "has_active_bookings": bool(active_booking_ids),
        "active_booking_count": len(active_booking_ids),
        "has_financial_obligations": has_financial_obligations,
    }
