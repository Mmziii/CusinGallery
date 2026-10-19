"""
Audit 19 item 5: a REAL 404 status for unknown storefront URLs.

The bug: nginx answered every page path with the built index.html, so
``/nonexistent-xyz`` and ``/products/does-not-exist/`` returned **200** with
the 404 design (a soft 404) -- crawlers index them, monitoring sees a healthy
page, and the back button "works" on links that should not exist.

The fix: nginx routes page requests to the Django catch-all
(apps/core/spa.py), which knows the SPA's route table AND the database. These
tests pin the contract:

  * known routes / existing active products / existing categories -> 200 and
    the built shell;
  * unknown paths, unknown or inactive product slugs, unknown categories ->
    404, the SAME Persian document, plus <meta name="robots" content="noindex">
    and an X-Robots-Tag header;
  * the cache headers never let a 404 be cached as a shell;
  * API/admin/static/media paths are NOT answered with the storefront shell
    (they keep Django's own 404);
  * with no shell available (a fresh box, the frontend container down) the
    view still answers Persian HTML with the right status -- never a 500 and
    never a blank 200.
"""
from pathlib import Path

from django.test import SimpleTestCase, TestCase, override_settings
from unittest.mock import Mock, patch

from apps.categories.models import Category
from apps.products.tests.helpers import make_category, make_product

import apps.core.spa as spa

SHELL = (
    "<!doctype html><html lang=\"fa\" dir=\"rtl\"><head>"
    "<title>کازین گالری</title></head><body><div id=\"root\"></div>"
    "<script type=\"module\" src=\"/assets/index-abc123.js\"></script></body></html>"
)


class SpawnShellMixin:
    """Serve a fixed shell without touching the filesystem/network."""

    def setUp(self):
        super().setUp()
        spa._shell_cache.update({"html": "", "source": "", "at": 0.0})
        patcher = override_settings(SPA_INDEX_FILE="", SPA_SHELL_URL="")
        patcher.enable()
        self.addCleanup(patcher.disable)
        html_patcher = self._patch_shell()
        self.addCleanup(html_patcher)

    @staticmethod
    def _patch_shell():
        original = spa.shell_html
        spa.shell_html = lambda: SHELL
        def restore():
            spa.shell_html = original
        return restore


class KnownPageTests(SpawnShellMixin, TestCase):
    def test_every_storefront_route_is_a_200(self):
        for path in [
            "/",
            "/shop/",
            "/cart/",
            "/wishlist/",
            "/checkout/",
            "/payment/result/123/",
            "/about/",
            "/contact/",
            "/shipping-returns/",
            "/terms/",
            "/privacy/",
            "/login/",
            "/register/",
            "/password-reset/",
            "/reset-password/confirm/",
            "/account/",
            "/account/orders/",
            "/account/orders/12/",
            "/account/addresses/",
            "/account/reviews/",
        ]:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn("<div id=\"root\"></div>", response.content.decode())
                self.assertEqual(response["Cache-Control"], "no-cache, must-revalidate")
                self.assertNotIn("noindex", response.content.decode())

    def test_existing_active_product_slug_is_a_200(self):
        product = make_product(name="قابلمه استیل", slug="قابلمه-استیل", is_active=True)

        response = self.client.get(f"/products/{product.slug}/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("<div id=\"root\"></div>", response.content.decode())

    def test_existing_active_category_filter_is_a_200(self):
        category = make_category(name="قابلمه", slug="ghabale")

        response = self.client.get("/shop/", {"category": category.slug})

        self.assertEqual(response.status_code, 200)

    def test_shop_accepts_unrelated_and_repeated_query_parameters(self):
        for query in (
            "?q=x",
            "?page=2",
            "?brand=iris",
            "?sort=price",
            "?q=x&page=2&brand=iris&sort=price",
            "?q=first&q=second&page=2&page=3",
            "?q=%E0%A4%A&sort=%",
        ):
            with self.subTest(query=query):
                self.assertEqual(self.client.get(f"/shop/{query}").status_code, 200)

    def test_shop_without_a_category_is_a_200(self):
        self.assertEqual(self.client.get("/shop/").status_code, 200)


class UnknownPageTests(SpawnShellMixin, TestCase):
    def test_unknown_path_is_a_real_404_with_the_same_page(self):
        response = self.client.get("/nonexistent-xyz")
        body = response.content.decode()

        self.assertEqual(response.status_code, 404)
        # Same document the shop uses (the SPA renders its Persian 404), so a
        # customer still gets the designed page...
        self.assertIn("<div id=\"root\"></div>", body)
        self.assertIn("<title>کازین گالری</title>", body)
        self.assertIn("noindex", body)
        # ... and the header carries the same intent for crawlers that never
        # read the HTML.
        self.assertEqual(response["X-Robots-Tag"], "noindex")

    def test_unknown_product_slug_is_a_real_404(self):
        response = self.client.get("/products/does-not-exist/")

        self.assertEqual(response.status_code, 404)
        self.assertIn("noindex", response.content.decode())

    def test_inactive_product_slug_is_a_real_404(self):
        product = make_product(slug="draft-pan", is_active=False)

        response = self.client.get(f"/products/{product.slug}/")

        self.assertEqual(response.status_code, 404)

    def test_unknown_category_is_a_real_404(self):
        response = self.client.get("/shop/", {"category": "nope"})

        self.assertEqual(response.status_code, 404)
        self.assertIn("noindex", response.content.decode())

    def test_unknown_trust_page_and_typo_are_404s(self):
        for path in ["/about-us/", "/shopp/", "/products/", "/account/orders/12/extra/"]:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)

    def test_a_404_is_never_cached_as_a_shell(self):
        response = self.client.get("/nonexistent-xyz")

        self.assertEqual(response.status_code, 404)
        self.assertIn("no-store", response["Cache-Control"])

    def test_noindex_is_added_once(self):
        body = self.client.get("/nonexistent-xyz").content.decode()

        self.assertEqual(body.count('name="robots"'), 1)
        self.assertLess(body.index('name="robots"'), body.index("</head>"))


class NonPagePrefixTests(SpawnShellMixin, TestCase):
    def test_api_admin_static_and_media_are_not_answered_with_the_shell(self):
        for path in [
            "/api/v1/definitely-not-here/",
            "/static/definitely-not-here.css",
            "/media/definitely-not-here.jpg",
        ]:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 404)
                self.assertNotIn("<div id=\"root\"></div>", response.content.decode())

    def test_admin_paths_keep_djangos_own_behaviour(self):
        """/admin/... is not a storefront page: it redirects to the admin login
        (or 404s for an unknown app) and NEVER gets the SPA shell."""
        response = self.client.get("/admin/definitely-not-here/")

        self.assertIn(response.status_code, (302, 404))
        self.assertNotIn("<div id=\"root\"></div>", response.content.decode())

    def test_healthz_and_seo_endpoints_still_work(self):
        self.assertEqual(self.client.get("/healthz").status_code, 200)
        self.assertEqual(self.client.get("/robots.txt").status_code, 200)
        self.assertEqual(self.client.get("/sitemap.xml").status_code, 200)


class ShellSourceTests(SpawnShellMixin, TestCase):
    """The document comes from a file, then the frontend container, then a
    built-in Persian fallback -- and never from a 200 that hides an error."""

    def test_configured_file_is_used_when_it_exists(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            index = Path(tmp) / "index.html"
            index.write_text(SHELL, encoding="utf-8")
            spa._shell_cache.update({"html": "", "source": "", "at": 0.0})
            with override_settings(SPA_INDEX_FILE=str(index)):
                self.assertEqual(spa.shell_html(), SHELL)

    def test_a_file_without_the_root_mount_is_rejected(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            index = Path(tmp) / "index.html"
            index.write_text("<html><body>not the SPA</body></html>", encoding="utf-8")
            spa._shell_cache.update({"html": "", "source": "", "at": 0.0})
            with override_settings(SPA_INDEX_FILE=str(index), SPA_SHELL_URL=""):
                # Falls through to the repository copy (or nothing), never the
                # wrong document.
                self.assertNotEqual(spa.shell_html(), "<html><body>not the SPA</body></html>")

    @patch("requests.get")
    def test_http_shell_is_decoded_as_utf8_when_charset_is_missing(self, get):
        response = Mock(status_code=200, content=SHELL.encode("utf-8"))
        get.return_value = response
        spa._shell_cache.update({"html": "", "source": "", "at": 0.0})
        with override_settings(SPA_INDEX_FILE="", SPA_SHELL_URL="http://frontend/index.html"):
            self.assertEqual(spa._fetch_shell_url("http://frontend/index.html"), SHELL)

    def test_missing_shell_still_answers_persian_html_with_the_right_status(self):
        original = spa.shell_html
        spa.shell_html = lambda: ""  # frontend container unreachable
        self.addCleanup(lambda: setattr(spa, "shell_html", original))

        unknown = self.client.get("/nonexistent-xyz")
        known = self.client.get("/shop/")

        self.assertEqual(unknown.status_code, 404)
        self.assertEqual(known.status_code, 200)
        self.assertIn("۴۰۴", unknown.content.decode())
        self.assertIn("صفحه مورد نظر پیدا نشد", unknown.content.decode())
        self.assertIn("noindex", unknown.content.decode())


class RouteTableGuardTests(TestCase):
    """
    The route table lives in TWO places (frontend/src/App.jsx and spa.py).
    A route added to the SPA and forgotten here would become a 404 on a real
    page, so the guard reads the real router and compares.
    """

    def test_every_spa_route_is_known_to_the_catch_all(self):
        import re as _re

        app_jsx = (
            Path(__import__("django.conf", fromlist=["settings"]).settings.BASE_DIR).parent
            / "frontend" / "src" / "App.jsx"
        ).read_text(encoding="utf-8")

        route_paths = _re.findall(r'path="([^"]+)"', app_jsx)
        self.assertGreater(len(route_paths), 10)

        for route in route_paths:
            # "*" is the SPA's own NotFound route; relative entries are the
            # nested children of /account/ (already covered by its parent).
            if route == "*" or not route.startswith("/"):
                continue
            # /products/:slug/ and /account/orders/:orderId/ need real slug
            # values (checked against the database in other tests), so only
            # the static routes are compared here.
            if ":" in route:
                continue
            with self.subTest(route=route):
                self.assertTrue(
                    spa.is_known_page(route),
                    f"{route} exists in App.jsx but the Django catch-all would 404 it",
                )
