from django.test import TestCase

from rest_framework.test import APIClient

from apps.catalog.models import Category, Service


class CatalogSerializerFieldRegressionTest(TestCase):
    """ServiceSerializer must expose category_slug alongside category and category_name."""

    def setUp(self):
        self.parent = Category.objects.create(title="Cleaning", slug="cleaning")
        self.category = Category.objects.create(
            title="Home Cleaning", slug="home-cleaning", parent=self.parent
        )
        self.service = Service.objects.create(
            category=self.category,
            title="Home Cleaning",
            booking_mode="scheduled",
            pricing_type="fixed",
        )
        self.client = APIClient()

    def test_service_detail_includes_category_slug(self):
        response = self.client.get(f"/api/v1/catalog/services/{self.service.id}/")

        self.assertEqual(response.status_code, 200, response.data)

        self.assertIn("category", response.data)
        self.assertIn("category_name", response.data)
        self.assertIn("category_slug", response.data)

        self.assertEqual(response.data["category"], self.category.id)
        self.assertEqual(response.data["category_name"], "Home Cleaning")
        self.assertEqual(response.data["category_slug"], "home-cleaning")

    def test_service_list_includes_category_slug(self):
        response = self.client.get("/api/v1/catalog/services/")

        self.assertEqual(response.status_code, 200, response.data)

        results = response.data if isinstance(response.data, list) else response.data.get("results", [])
        self.assertEqual(len(results), 1)

        service = results[0]
        self.assertEqual(service["category_slug"], "home-cleaning")
        self.assertEqual(service["category_name"], "Home Cleaning")


class CatalogServiceListFilterTest(TestCase):
    """Service list API filters: active-only, popular, category."""

    def setUp(self):
        self.client = APIClient()
        self.cleaning = Category.objects.create(title="Cleaning", slug="cleaning")
        self.beauty = Category.objects.create(title="Beauty", slug="beauty")

        self.active_home_cleaning = Service.objects.create(
            category=self.cleaning,
            title="Active Home Cleaning",
            booking_mode="scheduled",
            pricing_type="fixed",
            is_active=True,
            is_popular=True,
        )
        self.draft_beauty = Service.objects.create(
            category=self.beauty,
            title="Inactive Beauty Service",
            booking_mode="scheduled",
            pricing_type="fixed",
            is_active=False,
            is_popular=False,
        )
        self.active_beauty = Service.objects.create(
            category=self.beauty,
            title="Active Beauty Service",
            booking_mode="scheduled",
            pricing_type="fixed",
            is_active=True,
            is_popular=False,
        )

    def test_list_only_active_services(self):
        """Inactive services should be excluded from list."""
        response = self.client.get("/api/v1/catalog/services/")
        self.assertEqual(response.status_code, 200)

        results = response.data if isinstance(response.data, list) else response.data.get("results", [])
        self.assertEqual(len(results), 2)
        titles = [r["title"] for r in results]
        self.assertIn("Active Home Cleaning", titles)
        self.assertIn("Active Beauty Service", titles)
        self.assertNotIn("Inactive Beauty Service", titles)

    def test_list_with_popular_filter(self):
        """is_popular=true filter should return only popular services."""
        response = self.client.get("/api/v1/catalog/services/?is_popular=true")
        self.assertEqual(response.status_code, 200)

        results = response.data if isinstance(response.data, list) else response.data.get("results", [])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Active Home Cleaning")

    def test_list_with_category_filter(self):
        """category filter should return services from only that category."""
        response = self.client.get(f"/api/v1/catalog/services/?category={self.beauty.id}")
        self.assertEqual(response.status_code, 200)

        results = response.data if isinstance(response.data, list) else response.data.get("results", [])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Active Beauty Service")

    def test_list_combined_filters(self):
        """Multiple filters can be combined."""
        response = self.client.get(f"/api/v1/catalog/services/?category={self.cleaning.id}&is_popular=true")
        self.assertEqual(response.status_code, 200)

        results = response.data if isinstance(response.data, list) else response.data.get("results", [])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Active Home Cleaning")


class CatalogServiceDetailTest(TestCase):
    """Service detail view: 404 for missing/inactive service."""

    def setUp(self):
        self.client = APIClient()
        self.cleaning = Category.objects.create(title="Cleaning", slug="cleaning")
        self.active_service = Service.objects.create(
            category=self.cleaning,
            title="Active Service",
            booking_mode="scheduled",
            pricing_type="fixed",
            is_active=True,
        )
        self.inactive_service = Service.objects.create(
            category=self.cleaning,
            title="Inactive Service",
            booking_mode="scheduled",
            pricing_type="fixed",
            is_active=False,
        )
        self.nonexistent_id = 9999

    def test_detail_returns_200_for_active_service(self):
        """Active service should return 200 with full data."""
        response = self.client.get(f"/api/v1/catalog/services/{self.active_service.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["title"], "Active Service")

    def test_detail_returns_404_for_inactive_service(self):
        """Inactive service should return 404 (filtered by is_active=True)."""
        response = self.client.get(f"/api/v1/catalog/services/{self.inactive_service.id}/")
        self.assertEqual(response.status_code, 404)

    def test_detail_returns_404_for_nonexistent_service(self):
        """Non-existent service ID should return 404."""
        response = self.client.get(f"/api/v1/catalog/services/{self.nonexistent_id}/")
        self.assertEqual(response.status_code, 404)

class CityFilteredCategoryTreeTest(TestCase):
    def setUp(self):
        from apps.accounts.models import User, Address
        from apps.core.models import City, Zone
        from apps.catalog.models import CityService

        self.client = APIClient()
        self.user = User.objects.create_user(
            phone="+919876543299",
            password="password123",
        )
        self.client.force_authenticate(user=self.user)

        self.city = City.objects.create(name="Jaipur", state="Rajasthan")
        self.zone = Zone.objects.create(
            name="Vaishali Nagar",
            city=self.city,
            is_active=True,
        )
        self.address = Address.objects.create(
            user=self.user,
            label="Home",
            house_details="House 1",
            full_address="Vaishali Nagar, Jaipur",
            zone=self.zone,
        )

        self.root = Category.objects.create(title="Home Services", slug="home-services")
        self.visible_child = Category.objects.create(
            title="Cleaning",
            slug="city-cleaning",
            parent=self.root,
        )
        self.hidden_child = Category.objects.create(
            title="Electrical",
            slug="city-electrical",
            parent=self.root,
        )
        self.visible_service = Service.objects.create(
            category=self.visible_child,
            title="Home Deep Cleaning",
            booking_mode="scheduled",
            pricing_type="fixed",
            is_active=True,
        )
        self.hidden_service = Service.objects.create(
            category=self.hidden_child,
            title="Electrician Visit",
            booking_mode="scheduled",
            pricing_type="fixed",
            is_active=True,
        )
        CityService.objects.create(
            city=self.city,
            service=self.visible_service,
            is_active=True,
        )

    def test_category_tree_only_includes_categories_with_city_services(self):
        response = self.client.get(
            f"/api/v1/catalog/categories/?address_id={self.address.id}"
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], self.root.id)
        child_ids = [child["id"] for child in response.data[0]["children"]]
        self.assertEqual(child_ids, [self.visible_child.id])
