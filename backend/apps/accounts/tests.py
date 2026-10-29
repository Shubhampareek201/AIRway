
from django.contrib.auth import get_user_model

from rest_framework import status
from rest_framework.test import APITestCase

from apps.core.models import City, Zone
from .models import Address


User = get_user_model()


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
