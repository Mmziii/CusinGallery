from django.urls import reverse
from rest_framework import status
from apps.core.testing import CacheIsolatedAPITestCase

from ..models import Address
from .helpers import make_user


def address_payload(**overrides):
    payload = {
        "recipient_name": "Sara Ahmadi",
        "phone": "+989121234567",
        "province": "Tehran",
        "city": "Tehran",
        "address": "Valiasr St, No. 10",
        "postal_code": "1234567890",
        "unit": "",
        "building_number": "10",
        "is_default": False,
    }
    payload.update(overrides)
    return payload


class AddressCrudTests(CacheIsolatedAPITestCase):
    def setUp(self):
        self.list_url = reverse("address-list")
        self.user = make_user(phone="+989131111111")
        self.client.login(username="+989131111111", password="a-strong-passw0rd!")

    def test_create_address(self):
        response = self.client.post(self.list_url, address_payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        address = Address.objects.get(pk=response.data["id"])
        self.assertEqual(address.user, self.user)
        self.assertEqual(address.city, "Tehran")

    def test_invalid_postal_code_is_rejected(self):
        response = self.client.post(self.list_url, address_payload(postal_code="abc"), format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("postal_code", response.data)

    def test_list_only_returns_own_addresses(self):
        other_user = make_user(phone="+989132222222")
        Address.objects.create(user=other_user, **{**address_payload(), "recipient_name": "Not Mine"})
        Address.objects.create(user=self.user, **address_payload())

        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = [a["recipient_name"] for a in response.data["results"]] if "results" in response.data else [
            a["recipient_name"] for a in response.data
        ]
        self.assertEqual(names, ["Sara Ahmadi"])

    def test_update_own_address(self):
        address = Address.objects.create(user=self.user, **address_payload())
        detail_url = reverse("address-detail", args=[address.pk])

        response = self.client.patch(detail_url, {"city": "شهریار"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        address.refresh_from_db()
        self.assertEqual(address.city, "شهریار")

    def test_delete_own_address(self):
        address = Address.objects.create(user=self.user, **address_payload())
        detail_url = reverse("address-detail", args=[address.pk])

        response = self.client.delete(detail_url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Address.objects.filter(pk=address.pk).exists())

    def test_anonymous_cannot_access_addresses(self):
        self.client.logout()
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class AddressIsolationTests(CacheIsolatedAPITestCase):
    """User A must never be able to read, modify, or delete User B's
    address -- covers both the queryset-level scoping and the IsOwner
    permission independently exercising the same guarantee."""

    def setUp(self):
        self.owner = make_user(phone="+989133333333")
        self.intruder = make_user(phone="+989134444444")
        self.address = Address.objects.create(user=self.owner, **address_payload())
        self.detail_url = reverse("address-detail", args=[self.address.pk])

    def test_other_user_cannot_view_address(self):
        self.client.login(username="+989134444444", password="a-strong-passw0rd!")
        response = self.client.get(self.detail_url)
        # 404, not 403 -- get_queryset() is scoped to the requester's own
        # addresses, so another user's address doesn't exist from this
        # user's point of view at all (see AddressViewSet.get_queryset).
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_other_user_cannot_update_address(self):
        self.client.login(username="+989134444444", password="a-strong-passw0rd!")
        response = self.client.patch(self.detail_url, {"city": "Hacked"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.address.refresh_from_db()
        self.assertNotEqual(self.address.city, "Hacked")

    def test_other_user_cannot_delete_address(self):
        self.client.login(username="+989134444444", password="a-strong-passw0rd!")
        response = self.client.delete(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(Address.objects.filter(pk=self.address.pk).exists())

    def test_other_user_addresses_not_in_intruders_list(self):
        self.client.login(username="+989134444444", password="a-strong-passw0rd!")
        response = self.client.get(reverse("address-list"))
        results = response.data["results"] if "results" in response.data else response.data
        self.assertEqual(len(results), 0)


class DefaultAddressBehaviorTests(CacheIsolatedAPITestCase):
    """Exercises the API-level swap logic against the real Phase 2
    database constraint (addr_one_default_per_user) -- these must agree,
    or a request would fail with a raw IntegrityError instead of a clean
    API response."""

    def setUp(self):
        self.list_url = reverse("address-list")
        self.user = make_user(phone="+989135555555")
        self.client.login(username="+989135555555", password="a-strong-passw0rd!")

    def test_creating_a_default_address_when_none_exists(self):
        response = self.client.post(self.list_url, address_payload(is_default=True), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["is_default"])

    def test_creating_a_second_default_unsets_the_first(self):
        first = self.client.post(self.list_url, address_payload(is_default=True), format="json").data
        second = self.client.post(
            self.list_url, address_payload(recipient_name="Second Address", is_default=True), format="json"
        ).data

        first_addr = Address.objects.get(pk=first["id"])
        second_addr = Address.objects.get(pk=second["id"])
        self.assertFalse(first_addr.is_default)
        self.assertTrue(second_addr.is_default)
        # The real database constraint from Phase 2 must still hold: at
        # most one default row for this user.
        self.assertEqual(Address.objects.filter(user=self.user, is_default=True).count(), 1)

    def test_updating_an_address_to_default_unsets_the_previous_one(self):
        first = self.client.post(self.list_url, address_payload(is_default=True), format="json").data
        second = self.client.post(
            self.list_url, address_payload(recipient_name="Second Address", is_default=False), format="json"
        ).data

        detail_url = reverse("address-detail", args=[second["id"]])
        response = self.client.patch(detail_url, {"is_default": True}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertFalse(Address.objects.get(pk=first["id"]).is_default)
        self.assertTrue(Address.objects.get(pk=second["id"]).is_default)
        self.assertEqual(Address.objects.filter(user=self.user, is_default=True).count(), 1)

    def test_set_default_action_swaps_default_atomically(self):
        first = self.client.post(self.list_url, address_payload(is_default=True), format="json").data
        second = self.client.post(
            self.list_url, address_payload(recipient_name="Second Address"), format="json"
        ).data

        set_default_url = reverse("address-set-default", args=[second["id"]])
        response = self.client.post(set_default_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertFalse(Address.objects.get(pk=first["id"]).is_default)
        self.assertTrue(Address.objects.get(pk=second["id"]).is_default)
        self.assertEqual(Address.objects.filter(user=self.user, is_default=True).count(), 1)

    def test_two_different_users_can_each_have_their_own_default(self):
        """Regression guard for the exact constraint shape: the unique
        condition is scoped per-user (fields=["user"], condition
        is_default=True), so two different users each having a default
        address must NOT collide with each other."""
        other = make_user(phone="+989136666666")
        Address.objects.create(user=self.user, **{**address_payload(), "is_default": True})
        # Different user, also default -- must succeed.
        Address.objects.create(user=other, **{**address_payload(), "is_default": True})

        self.assertEqual(Address.objects.filter(user=self.user, is_default=True).count(), 1)
        self.assertEqual(Address.objects.filter(user=other, is_default=True).count(), 1)
