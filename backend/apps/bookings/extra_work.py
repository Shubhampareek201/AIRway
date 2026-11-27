from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.notifications.models import Notification

from apps.bookings.models import Booking, BookingAssignment, BookingExtraWork
from apps.workers.models import WorkerProfile


def _extra_work_payload(item, *, include_worker_payout=False):
    payload = {
        "id": item.pk,
        "request_key": str(item.request_key),
        "booking_id": item.booking_id,
        "appointment_group_id": item.appointment_group_id,
        "worker_id": item.worker_id,
        "reason": item.reason,
        "line_items": item.line_items,
        "subtotal": str(item.subtotal),
        "tax_amount": str(item.tax_amount),
        "total_amount": str(item.total_amount),
        "additional_duration_minutes": item.additional_duration_minutes,
        "status": (
            BookingExtraWork.Status.EXPIRED
            if item.status == BookingExtraWork.Status.PENDING_CUSTOMER
            and item.expires_at and item.expires_at <= timezone.now()
            else item.status
        ),
        "payment_choice": item.payment_choice,
        "payment_status": item.payment_status,
        "customer_response_note": item.customer_response_note,
        "expires_at": item.expires_at.isoformat() if item.expires_at else None,
        "responded_at": item.responded_at.isoformat() if item.responded_at else None,
        "approved_at": item.approved_at.isoformat() if item.approved_at else None,
        "created_at": item.created_at.isoformat(),
    }
    if include_worker_payout:
        payload["worker_payout_amount"] = (
            str(item.worker_payout_amount)
            if item.worker_payout_amount is not None else None
        )
    return payload



def _calculate_extra_work_worker_payout(booking, worker, subtotal):
    """
    Snapshot extra-work payout using this booking's own configured payout economics.
    Duration is deliberately not an input: ordinary time overruns never change fixed pay.
    """
    from apps.bookings.models import OrderItem
    from apps.workers.models import WorkerEarning

    subtotal = Decimal(str(subtotal))
    payout_snapshot = booking.worker_payout_snapshot or {}
    pricing_model = payout_snapshot.get("pricing_model")
    base_payout_raw = payout_snapshot.get("total")
    base_subtotal_raw = OrderItem.objects.filter(
        booking_id=booking.pk
    ).values_list("line_subtotal", flat=True).first()
    if base_subtotal_raw is None:
        pricing = booking.pricing_snapshot or {}
        base_subtotal_raw = pricing.get("subtotal", pricing.get("total"))

    if pricing_model in ("fixed_service_payout_v1", "admin_approved_quote_payout_v1"):
        if base_payout_raw in (None, "") or base_subtotal_raw in (None, ""):
            return None, {}
        base_payout = Decimal(str(base_payout_raw))
        base_subtotal = Decimal(str(base_subtotal_raw))
        if (
            not base_payout.is_finite() or base_payout <= 0
            or not base_subtotal.is_finite() or base_subtotal <= 0
        ):
            return None, {}
        payout_ratio = base_payout / base_subtotal
        calculation = {
            "pricing_model": "booking_fixed_payout_ratio_v1",
            "source_booking_id": booking.pk,
            "base_customer_subtotal": str(base_subtotal),
            "base_worker_payout": str(base_payout),
            "payout_ratio": str(payout_ratio),
        }
    else:
        # Legacy bookings retain their already locked commission basis; never
        # borrow the customer's wallet or infer payout from elapsed duration.
        locked_earning = WorkerEarning.objects.filter(
            booking=booking, worker=worker, extra_work__isnull=True
        ).first()
        rate = (
            locked_earning.commission_rate
            if locked_earning and locked_earning.commission_rate is not None
            else worker.commission_rate
        )
        if rate is None:
            return None, {}
        rate = Decimal(str(rate))
        if not rate.is_finite() or rate < 0 or rate > 100:
            return None, {}
        payout_ratio = (Decimal("100.00") - rate) / Decimal("100.00")
        calculation = {
            "pricing_model": "legacy_locked_commission_ratio_v1",
            "source_booking_id": booking.pk,
            "commission_rate": str(rate),
            "payout_ratio": str(payout_ratio),
        }

    payout = (subtotal * payout_ratio).quantize(Decimal("0.01"))
    if not payout.is_finite() or payout <= 0:
        return None, {}
    calculation["extra_work_customer_subtotal"] = str(subtotal)
    calculation["worker_payout_amount"] = str(payout)
    return payout, calculation


def _notify_extra_work(user, *, title, body, proposal, event):
    """Best-effort in-app event; notification failure must not break the job."""
    try:
        Notification.objects.get_or_create(
            user=user,
            type=Notification.Type.SYSTEM_ANNOUNCEMENT,
            title=title,
            data__extra_work_id=proposal.pk,
            data__event=event,
            defaults={
                "body": body,
                "channel": Notification.Channel.IN_APP,
                "data": {
                    "extra_work_id": proposal.pk,
                    "booking_id": proposal.booking_id,
                    "appointment_group_id": proposal.appointment_group_id,
                    "event": event,
                },
            },
        )
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "Could not create %s notification for extra-work proposal %s",
            event, proposal.pk,
        )


class WorkerExtraWorkProposalView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, job_id):
        try:
            worker = request.user.worker_profile
        except WorkerProfile.DoesNotExist:
            return Response({"detail": "Worker profile not found."}, status=status.HTTP_404_NOT_FOUND)
        if worker.status != WorkerProfile.Status.APPROVED:
            return Response({"detail": "Only approved workers can propose extra work."}, status=status.HTTP_403_FORBIDDEN)

        try:
            assignment = BookingAssignment.objects.select_for_update().select_related("booking").get(
                booking_id=job_id, worker=worker, accepted_at__isnull=False
            )
        except BookingAssignment.DoesNotExist:
            return Response({"detail": "Accepted job not found."}, status=status.HTTP_404_NOT_FOUND)

        booking = Booking.objects.select_for_update(of=("self",)).select_related("appointment_group").get(pk=job_id)
        if booking.status != Booking.Status.IN_PROGRESS:
            return Response({"detail": "Extra work can only be proposed after the job has started."}, status=status.HTTP_409_CONFLICT)

        # Expired pending rows must stop blocking a worker from submitting a
        # fresh request. The conditional unique constraint remains the final
        # concurrency guard for genuinely active proposals.
        now = timezone.now()
        BookingExtraWork.objects.filter(
            booking=booking,
            status=BookingExtraWork.Status.PENDING_CUSTOMER,
            expires_at__lte=now,
        ).update(
            status=BookingExtraWork.Status.EXPIRED,
            responded_at=now,
            updated_at=now,
        )

        reason = str(request.data.get("reason", "")).strip()
        raw_items = request.data.get("line_items")
        if not reason or len(reason) > 500 or not isinstance(raw_items, list) or not raw_items:
            return Response({"detail": "A reason and at least one item are required."}, status=status.HTTP_400_BAD_REQUEST)
        if len(raw_items) > 20:
            return Response({"detail": "A proposal can contain at most 20 items."}, status=status.HTTP_400_BAD_REQUEST)

        items = []
        subtotal = Decimal("0.00")
        try:
            for row in raw_items:
                if not isinstance(row, dict):
                    raise ValueError
                description = str(row.get("description", "")).strip()
                quantity = int(row.get("quantity", 1))
                unit_price = Decimal(str(row.get("unit_price", ""))).quantize(Decimal("0.01"))
                if not description or len(description) > 250 or quantity < 1 or quantity > 100 or unit_price <= 0 or not unit_price.is_finite():
                    raise ValueError
                line_total = (unit_price * quantity).quantize(Decimal("0.01"))
                subtotal += line_total
                items.append({
                    "description": description,
                    "quantity": quantity,
                    "unit_price": str(unit_price),
                    "line_total": str(line_total),
                })
        except (ValueError, TypeError, InvalidOperation, ArithmeticError):
            return Response({"detail": "Each item needs a description, quantity (1–100), and positive unit price."}, status=status.HTTP_400_BAD_REQUEST)

        if subtotal <= 0 or subtotal > Decimal("1000000.00"):
            return Response({"detail": "The proposal total is outside the allowed range."}, status=status.HTTP_400_BAD_REQUEST)

        tax_rate = Decimal(str(booking.service.tax_rate or "0.00"))
        if not tax_rate.is_finite() or tax_rate < 0 or tax_rate > 100:
            return Response({"detail": "The service tax configuration is invalid. Please contact Admin."}, status=status.HTTP_409_CONFLICT)
        tax_amount = (subtotal * tax_rate / Decimal("100.00")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        total_amount = subtotal + tax_amount

        try:
            duration = int(request.data.get("additional_duration_minutes", 0))
            if duration < 0 or duration > 600:
                raise ValueError
        except (TypeError, ValueError):
            return Response({"detail": "Additional duration must be between 0 and 600 minutes."}, status=status.HTTP_400_BAD_REQUEST)

        worker_payout, worker_payout_snapshot = _calculate_extra_work_worker_payout(
            booking, worker, subtotal
        )
        if worker_payout is None:
            return Response(
                {"detail": "AIRway cannot calculate a fixed payout for this additional scope yet. Please contact Admin."},
                status=status.HTTP_409_CONFLICT,
            )

        try:
            with transaction.atomic():
                proposal = BookingExtraWork.objects.create(
                    booking=booking,
                    appointment_group=booking.appointment_group,
                    worker=worker,
                    reason=reason,
                    line_items=items,
                    subtotal=subtotal,
                    worker_payout_amount=worker_payout,
                    worker_payout_snapshot=worker_payout_snapshot,
                    tax_amount=tax_amount,
                    total_amount=total_amount,
                    additional_duration_minutes=duration,
                    expires_at=timezone.now() + timedelta(hours=24),
                )
        except IntegrityError:
            return Response({"detail": "A pending extra-work proposal already exists for this booking."}, status=status.HTTP_409_CONFLICT)

        _notify_extra_work(
            booking.customer,
            title="Additional work needs your approval",
            body=f"Your AIRway professional requested ₹{proposal.total_amount} for additional work. Review the details before approving.",
            proposal=proposal,
            event="proposed",
        )
        return Response(
            _extra_work_payload(proposal, include_worker_payout=True),
            status=status.HTTP_201_CREATED,
        )


class CustomerExtraWorkListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, booking_id):
        booking = Booking.objects.filter(pk=booking_id, customer=request.user).first()
        if not booking:
            return Response({"detail": "Booking not found."}, status=status.HTTP_404_NOT_FOUND)
        rows = BookingExtraWork.objects.filter(booking=booking).select_related("worker").order_by("-created_at")
        return Response([_extra_work_payload(row) for row in rows])


class CustomerExtraWorkDecisionView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, extra_work_id):
        try:
            proposal = BookingExtraWork.objects.select_for_update().select_related("booking").get(
                pk=extra_work_id, booking__customer=request.user
            )
        except BookingExtraWork.DoesNotExist:
            return Response({"detail": "Extra-work proposal not found."}, status=status.HTTP_404_NOT_FOUND)

        if proposal.status != BookingExtraWork.Status.PENDING_CUSTOMER:
            return Response({"detail": "This proposal has already been decided or is no longer active."}, status=status.HTTP_409_CONFLICT)

        if proposal.expires_at and proposal.expires_at <= timezone.now():
            proposal.status = BookingExtraWork.Status.EXPIRED
            proposal.responded_at = timezone.now()
            proposal.save(update_fields=["status", "responded_at", "updated_at"])
            return Response(
                {"detail": "This extra-work proposal has expired. Ask the professional to submit a new request."},
                status=status.HTTP_409_CONFLICT,
            )

        booking = Booking.objects.select_for_update().get(pk=proposal.booking_id)
        if booking.status != Booking.Status.IN_PROGRESS:
            return Response({"detail": "The appointment is no longer in progress; this proposal cannot be approved."}, status=status.HTTP_409_CONFLICT)
        decision = request.data.get("decision")
        note = str(request.data.get("note", "")).strip()[:1000]
        if decision == "reject":
            proposal.status = BookingExtraWork.Status.REJECTED
            proposal.customer_response_note = note
        elif decision == "approve":
            choice = request.data.get("payment_choice")
            if choice not in BookingExtraWork.PaymentChoice.values:
                return Response({"detail": "Choose separate payment or add to appointment balance."}, status=status.HTTP_400_BAD_REQUEST)
            proposal.status = BookingExtraWork.Status.APPROVED
            proposal.payment_choice = choice
            proposal.payment_status = "pending"
            proposal.customer_response_note = note
            proposal.approved_at = timezone.now()
        else:
            return Response({"detail": "Decision must be approve or reject."}, status=status.HTTP_400_BAD_REQUEST)

        proposal.responded_at = timezone.now()
        proposal.save(update_fields=[
            "status", "payment_choice", "payment_status", "customer_response_note",
            "approved_at", "responded_at", "updated_at",
        ])
        _notify_extra_work(
            proposal.worker.user,
            title="Customer responded to extra-work request",
            body=(
                f"The customer approved the additional work for ₹{proposal.total_amount}."
                if decision == "approve"
                else "The customer declined the additional work request."
            ),
            proposal=proposal,
            event=f"customer_{decision}",
        )
        return Response(_extra_work_payload(proposal))
