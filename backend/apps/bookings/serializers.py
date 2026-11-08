from rest_framework import serializers
from decimal import Decimal
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
from apps.catalog.form_rules import visible_form_fields
from apps.accounts.models import Address
from apps.workers.eligibility import required_worker_gender_for_booking
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
    category_answers = serializers.DictField(required=False, write_only=True)
    quantity = serializers.IntegerField(required=False, min_value=1, max_value=20, write_only=True, default=1)

    class Meta:
        model = Booking
        fields = [
            "id", "service", "variant", "booking_mode", "scheduled_at", "drop_scheduled_at",
            "address_id", "addon_ids", "form_responses", "category_answers", "quantity", "notes"
        ]
        read_only_fields = ["id"]

    def validate(self, attrs):
        service = attrs["service"]
        variant = attrs.get("variant")
        booking_mode = attrs.get("booking_mode", Booking.BookingMode.SCHEDULED)
        quantity = attrs.get("quantity", 1)
        scheduled_at = attrs.get("scheduled_at")
        drop_scheduled_at = attrs.get("drop_scheduled_at")
        address_id = attrs["address_id"]

        # Validate variant belongs to service
        if variant and variant.service != service:
            raise serializers.ValidationError({"variant": "Variant does not belong to this service."})
        category_answers = attrs.get("category_answers", {})
        try:
            required_gender = required_worker_gender_for_booking(service, category_answers)
        except ValueError as exc:
            raise serializers.ValidationError({"category_answers": str(exc)})
        if variant and isinstance(category_answers, dict):
            required_attributes = variant.attributes or {}
            if any(category_answers.get(key) != value for key, value in required_attributes.items()):
                raise serializers.ValidationError({
                    "variant": "This package does not match the selected service details."
                })

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
                duration_minutes=(duration or 60) * quantity,
                booking_mode=booking_mode,
                drop_scheduled_at=drop_scheduled_at,
            )
        except SlotConflictError as e:
            raise serializers.ValidationError({"detail": str(e)})

        # Validate address belongs to user and is active
        user = self.context["request"].user
        try:
            address = Address.objects.select_related("zone__city").get(
                pk=address_id, user=user, deleted_at__isnull=True
            )
            try:
                check_service_available(service=service, address=address, audience="all")
            except ServiceUnavailableError as e:
                raise serializers.ValidationError({"service": str(e)})
            attrs["_address"] = address
            if required_gender:
                from apps.bookings.services import has_eligible_worker_for_slot
                duration = variant.duration_minutes if variant else service.duration_minutes
                if not has_eligible_worker_for_slot(
                    service=service,
                    address=address,
                    scheduled_at=scheduled_at,
                    duration_minutes=(duration or 60) * quantity,
                    required_gender=required_gender,
                    drop_scheduled_at=drop_scheduled_at if booking_mode == Booking.BookingMode.PICKUP_DROP else None,
                    exclude_customer_id=user.id,
                ):
                    preference_can_change = (
                        category_answers.get("professional_preference") == "female"
                        and not service.requires_female_worker
                    )
                    message = (
                        "No female professional is available for this time slot. "
                        "Please choose another time or change the preference to No preference."
                        if preference_can_change
                        else "No female professional is available for this service at the selected time. Please choose another time."
                    )
                    raise serializers.ValidationError({"category_answers": message})
        except Address.DoesNotExist:
            raise serializers.ValidationError({"address_id": "Invalid address."})

        # Validate addons belong to service
        addon_ids = attrs.get("addon_ids", [])
        if addon_ids:
            valid_addon_ids = set(AddOn.objects.filter(service=service).values_list("id", flat=True))
            invalid = set(addon_ids) - valid_addon_ids
            if invalid:
                raise serializers.ValidationError({"addon_ids": f"Invalid addon IDs: {invalid}"})

        # Validate every active configured field, including required answers
        # omitted by the client. Never trust client-side form validation alone.
        form_responses = attrs.get("form_responses", {})
        service_fields = list(service.form_fields.filter(is_active=True))
        if not isinstance(form_responses, dict):
            raise serializers.ValidationError({"form_responses": "Answers must be an object."})
        field_map = {field.key: field for field in service_fields}
        if set(form_responses) - set(field_map):
            raise serializers.ValidationError({"form_responses": "Unknown form field supplied."})
        try:
            visible_fields = visible_form_fields(
                service_fields, category_answers=category_answers, form_answers=form_responses
            )
        except ValueError:
            raise serializers.ValidationError({
                "form_responses": "This service has an invalid question configuration. Please contact support."
            })
        visible_keys = {field.key for field in visible_fields}
        if set(form_responses) - visible_keys:
            raise serializers.ValidationError({
                "form_responses": "An answer was supplied for a question that is not applicable."
            })
        for field in visible_fields:
            value = form_responses.get(field.key)
            if field.is_required and value in (None, ""):
                raise serializers.ValidationError({
                    "form_responses": f"Field '{field.label}' is required."
                })
            if value in (None, ""):
                continue
            if field.field_type == FormField.FieldType.SELECT:
                allowed_values = set()
                for option in (field.options or []):
                    option_value = (
                        option.get("value", option.get("label"))
                        if isinstance(option, dict) else option
                    )
                    if option_value is not None:
                        allowed_values.add(str(option_value))
                if str(value) not in allowed_values:
                    raise serializers.ValidationError({
                        "form_responses": f"Choose a valid option for {field.label}."
                    })
            if field.field_type == FormField.FieldType.NUMBER:
                try:
                    Decimal(str(value))
                except (ArithmeticError, TypeError, ValueError):
                    raise serializers.ValidationError({
                        "form_responses": f"Enter a valid number for {field.label}."
                    })

        return attrs

    def create(self, validated_data):
        addon_ids = validated_data.pop("addon_ids", [])
        form_responses = validated_data.pop("form_responses", {})
        category_answers = validated_data.pop("category_answers", {})
        validated_data.pop("quantity", 1)
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
        validated_data["customer_answers"] = category_answers

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
            "addons", "form_responses", "customer_answers", "status_history", "assignment", "can_cancel",
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
    quantity = serializers.IntegerField(required=False, min_value=1, max_value=20, default=1)
    category_answers = serializers.DictField(required=False, default=dict)

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
        variant = ServiceVariant.objects.filter(pk=attrs.get("variant_id"), is_active=True).first() if attrs.get("variant_id") else None
        if attrs.get("variant_id") and (variant is None or variant.service_id != service.id):
            raise serializers.ValidationError({"variant_id": "Choose an active package for this service."})
        attrs["variant"] = variant

        booking_mode = attrs.get("booking_mode", "scheduled")
        if booking_mode != service.booking_mode:
            raise serializers.ValidationError({"booking_mode": "This service does not support the selected booking mode."})

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
    booking_status = serializers.CharField(source="booking.status", read_only=True)
    worker_name = serializers.CharField(source="worker.user.name", read_only=True)
    worker_phone = serializers.CharField(source="worker.user.phone", read_only=True)
    service_title = serializers.CharField(source="booking.service.title", read_only=True)
    variant_title = serializers.CharField(source="booking.variant.title", read_only=True, allow_null=True)
    scheduled_at = serializers.DateTimeField(source="booking.scheduled_at", read_only=True)
    service_address = serializers.CharField(source="booking.address.full_address", read_only=True)
    customer_answers = serializers.SerializerMethodField()
    professional_preference = serializers.SerializerMethodField()
    form_responses = BookingFormResponseSerializer(many=True, read_only=True, source="booking.form_responses")
    addons = BookingAddOnSerializer(many=True, read_only=True, source="booking.booking_addons")
    quantity = serializers.SerializerMethodField()
    offered_at = serializers.DateTimeField(read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    can_accept = serializers.SerializerMethodField()
    can_decline = serializers.SerializerMethodField()
    can_withdraw = serializers.SerializerMethodField()

    class Meta:
        model = __import__("apps.bookings.models", fromlist=["WorkerOffer"]).WorkerOffer
        fields = [
            "id", "booking", "worker", "status", "status_display",
            "offered_at", "expires_at", "accepted_at", "responded_at",
            "booking_status", "worker_name", "worker_phone", "service_title",
            "variant_title", "scheduled_at", "service_address", "customer_answers",
            "professional_preference", "form_responses", "addons", "quantity",
            "can_accept", "can_decline", "can_withdraw",
        ]
        read_only_fields = fields

    def get_customer_answers(self, obj):
        answers = dict(obj.booking.customer_answers or {})
        if obj.booking.service.requires_female_worker:
            answers["professional_preference"] = "female"
        return answers

    def get_professional_preference(self, obj):
        return (obj.booking.customer_answers or {}).get("professional_preference", "any")

    def get_quantity(self, obj):
        order_item = getattr(obj.booking, "order_item", None)
        return order_item.quantity if order_item else 1

    def get_can_accept(self, obj):
        from django.utils import timezone
        return (
            obj.status == obj.Status.PENDING
            and obj.expires_at > timezone.now()
            and obj.booking.status in ("pending", "confirmed")
            and obj.worker.status == "approved"
            and obj.worker.is_online
        )

    def get_can_decline(self, obj):
        return obj.status == obj.Status.PENDING

    def get_can_withdraw(self, obj):
        return obj.status in (obj.Status.PENDING, obj.Status.ACCEPTED)


from decimal import Decimal
from .models import CustomerCart, CartItem


class CartItemSerializer(serializers.ModelSerializer):
    service_title = serializers.CharField(source="service.title", read_only=True)
    variant_title = serializers.CharField(source="variant.title", read_only=True)
    booking_mode = serializers.CharField(source="service.booking_mode", read_only=True)
    line_total = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = [
            "id", "service", "service_title", "variant", "variant_title", "booking_mode",
            "quantity", "addon_selections", "form_answers", "category_answers", "notes",
            "pricing_snapshot", "line_total",
        ]
        read_only_fields = ["id", "service_title", "variant_title", "pricing_snapshot", "line_total"]

    def get_line_total(self, obj):
        return str(obj.line_total)

    def validate(self, attrs):
        instance = self.instance
        service = attrs.get("service", instance.service if instance else None)
        variant = attrs.get("variant", instance.variant if instance else None)
        quantity = attrs.get("quantity", instance.quantity if instance else 1)
        addons = attrs.get("addon_selections", instance.addon_selections if instance else [])
        answers = attrs.get("form_answers", instance.form_answers if instance else {})
        category_answers = attrs.get("category_answers", instance.category_answers if instance else {})

        try:
            required_worker_gender_for_booking(service, category_answers)
        except ValueError as exc:
            raise serializers.ValidationError({"category_answers": str(exc)})

        if quantity < 1 or quantity > 20:
            raise serializers.ValidationError({"quantity": "Quantity must be between 1 and 20."})
        if not service.is_active:
            raise serializers.ValidationError({"service": "This service is not available."})
        if not isinstance(addons, list) or not isinstance(answers, dict) or not isinstance(category_answers, dict):
            raise serializers.ValidationError("Add-ons must be a list and answers must be objects.")
        if variant and (variant.service_id != service.id or not variant.is_active):
            raise serializers.ValidationError({"variant": "Choose an active package for this service."})
        if variant and any(
            category_answers.get(key) != value
            for key, value in (variant.attributes or {}).items()
        ):
            raise serializers.ValidationError({"variant": "This package does not match the selected service details."})

        addon_ids = []
        for row in addons:
            if not isinstance(row, dict) or "id" not in row:
                raise serializers.ValidationError({"addon_selections": "Each add-on needs an id."})
            addon_ids.append(row["id"])
        if len(addon_ids) != len(set(addon_ids)):
            raise serializers.ValidationError({"addon_selections": "Duplicate add-ons are not allowed."})
        addon_map = {
            obj.id: obj for obj in AddOn.objects.filter(
                service=service, is_active=True, id__in=addon_ids
            )
        }
        if set(addon_ids) != set(addon_map):
            raise serializers.ValidationError({"addon_selections": "An add-on does not belong to this service."})

        service_fields = list(service.form_fields.filter(is_active=True))
        field_map = {obj.key: obj for obj in service_fields}
        if set(answers) - set(field_map):
            raise serializers.ValidationError({"form_answers": "An unknown question was supplied."})
        try:
            visible_fields = visible_form_fields(
                service_fields, category_answers=category_answers, form_answers=answers
            )
        except ValueError:
            raise serializers.ValidationError({
                "form_answers": "This service has an invalid question configuration. Please contact support."
            })
        visible_keys = {field.key for field in visible_fields}
        if set(answers) - visible_keys:
            raise serializers.ValidationError({
                "form_answers": "An answer was supplied for a question that is not applicable."
            })
        for field in visible_fields:
            value = answers.get(field.key)
            if field.is_required and value in (None, ""):
                raise serializers.ValidationError({"form_answers": f"{field.label} is required."})
            if value in (None, ""):
                continue

            # Choice answers must match the live catalogue options. Accept both
            # legacy string options and structured {label, value} options.
            if field.field_type in ("select", "choice"):
                allowed_values = set()
                for option in (field.options or []):
                    if isinstance(option, dict):
                        option_value = option.get("value", option.get("label"))
                    else:
                        option_value = option
                    if option_value is not None:
                        allowed_values.add(str(option_value))
                if str(value) not in allowed_values:
                    raise serializers.ValidationError({
                        "form_answers": f"Choose a valid option for {field.label}."
                    })

            if field.field_type == "number":
                try:
                    Decimal(str(value))
                except (ArithmeticError, TypeError, ValueError):
                    raise serializers.ValidationError({
                        "form_answers": f"Enter a valid number for {field.label}."
                    })

        if variant:
            base = Decimal(variant.price)
            base_title = variant.title
        elif service.variants.filter(is_active=True).exists():
            raise serializers.ValidationError({"variant": "Please select a package."})
        else:
            base = Decimal(service.visit_fee)
            base_title = service.title

        addon_rows = []
        addon_total = Decimal("0")
        for row in addons:
            addon = addon_map[row["id"]]
            count = int(row.get("quantity", 1))
            if count < 1 or count > 20:
                raise serializers.ValidationError({"addon_selections": "Add-on quantity must be 1–20."})
            total = Decimal(addon.price) * count
            addon_total += total
            addon_rows.append({
                "id": addon.id, "title": addon.title,
                "unit_price": str(addon.price), "quantity": count, "total": str(total),
            })

        attrs["_cart_snapshot"] = {
            "base_title": base_title,
            "base_price": str(base),
            "addons": addon_rows,
            "addons_total": str(addon_total),
            "unit_total": str(base + addon_total),
            "line_total": str((base + addon_total) * quantity),
        }
        return attrs

    def create(self, validated_data):
        snapshot = validated_data.pop("_cart_snapshot")
        return CartItem.objects.create(pricing_snapshot=snapshot, **validated_data)

    def update(self, instance, validated_data):
        snapshot = validated_data.pop("_cart_snapshot")
        for key, value in validated_data.items():
            setattr(instance, key, value)
        instance.pricing_snapshot = snapshot
        instance.save()
        return instance


class CustomerCartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    subtotal = serializers.SerializerMethodField()
    item_count = serializers.SerializerMethodField()

    class Meta:
        model = CustomerCart
        fields = ["id", "address", "items", "item_count", "subtotal", "updated_at"]
        read_only_fields = fields

    def get_subtotal(self, obj):
        return str(obj.subtotal)

    def get_item_count(self, obj):
        return sum(item.quantity for item in obj.items.all())
