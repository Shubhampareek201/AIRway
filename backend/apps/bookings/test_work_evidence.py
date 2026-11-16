from datetime import timedelta
from io import BytesIO
from tempfile import TemporaryDirectory

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from apps.accounts.models import Address, User
from apps.bookings.models import Booking, BookingAssignment, BookingWorkEvidence
from apps.catalog.models import Category, Service
from apps.core.models import City, Zone
from apps.workers.models import WorkerProfile


def evidence_jpeg():
    buffer = BytesIO()
    Image.new("RGB", (32, 32), color=(40, 120, 80)).save(buffer, format="JPEG")
    return buffer.getvalue()


class BookingWorkEvidenceTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(phone="+919876543821", password="password123")
        self.worker_user = User.objects.create_user(phone="+919876543822", password="password123")
        self.other_user = User.objects.create_user(phone="+919876543823", password="password123")
        self.worker = WorkerProfile.objects.create(
            user=self.worker_user, status=WorkerProfile.Status.APPROVED
        )
        city = City.objects.create(name="Evidence Test City", state="Rajasthan")
        zone = Zone.objects.create(name="Evidence Test Zone", city=city, is_active=True)
        address = Address.objects.create(
            user=self.customer, label="Home", house_details="House 1",
            full_address="Evidence Test Address", zone=zone,
        )
        category = Category.objects.create(title="Cleaning", slug="evidence-test-cleaning")
        service = Service.objects.create(
            category=category, title="Cleaning", booking_mode=Service.BookingMode.SCHEDULED,
            pricing_type=Service.PricingType.FIXED,
        )
        self.booking = Booking.objects.create(
            customer=self.customer, address=address, service=service,
            scheduled_at=timezone.now() + timedelta(days=1),
            status=Booking.Status.IN_PROGRESS,
        )
        self.assignment = BookingAssignment.objects.create(
            booking=self.booking, worker=self.worker, started_at=timezone.now()
        )
        self.worker_client = APIClient()
        self.worker_client.force_authenticate(self.worker_user)
        self.customer_client = APIClient()
        self.customer_client.force_authenticate(self.customer)

    def test_assigned_worker_can_upload_private_before_and_after_evidence(self):
        with TemporaryDirectory() as private_root, override_settings(PRIVATE_UPLOAD_ROOT=private_root):
            url = f"/api/v1/workers/jobs/{self.assignment.id}/evidence/"
            before = self.worker_client.post(
                url,
                {"stage": "before", "note": "Original condition", "photo": SimpleUploadedFile("before.jpg", evidence_jpeg(), content_type="image/jpeg")},
                format="multipart",
            )
            self.assertEqual(before.status_code, 201, before.data)
            after = self.worker_client.post(
                url,
                {"stage": "after", "note": "Completed work", "photo": SimpleUploadedFile("after.jpg", evidence_jpeg(), content_type="image/jpeg")},
                format="multipart",
            )
            self.assertEqual(after.status_code, 201, after.data)
            self.assertEqual(
                set(BookingWorkEvidence.objects.filter(booking=self.booking).values_list("stage", flat=True)),
                {"before", "after"},
            )
            photo = self.customer_client.get(
                f"/api/v1/bookings/work-evidence/{before.data['id']}/photo/"
            )
            self.assertEqual(photo.status_code, 200)
            self.assertEqual(photo["Cache-Control"], "private, no-store")

            other_client = APIClient()
            other_client.force_authenticate(self.other_user)
            denied = other_client.get(
                f"/api/v1/bookings/work-evidence/{before.data['id']}/photo/"
            )
            self.assertEqual(denied.status_code, 404)

    def test_unassigned_worker_cannot_upload_evidence(self):
        other_client = APIClient()
        other_client.force_authenticate(self.other_user)
        response = other_client.post(
            f"/api/v1/workers/jobs/{self.assignment.id}/evidence/",
            {"stage": "before", "photo": SimpleUploadedFile("before.jpg", evidence_jpeg(), content_type="image/jpeg")},
            format="multipart",
        )
        self.assertEqual(response.status_code, 404)
