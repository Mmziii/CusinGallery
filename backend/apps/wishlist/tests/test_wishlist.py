from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from ..models import WishlistItem
from .helpers import make_product, make_user


class WishlistAuthenticationTests(APITestCase):
    def test_anonymous_cannot_list_wishlist(self):
        response = self.client.get(reverse("wishlist"))
        # 403, not 401 -- see apps/cart/tests/test_authentication.py's
        # comment for why (SessionAuthentication is the only registered
        # authenticator in this project).
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_cannot_add_item(self):
        response = self.client.post(reverse("wishlist-item-create"), {"product_id": 1}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_cannot_remove_item(self):
        response = self.client.delete(reverse("wishlist-item-detail", args=[1]))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_cannot_check_wishlist_status(self):
        response = self.client.get(reverse("wishlist-check"), {"product": 1})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class WishlistListTests(APITestCase):
    def setUp(self):
        self.user = make_user(phone="+989200000001")
        self.client.login(username="+989200000001", password="a-strong-passw0rd!")

    def test_empty_wishlist(self):
        response = self.client.get(reverse("wishlist"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    def test_list_shows_wishlisted_products(self):
        product = make_product(name="Wishlisted Pot", price=120000)
        WishlistItem.objects.create(user=self.user, product=product)

        response = self.client.get(reverse("wishlist"))
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["product"]["id"], product.id)
        self.assertEqual(response.data[0]["product"]["price_info"]["price"], 120000)
        self.assertTrue(response.data[0]["is_available"])

    def test_list_reuses_phase4_product_list_serializer_shape(self):
        """Confirms the nested product uses the same fields as the
        catalog's own product list endpoint (Phase 4), not a
        reinvented shape."""
        product = make_product()
        WishlistItem.objects.create(user=self.user, product=product)

        response = self.client.get(reverse("wishlist"))
        catalog_response = self.client.get(reverse("product-list"))
        catalog_fields = set(catalog_response.data["results"][0].keys())
        wishlist_product_fields = set(response.data[0]["product"].keys())
        self.assertEqual(catalog_fields, wishlist_product_fields)


class AddWishlistItemTests(APITestCase):
    def setUp(self):
        self.user = make_user(phone="+989200000002")
        self.client.login(username="+989200000002", password="a-strong-passw0rd!")
        self.url = reverse("wishlist-item-create")

    def test_add_product(self):
        product = make_product()
        response = self.client.post(self.url, {"product_id": product.id}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(WishlistItem.objects.filter(user=self.user, product=product).exists())

    def test_adding_same_product_twice_does_not_create_duplicate(self):
        product = make_product()
        first = self.client.post(self.url, {"product_id": product.id}, format="json")
        second = self.client.post(self.url, {"product_id": product.id}, format="json")

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        # Graceful, not an error -- see master spec step 13 ("handle
        # duplicate requests gracefully") and the real
        # unique_wishlist_user_product constraint from Phase 2.
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(WishlistItem.objects.filter(user=self.user, product=product).count(), 1)

    def test_add_nonexistent_product_returns_404(self):
        response = self.client.post(self.url, {"product_id": 999999}, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_add_inactive_product_returns_404(self):
        product = make_product(is_active=False)
        response = self.client.post(self.url, {"product_id": product.id}, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(WishlistItem.objects.filter(product=product).exists())

    def test_missing_product_id_is_rejected(self):
        response = self.client.post(self.url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_non_integer_product_id_is_rejected_cleanly(self):
        response = self.client.post(self.url, {"product_id": "not-a-number"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class RemoveWishlistItemTests(APITestCase):
    def setUp(self):
        self.user = make_user(phone="+989200000003")
        self.client.login(username="+989200000003", password="a-strong-passw0rd!")

    def test_remove_item(self):
        item = WishlistItem.objects.create(user=self.user, product=make_product())
        response = self.client.delete(reverse("wishlist-item-detail", args=[item.pk]))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(WishlistItem.objects.filter(pk=item.pk).exists())

    def test_remove_nonexistent_item_returns_404(self):
        response = self.client.delete(reverse("wishlist-item-detail", args=[999999]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class WishlistOwnershipTests(APITestCase):
    def setUp(self):
        self.owner = make_user(phone="+989200000004")
        self.intruder = make_user(phone="+989200000005")
        self.item = WishlistItem.objects.create(user=self.owner, product=make_product())

    def test_user_cannot_see_another_users_wishlist(self):
        self.client.login(username="+989200000005", password="a-strong-passw0rd!")
        response = self.client.get(reverse("wishlist"))
        self.assertEqual(response.data, [])

    def test_user_cannot_remove_another_users_wishlist_item(self):
        self.client.login(username="+989200000005", password="a-strong-passw0rd!")
        response = self.client.delete(reverse("wishlist-item-detail", args=[self.item.pk]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertTrue(WishlistItem.objects.filter(pk=self.item.pk).exists())

    def test_check_endpoint_is_scoped_to_the_requesting_user(self):
        self.client.login(username="+989200000005", password="a-strong-passw0rd!")
        response = self.client.get(reverse("wishlist-check"), {"product": self.item.product_id})
        self.assertFalse(response.data["is_wishlisted"])


class InactiveProductInWishlistTests(APITestCase):
    def setUp(self):
        self.user = make_user(phone="+989200000006")
        self.client.login(username="+989200000006", password="a-strong-passw0rd!")

    def test_product_deactivated_after_wishlisting_stays_visible_but_flagged(self):
        """See master spec step 13: "if a previously wishlisted product
        becomes inactive, handle it gracefully rather than breaking the
        entire wishlist endpoint" -- the item must stay in the list,
        clearly flagged, not vanish or 500."""
        product = make_product()
        WishlistItem.objects.create(user=self.user, product=product)
        product.is_active = False
        product.save(update_fields=["is_active"])

        response = self.client.get(reverse("wishlist"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertFalse(response.data[0]["is_available"])
        self.assertEqual(response.data[0]["product"]["id"], product.id)


class WishlistCheckTests(APITestCase):
    def setUp(self):
        self.user = make_user(phone="+989200000007")
        self.client.login(username="+989200000007", password="a-strong-passw0rd!")
        self.url = reverse("wishlist-check")

    def test_check_returns_true_when_wishlisted(self):
        product = make_product()
        WishlistItem.objects.create(user=self.user, product=product)
        response = self.client.get(self.url, {"product": product.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["is_wishlisted"])

    def test_check_returns_false_when_not_wishlisted(self):
        product = make_product()
        response = self.client.get(self.url, {"product": product.id})
        self.assertFalse(response.data["is_wishlisted"])

    def test_check_with_missing_product_param_is_rejected(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_malformed_product_param_returns_clean_400_not_500(self):
        """Regression test for the bug found during this phase's own
        review: reading request.query_params.get("product") directly
        into a queryset filter let a non-numeric value reach the ORM
        and raise an uncaught ValueError (a 500). Now validated through
        WishlistCheckSerializer first."""
        response = self.client.get(self.url, {"product": "not-a-number"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("product", response.data)

    def test_check_for_nonexistent_product_returns_false_not_error(self):
        response = self.client.get(self.url, {"product": 999999})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["is_wishlisted"])
