from datetime import timedelta, time
from decimal import Decimal
from io import BytesIO
from tempfile import TemporaryDirectory

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Address, User
from apps.bookings.models import Booking, BookingAssignment, BookingDispute, BookingDisputeEvidence, BookingReworkProposal
from apps.catalog.models import Category, Service
from apps.core.models import City, Zone
from apps.workers.models import WorkerProfile, WorkerSchedule, WorkerService, WorkerZone, WorkerEarning
from PIL import Image


class BookingDisputeAPITests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            phone="+919876542001", password="password123"
        )
        self.worker_user = User.objects.create_user(
            phone="+919876542002", password="password123"
        )
        self.other_user = User.objects.create_user(
            phone="+919876542003", password="password123"
        )
        self.staff_user = User.objects.create_user(
            phone="+919876542004", password="password123", is_staff=True
        )
        city = City.objects.create(name="Dispute Test City", state="Rajasthan")
        zone = Zone.objects.create(name="Dispute Test Zone", city=city, is_active=True)
        self.zone = zone
        address = Address.objects.create(
            user=self.customer,
            label="Home",
            house_details="House 1",
            full_address="Dispute Test Address",
            zone=zone,
        )
        category = Category.objects.create(
            title="Dispute Test", slug="dispute-test-category"
        )
        service = Service.objects.create(
            category=category,
            title="Test Service",
            booking_mode=Service.BookingMode.SCHEDULED,
            pricing_type=Service.PricingType.FIXED,
            is_active=True,
        )
        self.booking = Booking.objects.create(
            customer=self.customer,
            address=address,
            service=service,
            scheduled_at=timezone.now() - timedelta(hours=1),
            status=Booking.Status.IN_PROGRESS,
        )
        self.worker = WorkerProfile.objects.create(
            user=self.worker_user,
            status=WorkerProfile.Status.APPROVED,
        )
        self.assignment = BookingAssignment.objects.create(
            booking=self.booking,
            worker=self.worker,
            started_at=timezone.now() - timedelta(minutes=30),
        )
        self.customer_client = APIClient()
        self.customer_client.force_authenticate(self.customer)
        self.worker_client = APIClient()
        self.worker_client.force_authenticate(self.worker_user)
        self.other_client = APIClient()
        self.other_client.force_authenticate(self.other_user)
        self.staff_client = APIClient()
        self.staff_client.force_authenticate(self.staff_user)

    def _payload(self):
        return {
            "booking_id": self.booking.pk,
            "category": BookingDispute.Category.SERVICE_QUALITY,
            "description": "The service was not completed to the agreed standard.",
            "requested_outcome": BookingDispute.RequestedOutcome.REWORK,
            "evidence_items": [
                {"label": "Area", "detail": "Kitchen counter was not cleaned."}
            ],
        }

    def test_customer_can_raise_dispute_and_worker_can_view_it(self):
        response = self.customer_client.post(
            "/api/v1/bookings/disputes/", self._payload(), format="json"
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["raised_by_role"], "customer")
        detail = self.worker_client.get(
            f"/api/v1/bookings/disputes/{response.data['id']}/"
        )
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["booking_id"], self.booking.pk)

    def test_assigned_worker_can_raise_dispute(self):
        response = self.worker_client.post(
            "/api/v1/bookings/disputes/", self._payload(), format="json"
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["raised_by_role"], "worker")

    def test_unrelated_user_cannot_raise_or_view_dispute(self):
        response = self.other_client.post(
            "/api/v1/bookings/disputes/", self._payload(), format="json"
        )
        self.assertEqual(response.status_code, 403)
        dispute = BookingDispute.objects.create(
            booking=self.booking,
            raised_by=self.customer,
            raised_by_role="customer",
            category=BookingDispute.Category.SERVICE_QUALITY,
            description="A dispute raised by the customer.",
            requested_outcome=BookingDispute.RequestedOutcome.INVESTIGATION,
        )
        detail = self.other_client.get(
            f"/api/v1/bookings/disputes/{dispute.pk}/"
        )
        self.assertEqual(detail.status_code, 403)

    def test_only_one_active_dispute_can_exist_for_booking(self):
        first = self.customer_client.post(
            "/api/v1/bookings/disputes/", self._payload(), format="json"
        )
        self.assertEqual(first.status_code, 201)
        second = self.worker_client.post(
            "/api/v1/bookings/disputes/", self._payload(), format="json"
        )
        self.assertEqual(second.status_code, 409)

    def test_completed_booking_has_seven_day_dispute_window(self):
        self.booking.status = Booking.Status.COMPLETED
        self.booking.completed_at = timezone.now() - timedelta(days=8)
        self.booking.save(update_fields=["status", "completed_at", "updated_at"])
        response = self.customer_client.post(
            "/api/v1/bookings/disputes/", self._payload(), format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("window has expired", response.data["detail"])

    def test_staff_must_supply_resolution_note_and_cannot_skip_review(self):
        created = self.customer_client.post(
            "/api/v1/bookings/disputes/", self._payload(), format="json"
        )
        dispute_id = created.data["id"]
        invalid = self.staff_client.patch(
            f"/api/v1/bookings/disputes/{dispute_id}/",
            {"status": BookingDispute.Status.CLOSED},
            format="json",
        )
        self.assertEqual(invalid.status_code, 400)
        missing_note = self.staff_client.patch(
            f"/api/v1/bookings/disputes/{dispute_id}/",
            {"status": BookingDispute.Status.RESOLVED},
            format="json",
        )
        self.assertEqual(missing_note.status_code, 400)
        in_review = self.staff_client.patch(
            f"/api/v1/bookings/disputes/{dispute_id}/",
            {"status": BookingDispute.Status.IN_REVIEW},
            format="json",
        )
        self.assertEqual(in_review.status_code, 200)
        resolved = self.staff_client.patch(
            f"/api/v1/bookings/disputes/{dispute_id}/",
            {
                "status": BookingDispute.Status.RESOLVED,
                "resolution_note": "A rework visit has been approved.",
            },
            format="json",
        )
        self.assertEqual(resolved.status_code, 200, resolved.data)
        self.assertEqual(resolved.data["status"], BookingDispute.Status.RESOLVED)

    def test_non_staff_cannot_change_dispute_status(self):
        dispute = BookingDispute.objects.create(
            booking=self.booking,
            raised_by=self.customer,
            raised_by_role="customer",
            category=BookingDispute.Category.PAYMENT,
            description="Payment concern.",
            requested_outcome=BookingDispute.RequestedOutcome.REFUND_REVIEW,
        )
        response = self.customer_client.patch(
            f"/api/v1/bookings/disputes/{dispute.pk}/",
            {"status": BookingDispute.Status.IN_REVIEW},
            format="json",
        )
        self.assertEqual(response.status_code, 403)



    def _resolved_rework_proposal(self):
        self.booking.pricing_snapshot = {"subtotal": "500.00", "tax": "90.00", "total": "590.00"}
        self.booking.save(update_fields=["pricing_snapshot", "updated_at"])
        self.worker.is_online = True
        self.worker.commission_rate = Decimal("20.00")
        self.worker.save(update_fields=["is_online", "updated_at"])
        WorkerService.objects.create(worker=self.worker, service=self.booking.service)
        WorkerZone.objects.create(worker=self.worker, zone=self.zone)
        scheduled_at = timezone.now() + timedelta(days=2)
        local_time = timezone.localtime(scheduled_at)
        WorkerSchedule.objects.create(
            worker=self.worker,
            weekday=local_time.weekday(),
            start_time=time(0, 0),
            end_time=time(23, 59),
        )
        dispute = BookingDispute.objects.create(
            booking=self.booking,
            raised_by=self.customer,
            raised_by_role="customer",
            category=BookingDispute.Category.SERVICE_QUALITY,
            description="The original service needs a correction visit.",
            requested_outcome=BookingDispute.RequestedOutcome.REWORK,
            status=BookingDispute.Status.RESOLVED,
            resolution_note="AIRway approved a no-charge recovery visit.",
            resolved_by=self.staff_user,
            resolved_at=timezone.now(),
        )
        return BookingReworkProposal.objects.create(
            dispute=dispute,
            worker=self.worker,
            scheduled_at=scheduled_at,
            created_by=self.staff_user,
        )

    def test_customer_acceptance_creates_zero_charge_assigned_rework_booking(self):
        proposal = self._resolved_rework_proposal()
        response = self.customer_client.post(
            f"/api/v1/bookings/disputes/{proposal.dispute_id}/rework-decision/",
            {"decision": "accept"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, BookingReworkProposal.Status.ACCEPTED)
        self.assertIsNotNone(proposal.followup_booking_id)
        followup = proposal.followup_booking
        self.assertEqual(followup.status, Booking.Status.ASSIGNED)
        self.assertEqual(followup.pricing_snapshot["total"], "0.00")
        self.assertEqual(followup.assignment.worker_id, self.worker.pk)
        self.assertIsNotNone(followup.assignment.accepted_at)
        self.assertTrue(followup.notes.startswith("No-charge AIRway service recovery"))


    def test_completed_rework_creates_airway_funded_worker_earning(self):
        proposal = self._resolved_rework_proposal()
        accepted = self.customer_client.post(
            f"/api/v1/bookings/disputes/{proposal.dispute_id}/rework-decision/",
            {"decision": "accept"},
            format="json",
        )
        self.assertEqual(accepted.status_code, 200, accepted.data)
        proposal.refresh_from_db()
        followup = proposal.followup_booking
        followup.status = Booking.Status.COMPLETED
        followup.completed_at = timezone.now()
        followup.save(update_fields=["status", "completed_at", "updated_at"])

        from apps.workers.earnings import sync_rework_worker_earning
        earning = sync_rework_worker_earning(followup.pk)

        self.assertIsNotNone(earning)
        self.assertEqual(earning.worker_id, self.worker.pk)
        self.assertEqual(earning.gross_amount, Decimal("500.00"))
        self.assertEqual(earning.commission_rate, Decimal("20.00"))
        self.assertEqual(earning.net_amount, Decimal("400.00"))
        self.assertIsNone(earning.payment_id)
        self.assertEqual(earning.status, WorkerEarning.Status.AVAILABLE)

    def test_customer_can_decline_rework_without_creating_booking(self):
        proposal = self._resolved_rework_proposal()
        response = self.customer_client.post(
            f"/api/v1/bookings/disputes/{proposal.dispute_id}/rework-decision/",
            {"decision": "decline"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, BookingReworkProposal.Status.DECLINED)
        self.assertIsNone(proposal.followup_booking_id)

    def test_unrelated_user_cannot_accept_rework_proposal(self):
        proposal = self._resolved_rework_proposal()
        response = self.other_client.post(
            f"/api/v1/bookings/disputes/{proposal.dispute_id}/rework-decision/",
            {"decision": "accept"},
            format="json",
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Booking.objects.filter(rework_source__dispute=proposal.dispute).exists())

    def test_rework_acceptance_rechecks_worker_availability(self):
        proposal = self._resolved_rework_proposal()
        self.worker.is_online = False
        self.worker.save(update_fields=["is_online", "updated_at"])
        response = self.customer_client.post(
            f"/api/v1/bookings/disputes/{proposal.dispute_id}/rework-decision/",
            {"decision": "accept"},
            format="json",
        )
        self.assertEqual(response.status_code, 409)
        proposal.refresh_from_db()
        self.assertEqual(proposal.status, BookingReworkProposal.Status.EXPIRED)
        self.assertIsNone(proposal.followup_booking_id)

    def test_dispute_evidence_is_private_and_available_to_booking_participants(self):
        created = self.customer_client.post(
            "/api/v1/bookings/disputes/", self._payload(), format="json"
        )
        dispute_id = created.data["id"]
        buffer = BytesIO()
        Image.new("RGB", (32, 32), color=(40, 120, 80)).save(buffer, format="JPEG")
        image_bytes = buffer.getvalue()

        with TemporaryDirectory() as private_root, override_settings(PRIVATE_UPLOAD_ROOT=private_root):
            uploaded = self.customer_client.post(
                f"/api/v1/bookings/disputes/{dispute_id}/evidence/",
                {
                    "file": SimpleUploadedFile(
                        "evidence.jpg", image_bytes, content_type="image/jpeg"
                    ),
                    "note": "Counter condition after service",
                },
                format="multipart",
            )
            self.assertEqual(uploaded.status_code, 201, uploaded.data)
            evidence_id = uploaded.data["id"]
            evidence = BookingDisputeEvidence.objects.get(pk=evidence_id)
            self.assertNotIn(private_root, evidence.file_path)
            self.assertTrue(evidence.file_path.startswith("booking_dispute_evidence/"))

            customer_photo = self.customer_client.get(
                f"/api/v1/bookings/dispute-evidence/{evidence_id}/photo/"
            )
            self.assertEqual(customer_photo.status_code, 200)
            self.assertEqual(customer_photo["Cache-Control"], "private, no-store")

            worker_photo = self.worker_client.get(
                f"/api/v1/bookings/dispute-evidence/{evidence_id}/photo/"
            )
            self.assertEqual(worker_photo.status_code, 200)

            denied = self.other_client.get(
                f"/api/v1/bookings/dispute-evidence/{evidence_id}/photo/"
            )
            self.assertEqual(denied.status_code, 404)

    def test_dispute_evidence_rejects_invalid_file_type(self):
        created = self.customer_client.post(
            "/api/v1/bookings/disputes/", self._payload(), format="json"
        )
        response = self.customer_client.post(
            f"/api/v1/bookings/disputes/{created.data['id']}/evidence/",
            {"file": SimpleUploadedFile("notes.txt", b"not an image", content_type="text/plain")},
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)
