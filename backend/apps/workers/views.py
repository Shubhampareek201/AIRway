import logging
import uuid
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q
from django import forms
from rest_framework import status, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.views import APIView
from django.utils import timezone

from apps.accounts.models import Address, User
from apps.catalog.models import Service
from apps.core.models import Zone
from apps.bookings.models import Booking, BookingStatusHistory, BookingAssignment, WorkerOffer, BookingQuote, BookingWorkEvidence, Order, OrderItem, AppointmentGroup
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
                worker__schedules__is_active=True,
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
            service = Service.objects.get(pk=int(service_id), is_active=True, category__is_active=True)
        except (Service.DoesNotExist, ValueError, TypeError):
            return Response({"service": ["Invalid service."]}, status=status.HTTP_400_BAD_REQUEST)
        capabilities = request.data.get("capabilities", [])
        if not isinstance(capabilities, list):
            return Response({"capabilities": ["Provide a list of task capabilities."]}, status=400)
        normalized = list(dict.fromkeys(str(item).strip() for item in capabilities if str(item).strip()))
        obj, created = WorkerService.objects.get_or_create(worker=profile, service=service, defaults={"capabilities": normalized})
        if not created and obj.capabilities != normalized:
            obj.capabilities = normalized
            obj.capabilities_verified = False
            obj.save(update_fields=["capabilities", "capabilities_verified", "updated_at"])
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
    """Create a complete worker application only after validating every submitted field."""
    permission_classes = [IsAuthenticated]

    @staticmethod
    def _list_value(value, field_name):
        import json

        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except (TypeError, ValueError):
                parsed = [part.strip() for part in value.split(",") if part.strip()]
            value = parsed if isinstance(parsed, list) else [parsed]
        elif isinstance(value, (list, tuple)) and len(value) == 1 and isinstance(value[0], str):
            # Multipart clients may send a JSON-encoded array as one form value.
            # QueryDict.getlist() then returns e.g. ['[1, 2]']; unwrap that array
            # while preserving repeated form values such as ['1', '2'].
            try:
                parsed = json.loads(value[0])
            except (TypeError, ValueError):
                parsed = None
            if isinstance(parsed, list):
                value = parsed

        if not isinstance(value, (list, tuple)):
            raise DjangoValidationError({field_name: "Provide a list of selected IDs."})
        try:
            values = [int(item) for item in value]
        except (TypeError, ValueError):
            raise DjangoValidationError({field_name: "Every selected value must be a valid ID."})
        if not values or len(values) != len(set(values)):
            raise DjangoValidationError({field_name: "Select at least one unique value."})
        return values

    @transaction.atomic
    def post(self, request):
        if WorkerProfile.objects.filter(user=request.user).exists():
            return Response(
                {"detail": "Worker application already exists."},
                status=status.HTTP_409_CONFLICT,
            )

        data = request.data
        profile_photo = data.get("profile_photo")
        if not profile_photo:
            return Response({"profile_photo": ["This field is required."]}, status=400)
        if profile_photo.size > 5 * 1024 * 1024:
            return Response({"profile_photo": ["File size must not exceed 5MB."]}, status=400)
        try:
            from PIL import Image as PILImage
            profile_photo.seek(0)
            PILImage.open(profile_photo).verify()
            profile_photo.seek(0)
        except Exception:
            return Response({"profile_photo": ["Upload a valid image." ]}, status=400)

        try:
            # Multipart requests encode repeated list fields as QueryDict values.
            # getlist() preserves every selected ID; JSON requests keep their native lists.
            service_values = data.getlist("services") if hasattr(data, "getlist") else data.get("services")
            zone_values = data.getlist("zones") if hasattr(data, "getlist") else data.get("zones")
            service_ids = self._list_value(service_values, "services")
            zone_ids = self._list_value(zone_values, "zones")
            import json
            raw_capabilities = data.get("service_capabilities", {})
            if isinstance(raw_capabilities, str):
                raw_capabilities = json.loads(raw_capabilities)
            if not isinstance(raw_capabilities, dict):
                return Response({"service_capabilities": ["Provide tasks for each selected service."]}, status=400)
            service_capabilities = {}
            for raw_id, raw_tasks in raw_capabilities.items():
                try:
                    service_id = int(raw_id)
                except (TypeError, ValueError):
                    return Response({"service_capabilities": ["Invalid service ID."]}, status=400)
                if not isinstance(raw_tasks, list):
                    return Response({"service_capabilities": ["Tasks must be a list."]}, status=400)
                tasks = list(dict.fromkeys(str(task).strip() for task in raw_tasks if str(task).strip()))
                if len(tasks) > 100 or any(len(task) > 150 for task in tasks):
                    return Response({"service_capabilities": ["Each service can include up to 100 task names, each up to 150 characters."]}, status=400)
                service_capabilities[service_id] = tasks
            if set(service_capabilities) != set(service_ids):
                return Response({"service_capabilities": ["Submit task capabilities for every selected service only."]}, status=400)
            raw_experience = data.get("service_experience_years", {})
            if isinstance(raw_experience, str):
                raw_experience = json.loads(raw_experience)
            if not isinstance(raw_experience, dict):
                return Response({"service_experience_years": ["Provide experience for each selected service."]}, status=400)
            service_experience = {}
            for raw_id, raw_years in raw_experience.items():
                try:
                    service_id, years = int(raw_id), int(raw_years)
                except (TypeError, ValueError):
                    return Response({"service_experience_years": ["Experience must be a whole number of years."]}, status=400)
                if years < 0 or years > 60:
                    return Response({"service_experience_years": ["Experience must be between 0 and 60 years."]}, status=400)
                service_experience[service_id] = years
            if service_experience and set(service_experience) != set(service_ids):
                return Response({"service_experience_years": ["Provide experience for every selected service only."]}, status=400)
            services = list(Service.objects.filter(
                pk__in=service_ids, is_active=True, category__is_active=True
            ))
            zones = list(Zone.objects.filter(
                pk__in=zone_ids, is_active=True, city__is_active=True
            ))
            if len(services) != len(service_ids):
                return Response({"services": ["One or more selected services are invalid or inactive."]}, status=400)
            if len(zones) != len(zone_ids):
                return Response({"zones": ["One or more selected service areas are invalid or inactive."]}, status=400)

            experience = int(data.get("experience_years", 0) or 0)
            if experience < 0 or experience > 60:
                return Response({"experience_years": ["Enter experience between 0 and 60 years."]}, status=400)

            schedule_data = data.get("schedule", {})
            if isinstance(schedule_data, str):
                import json
                schedule_data = json.loads(schedule_data)
            if not isinstance(schedule_data, dict):
                return Response({"schedule": ["Provide working hours for each selected weekday."]}, status=400)
            schedules = []
            for weekday_raw, times in schedule_data.items():
                weekday = int(weekday_raw)
                if weekday not in range(7) or not isinstance(times, dict):
                    raise ValueError("Invalid weekday schedule.")
                start_time = forms.TimeField().to_python(times.get("start"))
                end_time = forms.TimeField().to_python(times.get("end"))
                if start_time is None or end_time is None or start_time >= end_time:
                    raise ValueError("Each working day must have an end time after its start time.")
                schedules.append((weekday, start_time, end_time))
            if not schedules:
                return Response({"schedule": ["Select at least one working day and set its hours."]}, status=400)
        except (DjangoValidationError, ValueError, TypeError, KeyError) as exc:
            detail = getattr(exc, "message_dict", None) or {"detail": str(exc)}
            return Response(detail, status=400)

        name = str(data.get("name") or request.user.name).strip()
        email = str(data.get("email") or request.user.email).strip()
        gender = str(data.get("gender") or request.user.gender).strip()
        if gender not in dict(WorkerProfile.Gender.choices):
            gender = ""
        residential_address = str(data.get("residential_address") or "").strip()
        if not name:
            return Response({"name": ["Full name is required."]}, status=400)
        if not email:
            return Response({"email": ["Email address is required."]}, status=400)
        if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
            return Response({"email": ["Enter a valid email address."]}, status=400)
        if not residential_address:
            return Response({"residential_address": ["Residential address is required."]}, status=400)
        if gender not in dict(WorkerProfile.Gender.choices):
            return Response({"gender": ["Choose your gender to continue."]}, status=400)

        try:
            latitude = Decimal(str(data.get("latitude"))) if data.get("latitude") not in (None, "") else None
            longitude = Decimal(str(data.get("longitude"))) if data.get("longitude") not in (None, "") else None
            if (latitude is None) != (longitude is None):
                raise ValueError
            if latitude is not None and not (Decimal("-90") <= latitude <= Decimal("90")):
                raise ValueError
            if longitude is not None and not (Decimal("-180") <= longitude <= Decimal("180")):
                raise ValueError
        except Exception:
            return Response({"location": ["Provide valid GPS coordinates together."]}, status=400)

        # Residential GPS and professional working areas are different concepts.
        # The worker explicitly selects one or more service zones above. Never
        # replace that selection with a single nearest zone derived from home GPS.

        profile = WorkerProfile.objects.create(
            user=request.user,
            gender=gender,
            experience_years=experience,
            bio=str(data.get("bio") or "").strip(),
            qualification=str(data.get("qualification") or "").strip(),
            equipment_details=str(data.get("equipment_details") or "").strip(),
            residential_address=residential_address,
            latitude=latitude,
            longitude=longitude,
            landmark=str(data.get("landmark") or "").strip(),
            upi_id=str(data.get("upi_id") or "").strip(),
        )
        request.user.name = name
        request.user.email = email
        if gender:
            request.user.gender = gender
        request.user.save(update_fields=["name", "email", "gender"])

        WorkerService.objects.bulk_create([
            WorkerService(
                worker=profile,
                service=service,
                capabilities=service_capabilities[service.pk],
                experience_years=service_experience.get(service.pk, experience),
            )
            for service in services
        ])
        WorkerZone.objects.bulk_create([
            WorkerZone(worker=profile, zone=zone) for zone in zones
        ])
        WorkerSchedule.objects.bulk_create([
            WorkerSchedule(
                worker=profile, weekday=weekday,
                start_time=start_time, end_time=end_time, is_active=True,
            )
            for weekday, start_time, end_time in schedules
        ])
        WorkerDocument.objects.create(
            worker=profile,
            doc_type=WorkerDocument.DocumentType.PHOTO,
            file=profile_photo,
            status=WorkerDocument.Status.PENDING,
        )

        return Response({
            "message": "Worker application submitted. Awaiting admin verification.",
            "status": profile.status,
            "worker_status": profile.status,
            "active_mode": request.user.active_mode,
        }, status=status.HTTP_201_CREATED)


def _worker_payment_label(booking):
    """Return a worker-safe summary of the payment stage for this assigned job."""
    from apps.payments.models import Payment

    recurring_visit = getattr(booking, "recurring_wash_visit", None)
    if recurring_visit and recurring_visit.plan.status in (
        recurring_visit.plan.Status.PAID_PENDING_SETUP,
        recurring_visit.plan.Status.ACTIVE,
    ):
        return (
            f"Prepaid recurring Car Wash plan #{recurring_visit.plan_id}; "
            f"visit {recurring_visit.visit_number} is covered. No payment to collect."
        )

    order_item = getattr(booking, "order_item", None)
    if order_item:
        order = order_item.order
        allocation = (order.metadata or {}).get("payment_allocation_v1", {})
        if allocation:
            advance_paid = Payment.objects.filter(
                order=order,
                stage=Payment.Stage.ADVANCE,
                status=Payment.Status.PAID,
            ).exists()
            return (
                "30% advance received. Remaining balance is due after OTP-verified completion."
                if advance_paid else "Customer advance payment is pending."
            )
        legacy_paid = Payment.objects.filter(
            order=order,
            stage=Payment.Stage.LEGACY,
            status=Payment.Status.PAID,
        ).exists()
        return "Full order payment received." if legacy_paid else "Full order payment pending."

    booking_paid = Payment.objects.filter(
        booking=booking,
        status=Payment.Status.PAID,
    ).exists()
    return "Full booking payment received." if booking_paid else "Booking payment pending."


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
            payment_label = _worker_payment_label(booking)
            results.append({
                "id": assign.id,
                "booking_id": booking.id,
                "status": booking.status,
                "service_title": booking.service.title,
                "customer_name": booking.customer.name or "AIRway Customer",
                "address": booking.address.full_address,
                "scheduled_at": booking.scheduled_at.isoformat() if booking.scheduled_at else "",
                "drop_scheduled_at": booking.drop_scheduled_at.isoformat() if booking.drop_scheduled_at else None,
                "amount": float(booking.pricing_snapshot.get("total", 0) or 0),
                "payment_label": payment_label,
                "recurring_visit": (
                    {
                        "plan_id": booking.recurring_wash_visit.plan_id,
                        "visit_id": booking.recurring_wash_visit.pk,
                        "visit_number": booking.recurring_wash_visit.visit_number,
                        "status": booking.recurring_wash_visit.status,
                        "prepaid_amount": str(booking.recurring_wash_visit.prepaid_amount),
                    }
                    if hasattr(booking, "recurring_wash_visit") else None
                ),
                "worker_notes": booking.worker_notes or None,
                "assigned_at": assign.assigned_at.isoformat() if assign.assigned_at else None,
            })
        return Response(results)


class WorkerJobEvidenceView(APIView):
    """Append private before/after photos to the assigned worker's active job."""

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, job_id):
        try:
            profile = request.user.worker_profile
        except WorkerProfile.DoesNotExist:
            return Response({"detail": "No worker profile found."}, status=status.HTTP_404_NOT_FOUND)
        assignment, booking = _get_assignment_and_booking(job_id, profile)
        if booking is None:
            return Response({"detail": "Job not found."}, status=status.HTTP_404_NOT_FOUND)
        if booking.status != Booking.Status.IN_PROGRESS:
            return Response({"detail": "Work evidence can be added only while the job is in progress."}, status=status.HTTP_400_BAD_REQUEST)

        stage = str(request.data.get("stage", "")).strip().lower()
        if stage not in (BookingWorkEvidence.Stage.BEFORE, BookingWorkEvidence.Stage.AFTER):
            return Response({"stage": ["Choose before or after."]}, status=status.HTTP_400_BAD_REQUEST)
        if stage == BookingWorkEvidence.Stage.AFTER and (
            booking.booking_mode == Booking.BookingMode.INSPECTION
            or booking.service.pricing_type == Service.PricingType.QUOTE
        ) and not booking.quotes.filter(status=BookingQuote.Status.ACCEPTED).exists():
            return Response({"detail": "The customer must approve the estimate before after-work evidence can be submitted."}, status=status.HTTP_409_CONFLICT)
        if booking.work_evidence.filter(stage=stage).count() >= 10:
            return Response({"detail": "A maximum of 10 photos is allowed for each work stage."}, status=status.HTTP_400_BAD_REQUEST)

        photo = request.FILES.get("photo")
        if photo is None:
            return Response({"detail": "Choose a photo to upload."}, status=status.HTTP_400_BAD_REQUEST)
        if photo.size > 5 * 1024 * 1024:
            return Response({"detail": "Photo must be 5 MB or smaller."}, status=status.HTTP_400_BAD_REQUEST)
        if photo.content_type not in ("image/jpeg", "image/png", "image/webp"):
            return Response({"detail": "Upload a JPG, PNG or WEBP image."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            from PIL import Image
            image = Image.open(photo)
            width, height = image.size
            image_format = image.format
            image.verify()
            if image_format not in ("JPEG", "PNG", "WEBP"):
                raise ValueError("Unsupported image format")
        except Exception:
            return Response({"detail": "The uploaded file is not a valid supported image."}, status=status.HTTP_400_BAD_REQUEST)
        finally:
            photo.seek(0)
        if width > 6000 or height > 6000:
            return Response({"detail": "Image dimensions must not exceed 6000 × 6000 pixels."}, status=status.HTTP_400_BAD_REQUEST)

        extension = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}[image_format]
        storage = FileSystemStorage(location=settings.PRIVATE_UPLOAD_ROOT)
        image_path = storage.save(
            f"booking_work_evidence/booking_{booking.id}/{stage}/{uuid.uuid4().hex}{extension}",
            photo,
        )
        note = str(request.data.get("note", "")).strip()
        if len(note) > 500:
            storage.delete(image_path)
            return Response({"note": ["Note must not exceed 500 characters."]}, status=status.HTTP_400_BAD_REQUEST)
        evidence = BookingWorkEvidence.objects.create(
            booking=booking,
            worker=profile,
            stage=stage,
            image_path=image_path,
            note=note,
        )
        photo_url = request.build_absolute_uri(
            f"/api/v1/bookings/work-evidence/{evidence.id}/photo/"
        )
        return Response({
            "id": evidence.id,
            "stage": evidence.stage,
            "note": evidence.note,
            "photo_url": photo_url,
            "created_at": evidence.created_at.isoformat(),
        }, status=status.HTTP_201_CREATED)


class WorkerJobQuoteView(APIView):
    """Create a versioned inspection quote for the worker's own active job."""

    permission_classes = [IsAuthenticated]

    def post(self, request, job_id):
        try:
            profile = request.user.worker_profile
        except WorkerProfile.DoesNotExist:
            return Response({"detail": "No worker profile found."}, status=status.HTTP_404_NOT_FOUND)

        assignment, booking = _get_assignment_and_booking(job_id, profile)
        if booking is None:
            return Response({"detail": "Job not found."}, status=status.HTTP_404_NOT_FOUND)
        if booking.booking_mode != Booking.BookingMode.INSPECTION and booking.service.pricing_type != Service.PricingType.QUOTE:
            return Response({"detail": "A quote is available only for inspection/quote-based services."}, status=status.HTTP_400_BAD_REQUEST)
        if booking.status != Booking.Status.IN_PROGRESS:
            return Response({"detail": "Start the assigned inspection job before submitting its estimate."}, status=status.HTTP_400_BAD_REQUEST)
        if BookingQuote.objects.filter(booking=booking, status=BookingQuote.Status.ACCEPTED).exists():
            return Response({"detail": "The customer has already accepted a quote for this booking."}, status=status.HTTP_409_CONFLICT)
        now = timezone.now()
        BookingQuote.objects.filter(
            booking=booking,
            status=BookingQuote.Status.PENDING_CUSTOMER,
            expires_at__lte=now,
        ).update(
            status=BookingQuote.Status.REJECTED,
            customer_response_note="Quote expired before customer response.",
            responded_at=now,
        )
        if BookingQuote.objects.filter(booking=booking, status=BookingQuote.Status.PENDING_CUSTOMER).exists():
            return Response({"detail": "A quote is already waiting for customer approval."}, status=status.HTTP_409_CONFLICT)

        rows = request.data.get("line_items")
        if not isinstance(rows, list) or not rows or len(rows) > 50:
            return Response({"line_items": ["Add between 1 and 50 estimate items."]}, status=status.HTTP_400_BAD_REQUEST)

        from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
        totals = {
            "labour": Decimal("0.00"),
            "material": Decimal("0.00"),
            "other": Decimal("0.00"),
        }
        clean_rows = []
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                return Response({"line_items": [f"Item {index + 1} must be an object."]}, status=status.HTTP_400_BAD_REQUEST)
            kind = str(row.get("type", "")).strip().lower()
            description = str(row.get("description", "")).strip()
            if kind not in totals or not description or len(description) > 200:
                return Response({"line_items": [f"Item {index + 1} needs a valid type and description (max 200 characters)."]}, status=status.HTTP_400_BAD_REQUEST)
            try:
                quantity = Decimal(str(row.get("quantity", "1")))
                unit_price = Decimal(str(row.get("unit_price", "0")))
            except (InvalidOperation, TypeError, ValueError):
                return Response({"line_items": [f"Item {index + 1} has an invalid quantity or price."]}, status=status.HTTP_400_BAD_REQUEST)
            if not quantity.is_finite() or quantity <= 0 or quantity > 1000 or quantity.as_tuple().exponent < -2:
                return Response({"line_items": [f"Item {index + 1} quantity must be between 0 and 1000 with at most 2 decimals."]}, status=status.HTTP_400_BAD_REQUEST)
            if not unit_price.is_finite() or unit_price < 0 or unit_price > Decimal("1000000") or unit_price.as_tuple().exponent < -2:
                return Response({"line_items": [f"Item {index + 1} unit price must be between 0 and 1000000 with at most 2 decimals."]}, status=status.HTTP_400_BAD_REQUEST)
            line_total = (quantity * unit_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            totals[kind] += line_total
            clean_rows.append({
                "type": kind,
                "description": description,
                "quantity": str(quantity),
                "unit_price": str(unit_price),
                "line_total": str(line_total),
            })

        subtotal = sum(totals.values(), Decimal("0.00"))
        if subtotal <= 0:
            return Response({"line_items": ["The estimate total must be greater than zero."]}, status=status.HTTP_400_BAD_REQUEST)
        tax = (subtotal * Decimal("0.18")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        total = subtotal + tax
        notes = str(request.data.get("notes", "")).strip()
        if len(notes) > 2000:
            return Response({"notes": ["Notes must not exceed 2000 characters."]}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            latest = BookingQuote.objects.select_for_update().filter(booking=booking).order_by("-version").first()
            if latest and latest.status == BookingQuote.Status.PENDING_CUSTOMER:
                return Response({"detail": "A quote is already waiting for customer approval."}, status=status.HTTP_409_CONFLICT)
            if latest and latest.status == BookingQuote.Status.ACCEPTED:
                return Response({"detail": "The customer has already accepted a quote for this booking."}, status=status.HTTP_409_CONFLICT)
            quote = BookingQuote.objects.create(
                booking=booking,
                worker=profile,
                version=(latest.version + 1) if latest else 1,
                line_items=clean_rows,
                labour_amount=totals["labour"],
                material_amount=totals["material"],
                other_amount=totals["other"],
                tax_amount=tax,
                total_amount=total,
                notes=notes,
                expires_at=timezone.now() + timedelta(hours=24),
            )
            Notification.objects.create(
                user=booking.customer,
                type=Notification.Type.SYSTEM_ANNOUNCEMENT,
                title="Inspection estimate ready",
                body=f"Your {booking.service.title} estimate of ₹{total:.2f} is ready. Review and approve or reject it in AIRway.",
                channel=Notification.Channel.IN_APP,
                data={"booking_id": booking.id, "quote_id": quote.id, "purpose": "booking_quote"},
            )

        return Response({
            "id": quote.id,
            "version": quote.version,
            "status": quote.status,
            "line_items": quote.line_items,
            "labour_amount": str(quote.labour_amount),
            "material_amount": str(quote.material_amount),
            "other_amount": str(quote.other_amount),
            "tax_amount": str(quote.tax_amount),
            "total_amount": str(quote.total_amount),
            "notes": quote.notes,
            "expires_at": quote.expires_at.isoformat(),
        }, status=status.HTTP_201_CREATED)


class WorkerJobDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, job_id):
        try:
            profile = request.user.worker_profile
        except WorkerProfile.DoesNotExist:
            return Response({"detail": "No worker profile found."}, status=status.HTTP_404_NOT_FOUND)
        try:
            assign = BookingAssignment.objects.select_related(
                "booking__service", "booking__customer", "booking__address",
            ).get(pk=job_id, worker=profile)
        except BookingAssignment.DoesNotExist:
            return Response({"detail": "Job not found."}, status=status.HTTP_404_NOT_FOUND)
        booking = assign.booking
        payment_label = _worker_payment_label(booking)
        latest_quote = booking.quotes.select_related("worker__user").order_by("-version").first()
        quote_data = None
        if latest_quote:
            quote_data = {
                "id": latest_quote.id,
                "version": latest_quote.version,
                "status": (
                    "expired"
                    if latest_quote.status == BookingQuote.Status.PENDING_CUSTOMER
                    and latest_quote.expires_at and latest_quote.expires_at <= timezone.now()
                    else latest_quote.status
                ),
                "line_items": latest_quote.line_items,
                "labour_amount": str(latest_quote.labour_amount),
                "material_amount": str(latest_quote.material_amount),
                "other_amount": str(latest_quote.other_amount),
                "tax_amount": str(latest_quote.tax_amount),
                "total_amount": str(latest_quote.total_amount),
                "notes": latest_quote.notes,
                "customer_response_note": latest_quote.customer_response_note,
                "expires_at": latest_quote.expires_at.isoformat() if latest_quote.expires_at else None,
                "responded_at": latest_quote.responded_at.isoformat() if latest_quote.responded_at else None,
            }
        recurring_visit = getattr(booking, "recurring_wash_visit", None)
        recurring_visit_data = (
            {
                "plan_id": recurring_visit.plan_id,
                "visit_id": recurring_visit.pk,
                "visit_number": recurring_visit.visit_number,
                "status": recurring_visit.status,
                "prepaid_amount": str(recurring_visit.prepaid_amount),
            }
            if recurring_visit else None
        )
        customer_answers = dict(booking.customer_answers or {})
        has_issue_photo = bool(customer_answers.pop("_airway_issue_photo", None))
        form_photo_paths = customer_answers.pop("_airway_form_photos", {})
        if booking.service.requires_female_worker:
            customer_answers["professional_preference"] = "female"
        return Response({
            "id": assign.id,
"booking_id": booking.id,
            "status": booking.status,
            "booking_mode": booking.booking_mode,
            "pricing_type": booking.service.pricing_type,
            "quote": quote_data,
            "can_submit_quote": (
                booking.status == Booking.Status.IN_PROGRESS
                and (booking.booking_mode == Booking.BookingMode.INSPECTION or booking.service.pricing_type == Service.PricingType.QUOTE)
                and not booking.quotes.filter(status=BookingQuote.Status.ACCEPTED).exists()
                and not booking.quotes.filter(
                    status=BookingQuote.Status.PENDING_CUSTOMER,
                    expires_at__gt=timezone.now(),
                ).exists()
            ),
            "service_title": booking.service.title,
            "customer_name": booking.customer.name or "AIRway Customer",
            "address": booking.address.full_address,
            "scheduled_at": booking.scheduled_at.isoformat() if booking.scheduled_at else "",
            "drop_scheduled_at": booking.drop_scheduled_at.isoformat() if booking.drop_scheduled_at else None,
            "amount": float(booking.pricing_snapshot.get("total", 0) or 0),
            "payment_label": payment_label,
            "recurring_visit": recurring_visit_data,
            "variant_title": booking.variant.title if booking.variant_id else None,
            "service_unit_label": booking.service.unit_label,
            "quantity": (
                booking.order_item.quantity
                if hasattr(booking, "order_item")
                else int((booking.pricing_snapshot or {}).get("quantity", 1))
            ),
            "customer_answers": customer_answers,
            "issue_photo_url": (
                request.build_absolute_uri(f"/api/v1/bookings/issue-photos/{booking.id}/")
                if has_issue_photo else None
            ),
            "notes": (
                booking.appointment_group.customer_message
                if booking.appointment_group_id else booking.notes
            ),
            "appointment_group_id": booking.appointment_group_id,
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
                {
                    "key": fr.form_field.key,
                    "label": fr.form_field.label,
                    "value": "Photo attached" if fr.form_field.field_type == "photo" and form_photo_paths.get(fr.form_field.key) else fr.value,
                    "photo_url": (
                        request.build_absolute_uri(
                            f"/api/v1/bookings/issue-photos/{booking.id}/?field_key={fr.form_field.key}"
                        )
                        if fr.form_field.field_type == "photo" and form_photo_paths.get(fr.form_field.key)
                        else None
                    ),
                }
                for fr in booking.form_responses.select_related("form_field").all()
            ],
            "work_evidence": [
                {
                    "id": evidence.id,
                    "stage": evidence.stage,
                    "note": evidence.note,
                    "photo_url": request.build_absolute_uri(
                        f"/api/v1/bookings/work-evidence/{evidence.id}/photo/"
                    ),
                    "created_at": evidence.created_at.isoformat(),
                }
                for evidence in booking.work_evidence.select_related("worker").all()
            ],
            "assignment": {
                "assigned_at": assign.assigned_at.isoformat() if assign.assigned_at else None,
                "accepted_at": assign.accepted_at.isoformat() if assign.accepted_at else None,
                "started_at": assign.started_at.isoformat() if assign.started_at else None,
                "completed_at": assign.completed_at.isoformat() if assign.completed_at else None,
                "location_sharing_enabled": bool(assign.location_sharing_enabled),
            },
        })


def _get_assignment_and_booking(job_id, profile):
    try:
        assign = BookingAssignment.objects.select_related("booking").get(pk=job_id, worker=profile)
        booking = assign.booking
        return assign, booking
    except BookingAssignment.DoesNotExist:
        return None, None


class WorkerJobLocationSharingView(APIView):
    """Let the assigned worker explicitly enable or disable customer-visible GPS."""

    permission_classes = [IsAuthenticated]

    def post(self, request, job_id):
        try:
            profile = request.user.worker_profile
        except WorkerProfile.DoesNotExist:
            return Response({"detail": "No worker profile found."}, status=status.HTTP_404_NOT_FOUND)

        assignment, booking = _get_assignment_and_booking(job_id, profile)
        if booking is None:
            return Response({"detail": "Job not found."}, status=status.HTTP_404_NOT_FOUND)
        if profile.status != WorkerProfile.Status.APPROVED:
            return Response({"detail": "Only approved workers can share job location."}, status=status.HTTP_403_FORBIDDEN)
        if not assignment.accepted_at or booking.status not in (
            Booking.Status.ASSIGNED, Booking.Status.IN_PROGRESS,
        ):
            return Response({"detail": "Location sharing is available only for an accepted active job."}, status=status.HTTP_409_CONFLICT)

        enabled = request.data.get("enabled")
        if not isinstance(enabled, bool):
            return Response({"enabled": ["Provide true or false."]}, status=status.HTTP_400_BAD_REQUEST)

        sharing_assignments = [assignment]
        if booking.appointment_group_id:
            sharing_assignments = list(
                BookingAssignment.objects.filter(
                    booking__appointment_group_id=booking.appointment_group_id,
                    worker=profile,
                )
            )
        update_fields = ["location_sharing_enabled", "updated_at"]
        if not enabled:
            update_fields += [
                "live_latitude", "live_longitude",
                "live_accuracy_m", "live_location_updated_at",
            ]
        for row in sharing_assignments:
            row.location_sharing_enabled = enabled
            if not enabled:
                row.live_latitude = None
                row.live_longitude = None
                row.live_accuracy_m = None
                row.live_location_updated_at = None
            row.save(update_fields=update_fields)
        assignment.refresh_from_db()
        return Response({
            "location_sharing_enabled": assignment.location_sharing_enabled,
            "customer_visibility_starts_at": (
                (booking.scheduled_at - timedelta(minutes=30)).isoformat()
            ),
        })


class WorkerJobLocationUpdateView(APIView):
    """Accept foreground GPS only from the worker currently assigned to an active job."""

    permission_classes = [IsAuthenticated]

    def post(self, request, job_id):
        try:
            profile = request.user.worker_profile
        except WorkerProfile.DoesNotExist:
            return Response({"detail": "No worker profile found."}, status=status.HTTP_404_NOT_FOUND)

        assignment, booking = _get_assignment_and_booking(job_id, profile)
        if booking is None:
            return Response({"detail": "Job not found."}, status=status.HTTP_404_NOT_FOUND)
        if profile.status != WorkerProfile.Status.APPROVED:
            return Response({"detail": "Only approved workers can share job location."}, status=status.HTTP_403_FORBIDDEN)
        if not assignment.accepted_at:
            return Response({"detail": "Accept this job before sharing your location."}, status=status.HTTP_409_CONFLICT)
        if booking.status not in (Booking.Status.ASSIGNED, Booking.Status.IN_PROGRESS):
            return Response({"detail": "Location sharing is available only for active assigned jobs."}, status=status.HTTP_409_CONFLICT)
        if not assignment.location_sharing_enabled:
            return Response({"detail": "Enable live location sharing before sending GPS updates."}, status=status.HTTP_403_FORBIDDEN)
        now = timezone.now()
        if now < booking.scheduled_at - timedelta(minutes=30):
            return Response({"detail": "Customer-visible live location becomes available 30 minutes before the appointment."}, status=status.HTTP_409_CONFLICT)

        try:
            latitude = Decimal(str(request.data.get("latitude")))
            longitude = Decimal(str(request.data.get("longitude")))
            accuracy_raw = request.data.get("accuracy_m")
            accuracy = Decimal(str(accuracy_raw)) if accuracy_raw not in (None, "") else None
            if (
                not latitude.is_finite()
                or not longitude.is_finite()
                or not (Decimal("-90") <= latitude <= Decimal("90"))
                or not (Decimal("-180") <= longitude <= Decimal("180"))
            ):
                raise ValueError
            if accuracy is not None and (
                not accuracy.is_finite() or accuracy < 0 or accuracy > Decimal("1000")
            ):
                raise ValueError
        except (TypeError, ValueError, ArithmeticError):
            return Response(
                {"detail": "Provide valid latitude and longitude, and accuracy between 0 and 1000 metres."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        location_assignments = [assignment]
        if booking.appointment_group_id:
            location_assignments = list(
                BookingAssignment.objects.filter(
                    booking__appointment_group_id=booking.appointment_group_id,
                    worker=profile,
                )
            )
        for row in location_assignments:
            row.live_latitude = latitude
            row.live_longitude = longitude
            row.live_accuracy_m = accuracy
            row.live_location_updated_at = now
            row.save(update_fields=[
                "live_latitude", "live_longitude", "live_accuracy_m",
                "live_location_updated_at", "updated_at",
            ])
        return Response({
            "accepted": True,
            "location_updated_at": now.isoformat(),
        })


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
        assign.live_latitude = None
        assign.live_longitude = None
        assign.live_accuracy_m = None
        assign.live_location_updated_at = None
        assign.save(update_fields=[
            "live_latitude", "live_longitude", "live_accuracy_m",
            "live_location_updated_at", "updated_at",
        ])
        BookingStatusHistory.objects.create(
            booking=booking, from_status=old, to_status=Booking.Status.CANCELLED,
            changed_by=request.user, note=f"Worker rejected. Reason: {request.data.get('reason', '')}",
        )
        return Response({"detail": "Job rejected.", "status": booking.status})


class WorkerJobStartView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
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
        if profile.status != WorkerProfile.Status.APPROVED:
            return Response(
                {"detail": "Only approved workers can start jobs."},
                status=status.HTTP_403_FORBIDDEN,
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
                appointment_group__isnull=True,
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

        from django.contrib.auth.hashers import check_password, make_password
        import secrets
        from apps.notifications.models import Notification

        if booking.appointment_group_id:
            group_bookings = list(
                booking.appointment_group.bookings.exclude(
                    status=Booking.Status.CANCELLED
                ).order_by("pk")
            )
            group_assignments = list(
                BookingAssignment.objects.select_for_update()
                .filter(booking__in=group_bookings)
                .select_related("booking", "worker__user")
            )
            if len(group_assignments) != len(group_bookings) or any(
                row.worker_id != profile.pk or not row.accepted_at
                for row in group_assignments
            ):
                return Response(
                    {"detail": "Every active service in this appointment must be assigned to and accepted by you."},
                    status=status.HTTP_409_CONFLICT,
                )
        else:
            group_bookings = [booking]
            group_assignments = [assign]

        now = timezone.now()
        otp_state = group_assignments[0]
        submitted_code = str(request.data.get("arrival_otp", "")).strip()

        if not all(row.arrival_verified_at for row in group_assignments):
            if not submitted_code:
                can_resend = (
                    not otp_state.arrival_otp_hash
                    or not otp_state.arrival_otp_last_sent_at
                    or otp_state.arrival_otp_last_sent_at <= now - timedelta(seconds=30)
                )
                if can_resend:
                    code = f"{secrets.randbelow(1000000):06d}"
                    code_hash = make_password(code)
                    expires_at = now + timedelta(minutes=10)
                    for row in group_assignments:
                        row.arrival_requested_at = row.arrival_requested_at or now
                        row.arrival_verified_at = None
                        row.arrival_otp_hash = code_hash
                        row.arrival_otp_expires_at = expires_at
                        row.arrival_otp_attempts = 0
                        row.arrival_otp_last_sent_at = now
                        row.save(update_fields=[
                            "arrival_requested_at", "arrival_verified_at",
                            "arrival_otp_hash", "arrival_otp_expires_at",
                            "arrival_otp_attempts", "arrival_otp_last_sent_at",
                            "updated_at",
                        ])
                    Notification.objects.create(
                        user=booking.customer,
                        type=Notification.Type.SYSTEM_ANNOUNCEMENT,
                        title="Your professional has arrived",
                        body=(
                            f"Share this 6-digit arrival code with your AIRway professional: {code}. "
                            "It expires in 10 minutes. AIRway will not start the service until you provide this code."
                        ),
                        channel=Notification.Channel.IN_APP,
                        data={
                            "booking_id": booking.pk,
                            "booking_ids": [row.pk for row in group_bookings],
                            "appointment_group_id": booking.appointment_group_id,
                            "arrival_otp_expires_at": expires_at.isoformat(),
                        },
                    )
                return Response({
                    "arrival_otp_required": True,
                    "detail": "Ask the customer for the arrival code shown in their AIRway notifications, then enter it to start work.",
                    "expires_at": (
                        otp_state.arrival_otp_expires_at.isoformat()
                        if otp_state.arrival_otp_expires_at else None
                    ),
                })

            if any(
                not row.arrival_otp_hash
                or not row.arrival_otp_expires_at
                or row.arrival_otp_expires_at <= now
                for row in group_assignments
            ):
                return Response(
                    {"detail": "The arrival code has expired. Request a new code and ask the customer again."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if any(row.arrival_otp_attempts >= 5 for row in group_assignments):
                return Response(
                    {"detail": "Too many incorrect arrival-code attempts. Request a new code."},
                    status=status.HTTP_429_TOO_MANY_REQUESTS,
                )
            if not check_password(submitted_code, otp_state.arrival_otp_hash):
                for row in group_assignments:
                    row.arrival_otp_attempts += 1
                    if row.arrival_otp_attempts >= 5:
                        row.arrival_otp_expires_at = now
                    row.save(update_fields=[
                        "arrival_otp_attempts", "arrival_otp_expires_at", "updated_at"
                    ])
                return Response(
                    {"detail": "Incorrect arrival code. Check with the customer and try again."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            for row in group_assignments:
                row.arrival_verified_at = now
                row.save(update_fields=["arrival_verified_at", "updated_at"])

        for row in group_assignments:
            row.started_at = row.started_at or now
            row.save(update_fields=["started_at", "updated_at"])

        for active_booking in group_bookings:
            if active_booking.status == Booking.Status.IN_PROGRESS:
                continue
            old = active_booking.status
            active_booking.status = Booking.Status.IN_PROGRESS
            active_booking.save(update_fields=["status", "updated_at"])
            BookingStatusHistory.objects.create(
                booking=active_booking,
                from_status=old,
                to_status=Booking.Status.IN_PROGRESS,
                changed_by=request.user,
                note="Worker started the appointment after customer arrival OTP verification.",
            )
            from apps.bookings.models import RecurringWashVisit
            RecurringWashVisit.objects.filter(
                booking=active_booking,
                status=RecurringWashVisit.Status.BOOKED,
            ).update(status=RecurringWashVisit.Status.IN_PROGRESS, updated_at=now)

        return Response({
            "detail": "Arrival verified. Appointment started.",
            "status": Booking.Status.IN_PROGRESS,
            "appointment_group_id": booking.appointment_group_id,
            "booking_ids": [row.pk for row in group_bookings],
        })


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

        doc_type = request.data.get("doc_type")
        # Approved workers may submit a replacement profile photo for admin
        # review. Their currently verified photo remains active until approval.
        if profile.status != WorkerProfile.Status.PENDING and not (
            profile.status == WorkerProfile.Status.APPROVED
            and doc_type == WorkerDocument.DocumentType.PHOTO
        ):
            return Response(
                {"error": "Only pending applications may upload identity documents. Approved workers may submit a new profile photo for review."},
                status=status.HTTP_400_BAD_REQUEST,
            )
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
        ).order_by("-created_at").first()
        if existing and existing.status == WorkerDocument.Status.VERIFIED:
            if profile.status != WorkerProfile.Status.APPROVED or doc_type != WorkerDocument.DocumentType.PHOTO:
                return Response(
                    {"error": "This document has already been verified and cannot be replaced."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            # Preserve the approved image and create a separate review record.
            doc = WorkerDocument.objects.create(
                worker=profile,
                doc_type=doc_type,
                file=uploaded_file,
                status=WorkerDocument.Status.PENDING,
            )
        elif existing:
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

        if online:
            has_service = profile.worker_services.filter(
                service__is_active=True, service__category__is_active=True
            ).exists()
            has_zone = profile.worker_zones.filter(
                zone__is_active=True, zone__city__is_active=True
            ).exists()
            has_schedule = profile.schedules.filter(is_active=True).exists()
            if not all((has_service, has_zone, has_schedule)):
                return Response(
                    {"detail": "Add at least one active service, service area, and working-hours schedule before going online."},
                    status=status.HTTP_409_CONFLICT,
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
            "booking__service", "booking__variant", "booking__address", "booking__order_item__order", "worker__user", "order", "appointment_group"
        ).prefetch_related(
            "booking__form_responses__form_field",
            "booking__booking_addons__addon",
            "order__items__booking__service",
            "order__items__booking__variant",
            "appointment_group__bookings__service",
            "appointment_group__bookings__variant",
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
            order_offer = bool(offer.order_id)
            group_offer = bool(offer.appointment_group_id)
            order = None
            group = None
            if order_offer:
                order = Order.objects.select_for_update().get(pk=offer.order_id)
            elif group_offer:
                group = AppointmentGroup.objects.get(pk=offer.appointment_group_id)
                order = Order.objects.select_for_update().get(pk=group.order_id)
            else:
                parent_order_id = OrderItem.objects.filter(
                    booking_id=offer.booking_id
                ).values_list("order_id", flat=True).first()
                if parent_order_id:
                    order = Order.objects.select_for_update().get(pk=parent_order_id)
            offer = WorkerOffer.objects.select_for_update().get(pk=offer.pk)
            worker = WorkerProfile.objects.select_for_update().get(pk=offer.worker_id)
            if worker.user_id != request.user.id:
                return Response({"detail": "This offer does not belong to you."}, status=status.HTTP_404_NOT_FOUND)
            if offer.status != WorkerOffer.Status.PENDING:
                if (
                    offer.status == WorkerOffer.Status.WITHDRAWN
                    and BookingAssignment.objects.filter(booking_id=offer.booking_id).exists()
                ):
                    detail = "This booking has already been assigned to another professional."
                else:
                    detail = f"Offer is already {offer.get_status_display().lower()}."
                return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)
            if offer.expires_at <= now:
                offer.status = WorkerOffer.Status.EXPIRED
                offer.responded_at = now
                offer.save(update_fields=["status", "responded_at", "updated_at"])
                return Response({"detail": "This job offer has expired."}, status=status.HTTP_410_GONE)
            if worker.status != WorkerProfile.Status.APPROVED or not worker.is_online:
                return Response({"detail": "Only online, approved workers can accept offers."}, status=status.HTTP_409_CONFLICT)

            if group_offer:
                group = AppointmentGroup.objects.select_for_update().get(pk=group.pk)
                bookings = list(
                    Booking.objects.select_for_update(of=("self",))
                    .filter(appointment_group=group)
                    .exclude(status=Booking.Status.CANCELLED)
                    .select_related("service__category", "variant", "address__zone__city")
                    .order_by("pk")
                )
                if not bookings:
                    return Response({"detail": "This appointment no longer has active services."}, status=status.HTTP_409_CONFLICT)
                if order.status not in (Order.Status.AWAITING_ASSIGNMENT, Order.Status.PARTIALLY_CANCELLED):
                    return Response({"detail": "This order is no longer awaiting assignment."}, status=status.HTTP_409_CONFLICT)
                from apps.payments.models import Payment
                if not (order.metadata or {}).get("payment_allocation_v1") or not Payment.objects.filter(
                    order=order, stage=Payment.Stage.ADVANCE, status=Payment.Status.PAID,
                ).exists():
                    return Response(
                        {"detail": "The customer's 30% advance must be verified before accepting this appointment."},
                        status=status.HTTP_409_CONFLICT,
                    )
            elif order_offer:
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
                if not (order.metadata or {}).get("payment_allocation_v1") or not Payment.objects.filter(
                    order=order, stage=Payment.Stage.ADVANCE, status=Payment.Status.PAID,
                ).exists():
                    return Response(
                        {"detail": "The customer's 30% advance must be verified before accepting this order."},
                        status=status.HTTP_409_CONFLICT,
                    )
            else:
                from apps.payments.models import Payment
                standalone_booking = Booking.objects.select_for_update(of=("self",)).select_related(
                    "service__category", "variant", "address__zone__city"
                ).get(pk=offer.booking_id)
                if order:
                    paid_advance = Payment.objects.filter(
                        order=order, stage=Payment.Stage.ADVANCE, status=Payment.Status.PAID,
                    ).exists()
                    has_allocation = bool((order.metadata or {}).get("payment_allocation_v1"))
                else:
                    recurring_visit = getattr(standalone_booking, "recurring_wash_visit", None)
                    prepaid_recurring = bool(
                        recurring_visit
                        and recurring_visit.status == recurring_visit.Status.BOOKED
                        and recurring_visit.plan.status in (
                            recurring_visit.plan.Status.PAID_PENDING_SETUP,
                            recurring_visit.plan.Status.ACTIVE,
                        )
                    )
                    paid_advance = prepaid_recurring or Payment.objects.filter(
                        booking=standalone_booking, stage=Payment.Stage.ADVANCE,
                        status=Payment.Status.PAID,
                    ).exists()
                    has_allocation = True
                if not paid_advance or not has_allocation:
                    return Response(
                        {"detail": "The customer's verified 30% advance is required before accepting this service."},
                        status=status.HTTP_409_CONFLICT,
                    )
                bookings = [standalone_booking]

            if order_offer:
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
                    duration_minutes=duration * (
                        1 if booking.service.pricing_type == "per_unit" else quantity
                    ),
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
                        {"detail": "You are no longer eligible or available for every service in this order." if order_offer else "You are no longer eligible or available for this booking time."},
                        status=status.HTTP_409_CONFLICT,
                    )

            if group_offer:
                from apps.availability.models import WorkerBlockedSlot
                from apps.bookings.services import _booking_intervals, _intervals_overlap

                group_duration = 0
                for booking in bookings:
                    duration = (
                        booking.variant.duration_minutes
                        if booking.variant_id and booking.variant.duration_minutes
                        else booking.service.duration_minutes
                    ) or 60
                    quantity = max(int((booking.pricing_snapshot or {}).get("quantity", 1) or 1), 1)
                    duration *= 1 if booking.service.pricing_type == "per_unit" else quantity
                    group_duration += duration + max(int(booking.service.buffer_minutes or 0), 0)

                group_start = group.scheduled_at
                group_end = group_start + timedelta(minutes=max(group_duration, 1))
                local_start = timezone.localtime(group_start)
                local_end = timezone.localtime(group_end)
                if local_start.date() != local_end.date() or not worker.schedules.filter(
                    weekday=local_start.weekday(),
                    is_active=True,
                    start_time__lte=local_start.time(),
                    end_time__gte=local_end.time(),
                ).exists():
                    return Response(
                        {"detail": "Your working schedule no longer covers the full appointment duration."},
                        status=status.HTTP_409_CONFLICT,
                    )
                if WorkerBlockedSlot.objects.filter(
                    worker=worker.user, start_at__lt=group_end, end_at__gt=group_start
                ).exists() or worker.leaves.filter(
                    start_at__lt=group_end, end_at__gt=group_start
                ).exists():
                    return Response(
                        {"detail": "You have a blocked time or leave during this appointment."},
                        status=status.HTTP_409_CONFLICT,
                    )
                existing_assignments = BookingAssignment.objects.filter(
                    worker=worker,
                    booking__status__in=(
                        Booking.Status.ASSIGNED, Booking.Status.CONFIRMED,
                        Booking.Status.IN_PROGRESS,
                    ),
                ).exclude(booking__appointment_group=group).select_related(
                    "booking__service", "booking__variant"
                )
                for existing_assignment in existing_assignments:
                    existing = existing_assignment.booking
                    occupied = DispatcherService._assigned_booking_intervals(existing)
                    if any(
                        _intervals_overlap((group_start, group_end), interval)
                        for interval in occupied
                    ):
                        return Response(
                            {"detail": "You are no longer available for the full appointment duration."},
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
                    note=(
                        f"Worker accepted appointment group #{group.group_number}"
                        if group_offer else
                        "Worker accepted complete order offer" if order_offer else
                        "Worker accepted service line from parent order" if order else
                        "Worker accepted job offer"
                    ),
                )
                assignment_payload = {
                    "booking_id": booking.pk,
                    "order_id": order.pk if order else None,
                    "appointment_group_id": group.pk if group_offer else None,
                    "worker_id": worker.pk,
                }
                Notification.objects.create(
                    user=booking.customer,
                    type=Notification.Type.BOOKING_ASSIGNED,
                    title="Worker Assigned",
                    body=f"Your service is now assigned to {worker.user.name or 'an AIRway professional'}.",
                    channel=Notification.Channel.IN_APP,
                    data=assignment_payload,
                )
                from apps.notifications.service import send_push_notification
                transaction.on_commit(
                    lambda customer=booking.customer, payload=assignment_payload:
                        send_push_notification(
                            customer,
                            "Worker Assigned",
                            "Your AIRway professional has accepted the service.",
                            data=payload,
                            channel_id="airway_booking_updates",
                        )
                )

            offer.status = WorkerOffer.Status.ACCEPTED
            offer.accepted_at = now
            offer.responded_at = now
            offer.save(update_fields=["status", "accepted_at", "responded_at", "updated_at"])
            if group_offer:
                WorkerOffer.objects.filter(
                    appointment_group=group, status=WorkerOffer.Status.PENDING
                ).exclude(pk=offer.pk).update(
                    status=WorkerOffer.Status.WITHDRAWN, responded_at=now
                )
                WorkerOffer.objects.filter(
                    booking__in=bookings, appointment_group__isnull=True,
                    order__isnull=True, status=WorkerOffer.Status.PENDING,
                ).update(status=WorkerOffer.Status.WITHDRAWN, responded_at=now)
                active_ids = list(
                    order.items.exclude(booking__status=Booking.Status.CANCELLED)
                    .values_list("booking_id", flat=True)
                )
                if active_ids and all(
                    BookingAssignment.objects.filter(booking_id=booking_id).exists()
                    for booking_id in active_ids
                ):
                    order.status = (
                        Order.Status.PARTIALLY_CANCELLED
                        if order.items.filter(booking__status=Booking.Status.CANCELLED).exists()
                        else Order.Status.AWAITING_PAYMENT
                    )
                    order.save(update_fields=["status", "updated_at"])
            elif order_offer:
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
            else:
                # Each service line has its own offer and worker assignment.
                WorkerOffer.objects.filter(
                    booking=bookings[0], order__isnull=True,
                    status=WorkerOffer.Status.PENDING,
                ).exclude(pk=offer.pk).update(
                    status=WorkerOffer.Status.WITHDRAWN, responded_at=now
                )
                if order:
                    active_ids = list(
                        order.items.exclude(booking__status=Booking.Status.CANCELLED)
                        .values_list("booking_id", flat=True)
                    )
                    if active_ids and all(
                        BookingAssignment.objects.filter(booking_id=booking_id).exists()
                        for booking_id in active_ids
                    ):
                        order.status = (
                            Order.Status.PARTIALLY_CANCELLED
                            if order.items.filter(booking__status=Booking.Status.CANCELLED).exists()
                            else Order.Status.AWAITING_PAYMENT
                        )
                        order.save(update_fields=["status", "updated_at"])

        response_data = {
            "status": "accepted",
            "detail": (f"Appointment group #{group.group_number} accepted successfully." if group_offer else "Complete order accepted successfully." if order_offer else "Offer accepted successfully."),
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
            # A worker-initiated withdrawal is a terminal decline for this
            # booking. WITHDRAWN is reserved for system-driven cancellation
            # and can be safely re-opened during an assignment replacement.
            offer.status = WorkerOffer.Status.DECLINED
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


class CustomerVerifiedWorkerProfileView(APIView):
    """Expose only admin-approved professional information to the assigned customer."""
    permission_classes = [IsAuthenticated]

    def get(self, request, booking_id):
        booking = Booking.objects.select_related(
            "customer", "assignment__worker__user"
        ).filter(pk=booking_id, customer=request.user).first()
        if booking is None:
            return Response({"detail": "Booking not found."}, status=status.HTTP_404_NOT_FOUND)
        assignment = getattr(booking, "assignment", None)
        if assignment is None or assignment.accepted_at is None:
            return Response({"detail": "A worker has not accepted this booking yet."}, status=status.HTTP_409_CONFLICT)
        worker = assignment.worker
        if worker.status != WorkerProfile.Status.APPROVED:
            return Response({"detail": "Worker profile is not currently available."}, status=status.HTTP_404_NOT_FOUND)
        photo = worker.documents.filter(
            doc_type=WorkerDocument.DocumentType.PHOTO,
            status=WorkerDocument.Status.VERIFIED,
        ).order_by("-created_at", "-id").first()
        try:
            photo_url = request.build_absolute_uri(photo.file.url) if photo else None
        except Exception:
            photo_url = None
        verified_services = worker.worker_services.filter(
            capabilities_verified=True,
            service__is_active=True,
            service__category__is_active=True,
        ).select_related("service", "service__category").order_by("service__title")
        services = [{
            "service": row.service.title,
            "category": row.service.category.title,
            "experience_years": row.experience_years,
            "verified_skills": row.capabilities or [],
        } for row in verified_services]
        completed_jobs = BookingAssignment.objects.filter(
            worker=worker, booking__status=Booking.Status.COMPLETED
        ).count()
        return Response({
            "worker_id": worker.pk,
            "name": worker.user.name or "AIRway Professional",
            "photo_url": photo_url,
            "bio": worker.bio,
            "experience_years": worker.experience_years,
            "qualification": worker.qualification,
            "rating": str(worker.rating_avg),
            "rating_count": worker.rating_count,
            "completed_jobs": completed_jobs,
            "services": services,
            "verified": True,
        })
