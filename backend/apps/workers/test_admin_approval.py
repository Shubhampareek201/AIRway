from types import SimpleNamespace

from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.accounts.models import User, UserRole
from apps.catalog.models import Category, Service
from apps.core.models import City, Zone
from apps.workers.admin import WorkerProfileAdmin
from apps.workers.approval import approve_worker, get_approval_requirements
from apps.workers.models import (
    WorkerDocument,
    WorkerProfile,
    WorkerSchedule,
    WorkerService,
    WorkerZone,
)


class WorkerApprovalServiceTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            phone="+919876543201",
            password="Admin-pass-123",
            name="Approval Admin",
        )
        self.worker_user = User.objects.create_user(
            phone="+919876543202",
            password="Worker-pass-123",
            name="Applicant",
        )
        self.worker = WorkerProfile.objects.create(
            user=self.worker_user,
            status=WorkerProfile.Status.PENDING,
            rejection_reason="",
        )

        self.city = City.objects.create(name="Approval Test City", state="Rajasthan")
        self.zone = Zone.objects.create(
            name="Approval Test Zone",
            city=self.city,
            is_active=True,
        )
        self.category = Category.objects.create(
            title="Approval Test Category",
            slug="approval-test-category",
            is_active=True,
        )
        self.service = Service.objects.create(
            category=self.category,
            title="Approval Test Service",
            booking_mode=Service.BookingMode.SCHEDULED,
            pricing_type=Service.PricingType.FIXED,
            is_active=True,
        )

    def add_verified_document(self, doc_type):
        return WorkerDocument.objects.create(
            worker=self.worker,
            doc_type=doc_type,
            file=SimpleUploadedFile(
                f"{doc_type}.txt",
                b"approval-test-document",
                content_type="text/plain",
            ),
            status=WorkerDocument.Status.VERIFIED,
            verified_by=self.admin,
        )

    def make_eligible(self):
        self.add_verified_document(WorkerDocument.DocumentType.AADHAAR)
        self.add_verified_document(WorkerDocument.DocumentType.PHOTO)
        WorkerService.objects.create(worker=self.worker, service=self.service)
        WorkerZone.objects.create(worker=self.worker, zone=self.zone)
        WorkerSchedule.objects.create(
            worker=self.worker,
            weekday=0,
            start_time="09:00",
            end_time="18:00",
            is_active=True,
        )

    def test_new_application_is_ineligible_and_lists_all_missing_requirements(self):
        result = get_approval_requirements(self.worker)

        self.assertFalse(result["eligible"])
        self.assertEqual(
            result["missing"],
            [
                "Verified ID (Aadhaar or other ID)",
                "Verified profile photograph",
                "At least one active service in an active category",
                "At least one active zone in an active city",
                "At least one active working schedule",
            ],
        )

    def test_inactive_related_records_do_not_satisfy_approval(self):
        self.make_eligible()
        self.category.is_active = False
        self.category.save(update_fields=["is_active"])

        result = get_approval_requirements(self.worker)

        self.assertFalse(result["has_service"])
        self.assertFalse(result["eligible"])
        self.assertIn(
            "At least one active service in an active category",
            result["missing"],
        )

    def test_eligible_worker_is_approved_and_worker_role_is_created(self):
        self.make_eligible()
        self.worker.rejection_reason = "Old reason"
        self.worker.save(update_fields=["rejection_reason", "updated_at"])

        result = approve_worker(self.worker.pk, self.admin)

        self.assertEqual(result["status"], "approved")
        self.worker.refresh_from_db()
        self.assertEqual(self.worker.status, WorkerProfile.Status.APPROVED)
        self.assertEqual(self.worker.approved_by, self.admin)
        self.assertIsNotNone(self.worker.approved_at)
        self.assertEqual(self.worker.rejection_reason, "")
        self.assertTrue(
            UserRole.objects.filter(
                user=self.worker_user,
                role=UserRole.Role.WORKER,
            ).exists()
        )

    def test_approval_is_idempotent_and_does_not_duplicate_worker_role(self):
        self.make_eligible()

        first = approve_worker(self.worker.pk, self.admin)
        second = approve_worker(self.worker.pk, self.admin)

        self.assertEqual(first["status"], "approved")
        self.assertEqual(second["status"], "already_processed")
        self.assertEqual(
            UserRole.objects.filter(
                user=self.worker_user,
                role=UserRole.Role.WORKER,
            ).count(),
            1,
        )

    def test_ineligible_worker_remains_pending_and_gets_no_worker_role(self):
        result = approve_worker(self.worker.pk, self.admin)

        self.assertEqual(result["status"], "ineligible")
        self.worker.refresh_from_db()
        self.assertEqual(self.worker.status, WorkerProfile.Status.PENDING)
        self.assertFalse(
            UserRole.objects.filter(
                user=self.worker_user,
                role=UserRole.Role.WORKER,
            ).exists()
        )

    def test_missing_worker_returns_not_found(self):
        result = approve_worker(999999, self.admin)

        self.assertEqual(result["status"], "not_found")
        self.assertIsNone(result["worker"])

    def _admin_request(self):
        request = RequestFactory().post("/admin/")
        request.user = self.admin
        request.session = {}
        request._messages = FallbackStorage(request)
        return request

    def test_admin_single_record_approval_waits_for_inline_saves(self):
        self.make_eligible()
        admin_model = WorkerProfileAdmin(WorkerProfile, AdminSite())
        request = self._admin_request()
        worker = WorkerProfile.objects.get(pk=self.worker.pk)
        worker.status = WorkerProfile.Status.APPROVED

        admin_model.save_model(request, worker, form=None, change=True)

        self.worker.refresh_from_db()
        self.assertEqual(self.worker.status, WorkerProfile.Status.PENDING)
        self.assertFalse(
            UserRole.objects.filter(
                user=self.worker_user,
                role=UserRole.Role.WORKER,
            ).exists()
        )
        self.assertTrue(request._worker_approval_requested)

        admin_model.save_related(
            request,
            SimpleNamespace(save_m2m=lambda: None),
            [],
            change=True,
        )

        self.worker.refresh_from_db()
        self.assertEqual(self.worker.status, WorkerProfile.Status.APPROVED)
        self.assertTrue(
            UserRole.objects.filter(
                user=self.worker_user,
                role=UserRole.Role.WORKER,
            ).exists()
        )

    def test_admin_bulk_action_uses_shared_approval_service(self):
        self.make_eligible()
        admin_model = WorkerProfileAdmin(WorkerProfile, AdminSite())
        request = self._admin_request()

        admin_model.approve_workers(
            request,
            WorkerProfile.objects.filter(pk=self.worker.pk),
        )

        self.worker.refresh_from_db()
        self.assertEqual(self.worker.status, WorkerProfile.Status.APPROVED)
        self.assertTrue(
            UserRole.objects.filter(
                user=self.worker_user,
                role=UserRole.Role.WORKER,
            ).exists()
        )

    def test_dashboard_approval_endpoint_uses_shared_service(self):
        self.make_eligible()
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("admin_dashboard:approve_application", args=[self.worker.pk])
        )

        self.assertEqual(response.status_code, 302)
        self.worker.refresh_from_db()
        self.assertEqual(self.worker.status, WorkerProfile.Status.APPROVED)
        self.assertTrue(
            UserRole.objects.filter(
                user=self.worker_user,
                role=UserRole.Role.WORKER,
            ).exists()
        )

    def test_dashboard_rejects_approval_when_requirements_are_missing(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("admin_dashboard:approve_application", args=[self.worker.pk])
        )

        self.assertEqual(response.status_code, 302)
        self.worker.refresh_from_db()
        self.assertEqual(self.worker.status, WorkerProfile.Status.PENDING)
        self.assertFalse(
            UserRole.objects.filter(
                user=self.worker_user,
                role=UserRole.Role.WORKER,
            ).exists()
        )

    def test_dashboard_approval_endpoint_rejects_get(self):
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse("admin_dashboard:approve_application", args=[self.worker.pk])
        )

        self.assertEqual(response.status_code, 405)

    def test_dashboard_approval_requires_superuser(self):
        regular_user = User.objects.create_user(
            phone="+919876543203",
            password="Customer-pass-123",
            name="Regular User",
        )
        self.client.force_login(regular_user)

        response = self.client.post(
            reverse("admin_dashboard:approve_application", args=[self.worker.pk])
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/control/login/", response.url)
        self.worker.refresh_from_db()
        self.assertEqual(self.worker.status, WorkerProfile.Status.PENDING)
