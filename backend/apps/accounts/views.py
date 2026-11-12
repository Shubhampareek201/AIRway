
import logging
import json
import os
import random
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from difflib import SequenceMatcher

from django.core.cache import cache
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.utils import timezone
from apps.workers.models import WorkerProfile

from firebase_admin import auth
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.models import City, Zone
from apps.workers.models import WorkerDocument

from .firebase_service import verify_firebase_token
from .models import Address
from .serializers import (
    AddressCreateSerializer,
    AddressSerializer,
    RegisterSerializer,
    LoginSerializer,
    ChangePasswordSerializer,
    ForgotPasswordSerializer,
    VerifyOTPSerializer,
    ResetPasswordSerializer,
    ProfileCompletionSerializer,
)

User = get_user_model()
logger = logging.getLogger(__name__)


class FirebaseLoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        id_token = request.data.get("id_token")

        if not isinstance(id_token, str) or not id_token:
            return Response(
                {"error": "Firebase ID token is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            decoded = verify_firebase_token(id_token)

        except (
            ValueError,
            auth.InvalidIdTokenError,
            auth.ExpiredIdTokenError,
            auth.RevokedIdTokenError,
            auth.UserDisabledError,
        ):
            return Response(
                {"error": "Invalid or expired authentication token."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        except Exception:
            logger.exception(
                "AIRway Firebase authentication failed"
            )
            return Response(
                {"error": "Authentication service unavailable."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        firebase_data = decoded.get("firebase", {})
        phone = decoded.get("phone_number")

        if (
            not isinstance(firebase_data, dict)
            or firebase_data.get("sign_in_provider") != "phone"
            or not isinstance(phone, str)
            or not phone.startswith("+91")
        ):
            return Response(
                {"error": "Verified Indian phone login required."},
                status=status.HTTP_403_FORBIDDEN,
            )

        with transaction.atomic():
            user, created = User.objects.get_or_create(
                phone=phone,
                defaults={"password": make_password(None)},
            )

        if not user.is_active:
            return Response(
                {"error": "Account disabled."},
                status=status.HTTP_403_FORBIDDEN,
            )

        refresh = RefreshToken.for_user(user)

        return Response({
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": {
                "id": user.id,
                "phone": user.phone,
                "name": user.name,
                "email": user.email,
                "active_mode": user.active_mode,
            },
            "is_new_user": created,
            "profile_complete": bool(user.name and user.name.strip()),
        })


class RegisterView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if not serializer.is_valid():
            errors = serializer.errors
            error_msg = next(iter(errors.values()))[0] if errors else "Invalid data."
            if isinstance(error_msg, list):
                error_msg = error_msg[0]
            return Response({"error": error_msg}, status=status.HTTP_400_BAD_REQUEST)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        return Response({
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": {
                "id": user.id,
                "phone": user.phone,
                "name": user.name,
                "active_mode": user.active_mode,
            },
            "message": "Account created successfully."
        }, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            errors = serializer.errors
            error_msg = next(iter(errors.values()))[0] if errors else "Invalid credentials."
            if isinstance(error_msg, list):
                error_msg = error_msg[0]
            return Response({"error": error_msg}, status=status.HTTP_400_BAD_REQUEST)
        user = serializer.validated_data['user']
        refresh = RefreshToken.for_user(user)
        return Response({
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": {
                "id": user.id,
                "phone": user.phone,
                "name": user.name,
                "email": user.email,
                "active_mode": user.active_mode,
            },
            "profile_complete": bool(user.name and user.name.strip()),
        })


class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        data = {
            "id": user.id,
            "phone": user.phone,
            "name": user.name,
            "email": user.email,
            "active_mode": user.active_mode,
            "profile_complete": bool(user.name and user.name.strip()),
            "can_switch_to_worker": user.active_mode == User.Mode.WORKER,
            "worker_application_status": self._get_worker_application_status(user),
        }

        # Add worker profile if exists
        try:
            profile = user.worker_profile
            data["worker_profile"] = {
                "id": profile.id,
                "status": profile.status,
                "gender": profile.gender,
                "upi_id": profile.upi_id,
                "is_online": profile.is_online,
                "rating_avg": float(profile.rating_avg) if profile.rating_avg else None,
                "experience_years": profile.experience_years,
                "qualification": profile.qualification,
                "equipment_details": profile.equipment_details,
                "residential_address": profile.residential_address,
                "landmark": profile.landmark,
                "bio": profile.bio,
                "rejection_reason": profile.rejection_reason,
                "photo_url": self._get_worker_photo_url(profile, request),
                "has_photo": profile.documents.filter(
                    doc_type=WorkerDocument.DocumentType.PHOTO
                ).exists(),
                "id_type": self._get_worker_id_type(profile),
                "service_ids": list(profile.worker_services.values_list("service_id", flat=True)),
                "zone_ids": list(profile.worker_zones.values_list("zone_id", flat=True)),
                "schedule": {
                    str(slot.weekday): {
                        "start": slot.start_time.strftime("%H:%M"),
                        "end": slot.end_time.strftime("%H:%M"),
                    }
                    for slot in profile.schedules.filter(is_active=True)
                },
            }
        except WorkerProfile.DoesNotExist:
            pass

        # Add customer profile if exists (placeholder for future implementation)
        # customer_profile relationship not yet defined in User model
        if hasattr(user, 'customer_profile'):
            data["customer_profile"] = {}

        return Response(data)

    def _get_worker_application_status(self, user):
        """Return worker application status for customers who applied."""
        try:
            profile = user.worker_profile
            return {
                "has_application": True,
                "status": profile.status,
                "rejection_reason": profile.rejection_reason,
            }
        except WorkerProfile.DoesNotExist:
            return {
                "has_application": False,
                "status": None,
                "rejection_reason": None,
            }

    def _get_worker_id_type(self, profile):
        document = profile.documents.filter(
            doc_type__in=[
                WorkerDocument.DocumentType.AADHAAR,
                WorkerDocument.DocumentType.ID,
            ]
        ).order_by("-created_at").first()
        return document.doc_type if document else None

    def _get_worker_photo_url(self, profile, request):
        """Return the photo URL from WorkerDocument if available."""
        try:
            photo_doc = profile.documents.filter(
                doc_type=WorkerDocument.DocumentType.PHOTO,
                status=WorkerDocument.Status.VERIFIED
            ).first()
            if photo_doc and photo_doc.file:
                return request.build_absolute_uri(photo_doc.file.url)
        except Exception:
            pass
        return None


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            errors = serializer.errors
            error_msg = next(iter(errors.values()))[0] if errors else "Invalid data."
            if isinstance(error_msg, list):
                error_msg = error_msg[0]
            return Response({"error": error_msg}, status=status.HTTP_400_BAD_REQUEST)
        user = request.user
        user.set_password(serializer.validated_data['new_password'])
        user.save()
        return Response({"message": "Password changed successfully."})


class ProfileCompletionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ProfileCompletionSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            errors = serializer.errors
            error_msg = next(iter(errors.values()))[0] if errors else "Invalid data."
            if isinstance(error_msg, list):
                error_msg = error_msg[0]
            return Response({"error": error_msg}, status=status.HTTP_400_BAD_REQUEST)
        user = request.user
        user.name = serializer.validated_data['name']
        user.email = serializer.validated_data.get('email', '') or ''
        if 'gender' in serializer.validated_data and serializer.validated_data['gender']:
            user.gender = serializer.validated_data['gender']
        user.save(update_fields=['name', 'email', 'gender'])
        return Response({
            "message": "Profile completed successfully.",
            "user": {
                "id": user.id,
                "phone": user.phone,
                "name": user.name,
                "email": user.email,
                "active_mode": user.active_mode,
            },
            "profile_complete": True,
        })


class CityListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        cities = City.objects.filter(
            is_active=True
        ).order_by("name")

        return Response([
            {
                "id": city.id,
                "name": city.name,
                "state": city.state,
            }
            for city in cities
        ])


class ZoneListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        city_id = request.query_params.get("city_id")

        # Build base queryset
        zones = Zone.objects.filter(
            city__is_active=True,
            is_active=True,
        )

        # Filter by city if provided
        if city_id:
            if not city_id.isascii() or not city_id.isdecimal():
                return Response(
                    {"error": "A valid city_id is required."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            zones = zones.filter(city_id=int(city_id))

        zones = zones.order_by("city", "name")

        return Response([
            {
                "id": zone.id,
                "name": zone.name,
                "city_id": zone.city_id,
                "city_name": zone.city.name,
                "latitude": str(zone.latitude) if zone.latitude is not None else None,
                "longitude": str(zone.longitude) if zone.longitude is not None else None,
                "coverage_radius_meters": zone.coverage_radius_meters,
            }
            for zone in zones
        ])


class ForgotPasswordView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        if not serializer.is_valid():
            errors = serializer.errors
            error_msg = next(iter(errors.values()))[0] if errors else "Invalid data."
            if isinstance(error_msg, list):
                error_msg = error_msg[0]
            return Response({"error": error_msg}, status=status.HTTP_400_BAD_REQUEST)
        phone = serializer.validated_data['phone']
        otp = str(random.randint(100000, 999999))
        cache_key = f"airway:forgot_otp:{phone}"
        cache.set(cache_key, otp, timeout=300)
        return Response({
            "message": "OTP sent successfully to your registered mobile number.",
            "otp": otp  # Only for testing as per user request
        })


class VerifyForgotOTPView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = VerifyOTPSerializer(data=request.data)
        if not serializer.is_valid():
            errors = serializer.errors
            error_msg = next(iter(errors.values()))[0] if errors else "Invalid data."
            if isinstance(error_msg, list):
                error_msg = error_msg[0]
            return Response({"error": error_msg}, status=status.HTTP_400_BAD_REQUEST)
        phone = serializer.validated_data['phone']
        otp = serializer.validated_data['otp']
        cache_key = f"airway:forgot_otp:{phone}"
        stored_otp = cache.get(cache_key)
        if not stored_otp or stored_otp != otp:
            return Response({"error": "Invalid or expired OTP."}, status=status.HTTP_400_BAD_REQUEST)
        cache_key_verified = f"airway:forgot_verified:{phone}"
        cache.set(cache_key_verified, True, timeout=600)
        return Response({"message": "OTP verified successfully."})


class ResetPasswordView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        if not serializer.is_valid():
            errors = serializer.errors
            error_msg = next(iter(errors.values()))[0] if errors else "Invalid data."
            if isinstance(error_msg, list):
                error_msg = error_msg[0]
            return Response({"error": error_msg}, status=status.HTTP_400_BAD_REQUEST)
        phone = serializer.validated_data['phone']
        otp = serializer.validated_data['otp']
        cache_key = f"airway:forgot_otp:{phone}"
        cache_key_verified = f"airway:forgot_verified:{phone}"
        stored_otp = cache.get(cache_key)
        verified = cache.get(cache_key_verified)
        if not stored_otp or stored_otp != otp or not verified:
            return Response({"error": "Invalid or expired OTP. Please try again."}, status=status.HTTP_400_BAD_REQUEST)
        user = User.objects.get(phone=phone)
        user.set_password(serializer.validated_data['new_password'])
        user.save()
        cache.delete(cache_key)
        cache.delete(cache_key_verified)
        return Response({"message": "Password reset successfully. You can now login."})


class AddressListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        addresses = (
            Address.objects.filter(
                user=request.user,
                deleted_at__isnull=True,
            )
            .select_related("zone", "zone__city")
            .order_by("-is_default", "-created_at")
        )

        return Response(
            AddressSerializer(addresses, many=True).data
        )

    def post(self, request):
        serializer = AddressCreateSerializer(
            data=request.data
        )
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            User.objects.select_for_update().get(
                pk=request.user.pk
            )

            has_address = Address.objects.filter(
                user=request.user,
                deleted_at__isnull=True,
            ).exists()

            address = serializer.save(
                user=request.user,
                is_default=not has_address,
            )

        return Response(
            AddressSerializer(address).data,
            status=status.HTTP_201_CREATED,
        )


class AddressDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, address_id):
        with transaction.atomic():
            User.objects.select_for_update().get(
                pk=request.user.pk
            )

            address = Address.objects.filter(
                pk=address_id,
                user=request.user,
                deleted_at__isnull=True,
            ).first()

            if address is None:
                return Response(
                    {"error": "Address not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            serializer = AddressCreateSerializer(
                address,
                data=request.data,
                partial=True,
            )
            serializer.is_valid(raise_exception=True)
            serializer.save()

        return Response(
            AddressSerializer(address).data
        )

    def delete(self, request, address_id):
        with transaction.atomic():
            User.objects.select_for_update().get(
                pk=request.user.pk
            )

            address = Address.objects.filter(
                pk=address_id,
                user=request.user,
                deleted_at__isnull=True,
            ).first()

            if address is None:
                return Response(
                    {"error": "Address not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            was_default = address.is_default

            address.deleted_at = timezone.now()
            address.is_default = False
            address.save(
                update_fields=[
                    "deleted_at",
                    "is_default",
                    "updated_at",
                ]
            )

            if was_default:
                next_address = (
                    Address.objects.filter(
                        user=request.user,
                        deleted_at__isnull=True,
                    )
                    .order_by("-created_at")
                    .first()
                )

                if next_address is not None:
                    next_address.is_default = True
                    next_address.save(
                        update_fields=[
                            "is_default",
                            "updated_at",
                        ]
                    )

        return Response(
            status=status.HTTP_204_NO_CONTENT
        )


class SetDefaultAddressView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, address_id):
        with transaction.atomic():
            User.objects.select_for_update().get(
                pk=request.user.pk
            )

            address = Address.objects.filter(
                pk=address_id,
                user=request.user,
                deleted_at__isnull=True,
            ).first()

            if address is None:
                return Response(
                    {"error": "Address not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            Address.objects.filter(
                user=request.user,
                deleted_at__isnull=True,
                is_default=True,
            ).exclude(
                pk=address.pk
            ).update(
                is_default=False
            )

            if not address.is_default:
                address.is_default = True
                address.save(
                    update_fields=[
                        "is_default",
                        "updated_at",
                    ]
                )

        return Response(
            AddressSerializer(address).data
        )

class LocationSearchView(APIView):
    permission_classes = [IsAuthenticated]

    @staticmethod
    def normalize(text):
        return re.sub(
            r"\s+",
            " ",
            re.sub(r"[^\w\s]", " ", text.casefold()),
        ).strip()

    def get(self, request):
        query = request.query_params.get("q", "").strip()

        if len(query) < 2 or len(query) > 150:
            return Response(
                {"error": "Enter 2 to 150 characters."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        normalized_query = self.normalize(query)
        results = []

        zones = Zone.objects.filter(
            is_active=True,
            city__is_active=True,
        ).select_related("city")

        for zone in zones:
            name = self.normalize(zone.name)
            full_name = self.normalize(
                f"{zone.name} {zone.city.name} {zone.city.state}"
            )

            if normalized_query in name:
                score = 1.0
            elif normalized_query in full_name:
                score = 0.95
            else:
                score = SequenceMatcher(
                    None, normalized_query, name
                ).ratio()

                score = max(
                    score,
                    SequenceMatcher(
                        None, normalized_query, full_name
                    ).ratio(),
                )

            if score < 0.55:
                continue

            results.append({
                "id": zone.id,
                "type": "zone",
                "name": zone.name,
                "display_name": (
                    f"{zone.name}, {zone.city.name}, "
                    f"{zone.city.state}"
                ),
                "city_id": zone.city_id,
                "zone_id": zone.id,
                "score": round(score, 3),
                "latitude": (
                    float(zone.latitude)
                    if zone.latitude is not None else None
                ),
                "longitude": (
                    float(zone.longitude)
                    if zone.longitude is not None else None
                ),
            })

        cities = City.objects.filter(is_active=True)

        for city in cities:
            name = self.normalize(city.name)

            score = (
                1.0
                if normalized_query in name
                else SequenceMatcher(
                    None, normalized_query, name
                ).ratio()
            )

            if score < 0.55:
                continue

            results.append({
                "id": city.id,
                "type": "city",
                "name": city.name,
                "display_name": f"{city.name}, {city.state}",
                "city_id": city.id,
                "zone_id": None,
                "score": round(score, 3),
            })

        results.sort(
            key=lambda item: item["score"],
            reverse=True,
        )

        return Response({
            "results": results[:10],
        })

class GeoapifyAutocompleteView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        query = request.query_params.get("q", "").strip()

        if len(query) < 3 or len(query) > 150:
            return Response(
                {"error": "Enter 3 to 150 characters."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        api_key = os.environ.get("GEOAPIFY_API_KEY")

        if not api_key:
            return Response(
                {"error": "Location search is not configured."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        params = {
            "text": query,
            "format": "json",
            "filter": "countrycode:in",
            "limit": 7,
            "lang": "en",
            "apiKey": api_key,
        }

        # Optional location bias: prefer results near the map.
        lat_text = request.query_params.get("lat")
        lon_text = request.query_params.get("lon")

        if lat_text is not None or lon_text is not None:
            try:
                latitude = float(lat_text)
                longitude = float(lon_text)

                if (
                    not -90 <= latitude <= 90
                    or not -180 <= longitude <= 180
                ):
                    raise ValueError

                params["bias"] = (
                    f"proximity:{longitude},{latitude}"
                )
            except (TypeError, ValueError):
                return Response(
                    {"error": "Invalid map coordinates."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Cache repeated searches to reduce external requests.
        from hashlib import sha256

        cache_params = {
            k: v for k, v in params.items()
            if k != "apiKey"
        }

        cache_key = "geoapify:" + sha256(
            json.dumps(
                cache_params,
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()

        cached = cache.get(cache_key)

        if cached is not None:
            return Response({"results": cached})

        url = (
            "https://api.geoapify.com/v1/geocode/autocomplete?"
            + urlencode(params)
        )

        upstream_request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "AIRway-Backend/1.0",
            },
        )

        try:
            with urlopen(upstream_request, timeout=8) as upstream:
                data = json.load(upstream)

        except (HTTPError, URLError, TimeoutError, ValueError):
            return Response(
                {"error": "Location search is temporarily unavailable."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        results = []

        for item in data.get("results", []):
            if not isinstance(item, dict):
                continue

            latitude = item.get("lat")
            longitude = item.get("lon")
            label = item.get("formatted")

            if (
                not isinstance(latitude, (int, float))
                or not isinstance(longitude, (int, float))
                or not isinstance(label, str)
                or not label.strip()
            ):
                continue

            results.append({
                "type": "external",
                "name": label,
                "latitude": latitude,
                "longitude": longitude,
                "city": item.get("city"),
                "postcode": item.get("postcode"),
            })

        cache.set(cache_key, results, timeout=300)

        return Response({"results": results})

class SwitchModeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        mode = request.data.get('mode')

        if mode not in [User.Mode.CUSTOMER, User.Mode.WORKER]:
            return Response(
                {"error": "Invalid mode. Must be 'customer' or 'worker'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if mode == User.Mode.WORKER:
            if not hasattr(user, 'worker_profile'):
                return Response(
                    {"error": "You must have an approved worker profile to switch to worker mode."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            try:
                profile = user.worker_profile
                if profile.status != WorkerProfile.Status.APPROVED:
                    return Response(
                        {"error": f"Your worker profile is not approved yet. Status: {profile.status}."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            except WorkerProfile.DoesNotExist:
                return Response(
                    {"error": "Worker profile not found. Apply to become a worker first."},
                    status=status.HTTP_404_NOT_FOUND,
                )

        user.active_mode = mode
        user.save(update_fields=['active_mode'])

        return Response({
            "message": "Mode switched successfully.",
            "active_mode": user.active_mode,
        })


class LocationReverseView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        import math

        try:
            lat = float(request.query_params["lat"])
            lon = float(request.query_params["lon"])
        except (KeyError, TypeError, ValueError):
            return Response(
                {"error": "Valid coordinates are required."},
                status=400,
            )

        if not (
            math.isfinite(lat)
            and math.isfinite(lon)
            and -90 <= lat <= 90
            and -180 <= lon <= 180
        ):
            return Response(
                {"error": "Coordinates are out of range."},
                status=400,
            )

        api_key = os.environ.get("GEOAPIFY_API_KEY")

        if not api_key:
            return Response(
                {"error": "Geocoding is not configured."},
                status=503,
            )

        # Round to approximately 11 m to reduce repeated
        # requests when the map moves by tiny amounts.
        key = f"airway:reverse:{lat:.4f}:{lon:.4f}"

        cached = cache.get(key)
        if cached is not None:
            return Response(cached)

        params = urlencode({
            "lat": lat,
            "lon": lon,
            "format": "json",
            "lang": "en",
            "limit": 1,
            "apiKey": api_key,
        })

        req = Request(
            "https://api.geoapify.com/v1/geocode/reverse?"
            + params,
            headers={
                "Accept": "application/json",
                "User-Agent": "AIRway-Backend/1.0",
            },
        )

        try:
            with urlopen(req, timeout=8) as upstream:
                payload = json.load(upstream)
        except (HTTPError, URLError, TimeoutError, ValueError):
            return Response(
                {"error": "Address lookup temporarily unavailable."},
                status=503,
            )

        results = payload.get("results", [])
        place = results[0] if results else {}

        if not isinstance(place, dict):
            place = {}

        result = {
            "formatted": place.get("formatted") or "",
            "address_line1": place.get("address_line1") or "",
            "address_line2": place.get("address_line2") or "",
            "city": place.get("city") or "",
            "state": place.get("state") or "",
            "postcode": place.get("postcode") or "",
            "latitude": lat,
            "longitude": lon,
        }

        cache.set(key, result, timeout=3600)
        return Response(result)
