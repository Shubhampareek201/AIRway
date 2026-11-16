from datetime import timedelta
from io import BytesIO
from tempfile import TemporaryDirectory

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from apps.accounts.models import Address, User
from apps.bookings.models import Booking, CartItem, CustomerCart
from apps.catalog.models import Category, FormField, Service, ServiceVariant
from apps.core.models import City, Zone


def valid_jpeg():
    buffer = BytesIO()
    Image.new("RGB", (32, 32), color=(120, 80, 40)).save(buffer, format="JPEG")
    return buffer.getvalue()


class DynamicServicePhotoUploadTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            phone="+919876543811", password="password123"
        )
        self.other_user = User.objects.create_user(
            phone="+919876543812", password="password123"
        )
        self.city = City.objects.create(name="Photo Test City", state="Rajasthan")
        self.zone = Zone.objects.create(name="Photo Test Zone", city=self.city, is_active=True)
        self.address = Address.objects.create(
            user=self.customer,
            label="Home",
            house_details="House 1",
            full_address="Photo Test Address",
            zone=self.zone,
        )
        category = Category.objects.create(title="Home Cleaning", slug="photo-test-home")
        self.service = Service.objects.create(
            category=category,
            title="Cleaning with photo requirement",
            booking_mode=Service.BookingMode.SCHEDULED,
            pricing_type=Service.PricingType.FIXED,
        )
        self.photo_field = FormField.objects.create(
            service=self.service,
            key="room_photo",
            label="Room photo",
            field_type=FormField.FieldType.PHOTO,
            is_required=True,
        )
        self.cart = CustomerCart.objects.create(customer=self.customer)
        self.item = CartItem.objects.create(
            cart=self.cart,
            service=self.service,
            form_answers={},
        )
        self.client = APIClient()
        self.client.force_authenticate(self.customer)

    def test_customer_can_upload_and_replace_private_photo_for_configured_field(self):
        with TemporaryDirectory() as private_root, override_settings(PRIVATE_UPLOAD_ROOT=private_root):
            url = f"/api/v1/bookings/cart/items/{self.item.id}/form-photos/{self.photo_field.key}/"
            first = self.client.post(
                url,
                {"photo": SimpleUploadedFile("room.jpg", valid_jpeg(), content_type="image/jpeg")},
                format="multipart",
            )
            self.assertEqual(first.status_code, 200, first.data)
            self.item.refresh_from_db()
            first_path = self.item.category_answers["_airway_form_photos"]["room_photo"]
            self.assertEqual(self.item.form_answers["room_photo"], "uploaded")

            second = self.client.post(
                url,
                {"photo": SimpleUploadedFile("room-new.jpg", valid_jpeg(), content_type="image/jpeg")},
                format="multipart",
            )
            self.assertEqual(second.status_code, 200, second.data)
            self.item.refresh_from_db()
            second_path = self.item.category_answers["_airway_form_photos"]["room_photo"]
            self.assertNotEqual(first_path, second_path)

            deleted = self.client.delete(url)
            self.assertEqual(deleted.status_code, 200, deleted.data)
            self.item.refresh_from_db()
            self.assertNotIn("_airway_form_photos", self.item.category_answers)
            self.assertNotIn("room_photo", self.item.form_answers)

    def test_customer_cannot_upload_photo_for_another_services_field(self):
        response = self.client.post(
            f"/api/v1/bookings/cart/items/{self.item.id}/form-photos/not-configured/",
            {"photo": SimpleUploadedFile("room.jpg", valid_jpeg(), content_type="image/jpeg")},
            format="multipart",
        )
        self.assertEqual(response.status_code, 404)

    def test_hiding_a_conditional_photo_question_removes_its_private_file(self):
        from django.core.files.base import ContentFile
        from django.core.files.storage import FileSystemStorage
        from apps.bookings.serializers import CartItemSerializer

        choice = FormField.objects.create(
            service=self.service,
            key="room_type",
            label="Room type",
            field_type=FormField.FieldType.SELECT,
            options=[{"label": "Kitchen", "value": "kitchen"}, {"label": "Bathroom", "value": "bathroom"}],
            is_required=True,
        )
        self.photo_field.visibility_rules = [
            {"field": "room_type", "operator": "equals", "value": "kitchen"}
        ]
        self.photo_field.save(update_fields=["visibility_rules", "updated_at"])

        variant = ServiceVariant.objects.create(
            service=self.service, title="Standard", mrp="100.00", price="100.00"
        )
        with TemporaryDirectory() as private_root, override_settings(PRIVATE_UPLOAD_ROOT=private_root):
            storage = FileSystemStorage(location=private_root)
            stored_path = storage.save(
                "booking_form_photos/customer/cart_item/room_photo/test.jpg",
                ContentFile(valid_jpeg()),
            )
            self.item.form_answers = {"room_type": "kitchen", "room_photo": "uploaded"}
            self.item.category_answers = {"_airway_form_photos": {"room_photo": stored_path}}
            self.item.save(update_fields=["form_answers", "category_answers", "updated_at"])

            serializer = CartItemSerializer(
                self.item,
                data={"variant": variant.id, "form_answers": {"room_type": "bathroom"}, "category_answers": {}},
                partial=True,
                context={"allow_incomplete": True},
            )
            self.assertTrue(serializer.is_valid(), serializer.errors)
            updated = serializer.save()
            self.assertNotIn("room_photo", updated.form_answers)
            self.assertNotIn("_airway_form_photos", updated.category_answers)
            self.assertFalse(storage.exists(stored_path))

    def test_private_photo_url_is_available_only_to_booking_customer_or_assigned_worker(self):
        with TemporaryDirectory() as private_root, override_settings(PRIVATE_UPLOAD_ROOT=private_root):
            from django.core.files.storage import FileSystemStorage
            storage = FileSystemStorage(location=private_root)
            path = storage.save("booking_form_photos/test/room.jpg", SimpleUploadedFile(
                "room.jpg", valid_jpeg(), content_type="image/jpeg"
            ))
            booking = Booking.objects.create(
                customer=self.customer,
                address=self.address,
                service=self.service,
                scheduled_at=timezone.now() + timedelta(days=1),
                customer_answers={"_airway_form_photos": {"room_photo": path}},
            )
            url = f"/api/v1/bookings/issue-photos/{booking.id}/?field_key=room_photo"

            customer_response = self.client.get(url)
            self.assertEqual(customer_response.status_code, 200)
            self.assertEqual(customer_response["Cache-Control"], "private, no-store")

            other_client = APIClient()
            other_client.force_authenticate(self.other_user)
            denied = other_client.get(url)
            self.assertEqual(denied.status_code, 404)
