from datetime import timedelta
import mimetypes
import os
import uuid

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.db import IntegrityError, transaction
from django.http import FileResponse
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser

from apps.notifications.models import Notification

from .models import (
    Booking, BookingAssignment, BookingDispute, BookingDisputeEvidence,
    BookingReworkProposal, BookingStatusHistory,
)


def _is_assigned_worker(booking, user):
    return BookingAssignment.objects.filter(booking=booking, worker__user=user).exists()


def _serialize_dispute(dispute):
    proposal = getattr(dispute, "rework_proposal", None)
    rework = None
    if proposal is not None:
        rework = {
            "id": proposal.pk,
            "status": proposal.status,
            "scheduled_at": proposal.scheduled_at,
            "worker_name": proposal.worker.user.name or "AIRway Professional",
            "followup_booking_id": proposal.followup_booking_id,
            "followup_status": proposal.followup_booking.status if proposal.followup_booking_id else None,
        }
    return {
        "id": dispute.pk,
        "booking_id": dispute.booking_id,
        "service": dispute.booking.service.title,
        "raised_by_role": dispute.raised_by_role,
        "category": dispute.category,
        "description": dispute.description,
        "requested_outcome": dispute.requested_outcome,
        "evidence_items": dispute.evidence_items,
        "evidence_files": [
            {"id": item.pk, "original_name": item.original_name,
             "note": item.note, "created_at": item.created_at}
            for item in dispute.evidence.all()
        ],
        "status": dispute.status,
        "resolution_note": dispute.resolution_note,
        "resolved_at": dispute.resolved_at,
        "rework_proposal": rework,
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



class BookingDisputeReworkDecisionView(APIView):
    """Customer accepts or declines an Admin-approved, no-charge recovery visit."""
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request, dispute_id):
        dispute = get_object_or_404(
            BookingDispute.objects.select_for_update().select_related(
                "booking__customer", "booking__service__category",
                "booking__variant", "booking__address__zone__city",
            ),
            pk=dispute_id,
            booking__customer=request.user,
        )
        proposal = get_object_or_404(
            BookingReworkProposal.objects.select_for_update().select_related(
                "worker__user", "dispute"
            ),
            dispute=dispute,
        )
        if proposal.status != BookingReworkProposal.Status.PENDING_CUSTOMER:
            return Response({"detail": "This recovery appointment has already been answered."}, status=status.HTTP_409_CONFLICT)
        decision = str(request.data.get("decision", "")).strip().lower()
        if decision not in ("accept", "decline"):
            return Response({"decision": "Choose accept or decline."}, status=status.HTTP_400_BAD_REQUEST)
        now = timezone.now()
        if decision == "decline":
            proposal.status = BookingReworkProposal.Status.DECLINED
            proposal.responded_at = now
            proposal.save(update_fields=["status", "responded_at", "updated_at"])
            Notification.objects.create(
                user=proposal.created_by,
                type=Notification.Type.SYSTEM_ANNOUNCEMENT,
                title="Rework appointment declined",
                body=f"The customer declined the proposed recovery appointment for dispute #{dispute.pk}.",
                channel=Notification.Channel.IN_APP,
                data={"dispute_id": dispute.pk, "rework_proposal_id": proposal.pk},
            )
            return Response(_serialize_dispute(dispute))

        original = dispute.booking
        if proposal.scheduled_at <= now:
            proposal.status = BookingReworkProposal.Status.EXPIRED
            proposal.responded_at = now
            proposal.save(update_fields=["status", "responded_at", "updated_at"])
            return Response({"detail": "The proposed appointment time has passed. AIRway support must issue a new proposal."}, status=status.HTTP_409_CONFLICT)
        if original.booking_mode != Booking.BookingMode.SCHEDULED:
            return Response({"detail": "This service type cannot be automatically rebooked as a recovery visit."}, status=status.HTTP_409_CONFLICT)

        from apps.bookings.dispatcher import DispatcherService
        from apps.workers.eligibility import required_worker_gender_for_booking
        duration = (
            original.variant.duration_minutes
            if original.variant_id and original.variant.duration_minutes
            else original.service.duration_minutes
        ) or 60
        try:
            required_gender = required_worker_gender_for_booking(original.service, original.customer_answers)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        eligible = DispatcherService._get_eligible_workers(
            service=original.service,
            zone=original.address.zone,
            scheduled_at=proposal.scheduled_at,
            duration_minutes=duration,
            exclude_booking_id=original.pk,
            exclude_customer_id=original.customer_id,
            required_gender=required_gender,
            required_tasks=(original.variant.included_tasks if original.variant_id else []),
        )
        if not eligible.filter(pk=proposal.worker_id).exists():
            return Response({"detail": "The proposed professional is no longer available for this time. AIRway support must reschedule."}, status=status.HTTP_409_CONFLICT)

        followup = Booking.objects.create(
            customer=original.customer,
            address=original.address,
            service=original.service,
            variant=original.variant,
            booking_mode=Booking.BookingMode.SCHEDULED,
            scheduled_at=proposal.scheduled_at,
            status=Booking.Status.ASSIGNED,
            pricing_snapshot={
                "subtotal": "0.00", "tax": "0.00", "discount": "0.00",
                "total": "0.00", "quantity": 1, "service_recovery": True,
                "original_booking_id": original.pk, "dispute_id": dispute.pk,
            },
            notes=f"No-charge AIRway service recovery for booking #{original.pk}.",
            customer_answers=original.customer_answers,
        )
        BookingAssignment.objects.create(
            booking=followup, worker=proposal.worker, accepted_at=now,
        )
        BookingStatusHistory.objects.create(
            booking=followup, from_status="", to_status=Booking.Status.ASSIGNED,
            changed_by=request.user,
            note=f"Admin-approved no-charge recovery for dispute #{dispute.pk}.",
        )
        proposal.status = BookingReworkProposal.Status.ACCEPTED
        proposal.responded_at = now
        proposal.followup_booking = followup
        proposal.save(update_fields=["status", "responded_at", "followup_booking", "updated_at"])
        Notification.objects.create(
            user=proposal.worker.user,
            type=Notification.Type.BOOKING_ASSIGNED,
            title="Service recovery appointment assigned",
            body=f"You have been assigned a no-charge recovery visit for booking #{original.pk}.",
            channel=Notification.Channel.IN_APP,
            data={"booking_id": followup.pk, "rework_proposal_id": proposal.pk},
        )
        Notification.objects.create(
            user=original.customer,
            type=Notification.Type.BOOKING_ASSIGNED,
            title="Your recovery appointment is confirmed",
            body=f"Your no-charge service recovery visit is scheduled for {timezone.localtime(proposal.scheduled_at):%d %b %Y, %I:%M %p}.",
            channel=Notification.Channel.IN_APP,
            data={"booking_id": followup.pk, "dispute_id": dispute.pk},
        )
        dispute = BookingDispute.objects.select_related("booking__service").get(pk=dispute.pk)
        return Response(_serialize_dispute(dispute), status=status.HTTP_200_OK)


class BookingDisputeEvidenceUploadView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, dispute_id):
        dispute = get_object_or_404(
            BookingDispute.objects.select_related("booking__customer"),
            pk=dispute_id,
        )
        is_participant = (
            dispute.booking.customer_id == request.user.pk
            or _is_assigned_worker(dispute.booking, request.user)
        )
        if not is_participant:
            return Response({"detail": "Dispute not found."}, status=status.HTTP_404_NOT_FOUND)
        if dispute.status not in (BookingDispute.Status.OPEN, BookingDispute.Status.IN_REVIEW):
            return Response({"detail": "Evidence can only be added while the dispute is active."},
                            status=status.HTTP_400_BAD_REQUEST)
        if dispute.evidence.count() >= 10:
            return Response({"detail": "A dispute can contain up to 10 evidence files."},
                            status=status.HTTP_400_BAD_REQUEST)

        uploaded = request.FILES.get("file")
        if not uploaded:
            return Response({"file": "Choose an image file."}, status=status.HTTP_400_BAD_REQUEST)
        if uploaded.size > 8 * 1024 * 1024:
            return Response({"file": "Evidence images must be 8 MB or smaller."},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            from PIL import Image
            image = Image.open(uploaded)
            width, height = image.size
            image_format = image.format
            image.verify()
            if image_format not in ("JPEG", "PNG", "WEBP"):
                raise ValueError("Unsupported image format")
        except Exception:
            return Response({"file": "Upload a valid JPEG, PNG or WEBP image."},
                            status=status.HTTP_400_BAD_REQUEST)
        finally:
            uploaded.seek(0)

        if width > 6000 or height > 6000:
            return Response({"file": "Image dimensions must not exceed 6000 x 6000 pixels."},
                            status=status.HTTP_400_BAD_REQUEST)

        extension = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}[image_format]
        storage = FileSystemStorage(location=settings.PRIVATE_UPLOAD_ROOT)
        stored_path = storage.save(
            f"booking_dispute_evidence/dispute_{dispute.pk}/{uuid.uuid4().hex}{extension}",
            uploaded,
        )
        evidence = BookingDisputeEvidence.objects.create(
            dispute=dispute,
            uploaded_by=request.user,
            file_path=stored_path,
            original_name=os.path.basename(uploaded.name or "evidence")[:255],
            note=str(request.data.get("note", "")).strip()[:500],
        )
        return Response({
            "id": evidence.pk,
            "original_name": evidence.original_name,
            "note": evidence.note,
            "created_at": evidence.created_at,
        }, status=status.HTTP_201_CREATED)


class BookingDisputeEvidencePhotoView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, evidence_id):
        evidence = get_object_or_404(
            BookingDisputeEvidence.objects.select_related(
                "dispute__booking__customer",
                "dispute__booking__assignment__worker__user",
            ),
            pk=evidence_id,
        )
        is_participant = (
            evidence.dispute.booking.customer_id == request.user.pk
            or _is_assigned_worker(evidence.dispute.booking, request.user)
        )
        if not request.user.is_staff and not is_participant:
            return Response({"detail": "Evidence not found."}, status=status.HTTP_404_NOT_FOUND)

        storage = FileSystemStorage(location=settings.PRIVATE_UPLOAD_ROOT)
        if not storage.exists(evidence.file_path):
            return Response({"detail": "Evidence not found."}, status=status.HTTP_404_NOT_FOUND)
        content_type = mimetypes.guess_type(evidence.file_path)[0] or "application/octet-stream"
        response = FileResponse(storage.open(evidence.file_path, "rb"), content_type=content_type)
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response
