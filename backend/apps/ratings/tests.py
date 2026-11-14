from django.contrib.auth import get_user_model

from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework.test import APIClient

from apps.bookings.models import Booking
from apps.ratings.models import BookingRating, RatingSummary
from apps.accounts.models import Address
from apps.catalog.models import Category, Service, ServiceVariant
from apps.core.models import Zone, City
from django.utils import timezone

User = get_user_model()


class BookingRatingModelTest(APITestCase):
    """Test booking rating model operations."""

    def setUp(self):
        self.client = APIClient()
        self.customer = User.objects.create_user(phone='1234567890', password='testpass')
        self.worker = User.objects.create_user(phone='9876543210', password='testpass')

        # Create required related objects
        self.address = self._create_address(self.customer)
        self.category = Category.objects.create(title="Cleaning", slug="cleaning")
        self.service = self._create_service(self.category)
        self.variant = self._create_variant(self.service)

        # Create booking
        future_time = timezone.now() + timezone.timedelta(days=1, hours=2)
        self.booking = Booking.objects.create(
            customer=self.customer,
            service=self.service,
            variant=self.variant,
            address=self.address,
            scheduled_at=future_time,
            booking_mode='scheduled',
        )

    def _create_address(self, user):
        city, _ = City.objects.get_or_create(name="Mumbai", defaults={"state": "Maharashtra"})
        zone, _ = Zone.objects.get_or_create(name="Dadar", defaults={"city": city, "is_active": True})
        return Address.objects.create(
            user=user,
            label='home',
            house_details='Floor 2, Apt 301',
            landmark='Near XYZ Mall',
            full_address='123 Main Street, Near XYZ Mall, Mumbai 400001',
        )

    def _create_service(self, category, title="Home Cleaning"):
        return Service.objects.create(
            category=category,
            title=title,
            booking_mode=Service.BookingMode.SCHEDULED,
            pricing_type=Service.PricingType.FIXED,
            is_active=True,
        )

    def _create_variant(self, service, title="Premium", price=500, mrp=600, duration_minutes=60):
        return ServiceVariant.objects.create(
            service=service,
            title=title,
            price=price,
            mrp=mrp,
            duration_minutes=duration_minutes,
        )

    def test_create_customer_rating(self):
        """Should create a customer rating successfully."""
        rating = BookingRating.objects.create(
            booking=self.booking,
            rater=self.customer,
            rated=self.worker,
            rating=5,
            rating_type='customer',
            comment='Great service',
        )

        self.assertEqual(rating.rating, 5)
        self.assertEqual(rating.rating_type, 'customer')
        self.assertEqual(rating.comment, 'Great service')
        self.assertEqual(rating.get_rating_type_display(), 'Customer Rating')

    def test_create_worker_rating(self):
        """Should create a worker rating successfully."""
        rating = BookingRating.objects.create(
            booking=self.booking,
            rater=self.worker,
            rated=self.customer,
            rating=4,
            rating_type='worker',
            comment='Good experience',
        )

        self.assertEqual(rating.rating, 4)
        self.assertEqual(rating.rating_type, 'worker')


class RatingSummaryTest(APITestCase):
    """Test rating summary model operations."""

    def setUp(self):
        self.client = APIClient()

    def test_update_stats_empty(self):
        """Should handle empty ratings gracefully."""
        user = User.objects.create_user(phone='1234567890', password='testpass')
        summary = RatingSummary.objects.create(user=user)
        summary.update_stats()

        self.assertEqual(summary.average_rating, 0)
        self.assertEqual(summary.total_ratings, 0)


class RatingAPITest(APITestCase):
    """Test rating API endpoints."""

    def setUp(self):
        self.client = APIClient()

    def test_list_ratings_requires_auth(self):
        """Should require authentication to list ratings."""
        response = self.client.get('/api/v1/ratings/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_rating_requires_auth(self):
        """Should require authentication to create rating."""
        response = self.client.post(
            '/api/v1/ratings/',
            {'rating': 5, 'rating_type': 'customer'},
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class RatingSignalTest(APITestCase):
    """Test rating signals."""

    def setUp(self):
        self.client = APIClient()

    def test_rating_creates_summary_on_post_save(self):
        """Should create rating summary when rating is created."""
        customer = User.objects.create_user(phone='1234567890', password='testpass')
        worker = User.objects.create_user(phone='9876543210', password='testpass')

        # Create required objects for booking
        city, _ = City.objects.get_or_create(name="Mumbai", defaults={"state": "Maharashtra"})
        zone, _ = Zone.objects.get_or_create(name="Dadar", defaults={"city": city, "is_active": True})
        address = Address.objects.create(
            user=customer, label='home',
            full_address='123 Main Street, Mumbai',
        )
        category = Category.objects.create(title="Cleaning", slug="cleaning5")
        service = Service.objects.create(
            category=category,
            title="Test",
            booking_mode=Service.BookingMode.SCHEDULED,
            pricing_type=Service.PricingType.FIXED,
            is_active=True,
        )
        variant = ServiceVariant.objects.create(service=service, title="Standard", price=100, mrp=120, duration_minutes=60)
        future_time = timezone.now() + timezone.timedelta(days=1)
        booking = Booking.objects.create(
            customer=customer,
            service=service,
            variant=variant,
            address=address,
            scheduled_at=future_time,
            booking_mode='scheduled'
        )

        rating = BookingRating.objects.create(
            booking=booking,
            rater=customer,
            rated=worker,
            rating=5,
            rating_type='customer',
        )

        self.assertTrue(hasattr(worker, 'rating_summary'))


class RatingSecurityAndFlowAPITest(APITestCase):
    def setUp(self):
        from apps.bookings.models import BookingAssignment
        from apps.workers.models import WorkerProfile

        self.customer = User.objects.create_user(phone="1111111111", password="testpass")
        self.worker_user = User.objects.create_user(phone="2222222222", password="testpass")
        self.other_user = User.objects.create_user(phone="3333333333", password="testpass")
        city = City.objects.create(name="Rating City", state="Rajasthan")
        zone = Zone.objects.create(name="Rating Zone", city=city, is_active=True)
        self.address = Address.objects.create(
            user=self.customer,
            label="home",
            house_details="House 1",
            landmark="Main road",
            full_address="Rating City",
            zone=zone,
        )
        category = Category.objects.create(title="Rating", slug="rating-test")
        service = Service.objects.create(
            category=category,
            title="Rating service",
            booking_mode=Service.BookingMode.SCHEDULED,
            pricing_type=Service.PricingType.FIXED,
            is_active=True,
        )
        variant = ServiceVariant.objects.create(
            service=service, title="Standard", price=100, mrp=100,
            duration_minutes=30,
        )
        self.booking = Booking.objects.create(
            customer=self.customer,
            service=service,
            variant=variant,
            address=self.address,
            scheduled_at=timezone.now() - timezone.timedelta(hours=2),
            booking_mode=Booking.BookingMode.SCHEDULED,
            status=Booking.Status.COMPLETED,
        )
        self.worker_profile = WorkerProfile.objects.create(
            user=self.worker_user,
            status=WorkerProfile.Status.APPROVED,
            gender=WorkerProfile.Gender.MALE,
        )
        BookingAssignment.objects.create(
            booking=self.booking,
            worker=self.worker_profile,
            accepted_at=timezone.now() - timezone.timedelta(hours=2),
            completed_at=timezone.now() - timezone.timedelta(hours=1),
        )

    def test_customer_can_rate_assigned_worker_for_completed_booking(self):
        self.client.force_authenticate(self.customer)
        response = self.client.post(
            f"/api/v1/ratings/{self.booking.pk}/rating/",
            {"rated_id": self.worker_user.pk, "rating_type": "customer", "rating": 5},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["booking"], self.booking.pk)
        self.assertNotIn("rated_phone", response.data)
        self.assertEqual(RatingSummary.objects.get(user=self.worker_user).total_ratings, 1)

    def test_assigned_worker_can_rate_customer(self):
        self.client.force_authenticate(self.worker_user)
        response = self.client.post(
            f"/api/v1/ratings/{self.booking.pk}/rating/",
            {"rated_id": self.customer.pk, "rating_type": "worker", "rating": 4},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(RatingSummary.objects.get(user=self.customer).total_ratings, 1)

    def test_unrelated_user_cannot_rate_booking(self):
        self.client.force_authenticate(self.other_user)
        response = self.client.post(
            f"/api/v1/ratings/{self.booking.pk}/rating/",
            {"rated_id": self.customer.pk, "rating_type": "worker", "rating": 5},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_customer_cannot_choose_arbitrary_rated_user(self):
        self.client.force_authenticate(self.customer)
        response = self.client.post(
            f"/api/v1/ratings/{self.booking.pk}/rating/",
            {"rated_id": self.other_user.pk, "rating_type": "customer", "rating": 5},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_incomplete_booking_cannot_be_rated(self):
        self.booking.status = Booking.Status.ASSIGNED
        self.booking.save(update_fields=["status", "updated_at"])
        self.client.force_authenticate(self.customer)
        response = self.client.post(
            f"/api/v1/ratings/{self.booking.pk}/rating/",
            {"rated_id": self.worker_user.pk, "rating_type": "customer", "rating": 5},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rating_list_is_limited_to_booking_participants(self):
        BookingRating.objects.create(
            booking=self.booking, rater=self.customer, rated=self.worker_user,
            rating_type="customer", rating=5,
        )
        other_booking = Booking.objects.create(
            customer=self.other_user,
            service=self.booking.service,
            variant=self.booking.variant,
            address=Address.objects.create(
                user=self.other_user, label="home", house_details="Other",
                landmark="Road", full_address="Other address",
            ),
            scheduled_at=timezone.now(),
            booking_mode=Booking.BookingMode.SCHEDULED,
            status=Booking.Status.COMPLETED,
        )
        BookingRating.objects.create(
            booking=other_booking, rater=self.other_user, rated=self.customer,
            rating_type="customer", rating=1,
        )
        self.client.force_authenticate(self.customer)
        response = self.client.get("/api/v1/ratings/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["booking"], self.booking.pk)

    def test_generic_create_endpoint_is_disabled(self):
        self.client.force_authenticate(self.customer)
        response = self.client.post(
            "/api/v1/ratings/",
            {"rating": 5, "rating_type": "customer"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_rating_summary_is_private_to_authenticated_user(self):
        RatingSummary.objects.create(user=self.worker_user, average_rating=4, total_ratings=1)
        RatingSummary.objects.create(user=self.customer, average_rating=5, total_ratings=1)
        self.client.force_authenticate(self.customer)
        response = self.client.get("/api/v1/ratings/summaries/user-ratings?user_ids=%s" % self.worker_user.pk)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])
