"""
Banners and daily-deals tests: active/date-window filtering, ordering,
CTA fields, expiration, server-provided timing, and honest (non-fake)
deal content.
"""
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.products.tests.helpers import make_image, make_product

from ..models import Banner, DailyDeal

BANNER_URL = reverse("banner-list")
DEAL_URL = reverse("daily-deal-list")


def make_banner(title, **overrides):
    defaults = {"image": "banners/test.jpg"}
    defaults.update(overrides)
    return Banner.objects.create(title=title, **defaults)


def make_deal(product=None, **overrides):
    from datetime import timedelta

    product = product or make_product()
    defaults = {
        "sale_price": product.price - 10000,
        "starts_at": timezone.now() - timedelta(hours=1),
        "ends_at": timezone.now() + timedelta(hours=5),
    }
    defaults.update(overrides)
    return DailyDeal.objects.create(product=product, **defaults)


class BannerListTests(APITestCase):
    def test_list_returns_only_active_banners(self):
        make_banner("Live")
        make_banner("Disabled", is_active=False)
        response = self.client.get(BANNER_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([b["title"] for b in response.data], ["Live"])

    def test_date_window_is_enforced(self):
        now = timezone.now()
        make_banner("Current")
        make_banner("Future", start_date=now + timezone.timedelta(days=1))
        make_banner("Past", end_date=now - timezone.timedelta(days=1))
        make_banner("NoDates")  # open-ended window = always current

        response = self.client.get(BANNER_URL)
        titles = [b["title"] for b in response.data]
        self.assertEqual(set(titles), {"Current", "NoDates"})

    def test_ordering_field_controls_position(self):
        make_banner("Second", ordering=2)
        make_banner("First", ordering=1)
        make_banner("Third", ordering=3)
        response = self.client.get(BANNER_URL)
        self.assertEqual([b["title"] for b in response.data], ["First", "Second", "Third"])

    def test_cta_fields_are_serialized(self):
        make_banner("Sale", cta_text="Buy now", cta_url="/shop/?sale=1", subtitle="Big sale")
        response = self.client.get(BANNER_URL)
        banner = response.data[0]
        self.assertEqual(banner["cta_text"], "Buy now")
        self.assertEqual(banner["cta_url"], "/shop/?sale=1")
        self.assertEqual(banner["subtitle"], "Big sale")
        self.assertIn("image", banner)


class DailyDealTests(APITestCase):
    def test_only_active_current_deals_for_active_products(self):
        now = timezone.now()
        live_product = make_product(name="Live Deal Product", slug="live-deal")
        make_image(live_product, is_primary=True)
        make_deal(product=live_product)

        expired_product = make_product(name="Expired Product", slug="expired-deal")
        make_deal(product=expired_product, ends_at=now - timezone.timedelta(hours=1))

        future_product = make_product(name="Future Product", slug="future-deal")
        make_deal(
            product=future_product,
            starts_at=now + timezone.timedelta(hours=1),
            ends_at=now + timezone.timedelta(hours=2),
        )

        inactive_flag_product = make_product(name="Flagged Off", slug="flagged-deal")
        make_deal(product=inactive_flag_product, is_active=False)

        inactive_product = make_product(name="Inactive Product", slug="inactive-product", is_active=False)
        make_deal(product=inactive_product)

        response = self.client.get(DEAL_URL)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["product"]["slug"], "live-deal")

    def test_response_carries_server_time_and_real_window(self):
        deal = make_deal()
        response = self.client.get(DEAL_URL)
        payload = response.data

        self.assertIn("server_now", payload)
        server_now = timezone.datetime.fromisoformat(payload["server_now"])
        self.assertTrue((timezone.now() - server_now).total_seconds() < 10)

        result = payload["results"][0]
        self.assertEqual(result["id"], deal.pk)
        self.assertEqual(result["sale_price"], deal.sale_price)
        # The countdown inputs are real: ends_at is in the future, and
        # there is no synthetic "always on" deal fabricating urgency.
        ends_at = timezone.datetime.fromisoformat(result["ends_at"])
        self.assertGreater(ends_at, server_now)

    def test_deal_product_uses_catalog_price_shape(self):
        product = make_product(price=120000, slug="deal-price-shape")
        make_image(product, is_primary=True)
        make_deal(product=product, sale_price=99000)
        response = self.client.get(DEAL_URL)
        embedded = response.data["results"][0]["product"]
        self.assertEqual(embedded["price_info"]["price"], 120000)
        self.assertIsNotNone(embedded["primary_image"])

    def test_empty_when_nothing_is_active(self):
        response = self.client.get(DEAL_URL)
        self.assertEqual(response.data["results"], [])
