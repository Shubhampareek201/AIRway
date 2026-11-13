
from decimal import Decimal
import re

from django.contrib.auth import get_user_model, authenticate
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.core.models import Zone
from .models import Address

User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)
    confirm_password = serializers.CharField(write_only=True)
    email = serializers.EmailField(required=False, allow_blank=True)

    class Meta:
        model = User
        fields = ["phone", "name", "email", "password", "confirm_password"]

    def validate_phone(self, value):
        if not re.match(r'^\+91[6-9]\d{9}$', value):
            raise serializers.ValidationError("Phone number must be in format +919876543210")
        if User.objects.filter(phone=value).exists():
            raise serializers.ValidationError("User with this phone number already exists.")
        return value

    def validate_email(self, value):
        if value and User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Email already registered.")
        return value

    def validate(self, attrs):
        if attrs.get('password') != attrs.get('confirm_password'):
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        validate_password(attrs.get('password'))
        from apps.core.coverage import resolve_active_zone
        zone = resolve_active_zone(latitude=latitude, longitude=longitude)
        if zone is None:
            raise serializers.ValidationError({
                "full_address": "AIRway is not serving this location yet. Please choose an address inside the Rawatbhata service area."
            })
        attrs["zone"] = zone
        return attrs

    def create(self, validated_data):
        validated_data.pop('confirm_password')
        password = validated_data.pop('password')
        user = User.objects.create_user(**validated_data, password=password)
        return user


class LoginSerializer(serializers.Serializer):
    phone = serializers.CharField(required=False)
    email = serializers.EmailField(required=False)
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        phone = attrs.get('phone')
        email = attrs.get('email')
        password = attrs.get('password')

        if not phone and not email:
            raise serializers.ValidationError("Either phone or email is required.")
        if phone and email:
            raise serializers.ValidationError("Provide either phone or email, not both.")

        # If email provided, look up user by email first
        if email:
            try:
                user = User.objects.get(email=email)
                phone = user.phone
            except User.DoesNotExist:
                raise serializers.ValidationError("Invalid credentials.")

        # Authenticate with phone (USERNAME_FIELD)
        user = authenticate(request=self.context.get('request'), username=phone, password=password)
        if not user:
            raise serializers.ValidationError("Invalid credentials.")
        if not user.is_active:
            raise serializers.ValidationError("Account disabled.")
        attrs['user'] = user
        return attrs


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)
    confirm_new_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user = self.context['request'].user
        if not user.check_password(attrs.get('old_password')):
            raise serializers.ValidationError({"old_password": "Old password is incorrect."})
        if attrs.get('new_password') != attrs.get('confirm_new_password'):
            raise serializers.ValidationError({"confirm_new_password": "Passwords do not match."})
        validate_password(attrs.get('new_password'), user)
        return attrs


class ForgotPasswordSerializer(serializers.Serializer):
    phone = serializers.CharField()

    def validate_phone(self, value):
        if not re.match(r'^\+91[6-9]\d{9}$', value):
            raise serializers.ValidationError("Phone number must be in format +919876543210")
        if not User.objects.filter(phone=value).exists():
            raise serializers.ValidationError("No account found with this phone number.")
        return value


class VerifyOTPSerializer(serializers.Serializer):
    phone = serializers.CharField()
    otp = serializers.CharField(max_length=6)
    purpose = serializers.ChoiceField(choices=['forgot_password'])

    def validate_phone(self, value):
        if not re.match(r'^\+91[6-9]\d{9}$', value):
            raise serializers.ValidationError("Phone number must be in format +919876543210")
        return value


class ProfileCompletionSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150)
    email = serializers.EmailField(required=False, allow_blank=True)
    gender = serializers.ChoiceField(choices=User.Gender.choices, required=False)

    def validate_email(self, value):
        if value and self.context['request'].user.email != value:
            if User.objects.filter(email=value).exists():
                raise serializers.ValidationError("Email already in use.")
        return value

    def validate(self, attrs):
        attrs['email'] = attrs.get('email', '') or ''
        return attrs


class ResetPasswordSerializer(serializers.Serializer):
    phone = serializers.CharField()
    otp = serializers.CharField(max_length=6)
    new_password = serializers.CharField(write_only=True)
    confirm_new_password = serializers.CharField(write_only=True)

    def validate_phone(self, value):
        if not re.match(r'^\+91[6-9]\d{9}$', value):
            raise serializers.ValidationError("Phone number must be in format +919876543210")
        if not User.objects.filter(phone=value).exists():
            raise serializers.ValidationError("No account found with this phone number.")
        return value

    def validate(self, attrs):
        if attrs.get('new_password') != attrs.get('confirm_new_password'):
            raise serializers.ValidationError({"confirm_new_password": "Passwords do not match."})
        validate_password(attrs.get('new_password'))
        return attrs


class AddressSerializer(serializers.ModelSerializer):
    """Read-only address details returned to the mobile app."""

    zone_name = serializers.CharField(
        source="zone.name",
        read_only=True,
        allow_null=True,
    )
    city_name = serializers.CharField(
        source="zone.city.name",
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = Address
        fields = [
            "id",
            "label",
            "house_details",
            "landmark",
            "full_address",
            "latitude",
            "longitude",
            "zone",
            "zone_name",
            "city_name",
            "is_default",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class AddressCreateSerializer(serializers.ModelSerializer):
    """Validate new addresses and edits to existing addresses."""


    class Meta:
        model = Address
        fields = [
            "id",
            "label",
            "house_details",
            "landmark",
            "full_address",
            "latitude",
            "longitude",
            "zone",
        ]
        read_only_fields = ["id", "zone"]

    def validate(self, attrs):
        existing = self.instance

        for field in (
            "house_details",
            "landmark",
            "full_address",
        ):
            value = attrs.get(
                field,
                getattr(existing, field, "") if existing else "",
            )

            if not isinstance(value, str) or not value.strip():
                raise serializers.ValidationError({
                    field: "This field is required."
                })

            if field in attrs:
                attrs[field] = value.strip()

        latitude = attrs.get(
            "latitude",
            existing.latitude if existing else None,
        )
        longitude = attrs.get(
            "longitude",
            existing.longitude if existing else None,
        )

        if latitude is None or longitude is None:
            raise serializers.ValidationError({
                "latitude": "Confirm the map location.",
                "longitude": "Confirm the map location.",
            })

        if not Decimal("-90") <= latitude <= Decimal("90"):
            raise serializers.ValidationError({
                "latitude": "Latitude must be between -90 and 90."
            })

        if not Decimal("-180") <= longitude <= Decimal("180"):
            raise serializers.ValidationError({
                "longitude": "Longitude must be between -180 and 180."
            })

        return attrs
