from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Booking, BookingAssignment, BookingDispute


def _is_assigned_worker(booking, user):
    return BookingAssignment.objects.filter(booking=booking, worker__user=user).exists()


def _serialize_dispute(dispute):
    return {
        "id": dispute.pk,
        "booking_id": dispute.booking_id,
        "service": dispute.booking.service.title,
        "raised_by_role": dispute.raised_by_role,
        "category": dispute.category,
        "description": dispute.description,
        "requested_outcome": dispute.requested_outcome,
        "evidence_items": dispute.evidence_items,
        "status": dispute.status,
        "resolution_note": dispute.resolution_note,
        "resolved_at": dispute.resolved_at,
        "created_at": dispute.created_at,
        "updated_at": dispute.updated_at,
    }


class BookingDisputeListCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        disputes = BookingDispute.objects.select_related("booking__service").all()
        if not request.user.is_staff:
            disputes = disputes.filter(
                Q(raised_by=request.user)
                | Q(booking__customer=request.user)
                | Q(booking__assignment__worker__user=request.user)
            ).distinct()
        return Response([_serialize_dispute(item) for item in disputes[:100]])

    def post(self, request):
        booking_id = request.data.get("booking_id")
        booking = get_object_or_404(
            Booking.objects.select_related("customer", "service"),
            pk=booking_id,
        )
        if booking.customer_id == request.user.pk:
            role = "customer"
        elif _is_assigned_worker(booking, request.user):
            role = "worker"
        else:
            return Response({"detail": "Only the booking customer or assigned professional can raise a dispute."},
                            status=status.HTTP_403_FORBIDDEN)

        if booking.status not in (Booking.Status.IN_PROGRESS, Booking.Status.COMPLETED):
            return Response({"detail": "A dispute can be raised while service is in progress or within the post-completion review window."},
                            status=status.HTTP_400_BAD_REQUEST)
        if booking.status == Booking.Status.COMPLETED:
            completion_time = booking.completed_at or booking.updated_at
            if completion_time < timezone.now() - timedelta(days=7):
                return Response({"detail": "The 7-day post-completion dispute window has expired."},
                                status=status.HTTP_400_BAD_REQUEST)

        category = request.data.get("category")
        outcome = request.data.get("requested_outcome")
        description = str(request.data.get("description", "")).strip()
        evidence = request.data.get("evidence_items", [])
        if category not in BookingDispute.Category.values:
            return Response({"category": "Choose a valid dispute category."}, status=status.HTTP_400_BAD_REQUEST)
        if outcome not in BookingDispute.RequestedOutcome.values:
            return Response({"requested_outcome": "Choose a valid requested outcome."}, status=status.HTTP_400_BAD_REQUEST)
        if not description or len(description) > 5000:
            return Response({"description": "Provide a description of up to 5000 characters."}, status=status.HTTP_400_BAD_REQUEST)
        if not isinstance(evidence, list) or len(evidence) > 10:
            return Response({"evidence_items": "Provide up to 10 evidence notes."}, status=status.HTTP_400_BAD_REQUEST)
        clean_evidence = []
        for item in evidence:
            if not isinstance(item, dict):
                return Response({"evidence_items": "Each evidence item must be an object."}, status=status.HTTP_400_BAD_REQUEST)
            label = str(item.get("label", "")).strip()
            detail = str(item.get("detail", "")).strip()
            if not label or len(label) > 100 or len(detail) > 1000:
                return Response({"evidence_items": "Each evidence item needs a label (max 100) and detail (max 1000)."},
                                status=status.HTTP_400_BAD_REQUEST)
            clean_evidence.append({"label": label, "detail": detail})

        try:
            with transaction.atomic():
                dispute = BookingDispute.objects.create(
                    booking=booking,
                    raised_by=request.user,
                    raised_by_role=role,
                    category=category,
                    description=description,
                    requested_outcome=outcome,
                    evidence_items=clean_evidence,
                )
        except IntegrityError:
            return Response({"detail": "An active dispute already exists for this booking."},
                            status=status.HTTP_409_CONFLICT)
        return Response(_serialize_dispute(dispute), status=status.HTTP_201_CREATED)


class BookingDisputeDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self, request, dispute_id):
        dispute = get_object_or_404(
            BookingDispute.objects.select_related("booking__service", "raised_by"),
            pk=dispute_id,
        )
        is_participant = (
            dispute.raised_by_id == request.user.pk
            or dispute.booking.customer_id == request.user.pk
            or _is_assigned_worker(dispute.booking, request.user)
        )
        if not request.user.is_staff and not is_participant:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("You cannot view this dispute.")
        return dispute

    def get(self, request, dispute_id):
        return Response(_serialize_dispute(self.get_object(request, dispute_id)))

    def patch(self, request, dispute_id):
        if not request.user.is_staff:
            return Response({"detail": "Only AIRway support can update dispute status."},
                            status=status.HTTP_403_FORBIDDEN)
        with transaction.atomic():
            dispute = get_object_or_404(BookingDispute.objects.select_for_update(), pk=dispute_id)
            new_status = request.data.get("status")
            allowed = {
                BookingDispute.Status.OPEN: {BookingDispute.Status.IN_REVIEW, BookingDispute.Status.RESOLVED, BookingDispute.Status.REJECTED},
                BookingDispute.Status.IN_REVIEW: {BookingDispute.Status.RESOLVED, BookingDispute.Status.REJECTED},
                BookingDispute.Status.RESOLVED: {BookingDispute.Status.CLOSED},
                BookingDispute.Status.REJECTED: {BookingDispute.Status.CLOSED},
            }
            if new_status not in allowed.get(dispute.status, set()):
                return Response({"status": "Invalid dispute status transition."}, status=status.HTTP_400_BAD_REQUEST)
            note = str(request.data.get("resolution_note", "")).strip()
            if new_status in (BookingDispute.Status.RESOLVED, BookingDispute.Status.REJECTED) and not note:
                return Response({"resolution_note": "A resolution note is required."}, status=status.HTTP_400_BAD_REQUEST)
            dispute.status = new_status
            if note:
                dispute.resolution_note = note[:5000]
            if new_status in (BookingDispute.Status.RESOLVED, BookingDispute.Status.REJECTED):
                dispute.resolved_by = request.user
                dispute.resolved_at = timezone.now()
            dispute.save(update_fields=["status", "resolution_note", "resolved_by", "resolved_at", "updated_at"])
        dispute = BookingDispute.objects.select_related("booking__service").get(pk=dispute.pk)
        return Response(_serialize_dispute(dispute))
