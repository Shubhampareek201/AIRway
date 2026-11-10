from django.test import TestCase
from decimal import Decimal
from django.utils import timezone
from rest_framework.test import APIClient
from django.db import IntegrityError
from datetime import timedelta, time, datetime
import pytz
import datetime as dt_module

from apps.accounts.models import User, Address
from apps.catalog.models import Category, Service, ServiceVariant, AddOn, FormField, CityService
from apps.core.models import City, Zone
from apps.workers.models import (
    WorkerProfile,
    WorkerService,
    WorkerZone,
    WorkerSchedule,
)
from apps.bookings.models import Booking, WorkerOffer, BookingAssignment, CustomerCart, CartItem, Order, OrderItem
from apps.availability.models import WorkerBlockedSlot
from apps.notifications.models import Notification


class BookingAPITestMixin:
    """Mixin to set up common test data for booking tests."""

    def _create_user(self, phone="+919876543210"):
        return User.objects.create_user(phone=phone, password="password123")

    def _create_category(self, title="Cleaning", slug="cleaning"):
        return Category.objects.create(title=title, slug="cleaning")

    def _create_service(self, category, title="Home Cleaning"):
        service = Service.objects.create(
            category=category,
            title=title,
            booking_mode=Service.BookingMode.SCHEDULED,
            pricing_type=Service.PricingType.FIXED,
            is_active=True,
        )
        # Support both fixture creation orders: service-before-address and
        # address-before-service.
        for city in City.objects.all():
            CityService.objects.get_or_create(
                city=city,
                service=service,
                defaults={"is_active": True},
            )
        return service

    def _create_variant(self, service, title="Premium", price=500, mrp=600, duration_minutes=60):
        return ServiceVariant.objects.create(
            service=service,
            title=title,
            price=price,
            mrp=mrp,
            duration_minutes=duration_minutes,
        )

    def _create_address(self, user, label="home"):
        # Create zone hierarchy
        city, _ = City.objects.get_or_create(name="Mumbai", defaults={"state": "Maharashtra"})
        zone, _ = Zone.objects.get_or_create(name="Dadar", defaults={"city": city, "is_active": True})

        address = Address.objects.create(
            user=user,
            label=label,
            house_details="Floor 2, Apt 301",
            landmark="Near XYZ Mall",
            full_address="123 Main Street, Near XYZ Mall, Mumbai 400001",
            latitude=19.0760,
            longitude=72.8777,
            zone=zone,
        )

        # Make fixture services available in the address city, as required
        # by the production serviceability validation.
        for service in Service.objects.filter(is_active=True):
            CityService.objects.get_or_create(
                city=city,
                service=service,
                defaults={"is_active": True},
            )
        return address


class BookingCreateTest(BookingAPITestMixin, TestCase):
    """Test booking creation endpoint."""

    def setUp(self):
        self.client = APIClient()
        self.user = self._create_user()
        self.client.force_authenticate(user=self.user)

        self.category = Category.objects.create(title="Cleaning", slug="cleaning")
        self.service = self._create_service(self.category)
        self.variant = self._create_variant(self.service)
        self.address = self._create_address(self.user)

    def test_booking_api_rejects_service_outside_selected_beauty_audience(self):
        beauty = Category.objects.create(title="Beauty", slug="beauty")
        hair = Category.objects.create(
            title="Hair Services", slug="hair-services", parent=beauty
        )
        service = self._create_service(hair, title="Men's Haircut")
        service.audience = "men"
        service.save(update_fields=["audience"])
        variant = self._create_variant(service)

        response = self.client.post("/api/v1/bookings/", {
            "service": service.id,
            "variant": variant.id,
            "booking_mode": "scheduled",
            "scheduled_at": (timezone.now() + timedelta(days=2)).isoformat(),
            "address_id": self.address.id,
            "category_answers": {"beauty_audience": "women"},
        }, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("not listed for the selected Beauty audience", str(response.data))

    def test_dispatcher_only_returns_female_workers_when_preferred(self):
        beauty = Category.objects.create(title="Beauty", slug="beauty-root")
        service = self._create_service(beauty, title="Facial")
        zone = self.address.zone
        local_start = timezone.localtime(timezone.now() + timedelta(days=2)).replace(
            hour=12, minute=0, second=0, microsecond=0
        )
        female_user = self._create_user("+919876543221")
        male_user = self._create_user("+919876543222")
        female = WorkerProfile.objects.create(
            user=female_user, status=WorkerProfile.Status.APPROVED,
            gender=WorkerProfile.Gender.FEMALE, is_online=True,
        )
        male = WorkerProfile.objects.create(
            user=male_user, status=WorkerProfile.Status.APPROVED,
            gender=WorkerProfile.Gender.MALE, is_online=True,
        )
        for worker in (female, male):
            WorkerService.objects.create(worker=worker, service=service)
            WorkerZone.objects.create(worker=worker, zone=zone)
            WorkerSchedule.objects.create(
                worker=worker,
                weekday=local_start.weekday(),
                start_time=time(0, 0),
                end_time=time(23, 59),
                is_active=True,
            )

        from apps.bookings.dispatcher import DispatcherService
        eligible = DispatcherService._get_eligible_workers(
            service=service,
            zone=zone,
            scheduled_at=local_start,
            duration_minutes=60,
            exclude_customer_id=self.user.id,
            required_gender=WorkerProfile.Gender.FEMALE,
        )
        self.assertEqual(list(eligible.values_list("id", flat=True)), [female.id])

        variant = self._create_variant(service)
        response = self.client.post("/api/v1/bookings/", {
            "service": service.id,
            "variant": variant.id,
            "booking_mode": "scheduled",
            "scheduled_at": local_start.isoformat(),
            "address_id": self.address.id,
            "category_answers": {"professional_preference": "female"},
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        booking = Booking.objects.get(pk=response.data["id"])
        offers = list(WorkerOffer.objects.filter(booking=booking))
        self.assertEqual([offer.worker_id for offer in offers], [female.id])
        from apps.bookings.serializers import WorkerOfferSerializer
        offer_data = WorkerOfferSerializer(offers[0]).data
        self.assertEqual(offer_data["professional_preference"], "female")
        self.assertEqual(
            offer_data["customer_answers"]["professional_preference"], "female"
        )

    def test_beauty_booking_rejects_preference_when_no_female_worker_is_available(self):
        beauty = Category.objects.create(title="Beauty", slug="beauty-root")
        service = self._create_service(beauty, title="Facial")
        variant = self._create_variant(service)
        response = self.client.post("/api/v1/bookings/", {
            "service": service.id,
            "variant": variant.id,
            "booking_mode": "scheduled",
            "scheduled_at": (timezone.now() + timezone.timedelta(days=1, hours=2)).isoformat(),
            "address_id": self.address.id,
            "category_answers": {"professional_preference": "female"},
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("category_answers", response.data)
        self.assertIn("No female professional", str(response.data))

    def test_beauty_slot_availability_reports_female_worker_unavailable(self):
        beauty = Category.objects.create(title="Beauty", slug="beauty-root")
        service = self._create_service(beauty, title="Facial")
        variant = self._create_variant(service)
        response = self.client.post("/api/v1/bookings/check_availability/", {
            "service": service.id,
            "variant_id": variant.id,
            "booking_mode": "scheduled",
            "scheduled_at": (timezone.now() + timezone.timedelta(days=1, hours=2)).isoformat(),
            "address_id": self.address.id,
            "category_answers": {"professional_preference": "female"},
        }, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["available"])
        self.assertEqual(response.data["reason"], "female_professional_unavailable")

    def test_non_beauty_booking_rejects_female_professional_preference(self):
        response = self.client.post("/api/v1/bookings/", {
            "service": self.service.id,
            "variant": self.variant.id,
            "booking_mode": "scheduled",
            "scheduled_at": (timezone.now() + timezone.timedelta(days=1, hours=2)).isoformat(),
            "address_id": self.address.id,
            "category_answers": {"professional_preference": "female"},
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("category_answers", response.data)

    def test_beauty_booking_defaults_to_no_professional_preference(self):
        beauty = Category.objects.create(title="Beauty", slug="beauty-root")
        service = self._create_service(beauty, title="Facial")
        variant = self._create_variant(service)
        response = self.client.post("/api/v1/bookings/", {
            "service": service.id,
            "variant": variant.id,
            "booking_mode": "scheduled",
            "scheduled_at": (timezone.now() + timezone.timedelta(days=1, hours=2)).isoformat(),
            "address_id": self.address.id,
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["customer_answers"].get("professional_preference", "any"), "any")

    def test_create_booking_with_minimal_data(self):
        """Should create booking with required fields only."""
        future_time = timezone.now() + timezone.timedelta(days=1, hours=2)

        response = self.client.post("/api/v1/bookings/", {
            "service": self.service.id,
            "variant": self.variant.id,
            "booking_mode": "scheduled",
            "scheduled_at": future_time.isoformat(),
            "address_id": self.address.id,
        }, format="json")

        self.assertEqual(response.status_code, 201)
        self.assertIn("id", response.data)
        self.assertEqual(response.data["service"], self.service.id)
        self.assertEqual(response.data["status"], "pending")

    def test_create_booking_preserves_quantity_in_price_snapshot(self):
        response = self.client.post("/api/v1/bookings/", {
            "service": self.service.id,
            "variant": self.variant.id,
            "booking_mode": "scheduled",
            "scheduled_at": (timezone.now() + timezone.timedelta(days=1, hours=2)).isoformat(),
            "address_id": self.address.id,
            "quantity": 2,
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["pricing_snapshot"]["quantity"], 2)
        self.assertEqual(response.data["pricing_snapshot"]["subtotal"], "1000.00")
        self.assertEqual(response.data["pricing_snapshot"]["total"], "1180.0000")

    def test_create_booking_with_addons(self):
        """Should create booking with add-ons and calculate pricing."""
        addon = AddOn.objects.create(
            service=self.service,
            title="Deep Clean",
            price=200,
            mrp=250,
        )
        future_time = timezone.now() + timezone.timedelta(days=1, hours=2)

        response = self.client.post("/api/v1/bookings/", {
            "service": self.service.id,
            "variant": self.variant.id,
            "booking_mode": "scheduled",
            "scheduled_at": future_time.isoformat(),
            "address_id": self.address.id,
            "addon_ids": [addon.id],
        }, format="json")

        self.assertEqual(response.status_code, 201)
        self.assertIn("addons", response.data)
        self.assertEqual(len(response.data["addons"]), 1)
        self.assertEqual(response.data["addons"][0]["addon_title"], "Deep Clean")

    def test_create_booking_with_form_responses(self):
        """Should create booking with form field responses."""
        form_field = FormField.objects.create(
            service=self.service,
            key="car_type",
            label="Car Type",
            field_type="select",
            options=["Sedan", "SUV", "Hatchback"],
            is_required=True,
        )

        future_time = timezone.now() + timezone.timedelta(days=1, hours=2)

        response = self.client.post("/api/v1/bookings/", {
            "service": self.service.id,
            "variant": self.variant.id,
            "booking_mode": "scheduled",
            "scheduled_at": future_time.isoformat(),
            "address_id": self.address.id,
            "form_responses": {"car_type": "SUV"},
        }, format="json")

        self.assertEqual(response.status_code, 201)
        self.assertIn("form_responses", response.data)

    def test_create_booking_rejects_omitted_required_form_answer(self):
        """A required active question cannot be bypassed by omitting its key."""
        FormField.objects.create(
            service=self.service,
            key="property_type",
            label="Property type",
            field_type="select",
            options=["Apartment", "Villa"],
            is_required=True,
        )
        response = self.client.post("/api/v1/bookings/", {
            "service": self.service.id,
            "variant": self.variant.id,
            "booking_mode": "scheduled",
            "scheduled_at": (timezone.now() + timezone.timedelta(days=1, hours=2)).isoformat(),
            "address_id": self.address.id,
            "form_responses": {},
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("form_responses", response.data)

    def test_create_booking_rejects_choice_outside_catalogue(self):
        """Choice answers must be one of the options configured for the service."""
        FormField.objects.create(
            service=self.service,
            key="car_type",
            label="Car Type",
            field_type="select",
            options=["Sedan", "SUV", "Hatchback"],
            is_required=True,
        )
        response = self.client.post("/api/v1/bookings/", {
            "service": self.service.id,
            "variant": self.variant.id,
            "booking_mode": "scheduled",
            "scheduled_at": (timezone.now() + timezone.timedelta(days=1, hours=2)).isoformat(),
            "address_id": self.address.id,
            "form_responses": {"car_type": "Truck"},
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("form_responses", response.data)

    def test_create_booking_rejects_invalid_numeric_answer(self):
        """Numeric form fields must reject non-numeric values."""
        FormField.objects.create(
            service=self.service,
            key="room_count",
            label="Room count",
            field_type="number",
            is_required=True,
        )
        response = self.client.post("/api/v1/bookings/", {
            "service": self.service.id,
            "variant": self.variant.id,
            "booking_mode": "scheduled",
            "scheduled_at": (timezone.now() + timezone.timedelta(days=1, hours=2)).isoformat(),
            "address_id": self.address.id,
            "form_responses": {"room_count": "many"},
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("form_responses", response.data)

    def test_create_booking_does_not_require_hidden_conditional_answer(self):
        FormField.objects.create(
            service=self.service, key="vehicle_type", label="Vehicle type",
            field_type="select", options=["Sedan", "SUV"], is_required=True,
        )
        FormField.objects.create(
            service=self.service, key="seat_count", label="Seat count",
            field_type="number", is_required=True,
            visibility_rules=[{
                "field": "vehicle_type", "operator": "equals", "value": "SUV",
            }],
        )
        response = self.client.post("/api/v1/bookings/", {
            "service": self.service.id,
            "variant": self.variant.id,
            "booking_mode": "scheduled",
            "scheduled_at": (timezone.now() + timezone.timedelta(days=1, hours=2)).isoformat(),
            "address_id": self.address.id,
            "form_responses": {"vehicle_type": "Sedan"},
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)

    def test_create_booking_requires_visible_conditional_answer(self):
        FormField.objects.create(
            service=self.service, key="vehicle_type", label="Vehicle type",
            field_type="select", options=["Sedan", "SUV"], is_required=True,
        )
        FormField.objects.create(
            service=self.service, key="seat_count", label="Seat count",
            field_type="number", is_required=True,
            visibility_rules=[{
                "field": "vehicle_type", "operator": "equals", "value": "SUV",
            }],
        )
        response = self.client.post("/api/v1/bookings/", {
            "service": self.service.id,
            "variant": self.variant.id,
            "booking_mode": "scheduled",
            "scheduled_at": (timezone.now() + timezone.timedelta(days=1, hours=2)).isoformat(),
            "address_id": self.address.id,
            "form_responses": {"vehicle_type": "SUV"},
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("form_responses", response.data)

    def test_create_booking_rejects_answer_for_hidden_conditional_question(self):
        FormField.objects.create(
            service=self.service, key="vehicle_type", label="Vehicle type",
            field_type="select", options=["Sedan", "SUV"], is_required=True,
        )
        FormField.objects.create(
            service=self.service, key="seat_count", label="Seat count",
            field_type="number", is_required=False,
            visibility_rules=[{
                "field": "vehicle_type", "operator": "equals", "value": "SUV",
            }],
        )
        response = self.client.post("/api/v1/bookings/", {
            "service": self.service.id,
            "variant": self.variant.id,
            "booking_mode": "scheduled",
            "scheduled_at": (timezone.now() + timezone.timedelta(days=1, hours=2)).isoformat(),
            "address_id": self.address.id,
            "form_responses": {"vehicle_type": "Sedan", "seat_count": "5"},
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("form_responses", response.data)

    def test_create_booking_fails_closed_for_invalid_visibility_configuration(self):
        FormField.objects.create(
            service=self.service, key="special_detail", label="Special detail",
            field_type="text", is_required=True,
            visibility_rules=[{
                "field": "vehicle_type", "operator": "unsupported", "value": "SUV",
            }],
        )
        response = self.client.post("/api/v1/bookings/", {
            "service": self.service.id,
            "variant": self.variant.id,
            "booking_mode": "scheduled",
            "scheduled_at": (timezone.now() + timezone.timedelta(days=1, hours=2)).isoformat(),
            "address_id": self.address.id,
            "form_responses": {},
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("form_responses", response.data)

    def test_create_booking_fails_with_past_date(self):
        """Should reject booking with past scheduled time."""
        past_time = timezone.now() - timezone.timedelta(hours=1)

        response = self.client.post("/api/v1/bookings/", {
            "service": self.service.id,
            "variant": self.variant.id,
            "booking_mode": "scheduled",
            "scheduled_at": past_time.isoformat(),
            "address_id": self.address.id,
        }, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("scheduled_at", response.data)

    def test_create_booking_fails_with_invalid_address(self):
        """Should reject booking with address not belonging to user."""
        other_user = self._create_user("+919876543211")
        other_address = self._create_address(other_user)
        future_time = timezone.now() + timezone.timedelta(days=1, hours=2)

        response = self.client.post("/api/v1/bookings/", {
            "service": self.service.id,
            "variant": self.variant.id,
            "booking_mode": "scheduled",
            "scheduled_at": future_time.isoformat(),
            "address_id": other_address.id,
        }, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("address_id", response.data)

    def test_create_booking_fails_with_invalid_variant(self):
        """Should reject booking where variant belongs to different service."""
        other_service = self._create_service(Category.objects.create(title="Beauty", slug="beauty"))
        other_variant = self._create_variant(other_service, title="Manicure")
        future_time = timezone.now() + timezone.timedelta(days=1, hours=2)

        response = self.client.post("/api/v1/bookings/", {
            "service": self.service.id,
            "variant": other_variant.id,
            "booking_mode": "scheduled",
            "scheduled_at": future_time.isoformat(),
            "address_id": self.address.id,
        }, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("variant", response.data)

    def test_create_booking_pickup_drop_requires_drop_time(self):
        """Should require drop_scheduled_at for pickup_drop mode."""
        # Create a service that supports pickup_drop mode
        pickup_drop_service = Service.objects.create(
            category=self.category,
            title="Pickup Drop Service",
            booking_mode=Service.BookingMode.PICKUP_DROP,
            pricing_type=Service.PricingType.FIXED,
            is_active=True,
        )
        pickup_drop_variant = ServiceVariant.objects.create(
            service=pickup_drop_service,
            title="Basic",
            price=300,
            mrp=400,
        )

        future_time = timezone.now() + timezone.timedelta(hours=1)

        response = self.client.post("/api/v1/bookings/", {
            "service": pickup_drop_service.id,
            "variant": pickup_drop_variant.id,
            "booking_mode": "pickup_drop",
            "scheduled_at": future_time.isoformat(),
            "address_id": self.address.id,
        }, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("drop_scheduled_at", response.data)


class BookingListTest(BookingAPITestMixin, TestCase):
    """Test booking list endpoint."""

    def setUp(self):
        self.client = APIClient()
        self.user = self._create_user()
        self.client.force_authenticate(user=self.user)

        self.category = Category.objects.create(title="Cleaning", slug="cleaning")
        self.service = self._create_service(self.category)
        self.variant = self._create_variant(self.service)
        self.address = self._create_address(self.user)

    def test_list_user_bookings(self):
        """Should return only authenticated user's bookings."""
        future_time = timezone.now() + timezone.timedelta(days=1, hours=2)

        self.client.post("/api/v1/bookings/", {
            "service": self.service.id,
            "variant": self.variant.id,
            "booking_mode": "scheduled",
            "scheduled_at": future_time.isoformat(),
            "address_id": self.address.id,
        }, format="json")

        response = self.client.get("/api/v1/bookings/")
        self.assertEqual(response.status_code, 200)
        results = response.data if isinstance(response.data, list) else response.data.get("results", [])
        self.assertEqual(len(results), 1)

    def test_list_bookings_filter_by_status(self):
        """Should filter bookings by status."""
        future_time = timezone.now() + timezone.timedelta(days=1, hours=2)

        self.client.post("/api/v1/bookings/", {
            "service": self.service.id,
            "variant": self.variant.id,
            "booking_mode": "scheduled",
            "scheduled_at": future_time.isoformat(),
            "address_id": self.address.id,
        }, format="json")

        response = self.client.get("/api/v1/bookings/?status=pending")
        self.assertEqual(response.status_code, 200)


class BookingCancelTest(BookingAPITestMixin, TestCase):
    """Test booking cancellation endpoint."""

    def setUp(self):
        self.client = APIClient()
        self.user = self._create_user()
        self.client.force_authenticate(user=self.user)

        self.category = Category.objects.create(title="Cleaning", slug="cleaning")
        self.service = self._create_service(self.category)
        self.variant = self._create_variant(self.service)
        self.address = self._create_address(self.user)
        self.future_time = timezone.now() + timezone.timedelta(days=1, hours=2)

    def test_cancel_pending_booking(self):
        """Should cancel a pending booking."""
        create_resp = self.client.post("/api/v1/bookings/", {
            "service": self.service.id,
            "variant": self.variant.id,
            "booking_mode": "scheduled",
            "scheduled_at": self.future_time.isoformat(),
            "address_id": self.address.id,
        }, format="json")

        booking_id = create_resp.data["id"]

        response = self.client.post(f"/api/v1/bookings/{booking_id}/cancel/", {
            "reason": "Customer requested cancellation"
        }, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "cancelled")

    def test_cancel_confirmed_booking_allowed(self):
        """Should allow cancelling confirmed bookings."""
        create_resp = self.client.post("/api/v1/bookings/", {
            "service": self.service.id,
            "variant": self.variant.id,
            "booking_mode": "scheduled",
            "scheduled_at": self.future_time.isoformat(),
            "address_id": self.address.id,
        }, format="json")

        from apps.bookings.models import Booking
        booking = Booking.objects.get(id=create_resp.data["id"])
        booking.status = Booking.Status.CONFIRMED
        booking.save()

        response = self.client.post(f"/api/v1/bookings/{booking.id}/cancel/", {
            "reason": "Customer request"
        }, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "cancelled")

    def test_cannot_cancel_completed_booking(self):
        """Should not allow cancelling completed bookings."""
        create_resp = self.client.post("/api/v1/bookings/", {
            "service": self.service.id,
            "variant": self.variant.id,
            "booking_mode": "scheduled",
            "scheduled_at": self.future_time.isoformat(),
            "address_id": self.address.id,
        }, format="json")

        from apps.bookings.models import Booking
        booking = Booking.objects.get(id=create_resp.data["id"])
        booking.status = Booking.Status.COMPLETED
        booking.save()

        response = self.client.post(f"/api/v1/bookings/{booking.id}/cancel/", {
            "reason": "Cannot cancel"
        }, format="json")

        self.assertEqual(response.status_code, 400)


class SplitPaymentCancellationPolicyAPITests(BookingAPITestMixin, TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = self._create_user()
        self.client.force_authenticate(user=self.user)
        self.category = Category.objects.create(title="Cleaning", slug="cleaning")
        self.service = self._create_service(self.category)
        self.variant = self._create_variant(self.service)
        self.address = self._create_address(self.user)

    def _freeze_same_day_clock(self):
        from unittest.mock import patch
        from zoneinfo import ZoneInfo

        local_now = timezone.now().astimezone(ZoneInfo("Asia/Kolkata"))
        frozen_now = local_now.replace(
            hour=10, minute=0, second=0, microsecond=0,
        )
        return patch("django.utils.timezone.now", return_value=frozen_now), frozen_now

    def _create_paid_booking(self, scheduled_at, *, accepted=False):
        response = self.client.post("/api/v1/bookings/checkout/", {
            "service": self.service.id,
            "variant": self.variant.id,
            "booking_mode": "scheduled",
            "scheduled_at": scheduled_at.isoformat(),
            "address_id": self.address.id,
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)

        from apps.payments.models import Payment, BookingFinancialPlan
        booking = Booking.objects.get(pk=response.data["id"])
        plan = BookingFinancialPlan.objects.get(booking=booking)
        payment = Payment.objects.create(
            booking=booking,
            customer=self.user,
            amount=plan.advance_due,
            method=Payment.Method.RAZORPAY,
            status=Payment.Status.PAID,
            razorpay_payment_id="pay_same_day_test",
        )
        if accepted:
            worker_user = self._create_user("+919876543299")
            worker = WorkerProfile.objects.create(
                user=worker_user,
                status=WorkerProfile.Status.APPROVED,
                is_online=True,
            )
            BookingAssignment.objects.create(
                booking=booking, worker=worker, accepted_at=timezone.now(),
            )
            booking.status = Booking.Status.ASSIGNED
            booking.save(update_fields=["status", "updated_at"])
        return booking, plan, payment

    def test_same_day_cancel_before_worker_acceptance_refunds_full_advance(self):
        from unittest.mock import patch
        from apps.payments.models import RefundRecord

        clock, frozen_now = self._freeze_same_day_clock()
        with clock:
            scheduled_at = frozen_now + timedelta(hours=2)
            booking, plan, payment = self._create_paid_booking(scheduled_at)
            detail = self.client.get(f"/api/v1/bookings/{booking.pk}/")
            self.assertEqual(detail.status_code, 200, detail.data)
            self.assertTrue(detail.data["can_cancel"])
            self.assertEqual(
                detail.data["cancellation_terms"]["policy"],
                "same_day_before_worker_acceptance",
            )
            self.assertEqual(
                Decimal(detail.data["cancellation_terms"]["refund_amount"]),
                plan.advance_due,
            )
            with patch("razorpay.Client") as client_class:
                client_class.return_value.payment.refund.return_value = {
                    "id": "rfnd_same_day_full",
                    "status": "pending",
                }
                response = self.client.post(
                    f"/api/v1/bookings/{booking.pk}/cancel/",
                    {"reason": "Changed my plan"},
                    format="json",
                )

            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual(response.data["refund_policy"], "same_day_before_worker_acceptance")
            self.assertEqual(Decimal(response.data["refund_amount"]), plan.advance_due)
            refund = RefundRecord.objects.get(booking=booking)
            self.assertEqual(refund.payment_id, payment.pk)
            self.assertEqual(refund.refund_amount, plan.advance_due)
            self.assertEqual(refund.status, RefundRecord.Status.PENDING)

    def test_same_day_cancel_after_worker_acceptance_is_non_refundable(self):
        from apps.payments.models import RefundRecord

        clock, frozen_now = self._freeze_same_day_clock()
        with clock:
            scheduled_at = frozen_now + timedelta(hours=2)
            booking, plan, payment = self._create_paid_booking(
                scheduled_at, accepted=True,
            )
            detail = self.client.get(f"/api/v1/bookings/{booking.pk}/")
            self.assertEqual(detail.status_code, 200, detail.data)
            self.assertTrue(detail.data["can_cancel"])
            self.assertFalse(detail.data["cancellation_terms"]["refundable"])
            self.assertTrue(detail.data["cancellation_terms"]["worker_accepted"])
            self.assertIn("non-refundable", detail.data["cancellation_terms"]["message"])
            response = self.client.post(
                f"/api/v1/bookings/{booking.pk}/cancel/",
                {"reason": "Changed my plan"},
                format="json",
            )

            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual(response.data["refund_policy"], "same_day_after_worker_acceptance")
            self.assertEqual(Decimal(response.data["refund_amount"]), Decimal("0.00"))
            self.assertEqual(response.data["refund_status"], "not_refundable")
            self.assertFalse(RefundRecord.objects.filter(booking=booking).exists())


class BookingTrackTest(BookingAPITestMixin, TestCase):
    """Test booking tracking endpoint."""

    def setUp(self):
        self.client = APIClient()
        self.user = self._create_user()
        self.client.force_authenticate(user=self.user)

        self.category = Category.objects.create(title="Cleaning", slug="cleaning")
        self.service = self._create_service(self.category)
        self.variant = self._create_variant(self.service)
        self.address = self._create_address(self.user)

    def test_track_unassigned_booking(self):
        """Should indicate no worker assigned for unassigned booking."""
        future_time = timezone.now() + timezone.timedelta(days=1, hours=2)

        create_resp = self.client.post("/api/v1/bookings/", {
            "service": self.service.id,
            "variant": self.variant.id,
            "booking_mode": "scheduled",
            "scheduled_at": future_time.isoformat(),
            "address_id": self.address.id,
        }, format="json")

        booking_id = create_resp.data["id"]

        response = self.client.get(f"/api/v1/bookings/{booking_id}/track/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["is_assigned"], False)


class BookingDetailTest(BookingAPITestMixin, TestCase):
    """Test booking detail endpoint."""

    def setUp(self):
        self.client = APIClient()
        self.user = self._create_user()
        self.client.force_authenticate(user=self.user)

        self.category = Category.objects.create(title="Cleaning", slug="cleaning")
        self.service = self._create_service(self.category)
        self.variant = self._create_variant(self.service)
        self.address = self._create_address(self.user)

    def test_booking_detail_includes_pricing_snapshot(self):
        """Should include pricing snapshot in detail response."""
        future_time = timezone.now() + timezone.timedelta(days=1, hours=2)

        create_resp = self.client.post("/api/v1/bookings/", {
            "service": self.service.id,
            "variant": self.variant.id,
            "booking_mode": "scheduled",
            "scheduled_at": future_time.isoformat(),
            "address_id": self.address.id,
        }, format="json")

        booking_id = create_resp.data["id"]
        response = self.client.get(f"/api/v1/bookings/{booking_id}/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("pricing_snapshot", response.data)
        self.assertIn("total", response.data["pricing_snapshot"])

    def test_booking_detail_includes_addons(self):
        """Should include addons in detail response."""
        addon = AddOn.objects.create(
            service=self.service,
            title="Deep Clean",
            price=200,
            mrp=250,
        )

        future_time = timezone.now() + timezone.timedelta(days=1, hours=2)

        create_resp = self.client.post("/api/v1/bookings/", {
            "service": self.service.id,
            "variant": self.variant.id,
            "booking_mode": "scheduled",
            "scheduled_at": future_time.isoformat(),
            "address_id": self.address.id,
            "addon_ids": [addon.id],
        }, format="json")

        booking_id = create_resp.data["id"]
        response = self.client.get(f"/api/v1/bookings/{booking_id}/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("addons", response.data)
        self.assertEqual(len(response.data["addons"]), 1)


class BookingAvailabilityTest(BookingAPITestMixin, TestCase):
    """Test slot availability checking."""

    def setUp(self):
        from apps.workers.models import WorkerProfile, WorkerService, WorkerZone, WorkerSchedule

        self.client = APIClient()
        self.user = self._create_user()
        self.client.force_authenticate(user=self.user)

        self.category = Category.objects.create(title="Cleaning", slug="cleaning")
        self.service = self._create_service(self.category)
        self.variant = self._create_variant(self.service, duration_minutes=60)
        self.address = self._create_address(self.user)

        # Create a worker for this service
        worker_user = User.objects.create_user(phone="+919876543220", password="password123", name="Test Worker")
        self.worker_profile = WorkerProfile.objects.create(
            user=worker_user,
            status=WorkerProfile.Status.APPROVED,
            is_online=True,
            rating_avg=4.5,
            acceptance_rate=95.0,
        )
        WorkerService.objects.create(worker=self.worker_profile, service=self.service)

        # Assign worker to address's zone
        zone = self.address.zone
        if zone:
            WorkerZone.objects.create(worker=self.worker_profile, zone=zone)

        # Create schedule for worker - all days (in local timezone Asia/Kolkata)
        for day in range(7):
            WorkerSchedule.objects.create(
                worker=self.worker_profile,
                weekday=day,
                start_time="09:00:00",
                end_time="21:00:00",
                is_active=True
            )

    def test_check_availability_slot_is_free(self):
        """Should return available=True for free slot."""
        # Use local timezone (Asia/Kolkata) for booking time to match worker schedule
        # Set booking at 14:00 (2 PM) on a future day to ensure it's within worker schedule (09:00-21:00)
        import pytz
        local_tz = pytz.timezone('Asia/Kolkata')
        now_local = timezone.now().astimezone(local_tz)
        # Book for tomorrow at 14:00 (ensures we're within 09:00-21:00 worker schedule)
        future_date = (now_local + timedelta(days=1)).date()
        future_time = local_tz.localize(datetime.combine(future_date, time(14, 0)))

        response = self.client.post("/api/v1/bookings/check_availability/", {
            "service": self.service.id,
            "scheduled_at": future_time.isoformat(),
            "variant_id": self.variant.id,
            "booking_mode": "scheduled",
        }, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["available"])

    def test_check_availability_slot_conflicts_with_existing(self):
        """Should return 409 Conflict for overlapping booking."""
        import pytz
        local_tz = pytz.timezone('Asia/Kolkata')
        now_local = timezone.now().astimezone(local_tz)
        # Book for tomorrow at 14:00 (within worker schedule 09:00-21:00)
        future_date = (now_local + timedelta(days=1)).date()
        future_time = local_tz.localize(datetime.combine(future_date, time(14, 0)))

        existing_booking_create = self.client.post("/api/v1/bookings/", {
            "service": self.service.id,
            "variant": self.variant.id,
            "booking_mode": "scheduled",
            "scheduled_at": future_time.isoformat(),
            "address_id": self.address.id,
        }, format="json")

        overlapping_time = future_time

        response = self.client.post("/api/v1/bookings/check_availability/", {
            "service": self.service.id,
            "scheduled_at": overlapping_time.isoformat(),
            "variant_id": self.variant.id,
            "booking_mode": "scheduled",
        }, format="json")

        self.assertEqual(response.status_code, 409)
        self.assertFalse(response.data["available"])

    def test_check_availability_fails_with_past_datetime(self):
        """Should reject availability check with past datetime."""
        past_time = timezone.now() - timezone.timedelta(hours=1)

        response = self.client.post("/api/v1/bookings/check_availability/", {
            "service": self.service.id,
            "scheduled_at": past_time.isoformat(),
            "variant_id": self.variant.id,
            "booking_mode": "scheduled",
        }, format="json")

        self.assertEqual(response.status_code, 400)

    def test_check_availability_pickup_drop_requires_drop_time(self):
        """Should fail for pickup_drop without drop_scheduled_at validation."""
        future_time = timezone.now() + timezone.timedelta(hours=1)

        response = self.client.post("/api/v1/bookings/check_availability/", {
            "service": self.service.id,
            "scheduled_at": future_time.isoformat(),
            "variant_id": self.variant.id,
            "booking_mode": "pickup_drop",
            # No drop_scheduled_at - should fail validation
        }, format="json")

        # Should return 400 because drop time is required for pickup_drop
        self.assertEqual(response.status_code, 400)


    def test_earlier_non_overlapping_booking_does_not_block_slot(self):
        """A booking that ended before the requested slot must not block it."""
        from apps.bookings.services import check_slot_availability

        local_tz = pytz.timezone("Asia/Kolkata")
        tomorrow = (timezone.now().astimezone(local_tz) + timedelta(days=1)).date()
        earlier = local_tz.localize(datetime.combine(tomorrow, time(9, 0)))
        requested = local_tz.localize(datetime.combine(tomorrow, time(14, 0)))

        Booking.objects.create(
            customer=self.user,
            address=self.address,
            service=self.service,
            variant=self.variant,
            scheduled_at=earlier,
            status=Booking.Status.PENDING,
        )

        self.assertTrue(
            check_slot_availability(
                service=self.service,
                scheduled_at=requested,
                duration_minutes=60,
                booking_mode=Booking.BookingMode.SCHEDULED,
            )
        )

    def test_buffer_time_is_included_in_overlap_check(self):
        """A new slot inside the previous job's buffer must be rejected."""
        from apps.bookings.services import check_slot_availability, SlotConflictError

        local_tz = pytz.timezone("Asia/Kolkata")
        tomorrow = (timezone.now().astimezone(local_tz) + timedelta(days=1)).date()
        existing_start = local_tz.localize(datetime.combine(tomorrow, time(13, 0)))
        requested = local_tz.localize(datetime.combine(tomorrow, time(14, 15)))

        Booking.objects.create(
            customer=self.user,
            address=self.address,
            service=self.service,
            variant=self.variant,
            scheduled_at=existing_start,
            status=Booking.Status.PENDING,
        )

        with self.assertRaises(SlotConflictError):
            check_slot_availability(
                service=self.service,
                scheduled_at=requested,
                duration_minutes=60,
                booking_mode=Booking.BookingMode.SCHEDULED,
            )

    def test_back_to_back_slot_after_buffer_is_allowed(self):
        """A slot beginning exactly after duration plus buffer is available."""
        from apps.bookings.services import check_slot_availability

        local_tz = pytz.timezone("Asia/Kolkata")
        tomorrow = (timezone.now().astimezone(local_tz) + timedelta(days=1)).date()
        existing_start = local_tz.localize(datetime.combine(tomorrow, time(12, 0)))
        requested = local_tz.localize(datetime.combine(tomorrow, time(13, 30)))

        Booking.objects.create(
            customer=self.user,
            address=self.address,
            service=self.service,
            variant=self.variant,
            scheduled_at=existing_start,
            status=Booking.Status.PENDING,
        )

        self.assertTrue(
            check_slot_availability(
                service=self.service,
                scheduled_at=requested,
                duration_minutes=60,
                booking_mode=Booking.BookingMode.SCHEDULED,
            )
        )


class BookingPaymentFlowCompatibilityTests(BookingAPITestMixin, TestCase):
    """Legacy booking creation and split-payment checkout remain separate contracts."""

    def setUp(self):
        self.client = APIClient()
        self.user = self._create_user("+919876543245")
        self.client.force_authenticate(user=self.user)
        self.category = Category.objects.create(title="Cleaning", slug="payment-flow-cleaning")
        self.service = self._create_service(self.category)
        self.variant = self._create_variant(self.service)
        self.address = self._create_address(self.user)

    def _payload(self):
        return {
            "service": self.service.id,
            "variant": self.variant.id,
            "booking_mode": "scheduled",
            "scheduled_at": (timezone.now() + timedelta(days=2)).isoformat(),
            "address_id": self.address.id,
        }

    def test_legacy_booking_endpoint_does_not_enrol_booking_in_split_payment(self):
        from apps.payments.models import BookingFinancialPlan

        response = self.client.post(
            "/api/v1/bookings/", self._payload(), format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        booking = Booking.objects.get(pk=response.data["id"])
        self.assertFalse(BookingFinancialPlan.objects.filter(booking=booking).exists())
        self.assertNotIn("payment_required", response.data)

    def test_explicit_checkout_endpoint_creates_split_payment_plan(self):
        from apps.payments.models import BookingFinancialPlan, PaymentInstallment

        response = self.client.post(
            "/api/v1/bookings/checkout/", self._payload(), format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        booking = Booking.objects.get(pk=response.data["id"])
        plan = BookingFinancialPlan.objects.get(booking=booking)
        self.assertTrue(response.data["payment_required"])
        self.assertEqual(Decimal(response.data["advance_due"]), plan.advance_due)
        self.assertEqual(Decimal(response.data["balance_due"]), plan.balance_due)
        self.assertEqual(
            PaymentInstallment.objects.filter(
                financial_plan=plan,
                kind=PaymentInstallment.Kind.ADVANCE,
            ).count(),
            1,
        )
        self.assertEqual(response.data["dispatch"], [])


class BookingDoubleBookingPreventionTest(BookingAPITestMixin, TestCase):
    """Test that double-booking is prevented at the database level."""

    def setUp(self):
        from apps.accounts.models import User
        from apps.workers.models import WorkerProfile, WorkerService, WorkerZone, WorkerSchedule
        from apps.core.models import Zone
        import pytz
        from datetime import timedelta

        self.client1 = APIClient()
        self.client2 = APIClient()

        self.user1 = self._create_user("+919876543210")
        self.user2 = self._create_user("+919876543211")

        self.client1.force_authenticate(user=self.user1)
        self.client2.force_authenticate(user=self.user2)

        self.category = Category.objects.create(title="Cleaning", slug="cleaning")
        self.service = self._create_service(self.category)
        self.variant = self._create_variant(self.service, duration_minutes=60)
        self.address1 = self._create_address(self.user1)
        self.address2 = self._create_address(self.user2)

        # Create a worker for this service
        self.worker_user = User.objects.create_user(phone="+919876543212", password="password123", name="Test Worker")
        self.worker_profile = WorkerProfile.objects.create(
            user=self.worker_user,
            status=WorkerProfile.Status.APPROVED,
            is_online=True,
            rating_avg=4.5,
            acceptance_rate=95.0
        )
        # Assign worker to service
        WorkerService.objects.create(worker=self.worker_profile, service=self.service)
        # Assign worker to zone
        zone = self.address1.zone
        WorkerZone.objects.create(worker=self.worker_profile, zone=zone)
        # Create schedule for worker - all weekdays 09:00-21:00
        for day in range(7):
            WorkerSchedule.objects.create(
                worker=self.worker_profile,
                weekday=day,
                start_time="09:00:00",
                end_time="21:00:00",
                is_active=True
            )

        # Store timezone for test methods
        self.local_tz = pytz.timezone('Asia/Kolkata')

    def test_double_booking_prevention_on_booking_creation(self):
        """Should prevent second user from booking the same slot."""
        from apps.bookings.models import Booking

        now_local = timezone.now().astimezone(self.local_tz)
        # Book for tomorrow at 14:00 (within worker schedule 09:00-21:00)
        future_date = (now_local + timedelta(days=1)).date()
        future_time = self.local_tz.localize(datetime.combine(future_date, time(14, 0)))

        # User 1 creates a booking
        response1 = self.client1.post("/api/v1/bookings/", {
            "service": self.service.id,
            "variant": self.variant.id,
            "booking_mode": "scheduled",
            "scheduled_at": future_time.isoformat(),
            "address_id": self.address1.id,
        }, format="json")

        self.assertEqual(response1.status_code, 201)
        booking1_id = response1.data["id"]

        # Verify booking was created
        self.assertTrue(Booking.objects.filter(id=booking1_id).exists())

        # User 2 tries to create a booking for the same slot
        response2 = self.client2.post("/api/v1/bookings/", {
            "service": self.service.id,
            "variant": self.variant.id,
            "booking_mode": "scheduled",
            "scheduled_at": future_time.isoformat(),
            "address_id": self.address2.id,
        }, format="json")

        # Should be rejected with validation error for slot conflict
        self.assertEqual(response2.status_code, 400)
        detail = str(response2.data.get("detail", ""))
        self.assertIn("Slot is already booked", detail)

    def test_availability_check_vs_actual_booking(self):
        """Availability check should match what happens on booking creation."""
        from apps.bookings.models import Booking

        now_local = timezone.now().astimezone(self.local_tz)
        # Book for tomorrow at 14:00 (within worker schedule 09:00-21:00)
        future_date = (now_local + timedelta(days=1)).date()
        future_time = self.local_tz.localize(datetime.combine(future_date, time(14, 0)))

        # User 1 creates booking
        response1 = self.client1.post("/api/v1/bookings/", {
            "service": self.service.id,
            "variant": self.variant.id,
            "booking_mode": "scheduled",
            "scheduled_at": future_time.isoformat(),
            "address_id": self.address1.id,
        }, format="json")

        self.assertEqual(response1.status_code, 201)

        # User 2 checks availability for same slot - should be unavailable
        response_check = self.client2.post("/api/v1/bookings/check_availability/", {
            "service": self.service.id,
            "scheduled_at": future_time.isoformat(),
            "variant_id": self.variant.id,
            "booking_mode": "scheduled",
        }, format="json")

        self.assertEqual(response_check.status_code, 409)
        self.assertFalse(response_check.data["available"])

        # User 2 tries to create booking - should fail
        response2 = self.client2.post("/api/v1/bookings/", {
            "service": self.service.id,
            "variant": self.variant.id,
            "booking_mode": "scheduled",
            "scheduled_at": future_time.isoformat(),
            "address_id": self.address2.id,
        }, format="json")

        self.assertEqual(response2.status_code, 400)

class WorkerOfferModelTest(TestCase):
    """Focused model and constraint tests for the WorkerOffer model."""

    def setUp(self):
        self.customer = User.objects.create_user(phone="+919876543200", password="password123")
        self.worker_user = User.objects.create_user(phone="+919876543201", password="password123")
        self.worker = WorkerProfile.objects.create(
            user=self.worker_user,
            status=WorkerProfile.Status.APPROVED,
            is_online=True,
            rating_avg=4.5,
            acceptance_rate=95.0,
        )
        self.category = Category.objects.create(title="Cleaning", slug="cleaning")
        self.service = Service.objects.create(
            category=self.category,
            title="Home Cleaning",
            booking_mode=Service.BookingMode.SCHEDULED,
            pricing_type=Service.PricingType.FIXED,
            is_active=True,
        )
        self.variant = ServiceVariant.objects.create(
            service=self.service,
            title="Premium",
            price=500,
            mrp=600,
            duration_minutes=60,
        )
        city, _ = City.objects.get_or_create(name="Mumbai", defaults={"state": "Maharashtra"})
        zone, _ = Zone.objects.get_or_create(name="Dadar", defaults={"city": city, "is_active": True})
        self.address = Address.objects.create(
            user=self.customer,
            label="home",
            house_details="Floor 2, Apt 301",
            landmark="Near XYZ Mall",
            full_address="123 Main Street, Near XYZ Mall, Mumbai 400001",
            latitude=19.0760,
            longitude=72.8777,
            zone=zone,
        )
        self.booking = Booking.objects.create(
            customer=self.customer,
            address=self.address,
            service=self.service,
            variant=self.variant,
            booking_mode=Booking.BookingMode.SCHEDULED,
            scheduled_at=timezone.now() + timezone.timedelta(days=1, hours=2),
            status=Booking.Status.PENDING,
        )

    def test_offer_defaults_to_pending(self):
        offer = WorkerOffer.objects.create(
            booking=self.booking,
            worker=self.worker,
            expires_at=timezone.now() + timezone.timedelta(minutes=5),
        )
        self.assertEqual(offer.status, WorkerOffer.Status.PENDING)
        self.assertIsNone(offer.responded_at)
        self.assertIsNone(offer.accepted_at)

    def test_unique_constraint_per_booking_worker(self):
        expires_at = timezone.now() + timezone.timedelta(minutes=5)
        WorkerOffer.objects.create(
            booking=self.booking,
            worker=self.worker,
            expires_at=expires_at,
        )
        with self.assertRaises(IntegrityError):
            WorkerOffer.objects.create(
                booking=self.booking,
                worker=self.worker,
                expires_at=expires_at,
            )

    def test_offer_status_choices(self):
        for status in WorkerOffer.Status.values:
            offer = WorkerOffer(
                booking=self.booking,
                worker=self.worker,
                status=status,
                expires_at=timezone.now() + timezone.timedelta(minutes=5),
            )
            try:
                offer.full_clean()
            except Exception:
                self.fail(f"Status '{status}' should be a valid WorkerOffer choice")

    def test_booking_has_no_assignment_until_accepted(self):
        """A booking created without assignment must raise RelatedObjectDoesNotExist."""
        with self.assertRaises(Booking.assignment.RelatedObjectDoesNotExist):
            _ = self.booking.assignment

    def test_offer_str_representation(self):
        offer = WorkerOffer.objects.create(
            booking=self.booking,
            worker=self.worker,
            expires_at=timezone.now() + timezone.timedelta(minutes=5),
        )
        self.assertIn(f"Booking #{self.booking.pk}", str(offer))
        self.assertIn(self.worker.user.phone, str(offer))

    def test_offer_expires_at_required(self):
        """expires_at is a required field with no default."""
        offer = WorkerOffer(
            booking=self.booking,
            worker=self.worker,
        )
        with self.assertRaises(Exception):
            offer.full_clean()


class WorkerJobLifecycleTest(BookingAPITestMixin, TestCase):
    """Test worker job lifecycle status transitions."""

    def _get_booking_time(self):
        """Get a booking time that falls within worker schedule (10:00-18:00)."""
        local_tz = pytz.timezone('Asia/Kolkata')
        now_local = timezone.now().astimezone(local_tz)
        future_date = (now_local + timedelta(days=1)).date()
        return local_tz.localize(datetime.combine(future_date, time(14, 0)))

    def setUp(self):
        from apps.workers.models import WorkerProfile, WorkerService, WorkerZone, WorkerSchedule

        self.customer_client = APIClient()
        self.worker_client = APIClient()

        self.customer = self._create_user("+919876543210")
        self.customer_client.force_authenticate(user=self.customer)

        self.worker_user = self._create_user("+919876543212")
        self.worker_client.force_authenticate(user=self.worker_user)

        self.category = Category.objects.create(title="Cleaning", slug="cleaning")
        self.service = self._create_service(self.category)
        self.variant = self._create_variant(self.service, duration_minutes=60)
        self.address = self._create_address(self.customer)

        self.worker_profile = WorkerProfile.objects.create(
            user=self.worker_user,
            status=WorkerProfile.Status.APPROVED,
            is_online=True,
            rating_avg=4.5,
        )
        WorkerService.objects.create(worker=self.worker_profile, service=self.service)
        zone = self.address.zone
        WorkerZone.objects.create(worker=self.worker_profile, zone=zone)
        for day in range(7):
            WorkerSchedule.objects.create(
                worker=self.worker_profile,
                weekday=day,
                start_time="10:00:00",
                end_time="18:00:00",
                is_active=True,
            )

    def test_worker_can_start_job(self):
        """Worker can mark a job as in progress."""
        from apps.bookings.models import Booking, BookingAssignment

        future_time = self._get_booking_time()
        booking = Booking.objects.create(
            customer=self.customer,
            address=self.address,
            service=self.service,
            variant=self.variant,
            booking_mode="scheduled",
            scheduled_at=future_time,
            status=Booking.Status.ASSIGNED,
        )
        assignment = BookingAssignment.objects.create(
            booking=booking,
            worker=self.worker_profile,
            accepted_at=timezone.now(),
        )

        start_resp = self.worker_client.post(f"/api/v1/bookings/{booking.id}/start/", format="json")
        self.assertEqual(start_resp.status_code, 200)
        self.assertEqual(start_resp.data["status"], "in_progress")

        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.IN_PROGRESS)

    def test_worker_can_complete_job(self):
        """Worker can mark a job as completed."""
        from apps.bookings.models import Booking, BookingAssignment

        future_time = self._get_booking_time()
        booking = Booking.objects.create(
            customer=self.customer,
            address=self.address,
            service=self.service,
            variant=self.variant,
            booking_mode="scheduled",
            scheduled_at=future_time,
            status=Booking.Status.IN_PROGRESS,
        )
        assignment = BookingAssignment.objects.create(
            booking=booking,
            worker=self.worker_profile,
            started_at=timezone.now(),
        )

        complete_resp = self.worker_client.post(f"/api/v1/bookings/{booking.id}/complete/", format="json")
        self.assertEqual(complete_resp.status_code, 200)
        self.assertEqual(complete_resp.data["status"], "completed")

        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.COMPLETED)

    def test_cannot_start_job_not_assigned(self):
        """Cannot start a job without assignment."""
        future_time = self._get_booking_time()
        booking = Booking.objects.create(
            customer=self.customer,
            address=self.address,
            service=self.service,
            variant=self.variant,
            booking_mode="scheduled",
            scheduled_at=future_time,
            status=Booking.Status.ASSIGNED,
        )

        with self.assertRaises(Booking.assignment.RelatedObjectDoesNotExist):
            assignment = booking.assignment
            assignment.worker = self.worker_profile

    def test_cannot_complete_job_not_in_progress(self):
        """Cannot complete a job that's not in progress."""
        from apps.bookings.models import Booking, BookingAssignment

        future_time = self._get_booking_time()
        booking = Booking.objects.create(
            customer=self.customer,
            address=self.address,
            service=self.service,
            variant=self.variant,
            booking_mode="scheduled",
            scheduled_at=future_time,
            status=Booking.Status.PENDING,
        )
        assignment = BookingAssignment.objects.create(
            booking=booking,
            worker=self.worker_profile,
        )

        complete_resp = self.worker_client.post(f"/api/v1/bookings/{booking.id}/complete/", format="json")
        self.assertEqual(complete_resp.status_code, 400)


class CustomerBookingWorkerAssignmentIntegrationTest(BookingAPITestMixin, TestCase):
    """Integration tests for the full customer booking -> worker assignment workflow."""

    def _get_booking_time(self):
        """Get a booking time that falls within worker schedule (10:00-18:00)."""
        local_tz = pytz.timezone('Asia/Kolkata')
        now_local = timezone.now().astimezone(local_tz)
        future_date = (now_local + timedelta(days=1)).date()
        return local_tz.localize(datetime.combine(future_date, time(14, 0)))

    def setUp(self):
        self.client = APIClient()
        self.customer = self._create_user("+919876543210")
        self.client.force_authenticate(user=self.customer)

        self.category = Category.objects.create(title="Cleaning", slug="cleaning")
        self.service = self._create_service(self.category)
        self.variant = self._create_variant(self.service, duration_minutes=60)
        self.address = self._create_address(self.customer)

        # Worker schedule hours (matches service hours in create_worker_offers_for_booking)
        self.worker_schedule_start = "10:00:00"
        self.worker_schedule_end = "18:00:00"

        # Create worker1 - online, same zone, same service, available schedule
        self.worker1_user = User.objects.create_user(phone="+919876543220", name="Worker One")
        self.worker1_profile = WorkerProfile.objects.create(
            user=self.worker1_user,
            status=WorkerProfile.Status.APPROVED,
            is_online=True,
            rating_avg=4.5,
        )
        WorkerService.objects.create(worker=self.worker1_profile, service=self.service)
        WorkerZone.objects.create(worker=self.worker1_profile, zone=self.address.zone)
        for day in range(7):
            WorkerSchedule.objects.create(
                worker=self.worker1_profile,
                weekday=day,
                start_time=self.worker_schedule_start,
                end_time=self.worker_schedule_end,
                is_active=True,
            )

        # Create worker2 - online, same zone, same service, available schedule
        self.worker2_user = User.objects.create_user(phone="+919876543221", name="Worker Two")
        self.worker2_profile = WorkerProfile.objects.create(
            user=self.worker2_user,
            status=WorkerProfile.Status.APPROVED,
            is_online=True,
        )
        WorkerService.objects.create(worker=self.worker2_profile, service=self.service)
        WorkerZone.objects.create(worker=self.worker2_profile, zone=self.address.zone)
        for day in range(7):
            WorkerSchedule.objects.create(
                worker=self.worker2_profile,
                weekday=day,
                start_time=self.worker_schedule_start,
                end_time=self.worker_schedule_end,
                is_active=True,
            )

        # Create worker3 - should NOT receive offer (offline)
        self.worker3_user = User.objects.create_user(phone="+919876543222", name="Worker Three")
        self.worker3_profile = WorkerProfile.objects.create(
            user=self.worker3_user,
            status=WorkerProfile.Status.APPROVED,
            is_online=False,
        )
        WorkerService.objects.create(worker=self.worker3_profile, service=self.service)
        WorkerZone.objects.create(worker=self.worker3_profile, zone=self.address.zone)

    def test_1_customer_creates_booking_pending(self):
        """Customer can create a booking with PENDING status."""
        future_time = self._get_booking_time()

        response = self.client.post("/api/v1/bookings/", {
            "service": self.service.id,
            "variant": self.variant.id,
            "booking_mode": "scheduled",
            "scheduled_at": future_time.isoformat(),
            "address_id": self.address.id,
        }, format="json")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["status"], "pending")
        self.assertIn("id", response.data)

    def test_2_customer_confirms_booking_creates_offers(self):
        """Customer confirming a booking creates worker offers."""
        from apps.bookings.models import WorkerOffer

        future_time = self._get_booking_time()

        # Create booking
        create_resp = self.client.post("/api/v1/bookings/", {
            "service": self.service.id,
            "variant": self.variant.id,
            "booking_mode": "scheduled",
            "scheduled_at": future_time.isoformat(),
            "address_id": self.address.id,
        }, format="json")

        booking_id = create_resp.data["id"]

        # Confirm booking
        confirm_resp = self.client.post(f"/api/v1/bookings/{booking_id}/confirm/", format="json")
        self.assertEqual(confirm_resp.status_code, 200)
        self.assertEqual(confirm_resp.data["status"], "confirmed")

        # Check that offers were created for eligible workers
        offers = WorkerOffer.objects.filter(booking_id=booking_id, status=WorkerOffer.Status.PENDING)
        self.assertEqual(offers.count(), 2)  # worker1 and worker2 are online

        # Verify worker3 has no offer (offline)
        self.assertFalse(WorkerOffer.objects.filter(booking_id=booking_id, worker=self.worker3_profile).exists())

    def test_3_worker_accepts_offer_creates_assignment(self):
        """Worker accepting an offer creates assignment and updates booking status."""
        from apps.bookings.models import WorkerOffer

        future_time = self._get_booking_time()

        # Create and confirm booking
        create_resp = self.client.post("/api/v1/bookings/", {
            "service": self.service.id,
            "variant": self.variant.id,
            "booking_mode": "scheduled",
            "scheduled_at": future_time.isoformat(),
            "address_id": self.address.id,
        }, format="json")

        booking_id = create_resp.data["id"]
        self.client.post(f"/api/v1/bookings/{booking_id}/confirm/", format="json")

        # Get the offer for worker1
        offer = WorkerOffer.objects.get(booking_id=booking_id, worker=self.worker1_profile)

        # Worker accepts offer
        worker_client = APIClient()
        worker_client.force_authenticate(user=self.worker1_user)
        accept_resp = worker_client.post(f"/api/v1/workers/offers/{offer.id}/accept/", format="json")

        self.assertEqual(accept_resp.status_code, 200)
        self.assertEqual(accept_resp.data["status"], "accepted")

        # Verify assignment created
        from apps.bookings.models import BookingAssignment
        booking = Booking.objects.get(id=booking_id)
        assignment = booking.assignment
        self.assertIsNotNone(assignment)
        self.assertEqual(assignment.worker, self.worker1_profile)

        # Verify booking status updated to ASSIGNED
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.ASSIGNED)

    def test_4_other_workers_cannot_accept_assigned_booking(self):
        """Other workers cannot accept an offer for a booking already assigned."""
        from apps.bookings.models import WorkerOffer, BookingAssignment

        future_time = self._get_booking_time()

        # Create and confirm booking
        create_resp = self.client.post("/api/v1/bookings/", {
            "service": self.service.id,
            "variant": self.variant.id,
            "booking_mode": "scheduled",
            "scheduled_at": future_time.isoformat(),
            "address_id": self.address.id,
        }, format="json")

        booking_id = create_resp.data["id"]
        self.client.post(f"/api/v1/bookings/{booking_id}/confirm/", format="json")

        # Worker1 accepts
        offer1 = WorkerOffer.objects.get(booking_id=booking_id, worker=self.worker1_profile)
        worker1_client = APIClient()
        worker1_client.force_authenticate(user=self.worker1_user)
        worker1_client.post(f"/api/v1/workers/offers/{offer1.id}/accept/", format="json")

        # Worker2 tries to accept (should fail)
        offer2 = WorkerOffer.objects.get(booking_id=booking_id, worker=self.worker2_profile)
        worker2_client = APIClient()
        worker2_client.force_authenticate(user=self.worker2_user)
        accept_resp = worker2_client.post(f"/api/v1/workers/offers/{offer2.id}/accept/", format="json")

        self.assertEqual(accept_resp.status_code, 400)
        self.assertIn("already been assigned", accept_resp.data["detail"].lower())

    def test_5_customer_sees_assigned_worker(self):
        """Customer can see the assigned worker in booking details."""
        from apps.bookings.models import WorkerOffer

        future_time = self._get_booking_time()

        create_resp = self.client.post("/api/v1/bookings/", {
            "service": self.service.id,
            "variant": self.variant.id,
            "booking_mode": "scheduled",
            "scheduled_at": future_time.isoformat(),
            "address_id": self.address.id,
        }, format="json")

        booking_id = create_resp.data["id"]
        self.client.post(f"/api/v1/bookings/{booking_id}/confirm/", format="json")

        # Worker accepts
        offer = WorkerOffer.objects.get(booking_id=booking_id, worker=self.worker1_profile)
        worker_client = APIClient()
        worker_client.force_authenticate(user=self.worker1_user)
        worker_client.post(f"/api/v1/workers/offers/{offer.id}/accept/", format="json")

        # Customer views booking details
        detail_resp = self.client.get(f"/api/v1/bookings/{booking_id}/")
        self.assertEqual(detail_resp.status_code, 200)

        # Check assignment is visible
        self.assertIn("assignment", detail_resp.data)
        self.assertIsNotNone(detail_resp.data["assignment"])
        self.assertEqual(detail_resp.data["assignment"]["worker"], self.worker1_profile.id)
        self.assertEqual(detail_resp.data["status"], "assigned")

    def test_6_customer_cancels_booking_cancels_offers(self):
        """Customer cancelling booking cancels all pending offers."""
        from apps.bookings.models import WorkerOffer, Booking

        future_time = self._get_booking_time()

        create_resp = self.client.post("/api/v1/bookings/", {
            "service": self.service.id,
            "variant": self.variant.id,
            "booking_mode": "scheduled",
            "scheduled_at": future_time.isoformat(),
            "address_id": self.address.id,
        }, format="json")

        booking_id = create_resp.data["id"]
        self.client.post(f"/api/v1/bookings/{booking_id}/confirm/", format="json")

        # Verify offers created
        self.assertEqual(WorkerOffer.objects.filter(booking_id=booking_id).count(), 2)

        # Customer cancels
        cancel_resp = self.client.post(f"/api/v1/bookings/{booking_id}/cancel/", {
            "reason": "Change of mind"
        }, format="json")

        self.assertEqual(cancel_resp.status_code, 200)

        # Verify booking is cancelled
        booking = Booking.objects.get(id=booking_id)
        self.assertEqual(booking.status, Booking.Status.CANCELLED)

        # Verify all offers are expired (not acceptable)
        for offer in WorkerOffer.objects.filter(booking_id=booking_id):
            self.assertEqual(offer.status, WorkerOffer.Status.EXPIRED)

    def test_7_worker_starts_assigned_job(self):
        """Assigned worker can start the job."""
        from apps.bookings.models import WorkerOffer

        future_time = self._get_booking_time()

        create_resp = self.client.post("/api/v1/bookings/", {
            "service": self.service.id,
            "variant": self.variant.id,
            "booking_mode": "scheduled",
            "scheduled_at": future_time.isoformat(),
            "address_id": self.address.id,
        }, format="json")

        booking_id = create_resp.data["id"]
        self.client.post(f"/api/v1/bookings/{booking_id}/confirm/", format="json")

        # Worker accepts
        offer = WorkerOffer.objects.get(booking_id=booking_id, worker=self.worker1_profile)
        worker_client = APIClient()
        worker_client.force_authenticate(user=self.worker1_user)
        worker_client.post(f"/api/v1/workers/offers/{offer.id}/accept/", format="json")

        # Worker starts job
        start_resp = worker_client.post(f"/api/v1/bookings/{booking_id}/start/", format="json")
        self.assertEqual(start_resp.status_code, 200)
        self.assertEqual(start_resp.data["status"], "in_progress")

    def test_8_worker_completes_job(self):
        """Assigned worker can complete the job."""
        from apps.bookings.models import WorkerOffer

        future_time = self._get_booking_time()

        create_resp = self.client.post("/api/v1/bookings/", {
            "service": self.service.id,
            "variant": self.variant.id,
            "booking_mode": "scheduled",
            "scheduled_at": future_time.isoformat(),
            "address_id": self.address.id,
        }, format="json")

        booking_id = create_resp.data["id"]
        self.client.post(f"/api/v1/bookings/{booking_id}/confirm/", format="json")

        # Worker accepts and starts
        offer = WorkerOffer.objects.get(booking_id=booking_id, worker=self.worker1_profile)
        worker_client = APIClient()
        worker_client.force_authenticate(user=self.worker1_user)
        worker_client.post(f"/api/v1/workers/offers/{offer.id}/accept/", format="json")
        start_resp = worker_client.post(f"/api/v1/bookings/{booking_id}/start/", format="json")
        self.assertEqual(start_resp.status_code, 200)

        # Worker completes job
        complete_resp = worker_client.post(f"/api/v1/bookings/{booking_id}/complete/", format="json")
        self.assertEqual(complete_resp.status_code, 200)
        self.assertEqual(complete_resp.data["status"], "completed")

    def test_9_customer_sees_completed_status(self):
        """Customer sees updated lifecycle after service completion."""
        from apps.bookings.models import WorkerOffer

        future_time = self._get_booking_time()

        create_resp = self.client.post("/api/v1/bookings/", {
            "service": self.service.id,
            "variant": self.variant.id,
            "booking_mode": "scheduled",
            "scheduled_at": future_time.isoformat(),
            "address_id": self.address.id,
        }, format="json")

        booking_id = create_resp.data["id"]
        self.client.post(f"/api/v1/bookings/{booking_id}/confirm/", format="json")

        # Worker accepts and completes
        offer = WorkerOffer.objects.get(booking_id=booking_id, worker=self.worker1_profile)
        worker_client = APIClient()
        worker_client.force_authenticate(user=self.worker1_user)
        worker_client.post(f"/api/v1/workers/offers/{offer.id}/accept/", format="json")
        worker_client.post(f"/api/v1/bookings/{booking_id}/start/", format="json")
        worker_client.post(f"/api/v1/bookings/{booking_id}/complete/", format="json")

        # Customer checks status
        detail_resp = self.client.get(f"/api/v1/bookings/{booking_id}/")
        self.assertEqual(detail_resp.data["status"], "completed")
        self.assertIsNotNone(detail_resp.data["completed_at"])

    def test_10_customer_cannot_start_others_booking(self):
        """Customer cannot start a booking they don't own."""
        from apps.bookings.models import WorkerOffer

        other_customer = self._create_user("+919876543211")
        future_time = self._get_booking_time()

        create_resp = self.client.post("/api/v1/bookings/", {
            "service": self.service.id,
            "variant": self.variant.id,
            "booking_mode": "scheduled",
            "scheduled_at": future_time.isoformat(),
            "address_id": self.address.id,
        }, format="json")

        booking_id = create_resp.data["id"]
        self.client.post(f"/api/v1/bookings/{booking_id}/confirm/", format="json")

        # Worker accepts
        offer = WorkerOffer.objects.get(booking_id=booking_id, worker=self.worker1_profile)
        worker_client = APIClient()
        worker_client.force_authenticate(user=self.worker1_user)
        worker_client.post(f"/api/v1/workers/offers/{offer.id}/accept/", format="json")
        worker_client.post(f"/api/v1/bookings/{booking_id}/start/", format="json")

        # Customer tries to start (should fail)
        start_resp = self.client.post(f"/api/v1/bookings/{booking_id}/start/", format="json")
        self.assertEqual(start_resp.status_code, 403)


class AutoDispatchOnBookingCreationTest(BookingAPITestMixin, TestCase):
    """Tests for auto-dispatch of worker offers on booking creation."""

    def _get_booking_time(self):
        """Get a booking time that falls within worker schedule (10:00-18:00)."""
        local_tz = pytz.timezone('Asia/Kolkata')
        now_local = timezone.now().astimezone(local_tz)
        future_date = (now_local + timedelta(days=1)).date()
        return local_tz.localize(datetime.combine(future_date, time(14, 0)))

    def setUp(self):
        self.client = APIClient()
        self.customer = self._create_user("+919876543310")
        self.client.force_authenticate(user=self.customer)

        self.category = Category.objects.create(title="Cleaning", slug="cleaning")
        self.service = self._create_service(self.category)
        self.variant = self._create_variant(self.service, duration_minutes=60)
        self.address = self._create_address(self.customer)

        # Worker schedule hours
        self.worker_schedule_start = "10:00:00"
        self.worker_schedule_end = "18:00:00"

        # Create eligible worker
        self.worker_user = User.objects.create_user(phone="+919876543320", name="Eligible Worker")
        self.worker_profile = WorkerProfile.objects.create(
            user=self.worker_user,
            status=WorkerProfile.Status.APPROVED,
            is_online=True,
            rating_avg=4.5,
        )
        WorkerService.objects.create(worker=self.worker_profile, service=self.service)
        WorkerZone.objects.create(worker=self.worker_profile, zone=self.address.zone)
        for day in range(7):
            WorkerSchedule.objects.create(
                worker=self.worker_profile,
                weekday=day,
                start_time=self.worker_schedule_start,
                end_time=self.worker_schedule_end,
                is_active=True,
            )

    def test_offers_created_on_booking_creation(self):
        """Offers should be created automatically when booking is created."""
        from apps.bookings.models import WorkerOffer

        future_time = self._get_booking_time()

        # Create booking via API
        response = self.client.post("/api/v1/bookings/", {
            "service": self.service.id,
            "variant": self.variant.id,
            "booking_mode": "scheduled",
            "scheduled_at": future_time.isoformat(),
            "address_id": self.address.id,
        }, format="json")

        self.assertEqual(response.status_code, 201)
        booking_id = response.data["id"]

        # Check offers were created automatically
        offers = WorkerOffer.objects.filter(booking_id=booking_id, status=WorkerOffer.Status.PENDING)
        self.assertEqual(offers.count(), 1)

    def test_booking_is_pending_after_creation(self):
        """Booking status should be PENDING after creation."""
        from apps.bookings.models import Booking

        future_time = self._get_booking_time()

        response = self.client.post("/api/v1/bookings/", {
            "service": self.service.id,
            "variant": self.variant.id,
            "booking_mode": "scheduled",
            "scheduled_at": future_time.isoformat(),
            "address_id": self.address.id,
        }, format="json")

        self.assertEqual(response.status_code, 201)
        booking = Booking.objects.get(id=response.data["id"])
        self.assertEqual(booking.status, Booking.Status.PENDING)

    def test_no_duplicate_offers_on_confirmation(self):
        """Confirming a booking with existing offers should not create duplicates."""
        from apps.bookings.models import WorkerOffer

        future_time = self._get_booking_time()

        # Create booking (offers created automatically)
        create_resp = self.client.post("/api/v1/bookings/", {
            "service": self.service.id,
            "variant": self.variant.id,
            "booking_mode": "scheduled",
            "scheduled_at": future_time.isoformat(),
            "address_id": self.address.id,
        }, format="json")

        booking_id = create_resp.data["id"]

        # Check initial offers
        initial_offers = WorkerOffer.objects.filter(booking_id=booking_id)
        self.assertEqual(initial_offers.count(), 1)

        # Confirm booking
        confirm_resp = self.client.post(f"/api/v1/bookings/{booking_id}/confirm/", format="json")
        self.assertEqual(confirm_resp.status_code, 200)

        # Check no duplicate offers
        final_offers = WorkerOffer.objects.filter(booking_id=booking_id)
        self.assertEqual(final_offers.count(), 1)

    def test_offers_exclude_ineligible_workers(self):
        """Offers should only be created for eligible workers."""
        from apps.bookings.models import WorkerOffer

        future_time = self._get_booking_time()

        # Create offline worker (ineligible)
        offline_worker_user = User.objects.create_user(phone="+919876543321", name="Offline Worker")
        offline_worker_profile = WorkerProfile.objects.create(
            user=offline_worker_user,
            status=WorkerProfile.Status.APPROVED,
            is_online=False,  # Offline - ineligible
        )
        WorkerService.objects.create(worker=offline_worker_profile, service=self.service)
        WorkerZone.objects.create(worker=offline_worker_profile, zone=self.address.zone)

        # Create booking
        response = self.client.post("/api/v1/bookings/", {
            "service": self.service.id,
            "variant": self.variant.id,
            "booking_mode": "scheduled",
            "scheduled_at": future_time.isoformat(),
            "address_id": self.address.id,
        }, format="json")

        booking_id = response.data["id"]

        # Check only eligible worker received offer
        offers = WorkerOffer.objects.filter(booking_id=booking_id)
        self.assertEqual(offers.count(), 1)
        self.assertEqual(offers.first().worker, self.worker_profile)


class OfferExpiryTaskTest(TestCase):
    """Tests for the expire_pending_offers Celery task."""

    def setUp(self):
        self.customer = User.objects.create_user(
            phone="+919876543310",
            password="password123"
        )

    def test_expire_pending_offers_marks_expired_offers(self):
        """PENDING offers past expires_at should be marked EXPIRED."""
        from apps.bookings.tasks import expire_pending_offers

        # Create a booking with offers
        city = City.objects.create(name="Mumbai", state="Maharashtra")
        zone = Zone.objects.create(name="Dadar", city=city, is_active=True)
        category = Category.objects.create(title="Cleaning", slug="cleaning")
        service = Service.objects.create(
            category=category,
            title="Home Cleaning",
            booking_mode=Service.BookingMode.SCHEDULED,
            pricing_type=Service.PricingType.FIXED,
            is_active=True,
        )
        variant = ServiceVariant.objects.create(
            service=service,
            title="Premium",
            price=500,
            mrp=600,
            duration_minutes=60,
        )
        address = Address.objects.create(
            user=self.customer,
            label="home",
            house_details="Floor 2, Apt 301",
            full_address="123 Main Street, Mumbai 400001",
            latitude=19.0760,
            longitude=72.8777,
            zone=zone,
        )
        worker_user = User.objects.create_user(phone="+919876543311", password="password123")
        worker = WorkerProfile.objects.create(
            user=worker_user,
            status=WorkerProfile.Status.APPROVED,
            is_online=True,
        )
        booking = Booking.objects.create(
            customer=self.customer,
            address=address,
            service=service,
            variant=variant,
            booking_mode=Booking.BookingMode.SCHEDULED,
            scheduled_at=timezone.now() + timezone.timedelta(days=1),
            status=Booking.Status.PENDING,
        )

        # Create an expired offer (expires_at in the past)
        offer = WorkerOffer.objects.create(
            booking=booking,
            worker=worker,
            expires_at=timezone.now() - timezone.timedelta(hours=1),
        )

        self.assertEqual(offer.status, WorkerOffer.Status.PENDING)

        # Run the task
        count = expire_pending_offers()

        # Verify the offer was expired
        offer.refresh_from_db()
        self.assertEqual(offer.status, WorkerOffer.Status.EXPIRED)
        self.assertIsNotNone(offer.responded_at)
        self.assertEqual(count, 1)

    def test_expire_pending_offers_does_not_expire_accepted_offers(self):
        """ACCEPTED offers should not be affected."""
        from apps.bookings.tasks import expire_pending_offers

        customer = User.objects.create_user(
            phone="+919876543312",
            password="password123"
        )
        city = City.objects.create(name="Mumbai", state="Maharashtra")
        zone = Zone.objects.create(name="Dadar", city=city, is_active=True)
        category = Category.objects.create(title="Cleaning", slug="cleaning2")
        service = Service.objects.create(
            category=category,
            title="Home Cleaning",
            booking_mode=Service.BookingMode.SCHEDULED,
            pricing_type=Service.PricingType.FIXED,
            is_active=True,
        )
        variant = ServiceVariant.objects.create(
            service=service,
            title="Premium",
            price=500,
            mrp=600,
            duration_minutes=60,
        )
        address = Address.objects.create(
            user=customer,
            label="home",
            house_details="Floor 2, Apt 301",
            full_address="123 Main Street, Mumbai 400001",
            latitude=19.0760,
            longitude=72.8777,
            zone=zone,
        )
        worker_user = User.objects.create_user(phone="+919876543313", password="password123")
        worker = WorkerProfile.objects.create(
            user=worker_user,
            status=WorkerProfile.Status.APPROVED,
            is_online=True,
        )
        booking = Booking.objects.create(
            customer=customer,
            address=address,
            service=service,
            variant=variant,
            booking_mode=Booking.BookingMode.SCHEDULED,
            scheduled_at=timezone.now() + timezone.timedelta(days=1),
            status=Booking.Status.CONFIRMED,
        )

        # Create an already accepted offer with expired date
        offer = WorkerOffer.objects.create(
            booking=booking,
            worker=worker,
            status=WorkerOffer.Status.ACCEPTED,
            expires_at=timezone.now() - timezone.timedelta(hours=1),
        )

        self.assertEqual(offer.status, WorkerOffer.Status.ACCEPTED)

        # Run the task
        count = expire_pending_offers()

        # Verify the accepted offer was NOT changed
        offer.refresh_from_db()
        self.assertEqual(offer.status, WorkerOffer.Status.ACCEPTED)
        self.assertIsNone(offer.responded_at)
        self.assertEqual(count, 0)

    def test_expire_pending_offers_is_idempotent(self):
        """Running the task multiple times should be safe."""
        from apps.bookings.tasks import expire_pending_offers

        # Create pending expired offers
        city = City.objects.create(name="Delhi", state="Delhi")
        zone = Zone.objects.create(name="Connaught Place", city=city, is_active=True)
        category = Category.objects.create(title="Cleaning", slug="cleaning-id")
        service = Service.objects.create(
            category=category,
            title="Deep Cleaning",
            booking_mode=Service.BookingMode.SCHEDULED,
            pricing_type=Service.PricingType.FIXED,
            is_active=True,
        )
        customer = User.objects.create_user(phone="+919876543410", password="password123")
        address = Address.objects.create(
            user=customer,
            label="home",
            house_details="Apt 101",
            full_address="123 Main Street, Delhi 110001",
            latitude=28.6139,
            longitude=77.2090,
            zone=zone,
        )
        worker_user = User.objects.create_user(phone="+919876543411", password="password123")
        worker = WorkerProfile.objects.create(
            user=worker_user,
            status=WorkerProfile.Status.APPROVED,
            is_online=True,
        )
        booking = Booking.objects.create(
            customer=customer,
            address=address,
            service=service,
            scheduled_at=timezone.now() + timezone.timedelta(days=1),
            status=Booking.Status.PENDING,
        )

        offer = WorkerOffer.objects.create(
            booking=booking,
            worker=worker,
            expires_at=timezone.now() - timezone.timedelta(minutes=30),
        )

        # Run the task twice
        expire_pending_offers()
        expire_pending_offers()

        # Verify offer is still expired
        offer.refresh_from_db()
        self.assertEqual(offer.status, WorkerOffer.Status.EXPIRED)


class FailedDispatchRetryTaskTest(TestCase):
    """Tests for the retry_failed_dispatches Celery task."""

    def setUp(self):
        self.customer = User.objects.create_user(
            phone="+919876543510",
            password="password123"
        )
        self.city = City.objects.create(name="Mumbai", state="Maharashtra")
        self.zone = Zone.objects.create(name="Dadar", city=self.city, is_active=True)
        self.category = Category.objects.create(title="Cleaning", slug="cleaning-fail")
        self.service = Service.objects.create(
            category=self.category,
            title="Home Cleaning",
            booking_mode=Service.BookingMode.SCHEDULED,
            pricing_type=Service.PricingType.FIXED,
            is_active=True,
        )
        self.variant = ServiceVariant.objects.create(
            service=self.service,
            title="Premium",
            price=500,
            mrp=600,
            duration_minutes=60,
        )
        self.address = Address.objects.create(
            user=self.customer,
            label="home",
            house_details="Floor 2, Apt 301",
            full_address="123 Main Street, Mumbai 400001",
            latitude=19.0760,
            longitude=72.8777,
            zone=self.zone,
        )

    def test_retry_failed_dispatches_creates_new_offers(self):
        """Bookings with expired offers should get new offers."""
        from apps.bookings.tasks import retry_failed_dispatches

        # Create an approved worker with the right service, zone, and schedule
        worker_user = User.objects.create_user(phone="+919876543511", password="password123")
        worker = WorkerProfile.objects.create(
            user=worker_user,
            status=WorkerProfile.Status.APPROVED,
            is_online=True,
        )
        WorkerService.objects.create(worker=worker, service=self.service)
        WorkerZone.objects.create(worker=worker, zone=self.zone)
        # Add schedule for tomorrow (weekday check)
        weekday = (timezone.now() + timezone.timedelta(days=1)).weekday()
        WorkerSchedule.objects.create(
            worker=worker,
            weekday=weekday,
            start_time="09:00:00",
            end_time="18:00:00",
        )

        # Create a confirmed booking with no assignment
        # Schedule within worker hours (09:00-18:00). Use 10:00 local time tomorrow.
        from datetime import time as dtime
        tomorrow = (timezone.now() + timezone.timedelta(days=1)).date()
        scheduled_at_local = timezone.make_aware(
            timezone.datetime.combine(tomorrow, dtime(10, 0))
        )
        scheduled_at_utc = timezone.localtime(scheduled_at_local, timezone.UTC)

        booking = Booking.objects.create(
            customer=self.customer,
            address=self.address,
            service=self.service,
            variant=self.variant,
            booking_mode=Booking.BookingMode.SCHEDULED,
            scheduled_at=scheduled_at_utc,
            status=Booking.Status.CONFIRMED,
        )

        # Run the task
        batch_count = retry_failed_dispatches()

        # Verify new offers were created
        self.assertGreater(batch_count, 0)
        offers = WorkerOffer.objects.filter(booking=booking)
        self.assertGreater(offers.count(), 0)

    def test_no_redispatch_for_assigned_bookings(self):
        """Assigned bookings should not be redispatched."""
        from apps.bookings.tasks import retry_failed_dispatches

        worker_user = User.objects.create_user(phone="+919876543511", password="password123")
        worker = WorkerProfile.objects.create(
            user=worker_user,
            status=WorkerProfile.Status.APPROVED,
            is_online=True,
        )
        WorkerService.objects.create(worker=worker, service=self.service)
        WorkerZone.objects.create(worker=worker, zone=self.zone)

        # Create an assigned booking
        booking = Booking.objects.create(
            customer=self.customer,
            address=self.address,
            service=self.service,
            scheduled_at=timezone.now() + timezone.timedelta(days=1),
            status=Booking.Status.ASSIGNED,
        )
        BookingAssignment.objects.create(
            booking=booking,
            worker=worker,
        )

        # Run the task
        batch_count = retry_failed_dispatches()

        # Verify no duplicate offers for assigned booking
        self.assertEqual(batch_count, 0)
        offers = WorkerOffer.objects.filter(booking=booking)
        self.assertEqual(offers.count(), 0)

    def test_no_redispatch_for_cancelled_bookings(self):
        """Cancelled bookings should not be redispatched."""
        from apps.bookings.tasks import retry_failed_dispatches

        # Create a cancelled booking
        booking = Booking.objects.create(
            customer=self.customer,
            address=self.address,
            service=self.service,
            scheduled_at=timezone.now() + timezone.timedelta(days=1),
            status=Booking.Status.CANCELLED,
        )

        # Run the task
        batch_count = retry_failed_dispatches()

        # Verify no offers created for cancelled booking
        self.assertEqual(batch_count, 0)
        offers = WorkerOffer.objects.filter(booking=booking)
        self.assertEqual(offers.count(), 0)

    def test_no_redispatch_when_pending_offers_exist(self):
        """Bookings with pending offers should not be redispatched."""
        from apps.bookings.tasks import retry_failed_dispatches

        worker_user = User.objects.create_user(phone="+919876543512", password="password123")
        worker = WorkerProfile.objects.create(
            user=worker_user,
            status=WorkerProfile.Status.APPROVED,
            is_online=True,
        )
        WorkerService.objects.create(worker=worker, service=self.service)
        WorkerZone.objects.create(worker=worker, zone=self.zone)
        WorkerSchedule.objects.create(
            worker=worker,
            weekday=0,  # Monday
            start_time="09:00:00",
            end_time="18:00:00",
        )

        # Create a confirmed booking with a pending offer
        booking = Booking.objects.create(
            customer=self.customer,
            address=self.address,
            service=self.service,
            scheduled_at=timezone.now() + timezone.timedelta(days=1),
            status=Booking.Status.CONFIRMED,
        )
        offer = WorkerOffer.objects.create(
            booking=booking,
            worker=worker,
            expires_at=timezone.now() + timezone.timedelta(hours=1),
        )

        # Run the task
        batch_count = retry_failed_dispatches()

        # Verify no new offers created (pending offer exists)
        self.assertEqual(batch_count, 0)
        all_offers = WorkerOffer.objects.filter(booking=booking)
        self.assertEqual(all_offers.count(), 1)  # Only the original offer


class PaymentTimeoutTaskTest(TestCase):
    """Tests for the timeout_pending_payments Celery task."""

    def setUp(self):
        self.customer = User.objects.create_user(
            phone="+919876543610",
            password="password123"
        )
        self.city = City.objects.create(name="Mumbai", state="Maharashtra")
        self.zone = Zone.objects.create(name="Dadar", city=self.city, is_active=True)
        self.category = Category.objects.create(title="Cleaning", slug="cleaning-pmt")
        self.service = Service.objects.create(
            category=self.category,
            title="Home Cleaning",
            booking_mode=Service.BookingMode.SCHEDULED,
            pricing_type=Service.PricingType.FIXED,
            is_active=True,
        )
        self.address = Address.objects.create(
            user=self.customer,
            label="home",
            house_details="Floor 2, Apt 301",
            full_address="123 Main Street, Mumbai 400001",
            latitude=19.0760,
            longitude=72.8777,
            zone=self.zone,
        )

    def test_payment_timeout_marks_payment_failed(self):
        """PENDING payments past timeout should be marked FAILED."""
        from apps.bookings.tasks import timeout_pending_payments
        from apps.payments.models import Payment

        # Create a booking with a pending payment
        booking = Booking.objects.create(
            customer=self.customer,
            address=self.address,
            service=self.service,
            scheduled_at=timezone.now() + timezone.timedelta(days=1),
            status=Booking.Status.CONFIRMED,
        )
        payment = Payment.objects.create(
            booking=booking,
            customer=self.customer,
            amount=500,
            method=Payment.Method.RAZORPAY,
            status=Payment.Status.PENDING,
            razorpay_order_id="order_test123",
        )

        # Manually set creation time to 10 minutes ago (past 5 min timeout)
        payment.created_at = timezone.now() - timezone.timedelta(minutes=10)
        payment.save()

        # Run the task
        count = timeout_pending_payments()

        # Verify payment was marked failed
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.FAILED)
        self.assertEqual(count, 1)

    def test_successful_payment_not_timed_out(self):
        """PAID payments should not be affected."""
        from apps.bookings.tasks import timeout_pending_payments
        from apps.payments.models import Payment

        # Create a booking with a PAID payment
        booking = Booking.objects.create(
            customer=self.customer,
            address=self.address,
            service=self.service,
            scheduled_at=timezone.now() + timezone.timedelta(days=1),
            status=Booking.Status.ASSIGNED,
        )
        payment = Payment.objects.create(
            booking=booking,
            customer=self.customer,
            amount=500,
            method=Payment.Method.RAZORPAY,
            status=Payment.Status.PAID,
            razorpay_order_id="order_test456",
            razorpay_payment_id="pay_test456",
            paid_at=timezone.now() - timezone.timedelta(minutes=5),
        )

        # Run the task
        count = timeout_pending_payments()

        # Verify payment status unchanged
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PAID)
        self.assertEqual(count, 0)

    def test_repeated_timeout_is_idempotent(self):
        """Running timeout task multiple times should be safe."""
        from apps.bookings.tasks import timeout_pending_payments
        from apps.payments.models import Payment

        # Create an expired pending payment
        booking = Booking.objects.create(
            customer=self.customer,
            address=self.address,
            service=self.service,
            scheduled_at=timezone.now() + timezone.timedelta(days=1),
            status=Booking.Status.CONFIRMED,
        )
        payment = Payment.objects.create(
            booking=booking,
            customer=self.customer,
            amount=500,
            method=Payment.Method.RAZORPAY,
            status=Payment.Status.PENDING,
            razorpay_order_id="order_test789",
        )
        payment.created_at = timezone.now() - timezone.timedelta(minutes=15)
        payment.save()

        # Run the task twice
        timeout_pending_payments()
        timeout_pending_payments()

        # Verify payment is still failed (not double-counted)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.FAILED)

    def test_payment_timeout_releases_assigned_worker(self):
        """ASSIGNED bookings with timeout should release worker and revert to PENDING."""
        from apps.bookings.tasks import timeout_pending_payments
        from apps.payments.models import Payment
        from apps.bookings.models import BookingAssignment, WorkerOffer

        # Create a worker and approve them
        worker_user = User.objects.create_user(phone="+919876543620", password="password123")
        category = Category.objects.create(title="Cleaning", slug="cleaning-release")
        service = Service.objects.create(
            category=category,
            title="Home Cleaning",
            booking_mode=Service.BookingMode.SCHEDULED,
            pricing_type=Service.PricingType.FIXED,
            is_active=True,
        )
        worker = WorkerProfile.objects.create(
            user=worker_user,
            status=WorkerProfile.Status.APPROVED,
            is_online=True,
            rating_avg=4.5
        )
        WorkerService.objects.create(worker=worker, service=service)
        WorkerZone.objects.create(worker=worker, zone=self.zone)
        WorkerSchedule.objects.create(
            worker=worker,
            weekday=timezone.now().weekday(),
            is_active=True,
            start_time=time(10, 0),
            end_time=time(18, 0)
        )

        # Create a scheduled_at time within worker's schedule
        local_tz = pytz.timezone('Asia/Kolkata')
        now_local = timezone.now().astimezone(local_tz)
        future_date = (now_local + timedelta(days=1)).date()
        booking_time = local_tz.localize(datetime.combine(future_date, time(14, 0)))

        # Create an ASSIGNED booking with pending payment
        booking = Booking.objects.create(
            customer=self.customer,
            address=self.address,
            service=service,
            scheduled_at=booking_time,
            status=Booking.Status.ASSIGNED,
        )

        # Create an accepted offer for the worker
        offer = WorkerOffer.objects.create(
            booking=booking,
            worker=worker,
            status=WorkerOffer.Status.ACCEPTED,
            expires_at=timezone.now() + timezone.timedelta(minutes=5)
        )

        # Create assignment (BookingAssignment doesn't have offer field)
        assignment = BookingAssignment.objects.create(
            booking=booking,
            worker=worker,
        )

        # Create a pending payment
        payment = Payment.objects.create(
            booking=booking,
            customer=self.customer,
            amount=500,
            method=Payment.Method.RAZORPAY,
            status=Payment.Status.PENDING,
            razorpay_order_id="order_release_test",
        )
        payment.created_at = timezone.now() - timezone.timedelta(minutes=10)
        payment.save()

        # Run the task
        count = timeout_pending_payments()

        # Verify payment was marked failed
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.FAILED)

        # Verify booking status reverted to PENDING
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.PENDING)

        # Verify offer was withdrawn
        offer.refresh_from_db()
        self.assertEqual(offer.status, WorkerOffer.Status.WITHDRAWN)

        # Verify assignment was deleted
        self.assertFalse(BookingAssignment.objects.filter(booking=booking).exists())

        # Verify notifications were sent
        self.assertEqual(Notification.objects.filter(
            user=self.customer,
            type=Notification.Type.PAYMENT_TIMEOUT
        ).count(), 1)

        self.assertEqual(Notification.objects.filter(
            user=worker_user,
            type=Notification.Type.WORKER_OFFER_WITHDRAWN
        ).count(), 1)

        self.assertEqual(count, 1)


class DispatcherServiceTest(TestCase):
    """Tests for DispatcherService worker offer dispatch."""

    def setUp(self):
        self.customer = User.objects.create_user(
            phone="+919876543630",
            password="password123"
        )
        self.city = City.objects.create(name="Mumbai", state="Maharashtra")
        self.zone = Zone.objects.create(name="Dadar", city=self.city, is_active=True)
        self.category = Category.objects.create(title="Cleaning", slug="cleaning-dispatcher")
        self.service = Service.objects.create(
            category=self.category,
            title="Home Cleaning",
            booking_mode=Service.BookingMode.SCHEDULED,
            pricing_type=Service.PricingType.FIXED,
            is_active=True,
        )
        self.address = Address.objects.create(
            user=self.customer,
            label="home",
            house_details="Floor 2, Apt 301",
            full_address="123 Main Street, Mumbai 400001",
            latitude=19.0760,
            longitude=72.8777,
            zone=self.zone,
        )

    def _get_booking_time(self):
        """Get a booking time that falls within worker schedule (10:00-18:00)."""
        local_tz = pytz.timezone('Asia/Kolkata')
        now_local = timezone.now().astimezone(local_tz)
        future_date = (now_local + timedelta(days=1)).date()
        return local_tz.localize(datetime.combine(future_date, time(14, 0)))

    def _create_eligible_worker(self, rating=4.0, suffix=""):
        """Helper to create an eligible worker."""
        from apps.workers.models import WorkerProfile, WorkerZone, WorkerSchedule

        worker_user = User.objects.create_user(
            phone=f"+919876543{suffix}", password="password123"
        )
        worker = WorkerProfile.objects.create(
            user=worker_user,
            status=WorkerProfile.Status.APPROVED,
            is_online=True,
            rating_avg=rating
        )
        # Create WorkerService to associate service
        WorkerService.objects.create(worker=worker, service=self.service)
        WorkerZone.objects.create(worker=worker, zone=self.zone)
        for day in range(7):
            WorkerSchedule.objects.create(
                worker=worker,
                weekday=day,
                is_active=True,
                start_time=time(10, 0),
                end_time=time(18, 0),
            )
        return worker

    def test_dispatcher_creates_5_offers_for_batch(self):
        """DispatcherService should create exactly 5 offers per batch."""
        from apps.bookings.dispatcher import DispatcherService

        # Create 10 workers, all eligible (more than batch_size of 5)
        for i in range(10):
            self._create_eligible_worker(suffix=f"3{i}", rating=4.0)

        # Create a PENDING booking with proper time
        booking = Booking.objects.create(
            customer=self.customer,
            address=self.address,
            service=self.service,
            scheduled_at=self._get_booking_time(),
            status=Booking.Status.PENDING,
        )

        # Dispatch offers
        offers = DispatcherService.dispatch_offers(booking)

        # Should create exactly 5 offers (batch_size)
        self.assertEqual(len(offers), 5)
        self.assertEqual(WorkerOffer.objects.filter(booking=booking).count(), 5)

    def test_dispatcher_limits_to_batch_size(self):
        """DispatcherService should respect batch_size parameter."""
        from apps.bookings.dispatcher import DispatcherService

        # Create only 3 eligible workers
        for i in range(3):
            self._create_eligible_worker(suffix=f"4{i}")

        booking = Booking.objects.create(
            customer=self.customer,
            address=self.address,
            service=self.service,
            scheduled_at=self._get_booking_time(),
            status=Booking.Status.PENDING,
        )

        # Dispatch with batch_size=2
        offers = DispatcherService.dispatch_offers(booking, batch_size=2)

        # Should create only 2 offers
        self.assertEqual(len(offers), 2)

    def test_dispatcher_excludes_unavailable_workers(self):
        """DispatcherService should not offer to offline or non-approved workers."""
        from apps.bookings.dispatcher import DispatcherService

        # Create an online, approved worker who should receive offer
        online_worker = self._create_eligible_worker(rating=4.5, suffix="50")

        # Create an offline worker (should be excluded)
        offline_user = User.objects.create_user(
            phone="+919876543651", password="password123"
        )
        offline_worker = WorkerProfile.objects.create(
            user=offline_user,
            status=WorkerProfile.Status.APPROVED,
            is_online=False,  # OFFLINE
            rating_avg=5.0
        )
        WorkerService.objects.create(worker=offline_worker, service=self.service)
        WorkerZone.objects.create(worker=offline_worker, zone=self.zone)
        for day in range(7):
            WorkerSchedule.objects.create(
                worker=offline_worker,
                weekday=day,
                is_active=True,
                start_time=time(10, 0),
                end_time=time(18, 0),
            )

        # Create a disapproved worker (should be excluded)
        disapproved_user = User.objects.create_user(
            phone="+919876543652", password="password123"
        )
        disapproved_worker = WorkerProfile.objects.create(
            user=disapproved_user,
            status=WorkerProfile.Status.PENDING,  # Not APPROVED yet
            is_online=True,
            rating_avg=5.0
        )
        WorkerService.objects.create(worker=disapproved_worker, service=self.service)
        WorkerZone.objects.create(worker=disapproved_worker, zone=self.zone)
        for day in range(7):
            WorkerSchedule.objects.create(
                worker=disapproved_worker,
                weekday=day,
                is_active=True,
                start_time=time(10, 0),
                end_time=time(18, 0),
            )

        booking = Booking.objects.create(
            customer=self.customer,
            address=self.address,
            service=self.service,
            scheduled_at=self._get_booking_time(),
            status=Booking.Status.PENDING,
        )

        # Dispatch offers
        offers = DispatcherService.dispatch_offers(booking)

        # Only the online approved worker should receive an offer
        self.assertEqual(len(offers), 1)
        self.assertEqual(offers[0].worker, online_worker)

    def test_dispatcher_sorts_by_rating(self):
        """DispatcherService should sort eligible workers by rating descending."""
        from apps.bookings.dispatcher import DispatcherService

        # Create 5 workers with different ratings
        ratings = [3.0, 5.0, 4.0, 4.5, 2.0]

        for i, rating in enumerate(ratings):
            self._create_eligible_worker(rating=rating, suffix=f"6{i}")

        booking = Booking.objects.create(
            customer=self.customer,
            address=self.address,
            service=self.service,
            scheduled_at=self._get_booking_time(),
            status=Booking.Status.PENDING,
        )

        # Dispatch offers
        offers = DispatcherService.dispatch_offers(booking)

        # Offers should be sorted by rating (descending): 5.0, 4.5, 4.0, 3.0, 2.0
        expected_order = [5.0, 4.5, 4.0, 3.0, 2.0]
        actual_ratings = [float(offers[i].worker.rating_avg) for i in range(len(offers))]
        self.assertEqual(actual_ratings, expected_order)


    def test_dispatcher_never_offers_booking_to_its_own_customer_worker(self):
        """A customer who is also an approved worker must not receive their own job."""
        from apps.bookings.dispatcher import DispatcherService

        self_worker = self._create_eligible_worker(rating=5.0, suffix="77")
        self.customer = self_worker.user
        self.address.user = self.customer
        self.address.save(update_fields=["user"])
        other_worker = self._create_eligible_worker(rating=4.5, suffix="78")

        booking = Booking.objects.create(
            customer=self.customer,
            address=self.address,
            service=self.service,
            scheduled_at=self._get_booking_time(),
            status=Booking.Status.PENDING,
        )

        offers = DispatcherService.dispatch_offers(booking)

        self.assertEqual([offer.worker_id for offer in offers], [other_worker.id])
        self.assertFalse(WorkerOffer.objects.filter(
            booking=booking, worker=self_worker
        ).exists())


class PaymentWebhookTest(TestCase):
    """Tests for Razorpay payment webhook."""

    def setUp(self):
        self.customer = User.objects.create_user(
            phone="+919876543700",
            password="password123"
        )
        self.city = City.objects.create(name="Mumbai", state="Maharashtra")
        self.zone = Zone.objects.create(name="Dadar", city=self.city, is_active=True)
        self.category = Category.objects.create(title="Cleaning", slug="cleaning-webhook")
        self.service = Service.objects.create(
            category=self.category,
            title="Home Cleaning",
            booking_mode=Service.BookingMode.SCHEDULED,
            pricing_type=Service.PricingType.FIXED,
            is_active=True,
        )
        self.address = Address.objects.create(
            user=self.customer,
            label="home",
            house_details="Floor 2, Apt 301",
            full_address="123 Main Street, Mumbai 400001",
            latitude=19.0760,
            longitude=72.8777,
            zone=self.zone,
        )

    def _make_webhook_payload(self, event_type, order_id, payment_id, amount=50000, currency="INR"):
        """Create a Razorpay webhook payload for testing."""
        return {
            "event": event_type,
            "payload": {
                "payment": {
                    "entity": {
                        "id": payment_id,
                        "order_id": order_id,
                        "amount": amount,
                        "currency": currency,
                        "status": "captured",
                    }
                }
            }
        }

    def _post_webhook(self, payload, secret="whsec_test123"):
        """Post a webhook payload with signature."""
        import hmac
        import hashlib
        import json

        raw_body = json.dumps(payload).encode('utf-8')
        signature = hmac.new(
            secret.encode(),
            raw_body,
            hashlib.sha256,
        ).hexdigest()

        from django.test import Client
        client = Client()
        response = client.post(
            '/api/v1/payments/webhook/',
            data=raw_body,
            content_type='application/json',
            HTTP_X_RAZORPAY_SIGNATURE=signature
        )
        return response

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Set webhook secret for tests
        from django.conf import settings
        settings.RAZORPAY_WEBHOOK_SECRET = "whsec_test123"

    def test_webhook_payment_captured_success(self):
        """Successful payment.captured webhook marks payment as PAID."""
        from apps.payments.models import Payment
        from django.test import Client

        booking = Booking.objects.create(
            customer=self.customer,
            address=self.address,
            service=self.service,
            scheduled_at=timezone.now() + timezone.timedelta(days=1),
            status=Booking.Status.ASSIGNED,
        )
        payment = Payment.objects.create(
            booking=booking,
            customer=self.customer,
            amount=500,
            method=Payment.Method.RAZORPAY,
            status=Payment.Status.PENDING,
            razorpay_order_id="order_test_capture",
        )

        payload = self._make_webhook_payload(
            "payment.captured", "order_test_capture", "pay_test_capture", 50000, "INR"
        )
        response = self._post_webhook(payload)

        self.assertEqual(response.status_code, 200)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PAID)
        self.assertEqual(payment.razorpay_payment_id, "pay_test_capture")

    def test_webhook_amount_mismatch_rejected(self):
        """Webhook with wrong amount should be rejected."""
        from apps.payments.models import Payment

        booking = Booking.objects.create(
            customer=self.customer,
            address=self.address,
            service=self.service,
            scheduled_at=timezone.now() + timezone.timedelta(days=1),
            status=Booking.Status.ASSIGNED,
        )
        payment = Payment.objects.create(
            booking=booking,
            customer=self.customer,
            amount=500,
            method=Payment.Method.RAZORPAY,
            status=Payment.Status.PENDING,
            razorpay_order_id="order_amount_mismatch",
        )

        # Amount in payload is 60000 paise (₹600) but payment is ₹500
        payload = self._make_webhook_payload(
            "payment.captured", "order_amount_mismatch", "pay_amount_mismatch", 60000, "INR"
        )
        response = self._post_webhook(payload)

        self.assertEqual(response.status_code, 400)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PENDING)  # Not changed

    def test_webhook_currency_mismatch_rejected(self):
        """Webhook with wrong currency should be rejected."""
        from apps.payments.models import Payment

        booking = Booking.objects.create(
            customer=self.customer,
            address=self.address,
            service=self.service,
            scheduled_at=timezone.now() + timezone.timedelta(days=1),
            status=Booking.Status.ASSIGNED,
        )
        payment = Payment.objects.create(
            booking=booking,
            customer=self.customer,
            amount=500,
            method=Payment.Method.RAZORPAY,
            status=Payment.Status.PENDING,
            razorpay_order_id="order_currency_mismatch",
        )

        # Currency in payload is USD but payment is INR
        payload = self._make_webhook_payload(
            "payment.captured", "order_currency_mismatch", "pay_currency_mismatch", 50000, "USD"
        )
        response = self._post_webhook(payload)

        self.assertEqual(response.status_code, 400)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PENDING)  # Not changed

    def test_webhook_idempotent_duplicate_captured(self):
        """Duplicate payment.captured events should be idempotent."""
        from apps.payments.models import Payment

        booking = Booking.objects.create(
            customer=self.customer,
            address=self.address,
            service=self.service,
            scheduled_at=timezone.now() + timezone.timedelta(days=1),
            status=Booking.Status.ASSIGNED,
        )
        payment = Payment.objects.create(
            booking=booking,
            customer=self.customer,
            amount=500,
            method=Payment.Method.RAZORPAY,
            status=Payment.Status.PENDING,
            razorpay_order_id="order_idempotent",
        )

        payload = self._make_webhook_payload(
            "payment.captured", "order_idempotent", "pay_idempotent", 50000, "INR"
        )

        # First call
        response1 = self._post_webhook(payload)
        self.assertEqual(response1.status_code, 200)

        # Second call (duplicate)
        response2 = self._post_webhook(payload)
        self.assertEqual(response2.status_code, 200)

        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PAID)

    def test_webhook_delayed_failed_after_captured(self):
        """Delayed payment.failed after captured should not regress PAID payment."""
        from apps.payments.models import Payment

        booking = Booking.objects.create(
            customer=self.customer,
            address=self.address,
            service=self.service,
            scheduled_at=timezone.now() + timezone.timedelta(days=1),
            status=Booking.Status.ASSIGNED,
        )
        payment = Payment.objects.create(
            booking=booking,
            customer=self.customer,
            amount=500,
            method=Payment.Method.RAZORPAY,
            status=Payment.Status.PENDING,
            razorpay_order_id="order_delayed_fail",
        )

        # First: captured
        payload_captured = self._make_webhook_payload(
            "payment.captured", "order_delayed_fail", "pay_delayed_fail", 50000, "INR"
        )
        response1 = self._post_webhook(payload_captured)
        self.assertEqual(response1.status_code, 200)

        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PAID)

        # Then: delayed failed event
        payload_failed = self._make_webhook_payload(
            "payment.failed", "order_delayed_fail", "pay_delayed_fail", 50000, "INR"
        )
        response2 = self._post_webhook(payload_failed)
        self.assertEqual(response2.status_code, 200)

        # Payment should remain PAID
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PAID)

    def test_webhook_authorized_then_captured(self):
        """payment.authorized followed by payment.captured should work."""
        from apps.payments.models import Payment

        booking = Booking.objects.create(
            customer=self.customer,
            address=self.address,
            service=self.service,
            scheduled_at=timezone.now() + timezone.timedelta(days=1),
            status=Booking.Status.ASSIGNED,
        )
        payment = Payment.objects.create(
            booking=booking,
            customer=self.customer,
            amount=500,
            method=Payment.Method.RAZORPAY,
            status=Payment.Status.PENDING,
            razorpay_order_id="order_auth_capture",
        )

        # First: authorized
        payload_auth = self._make_webhook_payload(
            "payment.authorized", "order_auth_capture", "pay_auth_capture", 50000, "INR"
        )
        response1 = self._post_webhook(payload_auth)
        self.assertEqual(response1.status_code, 200)

        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PAID)

        # Then: captured (duplicate, should be idempotent)
        payload_capture = self._make_webhook_payload(
            "payment.captured", "order_auth_capture", "pay_auth_capture", 50000, "INR"
        )
        response2 = self._post_webhook(payload_capture)
        self.assertEqual(response2.status_code, 200)

        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PAID)

    def test_webhook_late_capture_after_timeout(self):
        """Q12: Late payment.captured after timeout released worker."""
        from apps.payments.models import Payment
        from django.utils import timezone

        # Create a booking with PENDING status
        booking = Booking.objects.create(
            customer=self.customer,
            address=self.address,
            service=self.service,
            scheduled_at=timezone.now() + timezone.timedelta(days=1),
            status=Booking.Status.PENDING,
        )

        # Create payment that's still PENDING
        payment = Payment.objects.create(
            booking=booking,
            customer=self.customer,
            amount=500,
            method=Payment.Method.RAZORPAY,
            status=Payment.Status.PENDING,
            razorpay_order_id="order_late_webhook",
            created_at=timezone.now() - timezone.timedelta(minutes=10),  # Old enough for timeout
        )

        # First, capture the payment via webhook
        payload = self._make_webhook_payload(
            "payment.captured", "order_late_webhook", "pay_late_webhook", 50000, "INR"
        )
        response = self._post_webhook(payload)
        self.assertEqual(response.status_code, 200)

        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PAID)
        self.assertEqual(payment.razorpay_payment_id, "pay_late_webhook")

        booking.refresh_from_db()
        # Booking should be CONFIRMED after payment capture
        self.assertEqual(booking.status, Booking.Status.CONFIRMED)

        # Verify notification was created (Q12 handled)
        notifications = Notification.objects.filter(
            user=self.customer,
            type=Notification.Type.PAYMENT_SUCCESS,
            data__booking_id=booking.id,
        )
        self.assertTrue(notifications.exists())

        # Verify exactly ONE notification was created (no duplicates)
        self.assertEqual(notifications.count(), 1, "Should create exactly one notification to avoid duplicates")

        # Verify Q12-specific notification data
        notification = notifications.first()
        self.assertEqual(notification.data.get("late_webhook"), True)
        self.assertEqual(notification.data.get("booking_id"), booking.id)
        self.assertEqual(notification.data.get("payment_id"), payment.id)


    def test_parent_order_webhook_marks_every_booking_paid_and_confirmed(self):
        from apps.payments.models import Payment

        booking = Booking.objects.create(
            customer=self.customer,
            address=self.address,
            service=self.service,
            scheduled_at=timezone.now() + timedelta(days=3),
            status=Booking.Status.ASSIGNED,
            pricing_snapshot={"total": "2360.00"},
        )
        order = Order.objects.create(
            customer=self.customer,
            address=self.address,
            status=Order.Status.AWAITING_PAYMENT,
            subtotal="2000.00",
            tax_amount="360.00",
            total_amount="2360.00",
        )
        OrderItem.objects.create(
            order=order,
            booking=booking,
            quantity=2,
            line_subtotal="2000.00",
            tax_amount="360.00",
            line_total="2360.00",
        )
        payment = Payment.objects.create(
            order=order,
            customer=self.customer,
            amount="2360.00",
            method=Payment.Method.RAZORPAY,
            status=Payment.Status.PENDING,
            razorpay_order_id="order_parent_checkout",
        )

        payload = self._make_webhook_payload(
            "payment.captured",
            "order_parent_checkout",
            "pay_parent_checkout",
            236000,
            "INR",
        )
        response = self._post_webhook(payload)

        self.assertEqual(response.status_code, 200)
        payment.refresh_from_db()
        order.refresh_from_db()
        booking.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PAID)
        self.assertEqual(order.status, Order.Status.PAID)
        self.assertEqual(booking.status, Booking.Status.CONFIRMED)


class CustomerOrderReadIntegrityTest(BookingAPITestMixin, TestCase):
    """Reading an order must never mutate its lifecycle state."""

    def setUp(self):
        self.client = APIClient()
        self.customer = self._create_user("+919876543277")
        self.client.force_authenticate(user=self.customer)
        self.category = Category.objects.create(title="Cleaning", slug="order-read-cleaning")
        self.service = self._create_service(self.category)
        self.address = self._create_address(self.customer)

    def _create_order(self, order_status):
        booking = Booking.objects.create(
            customer=self.customer,
            address=self.address,
            service=self.service,
            scheduled_at=timezone.now() + timedelta(days=2),
            status=Booking.Status.ASSIGNED,
        )
        order = Order.objects.create(
            customer=self.customer,
            address=self.address,
            status=order_status,
            total_amount="500.00",
        )
        OrderItem.objects.create(
            order=order,
            booking=booking,
            line_total="500.00",
        )
        return order

    def test_order_detail_does_not_reopen_terminal_order(self):
        order = self._create_order(Order.Status.CANCELLED)

        response = self.client.get(f"/api/v1/bookings/orders/{order.pk}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], Order.Status.CANCELLED)
        self.assertFalse(response.data["ready_for_payment"])
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)

    def test_order_detail_does_not_advance_order_status_on_read(self):
        order = self._create_order(Order.Status.AWAITING_ASSIGNMENT)

        response = self.client.get(f"/api/v1/bookings/orders/{order.pk}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], Order.Status.AWAITING_ASSIGNMENT)
        self.assertFalse(response.data["ready_for_payment"])
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.AWAITING_ASSIGNMENT)

    def test_order_list_does_not_advance_order_status_on_read(self):
        order = self._create_order(Order.Status.AWAITING_ASSIGNMENT)

        response = self.client.get("/api/v1/bookings/orders/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]["status"], Order.Status.AWAITING_ASSIGNMENT)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.AWAITING_ASSIGNMENT)


class MultiServiceCheckoutAPITest(BookingAPITestMixin, TestCase):
    def setUp(self):
        self.client = APIClient()
        self.customer = self._create_user("+919876543288")
        self.client.force_authenticate(user=self.customer)
        self.category = Category.objects.create(title="Cleaning", slug="checkout-cleaning")
        self.service = self._create_service(self.category, title="Deep Home Cleaning")
        self.variant = self._create_variant(self.service, price=1000, mrp=1200)
        self.address = self._create_address(self.customer)
        CityService.objects.update_or_create(
            city=self.address.zone.city,
            service=self.service,
            defaults={"is_active": True},
        )
        self.cart = CustomerCart.objects.create(customer=self.customer, address=self.address)
        self.cart_item = CartItem.objects.create(
            cart=self.cart,
            service=self.service,
            variant=self.variant,
            quantity=2,
            pricing_snapshot={"line_total": "2000.00"},
        )

    def test_split_payment_checkout_is_explicit_and_defers_dispatch(self):
        from apps.payments.models import BookingFinancialPlan

        scheduled_at = (timezone.now() + timedelta(days=2)).isoformat()
        response = self.client.post(
            "/api/v1/bookings/cart/checkout/",
            {
                "payment_flow": "split_v1",
                "items": [{
                    "cart_item_id": self.cart_item.id,
                    "scheduled_at": scheduled_at,
                }],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        order = Order.objects.get(pk=response.data["order_id"])
        booking = Booking.objects.get(pk=response.data["items"][0]["booking_id"])
        self.assertEqual(order.status, Order.Status.AWAITING_PAYMENT)
        self.assertTrue(BookingFinancialPlan.objects.filter(booking=booking).exists())
        self.assertTrue(response.data["payment_required"])
        self.assertEqual(response.data["dispatch"], [])
    def test_checkout_dispatches_offer_to_eligible_worker(self):
        worker_user = self._create_user("+919876543299")
        worker = WorkerProfile.objects.create(
            user=worker_user,
            status=WorkerProfile.Status.APPROVED,
            is_online=True,
        )
        WorkerService.objects.create(worker=worker, service=self.service)
        WorkerZone.objects.create(worker=worker, zone=self.address.zone)
        scheduled_at = timezone.localtime(
            timezone.now() + timedelta(days=2)
        ).replace(hour=10, minute=0, second=0, microsecond=0)
        local_scheduled_at = timezone.localtime(scheduled_at)
        WorkerSchedule.objects.create(
            worker=worker,
            weekday=local_scheduled_at.weekday(),
            is_active=True,
            start_time=time(0, 0),
            end_time=time(23, 59),
        )

        response = self.client.post(
            "/api/v1/bookings/cart/checkout/",
            {
                "items": [{
                    "cart_item_id": self.cart_item.id,
                    "scheduled_at": scheduled_at.isoformat(),
                }]
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        booking_id = response.data["items"][0]["booking_id"]
        self.assertEqual(
            WorkerOffer.objects.filter(booking_id=booking_id, worker=worker).count(),
            1,
        )
        self.assertEqual(response.data["dispatch"][0]["offers_sent"], 1)

    def test_checkout_creates_one_parent_order_and_booking_line(self):
        scheduled_at = (timezone.now() + timedelta(days=2)).isoformat()
        response = self.client.post(
            "/api/v1/bookings/cart/checkout/",
            {
                "items": [
                    {
                        "cart_item_id": self.cart_item.id,
                        "scheduled_at": scheduled_at,
                    }
                ]
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        order = Order.objects.get(pk=response.data["order_id"], customer=self.customer)
        self.assertEqual(order.items.count(), 1)
        order_item = order.items.select_related("booking").get()
        self.assertEqual(order_item.quantity, 2)
        self.assertEqual(order_item.booking.service, self.service)
        self.assertEqual(order_item.booking.address, self.address)
        self.assertEqual(order.status, Order.Status.AWAITING_ASSIGNMENT)
        self.assertFalse(self.cart.items.exists())

    def test_checkout_requires_schedule_for_every_cart_item(self):
        response = self.client.post(
            "/api/v1/bookings/cart/checkout/",
            {"items": []},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertTrue(self.cart.items.exists())

    def test_checkout_rejects_duplicate_cart_item_ids(self):
        scheduled_at = (timezone.now() + timedelta(days=2)).isoformat()
        response = self.client.post(
            "/api/v1/bookings/cart/checkout/",
            {
                "items": [
                    {"cart_item_id": self.cart_item.id, "scheduled_at": scheduled_at},
                    {"cart_item_id": self.cart_item.id, "scheduled_at": scheduled_at},
                ]
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Duplicate cart_item_id", response.data["detail"])
        self.assertTrue(self.cart.items.filter(pk=self.cart_item.id).exists())
        self.assertFalse(Order.objects.filter(customer=self.customer).exists())

    def test_checkout_reprices_addon_quantities_on_server(self):
        addon = AddOn.objects.create(
            service=self.service,
            title="Extra room",
            mrp=150,
            price=100,
        )
        self.cart_item.addon_selections = [{"id": addon.id, "quantity": 3}]
        self.cart_item.save(update_fields=["addon_selections", "updated_at"])

        response = self.client.post(
            "/api/v1/bookings/cart/checkout/",
            {
                "items": [{
                    "cart_item_id": self.cart_item.id,
                    "scheduled_at": (timezone.now() + timedelta(days=2)).isoformat(),
                }]
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        order = Order.objects.get(pk=response.data["order_id"])
        order_item = order.items.select_related("booking").get()
        # (variant 1000 + 3 x addon 100) x quantity 2, plus 18% GST.
        self.assertEqual(order_item.line_subtotal, Decimal("2600.00"))
        self.assertEqual(order_item.tax_amount, Decimal("468.00"))
        self.assertEqual(order_item.line_total, Decimal("3068.00"))
        booking_addon = order_item.booking.booking_addons.get(addon=addon)
        self.assertEqual(booking_addon.quantity, 3)
        self.assertEqual(booking_addon.total_price, Decimal("300.00"))

    def test_parent_order_booking_line_cannot_be_confirmed_independently(self):
        scheduled_at = (timezone.now() + timedelta(days=2)).isoformat()
        checkout = self.client.post(
            "/api/v1/bookings/cart/checkout/",
            {"items": [{"cart_item_id": self.cart_item.id, "scheduled_at": scheduled_at}]},
            format="json",
        )
        self.assertEqual(checkout.status_code, 201, checkout.data)
        booking_id = checkout.data["items"][0]["booking_id"]

        response = self.client.post(
            f"/api/v1/bookings/{booking_id}/confirm/",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("parent order", response.data["detail"].lower())
        self.assertFalse(WorkerOffer.objects.filter(booking_id=booking_id, order__isnull=True).exists())

    def test_checkout_rejects_overlapping_service_windows_before_creating_order(self):
        second_service = self._create_service(self.category, title="Bathroom Cleaning")
        second_variant = self._create_variant(second_service, price=500, mrp=600)
        CityService.objects.update_or_create(
            city=self.address.zone.city,
            service=second_service,
            defaults={"is_active": True},
        )
        second_item = CartItem.objects.create(
            cart=self.cart,
            service=second_service,
            variant=second_variant,
            quantity=1,
            pricing_snapshot={"line_total": "500.00"},
        )
        same_time = (timezone.now() + timedelta(days=2)).isoformat()

        response = self.client.post(
            "/api/v1/bookings/cart/checkout/",
            {"items": [
                {"cart_item_id": self.cart_item.id, "scheduled_at": same_time},
                {"cart_item_id": second_item.id, "scheduled_at": same_time},
            ]},
            format="json",
        )

        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(response.data["code"], "order_schedule_overlap")
        self.assertFalse(Order.objects.filter(customer=self.customer).exists())
        self.assertFalse(Booking.objects.filter(customer=self.customer).exists())
        self.assertEqual(self.cart.items.count(), 2)

    def test_multi_service_dispatch_only_offers_worker_eligible_for_every_line(self):
        second_service = self._create_service(self.category, title="Bathroom Cleaning")
        second_variant = self._create_variant(second_service, price=500, mrp=600)
        partial_user = self._create_user("+919876543281")
        full_user = self._create_user("+919876543282")
        partial_worker = WorkerProfile.objects.create(
            user=partial_user, status=WorkerProfile.Status.APPROVED, is_online=True
        )
        full_worker = WorkerProfile.objects.create(
            user=full_user, status=WorkerProfile.Status.APPROVED, is_online=True
        )
        for worker, services in (
            (partial_worker, [self.service]),
            (full_worker, [self.service, second_service]),
        ):
            WorkerZone.objects.create(worker=worker, zone=self.address.zone)
            for service in services:
                WorkerService.objects.create(worker=worker, service=service)
            for weekday in range(7):
                WorkerSchedule.objects.create(
                    worker=worker, weekday=weekday, is_active=True,
                    start_time=time(0, 0), end_time=time(23, 59),
                )
        second_item = CartItem.objects.create(
            cart=self.cart, service=second_service, variant=second_variant,
            quantity=1, pricing_snapshot={"line_total": "500.00"},
        )
        first_time = timezone.localtime(
            timezone.now() + timedelta(days=2)
        ).replace(hour=10, minute=0, second=0, microsecond=0)
        second_time = timezone.localtime(
            timezone.now() + timedelta(days=3)
        ).replace(hour=10, minute=0, second=0, microsecond=0)
        response = self.client.post(
            "/api/v1/bookings/cart/checkout/",
            {"items": [
                {"cart_item_id": self.cart_item.id, "scheduled_at": first_time.isoformat()},
                {"cart_item_id": second_item.id, "scheduled_at": second_time.isoformat()},
            ]},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        order = Order.objects.get(pk=response.data["order_id"])
        offers = WorkerOffer.objects.filter(order=order)
        self.assertEqual(offers.count(), 1)
        self.assertEqual(offers.get().worker, full_worker)
        self.assertFalse(WorkerOffer.objects.filter(order=order, worker=partial_worker).exists())

    def test_one_worker_accepts_and_is_assigned_to_every_order_line(self):
        second_service = self._create_service(self.category, title="Bathroom Cleaning")
        second_variant = self._create_variant(second_service, price=500, mrp=600)
        worker_user = self._create_user("+919876543283")
        worker = WorkerProfile.objects.create(
            user=worker_user, status=WorkerProfile.Status.APPROVED, is_online=True
        )
        WorkerZone.objects.create(worker=worker, zone=self.address.zone)
        for service in (self.service, second_service):
            WorkerService.objects.create(worker=worker, service=service)
        for weekday in range(7):
            WorkerSchedule.objects.create(
                worker=worker, weekday=weekday, is_active=True,
                start_time=time(0, 0), end_time=time(23, 59),
            )
        second_item = CartItem.objects.create(
            cart=self.cart, service=second_service, variant=second_variant,
            quantity=1, pricing_snapshot={"line_total": "500.00"},
        )
        first_time = timezone.localtime(
            timezone.now() + timedelta(days=2)
        ).replace(hour=10, minute=0, second=0, microsecond=0)
        second_time = timezone.localtime(
            timezone.now() + timedelta(days=3)
        ).replace(hour=10, minute=0, second=0, microsecond=0)
        response = self.client.post(
            "/api/v1/bookings/cart/checkout/",
            {"items": [
                {"cart_item_id": self.cart_item.id, "scheduled_at": first_time.isoformat()},
                {"cart_item_id": second_item.id, "scheduled_at": second_time.isoformat()},
            ]},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        order = Order.objects.get(pk=response.data["order_id"])
        offer = WorkerOffer.objects.get(order=order, worker=worker)
        worker_client = APIClient()
        worker_client.force_authenticate(user=worker_user)
        accepted = worker_client.post(f"/api/v1/workers/offers/{offer.pk}/accept/", {}, format="json")
        self.assertEqual(accepted.status_code, 200, accepted.data)
        self.assertEqual(BookingAssignment.objects.filter(booking__order_item__order=order).count(), 2)
        self.assertEqual(
            set(BookingAssignment.objects.filter(booking__order_item__order=order).values_list("worker_id", flat=True)),
            {worker.pk},
        )
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.AWAITING_PAYMENT)

    def test_checkout_creates_multiple_service_lines_in_one_order(self):
        second_service = self._create_service(
            self.category,
            title="Bathroom Cleaning",
        )
        second_variant = self._create_variant(second_service, price=500, mrp=600)
        CityService.objects.update_or_create(
            city=self.address.zone.city,
            service=second_service,
            defaults={"is_active": True},
        )
        second_item = CartItem.objects.create(
            cart=self.cart,
            service=second_service,
            variant=second_variant,
            quantity=1,
            pricing_snapshot={"line_total": "500.00"},
        )

        response = self.client.post(
            "/api/v1/bookings/cart/checkout/",
            {
                "items": [
                    {
                        "cart_item_id": self.cart_item.id,
                        "scheduled_at": (timezone.now() + timedelta(days=2)).isoformat(),
                    },
                    {
                        "cart_item_id": second_item.id,
                        "scheduled_at": (timezone.now() + timedelta(days=3)).isoformat(),
                    },
                ]
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        order = Order.objects.get(pk=response.data["order_id"])
        self.assertEqual(order.items.count(), 2)
        self.assertEqual(
            set(order.items.values_list("booking__service_id", flat=True)),
            {self.service.id, second_service.id},
        )
        self.assertFalse(self.cart.items.exists())

class ParentOrderLineCancellationTests(BookingAPITestMixin, TestCase):
    """Regression coverage for split-payment parent-order line cancellation."""

    def setUp(self):
        self.client = APIClient()
        self.customer = self._create_user("+919876543288")
        self.client.force_authenticate(user=self.customer)
        self.category = Category.objects.create(
            title="Line Cancellation", slug="line-cancellation",
        )
        self.service = self._create_service(
            self.category, title="Line Cancellation Cleaning",
        )
        self.variant = self._create_variant(
            self.service, price=1000, mrp=1200,
        )
        self.address = self._create_address(self.customer)
        CityService.objects.update_or_create(
            city=self.address.zone.city,
            service=self.service,
            defaults={"is_active": True},
        )
        self.cart = CustomerCart.objects.create(
            customer=self.customer, address=self.address,
        )
        self.first_cart_item = CartItem.objects.create(
            cart=self.cart, service=self.service, variant=self.variant,
            quantity=1, pricing_snapshot={"line_total": "1000.00"},
        )
        self.second_service = self._create_service(
            self.category, title="Line Cancellation Bathroom",
        )
        self.second_variant = self._create_variant(
            self.second_service, price=500, mrp=600,
        )
        CityService.objects.update_or_create(
            city=self.address.zone.city,
            service=self.second_service,
            defaults={"is_active": True},
        )
        self.second_cart_item = CartItem.objects.create(
            cart=self.cart, service=self.second_service,
            variant=self.second_variant, quantity=1,
            pricing_snapshot={"line_total": "500.00"},
        )

    def _create_paid_split_order(self, *, wallet_tender="100.00"):
        from apps.payments.models import (
            BookingFinancialPlan, Payment, PaymentAllocation,
            PaymentInstallment,
        )

        first_time = timezone.localtime(
            timezone.now() + timedelta(days=2),
        ).replace(hour=10, minute=0, second=0, microsecond=0)
        second_time = timezone.localtime(
            timezone.now() + timedelta(days=3),
        ).replace(hour=10, minute=0, second=0, microsecond=0)
        response = self.client.post(
            "/api/v1/bookings/cart/checkout/",
            {
                "payment_flow": "split_v1",
                "items": [
                    {"cart_item_id": self.first_cart_item.pk, "scheduled_at": first_time.isoformat()},
                    {"cart_item_id": self.second_cart_item.pk, "scheduled_at": second_time.isoformat()},
                ],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        order = Order.objects.get(pk=response.data["order_id"])
        items = list(order.items.select_related("booking").order_by("id"))
        plans = [
            BookingFinancialPlan.objects.get(booking=item.booking)
            for item in items
        ]
        wallet_remaining = Decimal(wallet_tender)
        advance_total = sum(
            (plan.advance_due for plan in plans), Decimal("0.00"),
        )
        self.assertLessEqual(wallet_remaining, advance_total)
        payment = Payment.objects.create(
            order=order,
            customer=self.customer,
            amount=advance_total - wallet_remaining,
            wallet_amount=wallet_remaining,
            method=Payment.Method.RAZORPAY,
            status=Payment.Status.PAID,
            razorpay_payment_id="pay_parent_order_advance",
        )
        for plan in plans:
            installment = PaymentInstallment.objects.get(
                financial_plan=plan,
                kind=PaymentInstallment.Kind.ADVANCE,
            )
            wallet_part = min(installment.amount_due, wallet_remaining)
            wallet_remaining -= wallet_part
            gateway_part = installment.amount_due - wallet_part
            PaymentAllocation.objects.create(
                payment=payment,
                installment=installment,
                amount=installment.amount_due,
                gateway_amount=gateway_part,
                wallet_amount=wallet_part,
            )
            installment.amount_captured = installment.amount_due
            installment.status = PaymentInstallment.Status.PAID
            installment.settled_at = timezone.now()
            installment.save(update_fields=[
                "amount_captured", "status", "settled_at", "updated_at",
            ])
            plan.advance_captured = installment.amount_due
            plan.save(update_fields=["advance_captured", "updated_at"])
        self.assertEqual(wallet_remaining, Decimal("0.00"))
        order.status = Order.Status.AWAITING_ASSIGNMENT
        order.save(update_fields=["status", "updated_at"])
        return order, items, plans, payment

    def test_partial_cancellation_refunds_only_line_and_preserves_other_order_line(self):
        from unittest.mock import patch
        from apps.payments.models import RefundRecord

        order, items, plans, payment = self._create_paid_split_order()
        cancelled_item, remaining_item = items
        cancelled_plan = plans[0]
        allocation = cancelled_plan.installments.get(
            kind="advance",
        ).payment_allocations.get(payment=payment)

        with patch("razorpay.Client") as client_class, patch(
            "apps.bookings.dispatcher.DispatcherService.dispatch_order",
            return_value=[],
        ):
            client_class.return_value.payment.refund.return_value = {
                "id": "rfnd_parent_line_1",
                "status": "pending",
            }
            response = self.client.post(
                f"/api/v1/bookings/orders/{order.pk}/items/{cancelled_item.booking_id}/cancel/",
                {"reason": "Customer changed plans"},
                format="json",
            )

        self.assertEqual(response.status_code, 200, response.data)
        cancelled_item.booking.refresh_from_db()
        remaining_item.booking.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(cancelled_item.booking.status, Booking.Status.CANCELLED)
        self.assertNotEqual(remaining_item.booking.status, Booking.Status.CANCELLED)
        self.assertEqual(order.status, Order.Status.AWAITING_ASSIGNMENT)
        self.assertEqual(
            Decimal(response.data["refund_amount"]),
            allocation.amount - Decimal("40.00"),
        )
        refund = RefundRecord.objects.get(booking=cancelled_item.booking)
        self.assertEqual(refund.payment_allocation_id, allocation.pk)
        self.assertEqual(
            refund.gateway_refund_amount + refund.wallet_refund_amount,
            refund.refund_amount,
        )
        self.assertEqual(refund.wallet_refund_amount, allocation.wallet_amount - Decimal("40.00"))
        self.assertEqual(client_class.return_value.payment.refund.call_count, 1)

    def test_repeated_line_cancellation_returns_existing_refund_without_resubmitting(self):
        from unittest.mock import patch
        from apps.payments.models import RefundRecord

        order, items, plans, _payment = self._create_paid_split_order()
        booking = items[0].booking

        with patch("razorpay.Client") as client_class, patch(
            "apps.bookings.dispatcher.DispatcherService.dispatch_order",
            return_value=[],
        ):
            client_class.return_value.payment.refund.return_value = {
                "id": "rfnd_parent_line_replay",
                "status": "pending",
            }
            first = self.client.post(
                f"/api/v1/bookings/orders/{order.pk}/items/{booking.pk}/cancel/",
                {"reason": "First request"},
                format="json",
            )
            second = self.client.post(
                f"/api/v1/bookings/orders/{order.pk}/items/{booking.pk}/cancel/",
                {"reason": "Network retry"},
                format="json",
            )

        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual(second.status_code, 200, second.data)
        self.assertTrue(second.data["idempotent_replay"])
        self.assertEqual(first.data["refund_id"], second.data["refund_id"])
        self.assertEqual(RefundRecord.objects.filter(booking=booking).count(), 1)
        self.assertEqual(client_class.return_value.payment.refund.call_count, 1)

    def test_dispatch_failure_does_not_fail_committed_cancellation_or_skip_refund(self):
        from unittest.mock import patch
        from apps.payments.models import RefundRecord

        order, items, _plans, _payment = self._create_paid_split_order()
        booking = items[0].booking

        with patch(
            "apps.bookings.dispatcher.DispatcherService.dispatch_order",
            side_effect=RuntimeError("temporary dispatch outage"),
        ), patch("razorpay.Client") as client_class:
            client_class.return_value.payment.refund.return_value = {
                "id": "rfnd_dispatch_outage",
                "status": "pending",
            }
            response = self.client.post(
                f"/api/v1/bookings/orders/{order.pk}/items/{booking.pk}/cancel/",
                {"reason": "Customer changed plans"},
                format="json",
            )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["dispatch_pending"])
        booking.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CANCELLED)
        self.assertEqual(order.status, Order.Status.AWAITING_ASSIGNMENT)
        refund = RefundRecord.objects.get(booking=booking)
        self.assertEqual(refund.provider_refund_id, "rfnd_dispatch_outage")
        self.assertEqual(client_class.return_value.payment.refund.call_count, 1)


