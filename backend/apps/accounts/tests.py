
from django.contrib.auth import get_user_model

from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework.test import APIClient

from apps.core.models import City, Zone
from apps.workers.models import WorkerProfile
from apps.catalog.models import Category, Service
from .models import Address


User = get_user_model()


class CurrentUserAPITest(APITestCase):
    """Test authenticated user profile endpoint."""

    def setUp(self):
        self.user = User.objects.create_user(
            phone="+919876543210",
            name="Test User",
            email="test@example.com"
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_authenticated_user_profile(self):
        """Should return user profile for authenticated user."""
        response = self.client.get("/api/v1/auth/me/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], self.user.id)
        self.assertEqual(response.data["phone"], "+919876543210")
        self.assertEqual(response.data["name"], "Test User")
        self.assertEqual(response.data["email"], "test@example.com")
        self.assertTrue(response.data["profile_complete"])

    def test_user_profile_incomplete_no_name(self):
        """Should show profile_complete false for user without name."""
        user_no_name = User.objects.create_user(phone="+919876543211")
        self.client.force_authenticate(user=user_no_name)

        response = self.client.get("/api/v1/auth/me/")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["profile_complete"])

    def test_unauthenticated_me_endpoint(self):
        """Should return 401 for unauthenticated request."""
        self.client.force_authenticate(user=None)

        response = self.client.get("/api/v1/auth/me/")

        self.assertEqual(response.status_code, 401)


class LoginAPITest(APITestCase):
    """Test login endpoint authentication."""

    def setUp(self):
        self.user = User.objects.create_user(
            phone="+919876543210",
            password="validpassword123"
        )
        self.client = APIClient()

    def test_login_with_valid_credentials(self):
        """Should return tokens and user data on successful login."""
        response = self.client.post("/api/v1/auth/login/", {
            "phone": "+919876543210",
            "password": "validpassword123"
        }, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertIn("user", response.data)
        self.assertEqual(response.data["user"]["phone"], "+919876543210")

    def test_login_with_invalid_password(self):
        """Should return 400 for invalid password."""
        response = self.client.post("/api/v1/auth/login/", {
            "phone": "+919876543210",
            "password": "wrongpassword"
        }, format="json")

        self.assertEqual(response.status_code, 400)

    def test_login_with_nonexistent_user(self):
        """Should return 400 for nonexistent user."""
        response = self.client.post("/api/v1/auth/login/", {
            "phone": "+919999999999",
            "password": "anypassword"
        }, format="json")

        self.assertEqual(response.status_code, 400)


class AddressAPITests(APITestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            phone="+919876543210",
        )
        self.other_user = User.objects.create_user(
            phone="+919876543211",
        )

        self.city = City.objects.create(
            name="Rawatbhata",
            state="Rajasthan",
        )
        self.zone = Zone.objects.create(
            city=self.city,
            name="Anukiran Colony",
        )

        self.client.force_authenticate(user=self.user)

        self.list_url = "/api/v1/auth/addresses/"

        self.address_data = {
            "label": "home",
            "house_details": "House 12",
            "landmark": "Near Main Market",
            "full_address": "Anukiran Colony, Rawatbhata",
            "latitude": "24.930000",
            "longitude": "75.590000",
            "zone": self.zone.id,
        }

    def create_address(self):
        response = self.client.post(
            self.list_url,
            self.address_data,
            format="json",
        )
        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
            response.data,
        )
        return response.data

    def test_create_and_list_addresses(self):
        created = self.create_address()

        self.assertTrue(created["is_default"])

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)

    def test_update_address(self):
        created = self.create_address()

        response = self.client.patch(
            f"{self.list_url}{created['id']}/",
            {"landmark": "Near Hospital"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["landmark"],
            "Near Hospital",
        )

    def test_set_default_address(self):
        first = self.create_address()

        second_data = {
            **self.address_data,
            "label": "work",
            "house_details": "Office 5",
        }

        response = self.client.post(
            self.list_url,
            second_data,
            format="json",
        )
        self.assertEqual(response.status_code, 201)

        second_id = response.data["id"]

        response = self.client.post(
            f"{self.list_url}{second_id}/set-default/",
        )

        self.assertEqual(response.status_code, 200)

        self.assertTrue(
            Address.objects.get(pk=second_id).is_default
        )
        self.assertFalse(
            Address.objects.get(pk=first["id"]).is_default
        )

    def test_soft_delete_address(self):
        created = self.create_address()

        response = self.client.delete(
            f"{self.list_url}{created['id']}/"
        )

        self.assertEqual(response.status_code, 204)

        address = Address.objects.get(pk=created["id"])

        self.assertIsNotNone(address.deleted_at)
        self.assertFalse(address.is_default)

        response = self.client.get(self.list_url)
        self.assertEqual(len(response.data), 0)

    def test_cannot_access_another_users_address(self):
        other_address = Address.objects.create(
            user=self.other_user,
            label="home",
            house_details="House 99",
            landmark="Near Park",
            full_address="Rawatbhata",
            zone=self.zone,
        )

        url = f"{self.list_url}{other_address.id}/"

        self.assertEqual(
            self.client.patch(
                url,
                {"landmark": "Changed"},
                format="json",
            ).status_code,
            404,
        )

        self.assertEqual(
            self.client.delete(url).status_code,
            404,
        )

        self.assertEqual(
            self.client.post(
                f"{url}set-default/"
            ).status_code,
            404,
        )

    def test_invalid_coordinates_rejected(self):
        invalid_data = {
            **self.address_data,
            "latitude": "100.000000",
        }

        response = self.client.post(
            self.list_url,
            invalid_data,
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_inactive_zone_rejected(self):
        self.zone.is_active = False
        self.zone.save()

        response = self.client.post(
            self.list_url,
            self.address_data,
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_unauthenticated_address_access_denied(self):
        self.client.force_authenticate(user=None)

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 401)


class SwitchModeTest(APITestCase):
    """Test mode switching endpoint."""

    def setUp(self):
        self.customer = User.objects.create_user(
            phone="+919876543210",
            name="Customer User",
        )
        self.worker_user = User.objects.create_user(
            phone="+919876543211",
            name="Worker User",
        )
        self.client = APIClient()

    def test_switch_to_worker_mode_rejects_without_approved_profile(self):
        """Should reject mode switch to worker without approved profile."""
        self.client.force_authenticate(user=self.customer)

        response = self.client.post(
            "/api/v1/auth/switch-mode/",
            {"mode": "worker"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_switch_to_worker_mode_with_approved_profile(self):
        """Should allow mode switch with approved worker profile."""
        worker_profile = WorkerProfile.objects.create(
            user=self.worker_user,
            status=WorkerProfile.Status.APPROVED,
        )
        self.worker_user.active_mode = User.Mode.CUSTOMER
        self.worker_user.save()

        self.client.force_authenticate(user=self.worker_user)

        response = self.client.post(
            "/api/v1/auth/switch-mode/",
            {"mode": "worker"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["active_mode"], "worker")

        self.worker_user.refresh_from_db()
        self.assertEqual(self.worker_user.active_mode, "worker")

    def test_switch_to_customer_mode_from_worker(self):
        """Should allow switching back to customer mode."""
        self.customer.active_mode = User.Mode.WORKER
        self.customer.save()

        self.client.force_authenticate(user=self.customer)

        response = self.client.post(
            "/api/v1/auth/switch-mode/",
            {"mode": "customer"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["active_mode"], "customer")

    def test_invalid_mode_rejected(self):
        """Should reject invalid mode values."""
        self.client.force_authenticate(user=self.customer)

        response = self.client.post(
            "/api/v1/auth/switch-mode/",
            {"mode": "invalid_mode"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_unauthenticated_switch_mode_denied(self):
        """Should deny unauthenticated requests."""
        response = self.client.post(
            "/api/v1/auth/switch-mode/",
            {"mode": "worker"},
            format="json",
        )

        self.assertEqual(response.status_code, 401)


class WorkerApplicationTest(APITestCase):
    """Test worker application flow including photo upload."""

    def setUp(self):
        self.user = User.objects.create_user(
            phone="+919876543210",
            name="Test Worker",
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        # Create test city, category, service, and zone
        from apps.core.models import City

        self.city = City.objects.create(
            name="Test City",
            state="Test State",
            is_active=True,
        )
        self.category = Category.objects.create(
            title="Test Category",
            slug="test-category",
            is_active=True,
        )
        self.service = Service.objects.create(
            category=self.category,
            title="Test Service",
            is_active=True,
        )
        self.zone = Zone.objects.create(
            name="Test Zone",
            city=self.city,
            is_active=True,
        )

    def _application_payload(self, photo):
        import json

        return {
            "name": "Test Worker",
            "email": "worker@example.com",
            "gender": WorkerProfile.Gender.MALE,
            "experience_years": "0",
            "services": [self.service.id],
            "service_capabilities": json.dumps({str(self.service.id): []}),
            "service_experience_years": json.dumps({str(self.service.id): 0}),
            "zones": [self.zone.id],
            "residential_address": "12 Test Street, Rawatbhata",
            "schedule": json.dumps({"0": {"start": "09:00", "end": "18:00"}}),
            "profile_photo": photo,
        }

    def test_worker_application_requires_photo(self):
        """Worker application should require a profile photo."""
        response = self.client.post(
            "/api/v1/workers/apply/",
            {
                "services": [self.service.id],
                "zones": [self.zone.id],
            },
        )

        # Photo is required
        self.assertEqual(response.status_code, 400)
        self.assertIn("profile_photo", response.data)
        # DRF error response structure for ImageField required
        error_msg = str(response.data["profile_photo"])
        self.assertIn("required", error_msg.lower())

    def test_worker_application_with_photo_saves_to_workerd_document(self):
        """Worker application should save the photo to WorkerDocument, not user.photo."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        from apps.workers.models import WorkerDocument

        # Create a proper test image using PIL
        from PIL import Image
        import io

        img = Image.new('RGB', (100, 100), color='red')
        image_io = io.BytesIO()
        img.save(image_io, format='JPEG')
        image_io.seek(0)

        photo = SimpleUploadedFile(
            name="test_photo.jpg",
            content=image_io.read(),
            content_type="image/jpeg",
        )

        response = self.client.post(
            "/api/v1/workers/apply/",
            self._application_payload(photo),
            format="multipart",
        )

        self.assertEqual(response.status_code, 201)

        # Verify photo was NOT saved to user.photo (customer photo preserved)
        user = User.objects.get(phone="+919876543210")
        # user.photo should be empty (not set)
        self.assertFalse(bool(user.photo))

        # Verify photo was saved to WorkerDocument with PHOTO type
        photo_doc = WorkerDocument.objects.filter(
            worker__user=self.user,
            doc_type=WorkerDocument.DocumentType.PHOTO,
        ).first()
        self.assertIsNotNone(photo_doc)
        self.assertEqual(photo_doc.status, WorkerDocument.Status.PENDING)

    def test_customer_photo_is_preserved_when_applying_as_worker(self):
        """Customer's photo should be preserved when applying as worker."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        from apps.workers.models import WorkerDocument
        from PIL import Image
        import io

        # First, set a customer photo on the user
        img = Image.new('RGB', (100, 100), color='blue')
        image_io = io.BytesIO()
        img.save(image_io, format='JPEG')
        image_io.seek(0)

        customer_photo = SimpleUploadedFile(
            name="customer_photo.jpg",
            content=image_io.read(),
            content_type="image/jpeg",
        )
        self.user.photo.save("customer_photo.jpg", customer_photo)
        original_photo_name = self.user.photo.name

        # Now apply as worker with a different photo
        img2 = Image.new('RGB', (100, 100), color='red')
        image_io2 = io.BytesIO()
        img2.save(image_io2, format='JPEG')
        image_io2.seek(0)

        worker_photo = SimpleUploadedFile(
            name="worker_photo.jpg",
            content=image_io2.read(),
            content_type="image/jpeg",
        )

        response = self.client.post(
            "/api/v1/workers/apply/",
            self._application_payload(worker_photo),
            format="multipart",
        )

        self.assertEqual(response.status_code, 201)

        # Verify customer photo is still intact
        self.user.refresh_from_db()
        self.assertEqual(self.user.photo.name, original_photo_name)

    def _create_test_photo(self):
        """Helper to create a test photo file."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image
        import io

        img = Image.new('RGB', (100, 100), color='red')
        image_io = io.BytesIO()
        img.save(image_io, format='JPEG')
        image_io.seek(0)

        return SimpleUploadedFile(
            name="test_photo.jpg",
            content=image_io.read(),
            content_type="image/jpeg",
        )

    def test_worker_application_creates_pending_profile(self):
        """Worker application should create WorkerProfile with PENDING status."""
        photo = self._create_test_photo()
        response = self.client.post(
            "/api/v1/workers/apply/",
            self._application_payload(photo),
            format="multipart",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["status"], "pending")

        # Verify WorkerProfile was created
        profile = WorkerProfile.objects.get(user=self.user)
        self.assertEqual(profile.status, WorkerProfile.Status.PENDING)

    def test_worker_cannot_apply_twice(self):
        """User should not be able to apply twice."""
        photo = self._create_test_photo()
        # First application
        response = self.client.post(
            "/api/v1/workers/apply/",
            {
                "services": [self.service.id],
                "zones": [self.zone.id],
                "residential_address": "12 Test Street, Rawatbhata",
                "schedule": '{"0":{"start":"09:00","end":"18:00"}}',
                "profile_photo": photo,
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 201)

        # Second application should fail
        photo2 = self._create_test_photo()
        response = self.client.post(
            "/api/v1/workers/apply/",
            self._application_payload(photo2),
            format="multipart",
        )
        self.assertEqual(response.status_code, 409)
        self.assertIn("already exists", response.data["detail"].lower())

    def test_rejected_application_shows_reason_on_mode_switch(self):
        """Rejected applications should show rejection reason when trying to switch modes."""
        # Create a rejected profile
        profile = WorkerProfile.objects.create(
            user=self.user,
            status=WorkerProfile.Status.REJECTED,
            rejection_reason="Insufficient documentation",
        )

        response = self.client.post(
            "/api/v1/auth/switch-mode/",
            {"mode": "worker"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("not approved", response.data["error"].lower())

    def test_pending_application_cannot_switch_mode(self):
        """Pending worker applications cannot switch to worker mode."""
        profile = WorkerProfile.objects.create(
            user=self.user,
            status=WorkerProfile.Status.PENDING,
        )

        response = self.client.post(
            "/api/v1/auth/switch-mode/",
            {"mode": "worker"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("not approved", response.data["error"].lower())

    def test_current_user_view_shows_worker_profile(self):
        """CurrentUserView should include worker profile details."""
        profile = WorkerProfile.objects.create(
            user=self.user,
            status=WorkerProfile.Status.APPROVED,
            experience_years=3,
            bio="Test bio",
        )

        response = self.client.get("/api/v1/auth/me/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("worker_profile", response.data)
        self.assertEqual(response.data["worker_profile"]["status"], "approved")
        self.assertEqual(response.data["worker_profile"]["experience_years"], 3)
        self.assertEqual(response.data["worker_profile"]["rejection_reason"], "")

    def test_mode_switch_to_worker_rejects_pending_status(self):
        """Customer should not be able to switch to worker mode with PENDING profile."""
        worker_profile = WorkerProfile.objects.create(
            user=self.user,
            status=WorkerProfile.Status.PENDING,
        )
        self.user.active_mode = User.Mode.CUSTOMER
        self.user.save()

        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            "/api/v1/auth/switch-mode/",
            {"mode": "worker"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("not approved", response.data["error"].lower())

    def test_mode_switch_to_worker_rejects_rejected_profile(self):
        """Customer should not be able to switch to worker mode with REJECTED profile."""
        worker_profile = WorkerProfile.objects.create(
            user=self.user,
            status=WorkerProfile.Status.REJECTED,
            rejection_reason="Documentation incomplete",
        )
        self.user.active_mode = User.Mode.CUSTOMER
        self.user.save()

        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            "/api/v1/auth/switch-mode/",
            {"mode": "worker"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("not approved", response.data["error"].lower())
        self.assertIn("rejected", response.data["error"].lower())
