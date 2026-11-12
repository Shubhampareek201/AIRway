from django.test import TestCase

from rest_framework.test import APIClient

from apps.catalog.models import Category, Service, ServiceVariant


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
        from apps.workers.models import WorkerProfile, WorkerService, WorkerZone, WorkerSchedule

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
        # CityService controls catalogue publication independently of the
        # current worker's online state and schedule.
        CityService.objects.create(
            city=self.city,
            service=self.hidden_service,
            is_active=True,
        )
        worker_user = User.objects.create_user(
            phone="+919876543298",
            password="password123",
        )
        self.worker = WorkerProfile.objects.create(
            user=worker_user,
            status=WorkerProfile.Status.APPROVED,
            is_online=True,
        )
        WorkerService.objects.create(worker=self.worker, service=self.visible_service)
        WorkerZone.objects.create(worker=self.worker, zone=self.zone)
        WorkerSchedule.objects.create(
            worker=self.worker,
            weekday=0,
            start_time="09:00:00",
            end_time="18:00:00",
            is_active=True,
        )

    def test_category_tree_shows_active_categories_even_without_eligible_workers(self):
        response = self.client.get(
            f"/api/v1/catalog/categories/?address_id={self.address.id}"
        )

        self.assertEqual(response.status_code, 200, response.data)
        categories = response.data["results"]
        self.assertEqual([item["id"] for item in categories], [self.root.id])
        child_ids = [child["id"] for child in categories[0]["children"]]
        self.assertEqual(set(child_ids), {self.visible_child.id, self.hidden_child.id})

    def test_categories_remain_visible_when_no_worker_is_online(self):
        self.worker.is_online = False
        self.worker.save(update_fields=["is_online", "updated_at"])

        response = self.client.get(
            f"/api/v1/catalog/categories/?address_id={self.address.id}"
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual([item["id"] for item in response.data["results"]], [self.root.id])

    def test_customer_service_list_marks_services_without_eligible_workers_unavailable(self):
        list_response = self.client.get(
            f"/api/v1/catalog/services/?address_id={self.address.id}"
        )
        self.assertEqual(list_response.status_code, 200, list_response.data)
        listed_services = (
            list_response.data
            if isinstance(list_response.data, list)
            else list_response.data.get("results", [])
        )
        by_id = {item["id"]: item for item in listed_services}
        self.assertEqual(set(by_id), {self.visible_service.id, self.hidden_service.id})
        self.assertTrue(by_id[self.visible_service.id]["is_available"])
        self.assertFalse(by_id[self.hidden_service.id]["is_available"])

        detail_response = self.client.get(
            f"/api/v1/catalog/services/{self.hidden_service.id}/?address_id={self.address.id}"
        )
        self.assertEqual(detail_response.status_code, 200)
        self.assertFalse(detail_response.data["is_available"])



class CatalogPackageIncludedTasksTest(TestCase):
    def test_service_api_exposes_package_included_tasks(self):
        category = Category.objects.create(title="Home Cleaning", slug="home-cleaning")
        service = Service.objects.create(
            category=category,
            title="Kitchen Cleaning",
            booking_mode="scheduled",
            pricing_type="fixed",
        )
        variant = ServiceVariant.objects.create(
            service=service,
            title="Deep Kitchen Cleaning",
            description="Detailed kitchen cleaning.",
            included_tasks=[
                "Countertop and sink cleaning",
                "Grease removal",
                "Tile cleaning",
                "Cabinet interior cleaning",
            ],
            mrp="0.00",
            price="0.00",
        )

        response = APIClient().get(f"/api/v1/catalog/services/{service.id}/")

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["variants"][0]["id"], variant.id)
        self.assertEqual(
            response.data["variants"][0]["included_tasks"],
            variant.included_tasks,
        )


class LaunchCatalogueScopeTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.roots = {
            slug: Category.objects.create(title=title, slug=slug)
            for slug, title in [
                ("car-wash", "Car Wash"),
                ("beauty", "Beauty"),
                ("electrical", "Electrical"),
                ("home-cleaning", "Home Cleaning"),
                ("test-qa", "Test QA"),
                ("test", "Test"),
            ]
        }
        self.child = Category.objects.create(
            title="Exterior Car Cleaning", slug="exterior-car-cleaning",
            parent=self.roots["car-wash"],
        )
        self.services = {}
        for slug, category in self.roots.items():
            self.services[slug] = Service.objects.create(
                category=category,
                title=f"{category.title} sample",
                booking_mode="scheduled",
                pricing_type="fixed",
                is_active=True,
            )
        self.child_service = Service.objects.create(
            category=self.child,
            title="Side Profile Car Wash",
            booking_mode="scheduled",
            pricing_type="fixed",
            is_active=True,
        )

    def test_launch_categories_returns_only_four_approved_roots(self):
        response = self.client.get("/api/v1/catalog/categories/?launch_only=true")
        self.assertEqual(response.status_code, 200)
        results = response.data if isinstance(response.data, list) else response.data.get("results", [])
        self.assertEqual(
            {item["slug"] for item in results},
            {"car-wash", "beauty", "electrical", "home-cleaning"},
        )

    def test_launch_services_excludes_test_roots_and_keeps_subcategory_services(self):
        response = self.client.get("/api/v1/catalog/services/?launch_only=true")
        self.assertEqual(response.status_code, 200)
        results = response.data if isinstance(response.data, list) else response.data.get("results", [])
        titles = {item["title"] for item in results}
        self.assertIn("Side Profile Car Wash", titles)
        self.assertIn("Car Wash sample", titles)
        self.assertNotIn("Test sample", titles)
        self.assertNotIn("Test QA sample", titles)

    def test_launch_service_detail_rejects_service_outside_launch_roots(self):
        response = self.client.get(
            f"/api/v1/catalog/services/{self.services['test'].id}/?launch_only=true"
        )
        self.assertEqual(response.status_code, 404)



class BeautyAudienceValidationTest(TestCase):
    def setUp(self):
        self.root = Category.objects.create(title="Beauty", slug="beauty")
        self.hair = Category.objects.create(
            title="Hair Services", slug="hair-services", parent=self.root
        )
        self.mens_service = Service.objects.create(
            category=self.hair, title="Men's Haircut", audience="men"
        )
        self.womens_service = Service.objects.create(
            category=self.hair, title="Women's Haircut", audience="women"
        )
        self.unisex_service = Service.objects.create(
            category=self.hair, title="Head Massage", audience="all"
        )

    def test_men_selection_accepts_men_and_unisex_services(self):
        from apps.catalog.audience import validate_beauty_audience

        validate_beauty_audience(self.mens_service, {"beauty_audience": "men"})
        validate_beauty_audience(self.unisex_service, {"beauty_audience": "men"})

    def test_women_selection_rejects_mens_only_service(self):
        from apps.catalog.audience import validate_beauty_audience

        with self.assertRaisesMessage(ValueError, "not listed for the selected Beauty audience"):
            validate_beauty_audience(self.mens_service, {"beauty_audience": "women"})

    def test_both_selection_accepts_only_unisex_services(self):
        from apps.catalog.audience import validate_beauty_audience

        validate_beauty_audience(self.unisex_service, {"beauty_audience": "both"})
        with self.assertRaises(ValueError):
            validate_beauty_audience(self.womens_service, {"beauty_audience": "both"})

    def test_invalid_beauty_audience_is_rejected(self):
        from apps.catalog.audience import validate_beauty_audience

        with self.assertRaisesMessage(ValueError, "Choose Men, Women or Both"):
            validate_beauty_audience(self.unisex_service, {"beauty_audience": "children"})



class CategoryAudienceOptionsApiTest(TestCase):
    def test_category_tree_exposes_admin_managed_audience_options(self):
        from apps.catalog.models import CategoryAudienceOption

        beauty = Category.objects.create(title="Beauty", slug="beauty")
        CategoryAudienceOption.objects.create(
            category=beauty,
            audience="men",
            title="Men",
            subtitle="Haircut and grooming",
            image="",
            sort_order=1,
            is_active=True,
        )
        CategoryAudienceOption.objects.create(
            category=beauty,
            audience="women",
            title="Women",
            subtitle="Hair, skin and makeup",
            image="",
            sort_order=2,
            is_active=False,
        )

        response = APIClient().get("/api/v1/catalog/categories/?launch_only=true")

        self.assertEqual(response.status_code, 200, response.data)
        result = next(item for item in response.data["results"] if item["slug"] == "beauty")
        self.assertEqual(
            [item["audience"] for item in result["audience_options"]],
            ["men"],
        )
        self.assertEqual(result["audience_options"][0]["title"], "Men")

class BeautyCatalogueStagingCommandTest(TestCase):
    def test_beauty_catalogue_command_stages_new_records_inactive_and_idempotently(self):
        from django.core.management import call_command

        root = Category.objects.create(title="Beauty", slug="beauty")
        Category.objects.create(
            title="Grooming & Massage",
            slug="grooming-massage",
            parent=root,
        )

        call_command("configure_beauty_catalogue", verbosity=0)

        service = Service.objects.get(
            category__parent=root,
            title="Men's Face Cleanup",
        )
        self.assertFalse(service.is_active)
        self.assertEqual(service.audience, Service.Audience.MEN)
        self.assertTrue(service.variants.exists())
        self.assertTrue(service.form_fields.exists())

        variant = service.variants.first()
        self.assertFalse(variant.is_active)
        self.assertEqual(variant.price, 0)

        # Admin changes must survive a rerun of the staging command.
        service.description = "Admin-approved description draft"
        service.save(update_fields=["description", "updated_at"])
        call_command("configure_beauty_catalogue", verbosity=0)
        service.refresh_from_db()
        self.assertEqual(service.description, "Admin-approved description draft")
        self.assertEqual(
            Service.objects.filter(category__parent=root, title="Men's Face Cleanup").count(),
            1,
        )

