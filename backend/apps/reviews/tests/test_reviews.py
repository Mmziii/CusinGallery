"""
Review tests: authenticated creation, moderation gating, ownership,
duplicate prevention, and server-computed verified-purchase.
"""
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from ..models import Review
from .helpers import make_paid_order_for, make_product, make_unpaid_order_for, make_user

CREATE_URL = reverse("review-create")


def _login(client, user):
    client.login(username=user.username, password="a-strong-passw0rd!")


class CreateReviewTests(APITestCase):
    def setUp(self):
        self.user = make_user(phone="+989600000001")
        self.product = make_product()

    def test_requires_authentication(self):
        response = self.client.post(
            CREATE_URL, {"product_id": self.product.pk, "rating": 5}, format="json"
        )
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_authenticated_user_can_create_pending_review(self):
        _login(self.client, self.user)
        response = self.client.post(
            CREATE_URL,
            {"product_id": self.product.pk, "rating": 4, "title": "Good", "body": "Nice pan"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.content)
        review = Review.objects.get(user=self.user)
        self.assertEqual(review.status, Review.Status.PENDING)
        self.assertEqual(review.rating, 4)
        self.assertFalse(review.is_verified_purchase)

    def test_rating_out_of_range_rejected(self):
        _login(self.client, self.user)
        for bad in (0, 6):
            response = self.client.post(
                CREATE_URL, {"product_id": self.product.pk, "rating": bad}, format="json"
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_inactive_product_rejected(self):
        self.product.is_active = False
        self.product.save(update_fields=["is_active"])
        _login(self.client, self.user)
        response = self.client.post(
            CREATE_URL, {"product_id": self.product.pk, "rating": 5}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_duplicate_review_rejected(self):
        _login(self.client, self.user)
        first = self.client.post(CREATE_URL, {"product_id": self.product.pk, "rating": 5}, format="json")
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        second = self.client.post(CREATE_URL, {"product_id": self.product.pk, "rating": 3}, format="json")
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Review.objects.filter(user=self.user, product=self.product).count(), 1)


class VerifiedPurchaseTests(APITestCase):
    def setUp(self):
        self.user = make_user(phone="+989600000010")
        self.product = make_product()

    def _create_review(self):
        _login(self.client, self.user)
        return self.client.post(CREATE_URL, {"product_id": self.product.pk, "rating": 5}, format="json")

    def test_paid_order_marks_review_verified(self):
        make_paid_order_for(self.user, self.product)
        response = self._create_review()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Review.objects.get(user=self.user).is_verified_purchase)

    def test_unpaid_order_does_not_mark_verified(self):
        make_unpaid_order_for(self.user, self.product)
        response = self._create_review()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(Review.objects.get(user=self.user).is_verified_purchase)

    def test_client_cannot_force_verified_flag(self):
        _login(self.client, self.user)
        response = self.client.post(
            CREATE_URL,
            {"product_id": self.product.pk, "rating": 5, "is_verified_purchase": True},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(Review.objects.get(user=self.user).is_verified_purchase)


class ModerationVisibilityTests(APITestCase):
    def setUp(self):
        self.reviewer = make_user(phone="+989600000020")
        self.product = make_product()
        self.list_url = reverse("product-review-list", args=[self.product.pk])
        self.summary_url = reverse("product-review-summary", args=[self.product.pk])

    def _make_review(self, status_value, rating=5, user=None):
        # One review per user per product is a real constraint, so each
        # fixture review gets its own author.
        return Review.objects.create(
            product=self.product, user=user or make_user(), rating=rating,
            body="x", status=status_value,
        )

    def test_public_list_shows_only_approved(self):
        self._make_review(Review.Status.APPROVED, rating=5)
        self._make_review(Review.Status.PENDING, rating=1)
        self._make_review(Review.Status.REJECTED, rating=2)

        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["rating"], 5)

    def test_summary_counts_only_approved(self):
        self._make_review(Review.Status.APPROVED, rating=5)
        self._make_review(Review.Status.APPROVED, rating=3)
        self._make_review(Review.Status.PENDING, rating=1)  # must not affect score

        response = self.client.get(self.summary_url)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(response.data["average_rating"], 4.0)
        self.assertEqual(response.data["distribution"]["5"], 1)
        self.assertEqual(response.data["distribution"]["3"], 1)
        self.assertEqual(response.data["distribution"]["1"], 0)


class OwnershipTests(APITestCase):
    def setUp(self):
        self.owner = make_user(phone="+989600000030")
        self.other = make_user(phone="+989600000031")
        self.product = make_product()
        self.review = Review.objects.create(
            product=self.product, user=self.owner, rating=4, body="mine",
            status=Review.Status.APPROVED,
        )
        self.detail_url = reverse("review-detail", args=[self.review.pk])

    def test_owner_can_view_edit_delete(self):
        _login(self.client, self.owner)
        self.assertEqual(self.client.get(self.detail_url).status_code, status.HTTP_200_OK)
        patched = self.client.patch(self.detail_url, {"body": "edited"}, format="json")
        self.assertEqual(patched.status_code, status.HTTP_200_OK)
        self.review.refresh_from_db()
        self.assertEqual(self.review.body, "edited")
        self.assertEqual(self.client.delete(self.detail_url).status_code, status.HTTP_204_NO_CONTENT)

    def test_editing_resets_status_to_pending(self):
        _login(self.client, self.owner)
        self.client.patch(self.detail_url, {"rating": 3}, format="json")
        self.review.refresh_from_db()
        self.assertEqual(self.review.status, Review.Status.PENDING)

    def test_other_user_gets_404(self):
        _login(self.client, self.other)
        self.assertEqual(self.client.get(self.detail_url).status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.delete(self.detail_url).status_code, status.HTTP_404_NOT_FOUND)

    def test_anonymous_cannot_access_detail(self):
        response = self.client.get(self.detail_url)
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_my_reviews_lists_own_only(self):
        Review.objects.create(product=self.product, user=self.other, rating=2, status=Review.Status.APPROVED)
        _login(self.client, self.owner)
        response = self.client.get(reverse("review-mine"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], self.review.pk)
