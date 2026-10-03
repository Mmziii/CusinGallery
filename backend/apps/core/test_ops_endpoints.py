"""
Ops/SEO endpoint tests (Phase E): /healthz, /robots.txt, /sitemap.xml.

Real HTTP through the test client against the real URLconf, and the
sitemap test uses a REAL Persian slug to prove non-ASCII URLs are
percent-encoded exactly as the sitemap protocol requires.
"""
from urllib.parse import quote

from django.test import TestCase, override_settings

from apps.categories.models import Category
from apps.products.models import Product


class HealthzTests(TestCase):
    def test_healthy_returns_200_json(self):
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "database": "ok"})

    def test_no_auth_required_and_no_secrets_exposed(self):
        response = self.client.get("/healthz")
        body = response.content.decode()
        self.assertEqual(response.status_code, 200)
        for secret in ("SECRET_KEY", "POSTGRES_PASSWORD", "KAVENEGAR", "MERCHANT"):
            self.assertNotIn(secret, body)


class RobotsTxtTests(TestCase):
    @override_settings(FRONTEND_URL="https://cusin.ir")
    def test_policy_and_sitemap_reference(self):
        response = self.client.get("/robots.txt")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/plain", response["Content-Type"])
        body = response.content.decode()
        self.assertIn("User-agent: *", body)
        self.assertIn("Disallow: /admin/", body)
        self.assertIn("Disallow: /api/", body)
        self.assertIn("Sitemap: https://cusin.ir/sitemap.xml", body)


@override_settings(FRONTEND_URL="https://cusin.ir")
class SitemapXmlTests(TestCase):
    def make_product(self, slug, name, is_active=True):
        category = Category.objects.create(name=f"cat-{slug}", slug=f"cat-{slug}")
        return Product.objects.create(
            name=name, slug=slug, sku=f"SKU-{slug}", price=100000,
            stock_quantity=5, category=category, is_active=is_active,
        )

    def test_includes_static_pages_and_active_products(self):
        self.make_product("wooden-spoon", "Wooden Spoon")
        response = self.client.get("/sitemap.xml")
        self.assertEqual(response.status_code, 200)
        self.assertIn("application/xml", response["Content-Type"])
        body = response.content.decode()
        self.assertIn("<loc>https://cusin.ir/</loc>", body)
        self.assertIn("<loc>https://cusin.ir/shop/</loc>", body)
        self.assertIn("<loc>https://cusin.ir/about/</loc>", body)
        self.assertIn("<loc>https://cusin.ir/products/wooden-spoon/</loc>", body)
        self.assertIn("<lastmod>", body)

    def test_inactive_products_are_excluded(self):
        self.make_product("hidden-pan", "Hidden Pan", is_active=False)
        body = self.client.get("/sitemap.xml").content.decode()
        self.assertNotIn("hidden-pan", body)

    def test_persian_slugs_are_percent_encoded(self):
        persian_slug = "قاشق-چوبی"
        self.make_product(persian_slug, "قاشق چوبی")
        body = self.client.get("/sitemap.xml").content.decode()
        # The raw Persian characters must NOT appear in <loc> values --
        # the sitemap protocol requires RFC-3986 percent-encoding.
        self.assertNotIn(f"/products/{persian_slug}/", body)
        self.assertIn(f"/products/{quote(persian_slug)}/", body)
        self.assertIn(quote("قاشق")[1:], body)  # e.g. %D9%82%D8%A7%D8%B4%D9%82

    def test_unicode_slug_is_accepted_by_the_model_layer(self):
        """allow_unicode=True on the slug fields is what makes Persian
        URLs possible in the first place (Phase E)."""
        product = self.make_product("ماهیتابه-گرانیتی", "ماهیتابه گرانیتی")
        product.full_clean(exclude=["category", "brand"])  # validators must accept the slug
        self.assertEqual(product.slug, "ماهیتابه-گرانیتی")
