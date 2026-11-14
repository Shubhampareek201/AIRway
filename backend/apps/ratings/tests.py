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
