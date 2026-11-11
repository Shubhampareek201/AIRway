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
            ).exclude(worker__user=request.user)
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
            "payment_label": payment_label,
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
        from apps.payments.models import Payment
        order_item = getattr(booking, "order_item", None)
        if order_item:
            order = order_item.order
            allocation = (order.metadata or {}).get("payment_allocation_v1", {})
            if allocation:
                advance_paid = Payment.objects.filter(
                    order=order, stage=Payment.Stage.ADVANCE,
                    status=Payment.Status.PAID,
                ).exists()
                payment_label = (
                    "30% advance received. Remaining balance is due after OTP-verified completion."
                    if advance_paid else "Customer advance payment is pending."
                )
            else:
                legacy_paid = Payment.objects.filter(
                    order=order, stage=Payment.Stage.LEGACY,
                    status=Payment.Status.PAID,
                ).exists()
                payment_label = "Full order payment received." if legacy_paid else "Full order payment pending."
        else:
            booking_paid = Payment.objects.filter(
                booking=booking, status=Payment.Status.PAID
            ).exists()
            payment_label = "Full booking payment received." if booking_paid else "Booking payment pending."
        customer_answers = dict(booking.customer_answers or {})
        if booking.service.requires_female_worker:
            customer_answers["professional_preference"] = "female"
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
            "variant_title": booking.variant.title if booking.variant_id else None,
            "quantity": (
                booking.order_item.quantity
                if hasattr(booking, "order_item")
                else int((booking.pricing_snapshot or {}).get("quantity", 1))
            ),
            "customer_answers": customer_answers,
            "notes": booking.notes,
            "worker_notes": booking.worker_notes,
            "addons": [
                {
                    "title": row.addon.title,
                    "quantity": row.quantity,
                    "total_price": str(row.total_price),
                }
                for row in booking.booking_addons.select_related("addon").all()
            ],
            "form_responses": [
                {"key": fr.form_field.key, "label": fr.form_field.label, "value": fr.value}
                for fr in booking.form_responses.select_related("form_field").all()
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

        order_item = getattr(booking, "order_item", None)
        if order_item and "payment_allocation_v1" in (order_item.order.metadata or {}):
            from apps.payments.models import Payment
            if not Payment.objects.filter(
                order=order_item.order,
                stage=Payment.Stage.ADVANCE,
                status=Payment.Status.PAID,
            ).exists():
                return Response(
                    {"detail": "The customer advance payment has not been verified."},
                    status=status.HTTP_409_CONFLICT,
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

        # Keep the worker-facing route, but route completion through the single
        # booking lifecycle implementation that enforces customer OTP checks.
        from apps.bookings.views import BookingViewSet
        return BookingViewSet().complete_job(request, pk=booking.pk)


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

        if profile.status != WorkerProfile.Status.APPROVED:
            return Response(
                {"detail": "Only approved workers can change availability."},
                status=status.HTTP_403_FORBIDDEN,
            )

        online = request.data.get("is_online")
        if not isinstance(online, bool):
            return Response(
                {"is_online": ["A boolean value is required."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        profile.is_online = online
        profile.save(update_fields=["is_online", "updated_at"])
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
        ).select_related(
            "booking__service", "booking__variant", "booking__address", "worker__user", "order"
        ).prefetch_related(
            "booking__form_responses__form_field",
            "booking__booking_addons__addon",
            "order__items__booking__service",
            "order__items__booking__variant",
        )

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
        """Atomically accept either a standalone booking or every line in an order."""
        offer = self.get_object()
        payment_order_id = None
        now = timezone.now()
        with transaction.atomic():
            # Lock the parent order before any offer rows. This consistent lock
            # order prevents deadlocks when two workers accept different offers
            # for the same order at nearly the same time.
            order = None
            if offer.order_id:
                from apps.bookings.models import Order
                order = Order.objects.select_for_update().get(pk=offer.order_id)
            offer = WorkerOffer.objects.select_for_update().get(pk=offer.pk)
            worker = WorkerProfile.objects.select_for_update().get(pk=offer.worker_id)
            if worker.user_id != request.user.id:
                return Response({"detail": "This offer does not belong to you."}, status=status.HTTP_404_NOT_FOUND)
            if offer.status != WorkerOffer.Status.PENDING:
                return Response({"detail": f"Offer is already {offer.get_status_display().lower()}."}, status=status.HTTP_400_BAD_REQUEST)
            if offer.expires_at <= now:
                offer.status = WorkerOffer.Status.EXPIRED
                offer.responded_at = now
                offer.save(update_fields=["status", "responded_at", "updated_at"])
                return Response({"detail": "This job offer has expired."}, status=status.HTTP_410_GONE)
            if worker.status != WorkerProfile.Status.APPROVED or not worker.is_online:
                return Response({"detail": "Only online, approved workers can accept offers."}, status=status.HTTP_409_CONFLICT)

            if order:
                if offer.status != WorkerOffer.Status.PENDING:
                    return Response({"detail": "This order has already been accepted by another worker."}, status=status.HTTP_409_CONFLICT)
                bookings = list(
                    Booking.objects.select_for_update(of=("self",)).filter(order_item__order=order)
                    .exclude(status=Booking.Status.CANCELLED)
                    .select_related("service__category", "variant", "address__zone__city")
                    .order_by("pk")
                )
                if not bookings:
                    return Response({"detail": "This order no longer has service bookings."}, status=status.HTTP_409_CONFLICT)
                if order.status not in (Order.Status.AWAITING_ASSIGNMENT, Order.Status.PARTIALLY_CANCELLED):
                    return Response({"detail": "This order is no longer awaiting assignment."}, status=status.HTTP_409_CONFLICT)
                from apps.payments.models import Payment
                if "payment_allocation_v1" in (order.metadata or {}) and not Payment.objects.filter(
                    order=order,
                    stage=Payment.Stage.ADVANCE,
                    status=Payment.Status.PAID,
                ).exists():
                    return Response(
                        {"detail": "The customer's 30% advance must be verified before accepting this order."},
                        status=status.HTTP_409_CONFLICT,
                    )
            else:
                bookings = [Booking.objects.select_for_update(of=("self",)).select_related(
                    "service__category", "variant", "address__zone__city"
                ).get(pk=offer.booking_id)]

            if order:
                from apps.bookings.dispatcher import DispatcherService
                if not DispatcherService.order_schedule_is_compatible(bookings):
                    return Response({"detail": "The service times in this order overlap. Please reschedule the order before worker assignment."}, status=status.HTTP_409_CONFLICT)

            if any(
                booking.status not in (Booking.Status.PENDING, Booking.Status.CONFIRMED)
                or BookingAssignment.objects.filter(booking=booking).exists()
                for booking in bookings
            ):
                return Response({"detail": "This booking or order has already been assigned."}, status=status.HTTP_400_BAD_REQUEST)

            from apps.bookings.dispatcher import DispatcherService
            from apps.workers.eligibility import required_worker_gender_for_booking
            for booking in bookings:
                zone = booking.address.zone if booking.address_id else None
                if not (
                    booking.service.is_active and booking.service.category.is_active
                    and zone and zone.is_active and zone.city.is_active
                ):
                    return Response({"detail": "A service or booking area is no longer active."}, status=status.HTTP_409_CONFLICT)
                duration = (
                    booking.variant.duration_minutes
                    if booking.variant_id and booking.variant.duration_minutes
                    else booking.service.duration_minutes
                ) or 60
                quantity = max(int((booking.pricing_snapshot or {}).get("quantity", 1) or 1), 1)
                try:
                    required_gender = required_worker_gender_for_booking(
                        booking.service, booking.customer_answers
                    )
                except ValueError:
                    return Response({"detail": "A service has an invalid professional preference."}, status=status.HTTP_409_CONFLICT)
                eligible = DispatcherService._get_eligible_workers(
                    service=booking.service,
                    zone=zone,
                    scheduled_at=booking.scheduled_at,
                    duration_minutes=duration * quantity,
                    drop_scheduled_at=(
                        booking.drop_scheduled_at
                        if booking.booking_mode == Booking.BookingMode.PICKUP_DROP else None
                    ),
                    exclude_booking_id=booking.pk,
                    exclude_customer_id=booking.customer_id,
                    required_gender=required_gender,
                ).filter(pk=worker.pk).exists()
                if not eligible:
                    return Response(
                        {"detail": "You are no longer eligible or available for every service in this order." if order else "You are no longer eligible or available for this booking time."},
                        status=status.HTTP_409_CONFLICT,
                    )

            assignments = []
            for booking in bookings:
                assignment = BookingAssignment.objects.create(
                    booking=booking, worker=worker, accepted_at=now,
                )
                assignments.append(assignment)
                old_status = booking.status
                booking.status = Booking.Status.ASSIGNED
                booking.save(update_fields=["status", "updated_at"])
                BookingStatusHistory.objects.create(
                    booking=booking, from_status=old_status,
                    to_status=Booking.Status.ASSIGNED, changed_by=worker.user,
                    note="Worker accepted complete order offer" if order else "Worker accepted job offer",
                )
                Notification.objects.create(
                    user=booking.customer,
                    type=Notification.Type.BOOKING_ASSIGNED,
                    title="Worker Assigned",
                    body=f"Your service is now assigned to {worker.user.name or worker.user.phone}.",
                    channel=Notification.Channel.IN_APP,
                    data={"booking_id": booking.pk, "order_id": order.pk if order else None, "worker_id": worker.pk},
                )

            offer.status = WorkerOffer.Status.ACCEPTED
            offer.accepted_at = now
            offer.responded_at = now
            offer.save(update_fields=["status", "accepted_at", "responded_at", "updated_at"])
            if order:
                WorkerOffer.objects.filter(
                    order=order, status=WorkerOffer.Status.PENDING
                ).exclude(pk=offer.pk).update(
                    status=WorkerOffer.Status.WITHDRAWN, responded_at=now
                )
                order.status = (
                    Order.Status.PARTIALLY_CANCELLED
                    if order.items.filter(booking__status=Booking.Status.CANCELLED).exists()
                    else Order.Status.AWAITING_PAYMENT
                )
                order.save(update_fields=["status", "updated_at"])

        if not order:
            try:
                from apps.payments.views import create_or_get_payment
                _, payment_order_id, _ = create_or_get_payment(
                    booking=bookings[0], customer=bookings[0].customer,
                    trigger_source="worker_accept",
                )
            except Exception as exc:
                logger.warning("Payment creation failed for booking %s after worker accept: %s", bookings[0].pk, exc)

        response_data = {
            "status": "accepted",
            "detail": "Complete order accepted successfully." if order else "Offer accepted successfully.",
            "booking_status": bookings[0].status,
            "assignment_id": assignments[0].pk,
            "assigned_booking_ids": [booking.pk for booking in bookings],
            "order_id": order.pk if order else None,
        }
        if payment_order_id:
            response_data["payment_order_id"] = payment_order_id
        return Response(response_data)

    @action(detail=True, methods=["post"], url_path="decline")
    def decline(self, request, pk=None):
        """Decline an offer and advance dispatch when the current batch is exhausted."""
        offer = self.get_object()
        with transaction.atomic():
            offer = WorkerOffer.objects.select_for_update().get(pk=offer.pk)
            if offer.worker.user_id != request.user.id:
                return Response({"detail": "This offer does not belong to you."}, status=status.HTTP_404_NOT_FOUND)
            if offer.status != WorkerOffer.Status.PENDING:
                return Response({"detail": f"Offer is already {offer.get_status_display().lower()}."}, status=status.HTTP_400_BAD_REQUEST)
            offer.status = WorkerOffer.Status.DECLINED
            offer.responded_at = timezone.now()
            offer.save(update_fields=["status", "responded_at", "updated_at"])
            order_id = offer.order_id
            booking_id = offer.booking_id
        if order_id and not WorkerOffer.objects.filter(order_id=order_id, status=WorkerOffer.Status.PENDING).exists():
            from apps.bookings.models import Order
            from apps.bookings.dispatcher import DispatcherService
            DispatcherService.dispatch_order(Order.objects.get(pk=order_id))
        elif not order_id and not WorkerOffer.objects.filter(booking_id=booking_id, order__isnull=True, status=WorkerOffer.Status.PENDING).exists():
            from apps.bookings.dispatcher import DispatcherService
            DispatcherService.dispatch_offers(Booking.objects.get(pk=booking_id))
        return Response({"detail": "Offer declined."})

    @action(detail=True, methods=["post"], url_path="withdraw")
    def withdraw(self, request, pk=None):
        """Withdraw a pending offer and advance dispatch when its batch is exhausted."""
        offer = self.get_object()
        with transaction.atomic():
            offer = WorkerOffer.objects.select_for_update().get(pk=offer.pk)
            if offer.worker.user_id != request.user.id:
                return Response({"detail": "Cannot withdraw offer from another user."}, status=status.HTTP_403_FORBIDDEN)
            if offer.status != WorkerOffer.Status.PENDING:
                return Response(
                    {"detail": f"Cannot withdraw offer in {offer.get_status_display().lower()} state."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            offer.status = WorkerOffer.Status.WITHDRAWN
            offer.responded_at = timezone.now()
            offer.save(update_fields=["status", "responded_at", "updated_at"])
            order_id, booking_id = offer.order_id, offer.booking_id
        if order_id and not WorkerOffer.objects.filter(order_id=order_id, status=WorkerOffer.Status.PENDING).exists():
            from apps.bookings.models import Order
            from apps.bookings.dispatcher import DispatcherService
            DispatcherService.dispatch_order(Order.objects.get(pk=order_id))
        elif not order_id and not WorkerOffer.objects.filter(
            booking_id=booking_id, order__isnull=True, status=WorkerOffer.Status.PENDING
        ).exists():
            from apps.bookings.dispatcher import DispatcherService
            DispatcherService.dispatch_offers(Booking.objects.get(pk=booking_id))
        return Response({"detail": "Offer withdrawn."})
