from rest_framework import serializers
from django.utils import timezone

from .models import (
    Booking,
    BookingAddOn,
    BookingFormResponse,
    BookingStatusHistory,
    BookingAssignment,
)
from .services import check_slot_availability, check_service_available, create_worker_offers_for_booking, SlotConflictError, ServiceUnavailableError
from apps.catalog.models import Service, ServiceVariant, AddOn, FormField
from apps.accounts.models import Address
from apps.notifications.models import Notification


class BookingAddOnSerializer(serializers.ModelSerializer):
    addon_title = serializers.CharField(source="addon.title", read_only=True)
    addon_title_hi = serializers.CharField(source="addon.title_hi", read_only=True)

    class Meta:
        model = BookingAddOn
        fields = ["id", "addon", "addon_title", "addon_title_hi", "quantity", "unit_price", "total_price"]
        read_only_fields = ["unit_price", "total_price"]


class BookingFormResponseSerializer(serializers.ModelSerializer):
    field_key = serializers.CharField(source="form_field.key", read_only=True)
    field_label = serializers.CharField(source="form_field.label", read_only=True)
    field_label_hi = serializers.CharField(source="form_field.label_hi", read_only=True)
    field_type = serializers.CharField(source="form_field.field_type", read_only=True)
    field_options = serializers.JSONField(source="form_field.options", read_only=True)

    class Meta:
        model = BookingFormResponse
        fields = ["id", "form_field", "field_key", "field_label", "field_label_hi", "field_type", "field_options", "value"]
        read_only_fields = ["form_field"]


class BookingStatusHistorySerializer(serializers.ModelSerializer):
    changed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = BookingStatusHistory
        fields = ["id", "from_status", "to_status", "changed_by", "changed_by_name", "note", "created_at"]

    def get_changed_by_name(self, obj):
        if obj.changed_by:
            if obj.changed_by.name:
                return obj.changed_by.name
            return obj.changed_by.phone
        return "System"


class BookingAssignmentSerializer(serializers.ModelSerializer):
    worker_name = serializers.SerializerMethodField()
    worker_phone = serializers.SerializerMethodField()
    worker_rating = serializers.SerializerMethodField()
    worker_photo = serializers.SerializerMethodField()

    class Meta:
        model = BookingAssignment
        fields = [
            "id", "worker", "worker_name", "worker_phone", "worker_rating", "worker_photo",
            "assigned_at", "accepted_at", "started_at", "completed_at"
        ]

    def get_worker_name(self, obj):
        user = obj.worker.user
        if user.name:
            return user.name
        return user.phone

    def get_worker_phone(self, obj):
        return obj.worker.user.phone

    def get_worker_rating(self, obj):
        return float(obj.worker.rating_avg) if obj.worker.rating_avg else None

    def get_worker_photo(self, obj):
        if obj.worker.user.photo:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.worker.user.photo.url)
        return None


class BookingCreateSerializer(serializers.ModelSerializer):
    addon_ids = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=False,
        help_text="List of AddOn IDs to include"
    )
    form_responses = serializers.DictField(
        child=serializers.JSONField(),
        write_only=True,
        required=False,
        help_text="Dict of form_field_key -> value"
    )
    address_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = Booking
        fields = [
            "id", "service", "variant", "booking_mode", "scheduled_at", "drop_scheduled_at",
            "address_id", "addon_ids", "form_responses", "notes"
        ]
        read_only_fields = ["id"]

    def validate(self, attrs):
        service = attrs["service"]
        variant = attrs.get("variant")
        booking_mode = attrs.get("booking_mode", Booking.BookingMode.SCHEDULED)
        scheduled_at = attrs.get("scheduled_at")
        drop_scheduled_at = attrs.get("drop_scheduled_at")
        address_id = attrs["address_id"]

        # Validate variant belongs to service
        if variant and variant.service != service:
            raise serializers.ValidationError({"variant": "Variant does not belong to this service."})

        # Validate booking mode matches service
        if booking_mode != service.booking_mode:
            raise serializers.ValidationError({"booking_mode": f"This service only supports {service.get_booking_mode_display()} booking."})

        # Validate scheduled_at is in future
        if scheduled_at and scheduled_at <= timezone.now():
            raise serializers.ValidationError({"scheduled_at": "Scheduled time must be in the future."})

        # Mode-specific validations
        if booking_mode == Booking.BookingMode.PICKUP_DROP:
            if not drop_scheduled_at:
                raise serializers.ValidationError({"drop_scheduled_at": "Drop time is required for Pickup & Drop booking."})
            if drop_scheduled_at <= scheduled_at:
                raise serializers.ValidationError({"drop_scheduled_at": "Drop time must be after pickup time."})
        else:
            if drop_scheduled_at:
                raise serializers.ValidationError({"drop_scheduled_at": "Drop time only allowed for Pickup & Drop booking."})

        # Check service availability
        try:
            check_service_available(service=service, address=None, audience="all")
        except ServiceUnavailableError as e:
            raise serializers.ValidationError({"service": str(e)})

        # Validate slot availability
        try:
            duration = variant.duration_minutes if variant else service.duration_minutes
            check_slot_availability(
                service=service,
                scheduled_at=scheduled_at,
                duration_minutes=duration or 60,
                booking_mode=booking_mode,
                drop_scheduled_at=drop_scheduled_at,
            )
        except SlotConflictError as e:
            raise serializers.ValidationError({"detail": str(e)})

        # Validate address belongs to user and is active
        user = self.context["request"].user
        try:
            address = Address.objects.get(pk=address_id, user=user, deleted_at__isnull=True)
            attrs["_address"] = address
        except Address.DoesNotExist:
            raise serializers.ValidationError({"address_id": "Invalid address."})

        # Validate addons belong to service
        addon_ids = attrs.get("addon_ids", [])
        if addon_ids:
            valid_addon_ids = set(AddOn.objects.filter(service=service).values_list("id", flat=True))
            invalid = set(addon_ids) - valid_addon_ids
            if invalid:
                raise serializers.ValidationError({"addon_ids": f"Invalid addon IDs: {invalid}"})

        # Validate form responses
        form_responses = attrs.get("form_responses", {})
        if form_responses:
            service_fields = {f.key: f for f in service.form_fields.filter(is_active=True)}
            for key, value in form_responses.items():
                if key not in service_fields:
                    raise serializers.ValidationError({"form_responses": f"Unknown form field: {key}"})
                field = service_fields[key]
                if field.is_required and (value is None or value == ""):
                    raise serializers.ValidationError({"form_responses": f"Field '{field.label}' is required."})

        return attrs

    def create(self, validated_data):
        addon_ids = validated_data.pop("addon_ids", [])
        form_responses = validated_data.pop("form_responses", {})
        address = validated_data.pop("_address")
        user = self.context["request"].user

        variant = validated_data.get("variant")
        service = validated_data["service"]
        booking_mode = validated_data["booking_mode"]

        # Build pricing snapshot
        pricing = {}

        # Variant price
        variant_price = 0
        if variant:
            variant_price = variant.price
            pricing["variant"] = {
                "id": variant.id,
                "title": variant.title,
                "title_hi": variant.title_hi,
                "price": str(variant.price),
                "mrp": str(variant.mrp),
                "discount_percent": variant.discount_percent,
            }
        elif service.pricing_type == Service.PricingType.FIXED:
            # For fixed price services without variant, use a base price (could be from a default variant)
            # For now, we'll require a variant for fixed price services
            pass

        pricing["variant_price"] = str(variant_price)

        # Addon prices
        addon_prices = []
        addon_total = 0
        for addon_id in addon_ids:
            addon = AddOn.objects.get(pk=addon_id)
            addon_prices.append({
                "id": addon.id,
                "title": addon.title,
                "title_hi": addon.title_hi,
                "price": str(addon.price),
                "mrp": str(addon.mrp),
                "discount_percent": addon.discount_percent,
            })
            addon_total += addon.price

        pricing["addons"] = addon_prices
        pricing["addon_total"] = str(addon_total)

        # Visit fee for inspection
        visit_fee = service.visit_fee if booking_mode == Booking.BookingMode.INSPECTION else 0
        pricing["visit_fee"] = str(visit_fee)

        # Calculate totals
        from decimal import Decimal
        subtotal = Decimal(str(variant_price)) + Decimal(str(addon_total)) + Decimal(str(visit_fee))
        tax = subtotal * Decimal("0.18")  # 18% GST
        total = subtotal + tax

        pricing["subtotal"] = str(subtotal)
        pricing["tax"] = str(tax)
        pricing["total"] = str(total)
        pricing["currency"] = "INR"

        validated_data["customer"] = user
        validated_data["address"] = address
        validated_data["pricing_snapshot"] = pricing

        booking = Booking.objects.create(**validated_data)

        # Create BookingAddOn entries
        for addon_id in addon_ids:
            addon = AddOn.objects.get(pk=addon_id)
            BookingAddOn.objects.create(
                booking=booking,
                addon=addon,
                quantity=1,
                unit_price=addon.price,
                total_price=addon.price,
            )

        # Create BookingFormResponse entries
        for key, value in form_responses.items():
            field = FormField.objects.get(service=service, key=key)
            BookingFormResponse.objects.create(
                booking=booking,
                form_field=field,
                value=value,
            )

        # Create initial status history
        BookingStatusHistory.objects.create(
            booking=booking,
            from_status="",
            to_status=Booking.Status.PENDING,
            changed_by=user,
            note="Booking created",
        )

        # Create worker offers for this booking
        offers = create_worker_offers_for_booking(booking)

        # Notify customer about offers
        if offers:
            Notification.objects.create(
                user=user,
                type=Notification.Type.BOOKING_CONFIRMED,
                title="Booking Request Submitted",
                body=f"Your booking for {service.title} has been submitted. We're finding a worker.",
                channel=Notification.Channel.IN_APP,
                data={"booking_id": booking.id, "offers_sent": len(offers)},
            )

        return booking


class BookingListSerializer(serializers.ModelSerializer):
    service_title = serializers.CharField(source="service.title", read_only=True)
    service_image = serializers.SerializerMethodField()
    variant_title = serializers.CharField(source="variant.title", read_only=True)
    address_label = serializers.CharField(source="address.label", read_only=True)
    address_full = serializers.CharField(source="address.full_address", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Booking
        fields = [
            "id", "service", "service_title", "service_image", "variant_title",
            "booking_mode", "scheduled_at", "status", "status_display",
            "address_label", "address_full", "pricing_snapshot", "created_at"
        ]

    def get_service_image(self, obj):
        if obj.service.image:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.service.image.url)
        return None


class BookingDetailSerializer(serializers.ModelSerializer):
    service_title = serializers.CharField(source="service.title", read_only=True)
    service_title_hi = serializers.CharField(source="service.title_hi", read_only=True)
    service_image = serializers.SerializerMethodField()
    variant_title = serializers.CharField(source="variant.title", read_only=True)
    variant_title_hi = serializers.CharField(source="variant.title_hi", read_only=True)
    address_detail = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    booking_mode_display = serializers.CharField(source="get_booking_mode_display", read_only=True)
    addons = BookingAddOnSerializer(many=True, read_only=True, source="booking_addons")
    form_responses = BookingFormResponseSerializer(many=True, read_only=True)
    status_history = BookingStatusHistorySerializer(many=True, read_only=True)
    assignment = BookingAssignmentSerializer(read_only=True)
    can_cancel = serializers.BooleanField(read_only=True)

    class Meta:
        model = Booking
        fields = [
            "id", "service", "service_title", "service_title_hi", "service_image",
            "variant", "variant_title", "variant_title_hi", "booking_mode", "booking_mode_display",
            "scheduled_at", "drop_scheduled_at", "status", "status_display",
            "address_detail", "pricing_snapshot", "notes", "worker_notes",
            "cancelled_at", "cancellation_reason", "completed_at",
            "addons", "form_responses", "status_history", "assignment", "can_cancel",
            "created_at", "updated_at"
        ]

    def get_service_image(self, obj):
        if obj.service.image:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.service.image.url)
        return None

    def get_address_detail(self, obj):
        addr = obj.address
        return {
            "id": addr.id,
            "label": addr.label,
            "house_details": addr.house_details,
            "landmark": addr.landmark,
            "full_address": addr.full_address,
            "latitude": str(addr.latitude) if addr.latitude else None,
            "longitude": str(addr.longitude) if addr.longitude else None,
        }


class BookingAvailabilitySerializer(serializers.Serializer):
    """Serializer for checking booking slot availability."""
    service = serializers.IntegerField()
    scheduled_at = serializers.DateTimeField()
    drop_scheduled_at = serializers.DateTimeField(required=False, allow_null=True)
    variant_id = serializers.IntegerField(required=False, allow_null=True, write_only=True)
    booking_mode = serializers.CharField(required=False, default="scheduled")
    audience = serializers.CharField(required=False, default="all")
    address_id = serializers.IntegerField(required=False, allow_null=True, write_only=True)

    def validate_scheduled_at(self, value):
        from django.utils import timezone
        if value <= timezone.now():
            raise serializers.ValidationError("Scheduled time must be in the future.")
        return value

    def validate(self, attrs):
        from apps.catalog.models import Service, ServiceVariant

        service = Service.objects.filter(pk=attrs.get("service")).first()
        if not service:
            raise serializers.ValidationError({"service": "Invalid service ID."})

        attrs["service_obj"] = service
        attrs["variant"] = ServiceVariant.objects.filter(pk=attrs.get("variant_id")).first() if attrs.get("variant_id") else None

        booking_mode = attrs.get("booking_mode", "scheduled")

        # Validate drop_scheduled_at is provided for pickup_drop mode
        if booking_mode == "pickup_drop" and not attrs.get("drop_scheduled_at"):
            raise serializers.ValidationError({"drop_scheduled_at": "Drop time is required for Pickup & Drop booking."})

        return attrs


class BookingCancelSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        booking = self.context["booking"]
        if not booking.can_cancel:
            raise serializers.ValidationError("This booking cannot be cancelled at its current status.")
        return attrs


class WorkerOfferSerializer(serializers.ModelSerializer):
    booking_status = serializers.CharField(source='booking.status', read_only=True)
    worker_name = serializers.CharField(source='worker.user.name', read_only=True)
    worker_phone = serializers.CharField(source='worker.user.phone', read_only=True)

    class Meta:
        model = __import__('apps.bookings.models', fromlist=['WorkerOffer']).WorkerOffer
        fields = [
            'id', 'booking', 'worker', 'status', 'expires_at', 'accepted_at',
            'responded_at', 'booking_status', 'worker_name', 'worker_phone',
        ]
