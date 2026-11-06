import logging
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q
from django import forms
from rest_framework import status, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils import timezone

from apps.accounts.models import Address, User
from apps.catalog.models import Service
from apps.core.models import Zone
from apps.bookings.models import Booking, BookingStatusHistory, BookingAssignment, WorkerOffer
from apps.notifications.models import Notification
from apps.wallet.models import WalletTransaction

logger = logging.getLogger(__name__)

from .models import (
    WorkerProfile,
    WorkerService,
    WorkerZone,
    WorkerSchedule,
    WorkerLeave,
    WorkerDocument,
    WorkerJobStreak,
)
from .serializers import (
    WorkerProfileSerializer,
    WorkerProfileUpdateSerializer,
    WorkerDocumentSerializer,
    WorkerServiceSerializer,
    WorkerZoneSerializer,
    WorkerScheduleSerializer,
    WorkerLeaveSerializer,
    WorkerJobStreakSerializer,
)


class NearbyWorkersView(APIView):
    """Return approved, online workers assigned to the customer's saved service zone."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        address_id = request.query_params.get("address_id")
        addresses = Address.objects.filter(
            user=request.user, deleted_at__isnull=True,
        ).select_related("zone")

        if address_id:
            address = addresses.filter(pk=address_id).first()
            if address is None:
                return Response({"detail": "Saved address not found."}, status=status.HTTP_404_NOT_FOUND)
        else:
            address = addresses.filter(is_default=True).first() or addresses.order_by("-id").first()

        if address is None:
            return Response({"count": 0, "results": [], "message": "Add a saved address to check local partner availability."})

        if not address.zone_id or not address.zone.is_active:
            return Response({"count": 0, "results": [], "message": "A supported service zone has not been confirmed for this address."})

        zone_links = (
            WorkerZone.objects.filter(
                zone_id=address.zone_id,
                worker__status="approved",
                worker__is_online=True,
            )
            .select_related("worker__user")
            .distinct()
        )

        results = []
        seen_worker_ids = set()
        for zone_link in zone_links:
            worker = zone_link.worker
            if worker.pk in seen_worker_ids:
                continue

            service_rows = WorkerService.objects.filter(
                worker=worker,
                service__is_active=True,
                service__category__is_active=True,
            ).select_related("service").order_by("service__sort_order", "service__title")
            service_titles = list(service_rows.values_list("service__title", flat=True))
            if not service_titles:
                continue

            user = worker.user
            name = (user.name or "").strip() or "Verified partner"
            rating = getattr(worker, "rating_avg", None)
            results.append({
                "id": worker.pk,
                "name": name,
                "rating": float(rating) if rating is not None else None,
                "services": service_titles,
                "is_online": True,
            })
            seen_worker_ids.add(worker.pk)

        results.sort(key=lambda item: (item["rating"] is None, -(item["rating"] or 0)))
        return Response({"count": len(results), "results": results})


class WorkerProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile = WorkerProfile.objects.filter(user=request.user).first()
        if profile is None:
            return Response({
                "id": None,
                "status": "no_profile",
                "is_online": False,
                "rating_avg": None,
                "experience_years": None,
                "upi_id": None,
                "photo_url": None,
            })
        serializer = WorkerProfileSerializer(profile)
        return Response(serializer.data)

    def put(self, request):
        profile, _ = WorkerProfile.objects.get_or_create(user=request.user)
        serializer = WorkerProfileUpdateSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(WorkerProfileSerializer(profile).data)

    def patch(self, request):
        return self.put(request)


class WorkerServiceListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            profile = request.user.worker_profile
        except WorkerProfile.DoesNotExist:
            return Response({"detail": "No worker profile found."}, status=status.HTTP_404_NOT_FOUND)
        services = WorkerService.objects.filter(worker=profile).select_related("service", "service__category")
        serializer = WorkerServiceSerializer(services, many=True)
        return Response(serializer.data)

    def post(self, request):
        try:
            profile = request.user.worker_profile
        except WorkerProfile.DoesNotExist:
            return Response({"detail": "No worker profile found."}, status=status.HTTP_404_NOT_FOUND)
        service_id = request.data.get("service")
        if not service_id:
            return Response({"service": ["This field is required."]}, status=status.HTTP_400_BAD_REQUEST)
        try:
            service = Service.objects.get(pk=int(service_id), is_active=True)
        except (Service.DoesNotExist, ValueError, TypeError):
            return Response({"service": ["Invalid service."]}, status=status.HTTP_400_BAD_REQUEST)
        obj, created = WorkerService.objects.get_or_create(worker=profile, service=service)
        serializer = WorkerServiceSerializer(obj)
        return Response(serializer.data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class WorkerServiceDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, service_id):
        try:
            profile = request.user.worker_profile
        except WorkerProfile.DoesNotExist:
            return Response({"detail": "No worker profile found."}, status=status.HTTP_404_NOT_FOUND)
        try:
            obj = WorkerService.objects.get(worker=profile, service_id=service_id)
        except WorkerService.DoesNotExist:
            return Response({"detail": "Service link not found."}, status=status.HTTP_404_NOT_FOUND)
        obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class WorkerZoneListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            profile = request.user.worker_profile
        except WorkerProfile.DoesNotExist:
            return Response({"detail": "No worker profile found."}, status=status.HTTP_404_NOT_FOUND)
        zones = WorkerZone.objects.filter(worker=profile).select_related("zone", "zone__city")
        serializer = WorkerZoneSerializer(zones, many=True)
        return Response(serializer.data)

    def post(self, request):
        try:
            profile = request.user.worker_profile
        except WorkerProfile.DoesNotExist:
            return Response({"detail": "No worker profile found."}, status=status.HTTP_404_NOT_FOUND)
        zone_id = request.data.get("zone")
        if not zone_id:
            return Response({"zone": ["This field is required."]}, status=status.HTTP_400_BAD_REQUEST)
        try:
            zone = Zone.objects.get(pk=int(zone_id), is_active=True)
        except (Zone.DoesNotExist, ValueError, TypeError):
            return Response({"zone": ["Invalid zone."]}, status=status.HTTP_400_BAD_REQUEST)
        obj, created = WorkerZone.objects.get_or_create(worker=profile, zone=zone)
        serializer = WorkerZoneSerializer(obj)
        return Response(serializer.data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class WorkerZoneDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, zone_id):
        try:
            profile = request.user.worker_profile
        except WorkerProfile.DoesNotExist:
            return Response({"detail": "No worker profile found."}, status=status.HTTP_404_NOT_FOUND)
        try:
            obj = WorkerZone.objects.get(worker=profile, zone_id=zone_id)
        except WorkerZone.DoesNotExist:
            return Response({"detail": "Zone link not found."}, status=status.HTTP_404_NOT_FOUND)
        obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class WorkerScheduleListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            profile = request.user.worker_profile
        except WorkerProfile.DoesNotExist:
            return Response({"detail": "No worker profile found."}, status=status.HTTP_404_NOT_FOUND)
        schedules = WorkerSchedule.objects.filter(worker=profile)
        serializer = WorkerScheduleSerializer(schedules, many=True)
        return Response(serializer.data)

    def post(self, request):
        try:
            profile = request.user.worker_profile
        except WorkerProfile.DoesNotExist:
            return Response({"detail": "No worker profile found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = WorkerScheduleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        obj = serializer.save(worker=profile)
        return Response(WorkerScheduleSerializer(obj).data, status=status.HTTP_201_CREATED)


class WorkerScheduleDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, schedule_id):
        try:
            profile = request.user.worker_profile
        except WorkerProfile.DoesNotExist:
            return Response({"detail": "No worker profile found."}, status=status.HTTP_404_NOT_FOUND)
        try:
            obj = WorkerSchedule.objects.get(pk=schedule_id, worker=profile)
        except WorkerSchedule.DoesNotExist:
            return Response({"detail": "Schedule not found."}, status=status.HTTP_404_NOT_FOUND)
        obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class WorkerOnboardingView(APIView):
    """Submit/complete worker onboarding. Called when user clicks Done on Step 5 of the onboarding flow."""
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        # Check if user already applied (WorkerProfile exists)
        if WorkerProfile.objects.filter(user=request.user).exists():
            return Response(
                {"detail": "Worker application already exists."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate profile_photo is required
        profile_photo = request.data.get("profile_photo")
        if not profile_photo:
            return Response(
                {"profile_photo": ["This field is required."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate it is a real image (Pillow will raise for non-images)
        try:
            from PIL import Image as PILImage
            if hasattr(profile_photo, 'read'):
                profile_photo.seek(0)
            PILImage.open(profile_photo).verify()
            if hasattr(profile_photo, 'seek'):
                profile_photo.seek(0)
        except Exception:
            return Response(
                {"profile_photo": ["Upload a valid image. The file you uploaded was not a valid image."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Reject files larger than 5MB
        if hasattr(profile_photo, 'size') and profile_photo.size > 5 * 1024 * 1024:
            return Response(
                {"profile_photo": ["File size must not exceed 5MB."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Update User profile fields
        user_updates = {}
        if "name" in request.data and request.data["name"]:
            name = str(request.data["name"]).strip()
            if name:
                request.user.name = name
                user_updates["name"] = name
        if "email" in request.data and request.data["email"]:
            email = str(request.data["email"]).strip()
            if email:
                request.user.email = email
                user_updates["email"] = email
        if "gender" in request.data and request.data["gender"]:
            gender = request.data["gender"]
            if gender in dict(User.Gender.choices):
                request.user.gender = gender
                user_updates["gender"] = gender
        if user_updates:
            request.user.save(update_fields=list(user_updates.keys()))

        # Create WorkerProfile first (required for FK relationships)
        profile = WorkerProfile.objects.create(user=request.user)

        # Attach services by id/title (Service doesn't have slug field)
        services = request.data.get("services", [])
        for sid in services:
            if not sid:
                continue
            try:
                service = Service.objects.get(pk=int(sid), is_active=True)
            except (Service.DoesNotExist, ValueError, TypeError):
                try:
                    service = Service.objects.get(title__iexact=str(sid), is_active=True)
                except Service.DoesNotExist:
                    try:
                        service = Service.objects.get(title__icontains=str(sid), is_active=True)
                    except Service.DoesNotExist:
                        continue
            WorkerService.objects.get_or_create(worker=profile, service=service)

        # Attach zones by id/name
        zones = request.data.get("zones", [])
        for zid in zones:
            if not zid:
                continue
            try:
                zone = Zone.objects.get(pk=int(zid), is_active=True)
            except (Zone.DoesNotExist, ValueError, TypeError):
                try:
                    zone = Zone.objects.get(name__iexact=str(zid), is_active=True)
                except Zone.DoesNotExist:
                    try:
                        zone = Zone.objects.get(name__icontains=str(zid), is_active=True)
                    except Zone.DoesNotExist:
                        continue
            WorkerZone.objects.get_or_create(worker=profile, zone=zone)

        # Attach schedules keyed by weekday (0=Monday..6=Sunday)
        schedule = request.data.get("schedule", {})
        for weekday_str, times in schedule.items():
            try:
                weekday = int(weekday_str)
            except (ValueError, TypeError):
                continue
            if not isinstance(times, dict):
                continue
            start = str(times.get("start", "")).strip()
            end = str(times.get("end", "")).strip()
            if not start or not end:
                continue
            try:
                s = forms.TimeField().to_python(start)
                e = forms.TimeField().to_python(end)
            except DjangoValidationError:
                continue
            WorkerSchedule.objects.update_or_create(
                worker=profile, weekday=weekday, defaults={"start_time": s, "end_time": e, "is_active": True},
            )

        # Save profile photo as WorkerDocument
        WorkerDocument.objects.create(
            worker=profile,
            doc_type=WorkerDocument.DocumentType.PHOTO,
            file=profile_photo,
            status=WorkerDocument.Status.PENDING,
        )

        profile.status = WorkerProfile.Status.PENDING
        profile.save(update_fields=["status"])

        return Response({
            "message": "Onboarding submitted. Awaiting admin approval.",
            "status": profile.status,
            "active_mode": request.user.active_mode,
            "worker_status": profile.status,
        }, status=status.HTTP_201_CREATED)


class WorkerJobListView(APIView):
    """Jobs assigned to the current worker."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            profile = request.user.worker_profile
        except WorkerProfile.DoesNotExist:
            return Response({"detail": "No worker profile found."}, status=status.HTTP_404_NOT_FOUND)

        status_param = request.query_params.get("status")
        query = (
            BookingAssignment.objects
            .filter(worker=profile)
            .select_related("booking__service", "booking__customer", "booking__address")
        )
        if status_param:
            query = query.filter(booking__status=status_param)
        query = query.order_by("-booking__scheduled_at", "-booking__created_at")

        results = []
        for assign in query:
            booking = assign.booking
            results.append({
                "id": assign.id,
                "booking_id": booking.id,
                "status": booking.status,
                "service_title": booking.service.title,
                "customer_name": booking.customer.name or booking.customer.phone,
                "customer_phone": booking.customer.phone,
                "address": booking.address.full_address,
                "scheduled_at": booking.scheduled_at.isoformat() if booking.scheduled_at else "",
                "drop_scheduled_at": booking.drop_scheduled_at.isoformat() if booking.drop_scheduled_at else None,
                "amount": float(booking.pricing_snapshot.get("total", 0) or 0),
                "worker_notes": booking.worker_notes or None,
                "assigned_at": assign.assigned_at.isoformat() if assign.assigned_at else None,
            })
        return Response(results)


class WorkerJobDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            profile = request.user.worker_profile
        except WorkerProfile.DoesNotExist:
            return Response({"detail": "No worker profile found."}, status=status.HTTP_404_NOT_FOUND)
        try:
            assign = BookingAssignment.objects.select_related(
                "booking__service", "booking__customer", "booking__address",
            ).get(pk=pk, worker=profile)
        except BookingAssignment.DoesNotExist:
            return Response({"detail": "Job not found."}, status=status.HTTP_404_NOT_FOUND)
        booking = assign.booking
        return Response({
            "id": assign.id,
"booking_id": booking.id,
            "status": booking.status,
            "service_title": booking.service.title,
            "customer_name": booking.customer.name or booking.customer.phone,
            "customer_phone": booking.customer.phone,
            "address": booking.address.full_address,
            "scheduled_at": booking.scheduled_at.isoformat() if booking.scheduled_at else "",
            "drop_scheduled_at": booking.drop_scheduled_at.isoformat() if booking.drop_scheduled_at else None,
            "amount": float(booking.pricing_snapshot.get("total", 0) or 0),
            "notes": booking.notes,
            "worker_notes": booking.worker_notes,
            "form_responses": [
                {"key": fr.form_field.key, "label": fr.form_field.label, "value": fr.value}
                for fr in booking.form_responses.all()
            ],
            "assignment": {
                "assigned_at": assign.assigned_at.isoformat() if assign.assigned_at else None,
                "accepted_at": assign.accepted_at.isoformat() if assign.accepted_at else None,
                "started_at": assign.started_at.isoformat() if assign.started_at else None,
                "completed_at": assign.completed_at.isoformat() if assign.completed_at else None,
            },
        })


def _get_assignment_and_booking(job_id, profile):
    try:
        assign = BookingAssignment.objects.select_related("booking").get(pk=job_id, worker=profile)
        booking = assign.booking
        return assign, booking
    except BookingAssignment.DoesNotExist:
        return None, None


class WorkerJobAcceptView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, job_id):
        try:
            profile = request.user.worker_profile
        except WorkerProfile.DoesNotExist:
            return Response(
                {"detail": "No worker profile found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        assign, booking = _get_assignment_and_booking(job_id, profile)
        if not booking:
            return Response(
                {"detail": "Job not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if booking.status != Booking.Status.ASSIGNED:
            return Response(
                {"detail": "Job must be assigned before accepting."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        assign.accepted_at = timezone.now()
        assign.save(update_fields=["accepted_at"])

        return Response({"detail": "Job accepted.", "status": booking.status})

class WorkerJobRejectView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, job_id):
        try:
            profile = request.user.worker_profile
        except WorkerProfile.DoesNotExist:
            return Response({"detail": "No worker profile found."}, status=status.HTTP_404_NOT_FOUND)
        assign, booking = _get_assignment_and_booking(job_id, profile)
        if not booking:
            return Response({"detail": "Job not found."}, status=status.HTTP_404_NOT_FOUND)
        if booking.status in (Booking.Status.COMPLETED, Booking.Status.CANCELLED):
            return Response({"detail": "Job already completed or cancelled."}, status=status.HTTP_400_BAD_REQUEST)
        if booking.status != Booking.Status.ASSIGNED:
            return Response({"detail": "Job must be assigned to be rejected."}, status=status.HTTP_400_BAD_REQUEST)
        old = booking.status
        booking.status = Booking.Status.CANCELLED
        booking.cancellation_reason = request.data.get("reason", "")
        booking.cancelled_by = request.user
        booking.cancelled_at = timezone.now()
        booking.save(update_fields=["status", "cancellation_reason", "cancelled_by", "cancelled_at"])
        BookingStatusHistory.objects.create(
            booking=booking, from_status=old, to_status=Booking.Status.CANCELLED,
            changed_by=request.user, note=f"Worker rejected. Reason: {request.data.get('reason', '')}",
        )
        return Response({"detail": "Job rejected.", "status": booking.status})


class WorkerJobStartView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, job_id):
        try:
            profile = request.user.worker_profile
        except WorkerProfile.DoesNotExist:
            return Response(
                {"detail": "No worker profile found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        assign, booking = _get_assignment_and_booking(job_id, profile)
        if not booking:
            return Response(
                {"detail": "Job not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if booking.status not in (Booking.Status.ASSIGNED, Booking.Status.CONFIRMED):
            return Response(
                {"detail": "Job must be assigned and confirmed before starting."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not assign.accepted_at:
            return Response(
                {"detail": "Accept the job before starting work."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        now = timezone.now()
        assign.started_at = now
        assign.save(update_fields=["started_at"])

        old = booking.status
        booking.status = Booking.Status.IN_PROGRESS
        booking.save(update_fields=["status"])

        BookingStatusHistory.objects.create(
            booking=booking,
            from_status=old,
            to_status=Booking.Status.IN_PROGRESS,
            changed_by=request.user,
            note="Worker started the job.",
        )

        return Response({"detail": "Job started.", "status": booking.status})

class WorkerJobCompleteView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, job_id):
        try:
            profile = request.user.worker_profile
        except WorkerProfile.DoesNotExist:
            return Response({"detail": "No worker profile found."}, status=status.HTTP_404_NOT_FOUND)
        assign, booking = _get_assignment_and_booking(job_id, profile)
        if not booking:
            return Response({"detail": "Job not found."}, status=status.HTTP_404_NOT_FOUND)
        if booking.status != Booking.Status.IN_PROGRESS:
            return Response({"detail": "Job must be in progress."}, status=status.HTTP_400_BAD_REQUEST)
        notes = request.data.get("notes", "")
        assign.completed_at = timezone.now()
        assign.save()
        old = booking.status
        booking.status = Booking.Status.COMPLETED
        booking.worker_notes = notes
        booking.save(update_fields=["status", "worker_notes"])
        BookingStatusHistory.objects.create(
            booking=booking, from_status=old, to_status=Booking.Status.COMPLETED,
            changed_by=request.user, note="Worker marked complete.",
        )
        return Response({"detail": "Job completed.", "status": booking.status})


class WorkerEarningsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            profile = request.user.worker_profile
        except WorkerProfile.DoesNotExist:
            return Response({"detail": "No worker profile found."}, status=status.HTTP_404_NOT_FOUND)

        txs = WalletTransaction.objects.filter(
            wallet__user=request.user,
            type=WalletTransaction.Type.CREDIT,
            status=WalletTransaction.Status.COMPLETED,
        ).order_by("-created_at")[:100]
        jobs = Booking.objects.filter(
            assignment__worker=profile, status=Booking.Status.COMPLETED,
        ).select_related("service").order_by("-completed_at")

        results = []
        for tx in txs:
            results.append({
                "id": tx.id,
                "amount": float(tx.amount),
                "status": tx.status,
                "booking_id": int(tx.reference_id) if tx.reference_id else None,
                "service_title": tx.description or "",
                "created_at": tx.created_at.isoformat() if tx.created_at else "",
            })
        for job in jobs:
            if any(r.get("booking_id") == job.id for r in results):
                continue
            results.append({
                "id": job.id,
                "amount": float(job.pricing_snapshot.get("total", 0) or 0),
                "status": "completed",
                "booking_id": job.id,
                "service_title": job.service.title,
                "created_at": job.completed_at.isoformat() if job.completed_at else job.created_at.isoformat(),
            })
        results.sort(key=lambda r: r["created_at"], reverse=True)
        return Response(results)


class WorkerStreaksView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            profile = request.user.worker_profile
        except WorkerProfile.DoesNotExist:
            return Response({"detail": "No worker profile found."}, status=status.HTTP_404_NOT_FOUND)
        streaks = WorkerJobStreak.objects.filter(worker=profile)
        serializer = WorkerJobStreakSerializer(streaks, many=True)
        return Response(serializer.data)



class WorkerDocumentUploadView(APIView):
    """Upload a worker ID document (aadhaar / id / photo / other)."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            profile = request.user.worker_profile
        except WorkerProfile.DoesNotExist:
            return Response(
                {"error": "Worker profile not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if profile.status != WorkerProfile.Status.PENDING:
            return Response(
                {"error": "Document upload is only allowed for pending worker profiles."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        doc_type = request.data.get("doc_type")
        if not doc_type:
            return Response(
                {"doc_type": ["This field is required."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        valid_types = {choice for choice, _ in WorkerDocument.DocumentType.choices}
        if doc_type not in valid_types:
            return Response(
                {"doc_type": ["Invalid document type."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        uploaded_file = request.data.get("file")
        if not uploaded_file:
            return Response(
                {"file": ["No file provided."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Reject files larger than 5MB
        if uploaded_file.size > 5 * 1024 * 1024:
            return Response(
                {"file": ["File size must not exceed 5MB."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate it is a real image (Pillow will raise for non-images)
        try:
            from PIL import Image as PILImage
            PILImage.open(uploaded_file).verify()
        except Exception:
            return Response(
                {"file": ["Uploaded file is not a valid image."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        uploaded_file.seek(0)

        existing = WorkerDocument.objects.filter(
            worker=profile, doc_type=doc_type
        ).first()
        if existing and existing.status == WorkerDocument.Status.VERIFIED:
            return Response(
                {"error": "This document has already been verified and cannot be replaced."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if existing:
            existing.file = uploaded_file
            existing.status = WorkerDocument.Status.PENDING
            existing.save()
            doc = existing
        else:
            doc = WorkerDocument.objects.create(
                worker=profile,
                doc_type=doc_type,
                file=uploaded_file,
                status=WorkerDocument.Status.PENDING,
            )

        return Response(
            {
                "id": doc.id,
                "doc_type": doc.doc_type,
                "status": doc.status,
                "message": "Document uploaded successfully.",
            },
            status=status.HTTP_201_CREATED,
        )


class WorkerDocumentListView(APIView):
    """List worker documents (without sensitive file URLs)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile = WorkerProfile.objects.filter(user=request.user).first()
        if profile is None:
            return Response({"results": []})

        docs = WorkerDocument.objects.filter(worker=profile)
        results = [
            {
                "id": doc.id,
                "doc_type": doc.doc_type,
                "status": doc.status,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
            }
            for doc in docs
        ]
        return Response({"results": results})


class WorkerStatusUpdateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            profile = request.user.worker_profile
        except WorkerProfile.DoesNotExist:
            return Response({"detail": "No worker profile found."}, status=status.HTTP_404_NOT_FOUND)
        online = request.data.get("is_online")
        if online is not None:
            profile.is_online = bool(online)
            profile.save(update_fields=["is_online"])
        return Response({"is_online": profile.is_online})


class WorkerOfferViewSet(viewsets.ModelViewSet):
    """
    Worker job offers API.

    Workers can:
    - List their pending job offers
    - Accept an offer (creates BookingAssignment, transitions booking to ASSIGNED,
      and auto-creates an idempotent Razorpay payment order)
    - Decline an offer (marks offer as declined)
    - Withdraw an offer (retracts their own offer)
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return WorkerOffer.objects.filter(
            worker__user=self.request.user,
            worker__status=WorkerProfile.Status.APPROVED,
        ).select_related("booking", "worker__user")

    def get_serializer_class(self):
        from apps.bookings.serializers import WorkerOfferSerializer
        return WorkerOfferSerializer

    def list(self, request, *args, **kwargs):
        """Override list to return 404 if user has no worker profile."""
        try:
            profile = WorkerProfile.objects.get(user=request.user)
        except WorkerProfile.DoesNotExist:
            return Response(
                {"detail": "No worker profile found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        if profile.status != WorkerProfile.Status.APPROVED:
            return Response(
                {"detail": "Worker profile is not approved."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().list(request, *args, **kwargs)

    @action(detail=True, methods=["post"], url_path="accept")
    def accept(self, request, pk=None):
        """
        Accept a job offer.

        Creates a BookingAssignment and transitions the booking to ASSIGNED.
        Payment creation is idempotent and best-effort: if Razorpay is unavailable
        the assignment still succeeds and payment can be created later.
        Uses atomic transaction to prevent race conditions.
        """
        offer = self.get_object()
        booking = offer.booking

        if offer.status != WorkerOffer.Status.PENDING:
            return Response(
                {"detail": f"Offer is already {offer.get_status_display().lower()}."},
                status=status.HTTP_400_BAD_REQUEST
            )

        worker = offer.worker
        if worker.status != WorkerProfile.Status.APPROVED:
            return Response(
                {"detail": "Worker profile is not approved."},
                status=status.HTTP_403_FORBIDDEN
            )

        if not WorkerService.objects.filter(worker=worker, service=booking.service).exists():
            return Response(
                {"detail": "Worker is not assigned to this service."},
                status=status.HTTP_403_FORBIDDEN
            )

        payment_order_id = None

        # Phase 1: Create assignment in transaction for atomicity
        with transaction.atomic():
            existing_assignment = BookingAssignment.objects.filter(booking=booking).first()
            if existing_assignment:
                return Response(
                    {"detail": "Booking already assigned."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            if booking.status not in [Booking.Status.PENDING, Booking.Status.CONFIRMED]:
                return Response(
                    {"detail": f"Cannot accept offer for booking in {booking.get_status_display()} state."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            assignment = BookingAssignment.objects.create(
                booking=booking,
                worker=worker,
                accepted_at=timezone.now(),
            )

            offer.status = WorkerOffer.Status.ACCEPTED
            offer.accepted_at = timezone.now()
            offer.save()

            old_status = booking.status
            booking.status = Booking.Status.ASSIGNED
            booking.save()

            from apps.bookings.models import BookingStatusHistory
            BookingStatusHistory.objects.create(
                booking=booking,
                from_status=old_status,
                to_status=Booking.Status.ASSIGNED,
                changed_by=worker.user,
                note="Worker accepted job offer",
            )

            Notification.objects.create(
                user=booking.customer,
                type=Notification.Type.BOOKING_ASSIGNED,
                title="Worker Assigned",
                body=f"Your service is now assigned to {worker.user.name or worker.user.phone}.",
                channel=Notification.Channel.IN_APP,
                data={"booking_id": booking.id, "worker_id": worker.id},
            )

        # For a booking inside a multi-service order, the customer pays
        # once at the parent order after every service has an assigned worker.
        # Keep the existing one-booking payment flow unchanged.
        payment_order_id = None
        if not hasattr(booking, "order_item"):
            try:
                from apps.payments.views import create_or_get_payment
                payment, payment_order_id, already_existed = create_or_get_payment(
                    booking=booking,
                    customer=booking.customer,
                    trigger_source="worker_accept",
                )
            except Exception as exc:
                logger.warning(
                    "Payment creation failed for booking %s after worker accept: %s",
                    booking.id, exc,
                )

        response_data = {
            "status": "accepted",
            "detail": "Offer accepted successfully.",
            "booking_status": booking.status,
            "assignment_id": assignment.id,
        }
        if payment_order_id:
            response_data["payment_order_id"] = payment_order_id
        return Response(response_data)

    @action(detail=True, methods=["post"], url_path="decline")
    def decline(self, request, pk=None):
        """Decline a job offer."""
        offer = self.get_object()

        if offer.status != WorkerOffer.Status.PENDING:
            return Response(
                {"detail": f"Offer is already {offer.get_status_display().lower()}."},
                status=status.HTTP_400_BAD_REQUEST
            )

        offer.status = WorkerOffer.Status.DECLINED
        offer.responded_at = timezone.now()
        offer.save()

        return Response({"detail": "Offer declined."})

    @action(detail=True, methods=["post"], url_path="withdraw")
    def withdraw(self, request, pk=None):
        """Withdraw a job offer (worker retracts their offer)."""
        offer = self.get_object()

        if offer.worker.user != request.user:
            return Response(
                {"detail": "Cannot withdraw offer from another user."},
                status=status.HTTP_403_FORBIDDEN
            )

        if offer.status not in [WorkerOffer.Status.PENDING, WorkerOffer.Status.ACCEPTED]:
            return Response(
                {"detail": f"Cannot withdraw offer in {offer.get_status_display().state} state."},
                status=status.HTTP_400_BAD_REQUEST
            )

        offer.status = WorkerOffer.Status.WITHDRAWN
        offer.responded_at = timezone.now()
        offer.save()

        return Response({"detail": "Offer withdrawn."})
