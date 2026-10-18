from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote
from xml.etree import ElementTree

from django.conf import settings
from django.test import SimpleTestCase, TestCase, override_settings

from apps.products.tests.helpers import make_brand


@override_settings(FRONTEND_URL="https://cusin.ir")
class BrandPageTests(TestCase):
    def test_active_brand_is_200_for_raw_and_encoded_slugs_with_or_without_slash(self):
        brand = make_brand(name="برند ایرانی", slug="برند-ایرانی")
        shell = '<html><head></head><body><div id="root"></div></body></html>'
        with patch("apps.core.spa.shell_html", return_value=shell):
            for slug in (brand.slug, quote(brand.slug)):
                for suffix in ("/", ""):
                    with self.subTest(slug=slug, suffix=suffix):
                        response = self.client.get(f"/brands/{slug}{suffix}")
                        self.assertEqual(response.status_code, 200)
                        self.assertNotIn("noindex", response.content.decode())

    def test_unknown_and_inactive_brands_are_real_404s_not_empty_200_lists(self):
        brand = make_brand(slug="inactive", is_active=False)
        for slug in (brand.slug, "unknown-brand"):
            with self.subTest(slug=slug):
                response = self.client.get(f"/brands/{slug}/")
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response["X-Robots-Tag"], "noindex")
                self.assertIn("noindex", response.content.decode())

    def test_sitemap_includes_only_active_brands_and_encodes_unicode(self):
        brand = make_brand(slug="برند-ایرانی")
        make_brand(slug="hidden", is_active=False)
        response = self.client.get("/sitemap.xml")
        tree = ElementTree.fromstring(response.content)
        namespace = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        urls = [node.text for node in tree.findall("s:url/s:loc", namespace)]
        self.assertIn(f"https://cusin.ir/brands/{quote(brand.slug)}/", urls)
        self.assertNotIn("https://cusin.ir/brands/hidden/", urls)
        self.assertNotIn(f"https://cusin.ir/brands/{brand.slug}/", urls)

    def test_crawler_gets_brand_title_canonical_and_share_image(self):
        brand = make_brand(name="برند 123", slug="برند-ایرانی", logo="brands/logo.jpg")
        response = self.client.get(f"/seo/brand/{quote(brand.slug)}/", {"page": "2"})
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("محصولات برند برند ۱۲۳", body)
        self.assertIn(f'<link rel="canonical" href="https://cusin.ir/brands/{quote(brand.slug)}/">', body)
        self.assertIn('content="https://cusin.ir/media/brands/logo.jpg"', body)
        self.assertNotIn("?page=", body)

    def test_crawler_uses_placeholder_and_rejects_inactive_and_unknown_brands(self):
        active = make_brand()
        inactive = make_brand(is_active=False)
        self.assertIn("/brand/og-placeholder.png", self.client.get(f"/seo/brand/{active.slug}/").content.decode())
        for slug in (inactive.slug, "unknown-brand"):
            self.assertEqual(self.client.get(f"/seo/brand/{slug}/").status_code, 404)


class BrandCrawlerRoutingTests(SimpleTestCase):
    def test_both_edge_configs_route_brand_bots_without_bypassing_the_status_check(self):
        root = Path(settings.BASE_DIR).parent
        for config in (root / "nginx/conf.d/cusin.conf", root / "nginx/prod.d/cusin.conf"):
            with self.subTest(config=config):
                text = config.read_text()
                self.assertIn("location ~ ^/brands/(?<cusin_brand_slug>[^/]+)/$", text)
                self.assertIn("rewrite ^ /seo/brand/$cusin_brand_slug/ break;", text)
