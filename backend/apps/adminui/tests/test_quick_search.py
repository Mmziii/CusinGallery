"""B6: staff-only quick-search JSON endpoint -- permissions, Persian
normalization, per-group limits, sections and throttling."""
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.testing import CacheIsolationMixin
from apps.orders.models import Order

from .helpers import (
    PLAIN_STATIC,
    make_customer,
    make_order,
    make_product,
    make_staff,
    make_superuser,
)

URL = "admin_quick_search"


@override_settings(**PLAIN_STATIC)
class QuickSearchAccessTests(CacheIsolationMixin, TestCase):
    def setUp(self):
        self.url = reverse(URL)

    def test_anonymous_is_redirected_to_login(self):
        response = self.client.get(self.url, {"q": "کتری"})
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("admin:login"), response["Location"])

    def test_non_staff_customer_is_redirected(self):
        self.client.force_login(make_customer())
        response = self.client.get(self.url, {"q": "کتری"})
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("admin:login"), response["Location"])

    def test_post_is_not_allowed(self):
        self.client.force_login(make_superuser(username="qs1", phone="+989000050001"))
        response = self.client.post(self.url, {"q": "کتری"})
        self.assertEqual(response.status_code, 405)

    def test_short_query_returns_no_groups(self):
        self.client.force_login(make_superuser(username="qs2", phone="+989000050002"))
        make_product(name="کتری لعابی")
        response = self.client.get(self.url, {"q": "ک"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["groups"], [])


@override_settings(**PLAIN_STATIC)
class QuickSearchResultTests(CacheIsolationMixin, TestCase):
    def setUp(self):
        self.admin = make_superuser(username="qs3", phone="+989000050003")
        self.client.force_login(self.admin)
        self.url = reverse(URL)

    def _search(self, q):
        response = self.client.get(self.url, {"q": q})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        body = response.json()
        self.assertEqual(body["query"], q)
        return {g["id"]: g for g in body["groups"]}

    def test_finds_order_by_number(self):
        order = make_order()
        groups = self._search(order.order_number)
        self.assertIn("orders", groups)
        titles = [r["title"] for r in groups["orders"]["results"]]
        self.assertIn(order.order_number, titles)
        result = groups["orders"]["results"][0]
        self.assertEqual(
            result["url"],
            reverse("admin:orders_order_change", args=[order.pk]),
        )
        self.assertIn("تومان", result["subtitle"])

    def test_finds_order_and_customer_by_persian_digits(self):
        customer = make_customer(phone="09120001122", username="09120001122")
        order = make_order(user=customer, shipping_phone="09120001122")
        groups = self._search("۰۹۱۲۰۰۰۱۱۲۲")   # Persian digits
        self.assertIn("orders", groups)
        self.assertIn(order.order_number,
                      [r["title"] for r in groups["orders"]["results"]])
        self.assertIn("customers", groups)
        # a shorter digit run also matches (contains-style)
        groups = self._search("۰۹۱۲")
        self.assertIn("orders", groups)
        self.assertIn("customers", groups)

    def test_product_search_uses_storefront_normalizer(self):
        product = make_product(name="لیوان سرامیکی", sku="LIV-1")
        # Arabic ي instead of Persian ی + ZWNJ-free query must still match
        groups = self._search("ليوان")
        self.assertIn("products", groups)
        self.assertIn(product.name, [r["title"] for r in groups["products"]["results"]])
        # SKU substring
        groups = self._search("liv-1")
        self.assertIn("products", groups)

    def test_product_group_limit_is_five(self):
        for i in range(7):
            make_product(name=f"کالای شماره {i}", sku=f"KALA-{i}")
        groups = self._search("کالا")
        self.assertEqual(len(groups["products"]["results"]), 5)

    def test_sections_group(self):
        groups = self._search("سفارش")
        self.assertIn("sections", groups)
        titles = [r["title"] for r in groups["sections"]["results"]]
        self.assertIn("سفارش‌ها", titles)
        row = next(r for r in groups["sections"]["results"] if r["title"] == "سفارش‌ها")
        self.assertEqual(row["url"], reverse("admin:orders_order_changelist"))

    def test_no_leak_of_other_customer_orders_via_username(self):
        order = make_order()  # its own customer
        stranger = make_customer(phone="+989999998888", username="+989999998888")
        groups = self._search(stranger.username)
        if "orders" in groups:
            self.assertNotIn(
                order.order_number,
                [r["title"] for r in groups["orders"]["results"]],
            )


@override_settings(**PLAIN_STATIC)
class QuickSearchPermissionTests(CacheIsolationMixin, TestCase):
    def setUp(self):
        self.url = reverse(URL)
        self.order = make_order()
        make_product(name="کتری لعابی")
        self.customer = make_customer(first_name="کتری", last_name="دوست")

    def test_orders_only_staff_gets_only_orders_and_sections(self):
        staff = make_staff(permissions=["orders.view_order"],
                           username="+989000051001", phone="+989000051001")
        self.client.force_login(staff)
        response = self.client.get(self.url, {"q": self.order.order_number})
        groups = {g["id"] for g in response.json()["groups"]}
        self.assertIn("orders", groups)
        self.assertNotIn("products", groups)
        self.assertNotIn("customers", groups)
        # section scoping shows on a label query
        response = self.client.get(self.url, {"q": "سفارش"})
        body = response.json()
        sections = [g for g in body["groups"] if g["id"] == "sections"]
        self.assertTrue(sections)
        titles = [r["title"] for r in sections[0]["results"]]
        self.assertIn("سفارش‌ها", titles)
        self.assertNotIn("محصولات", titles)

    def test_products_only_staff_gets_no_order_numbers(self):
        staff = make_staff(permissions=["products.view_product"],
                           username="+989000051002", phone="+989000051002")
        self.client.force_login(staff)
        response = self.client.get(self.url, {"q": "کتری"})
        groups = {g["id"] for g in response.json()["groups"]}
        self.assertNotIn("orders", groups)
        self.assertIn("products", groups)
        body = response.content.decode()
        self.assertNotIn(self.order.order_number, body)

    def test_superuser_gets_every_group(self):
        self.client.force_login(
            make_superuser(username="qs4", phone="+989000050004")
        )
        response = self.client.get(self.url, {"q": "کتری"})
        groups = {g["id"] for g in response.json()["groups"]}
        self.assertTrue({"products", "customers"} <= groups)
        response = self.client.get(self.url, {"q": "سفارش"})
        self.assertIn("sections", {g["id"] for g in response.json()["groups"]})


@override_settings(**PLAIN_STATIC)
class QuickSearchThrottleTests(CacheIsolationMixin, TestCase):
    def setUp(self):
        cache.clear()
        self.staff = make_staff(permissions=["orders.view_order"],
                                username="+989000051003", phone="+989000051003")
        self.client.force_login(self.staff)
        self.url = reverse(URL)

    def test_rate_limit_after_60_requests_per_minute(self):
        for i in range(60):
            response = self.client.get(self.url, {"q": "سفارش"})
            self.assertEqual(response.status_code, 200, f"request {i+1}")
        response = self.client.get(self.url, {"q": "سفارش"})
        self.assertEqual(response.status_code, 429)
        self.assertIn("صبر کنید", response.json()["detail"])
