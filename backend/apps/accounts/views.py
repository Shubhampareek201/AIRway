
from django.contrib.auth import get_user_model
from django.db import transaction

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth.hashers import make_password
from firebase_admin import auth

from .firebase_service import verify_firebase_token

User = get_user_model()


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
        except (ValueError, auth.InvalidIdTokenError,
                auth.ExpiredIdTokenError, auth.RevokedIdTokenError,
                auth.UserDisabledError):
            return Response(
                {"error": "Invalid or expired authentication token."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
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
                "active_mode": user.active_mode,
            },
            "is_new_user": created,
        })
