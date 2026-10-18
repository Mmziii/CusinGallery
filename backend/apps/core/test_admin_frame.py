"""Same-origin framing for the admin's own popups (Task 1).

The RelatedObjectLookups "+" buttons open ``/admin/...?_popup=1`` in an
in-page iframe. The global ``X_FRAME_OPTIONS`` is DENY (production, and
Django's default), which left that iframe blank; admin responses must be
``SAMEORIGIN`` instead, while the storefront and the API stay DENY.

Also covers the nginx side: the edge proxies Django's header untouched,
so the admin location must hide the conflicting value and send exactly
one SAMEORIGIN.
"""
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase
from django.urls import reverse

from apps.core.testing import CacheIsolatedAPITestCase

NGINX_ROOT = Path(settings.BASE_DIR).parent / "nginx"
NGINX_FILES = (
    NGINX_ROOT / "conf.d" / "cusin.conf",
    NGINX_ROOT / "prod.d" / "cusin.conf",
    NGINX_ROOT / "prod.d" / "00-bootstrap-http.conf.example",
)


def strip_comments(text):
    """Drop ``#`` comments (these files never use ``#`` inside a token)."""
    out = []
    for line in text.splitlines():
        quote = None
        cleaned = []
        for char in line:
            if quote:
                cleaned.append(char)
                if char == quote:
                    quote = None
            elif char in "\"'":
                quote = char
                cleaned.append(char)
            elif char == "#":
                break
            else:
                cleaned.append(char)
        out.append("".join(cleaned))
    return "\n".join(out)


def location_blocks(text):
    """Yield ``(header, body)`` for every ``location`` block (indent-based)."""
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.lstrip()
        if not stripped.startswith("location ") or not stripped.rstrip().endswith("{"):
            index += 1
            continue
        indent = len(line) - len(stripped)
        header = stripped[:-1].strip()
        body = []
        index += 1
        while index < len(lines):
            candidate = lines[index]
            if candidate.strip() == "}" and len(candidate) - len(candidate.lstrip()) == indent:
                break
            body.append(candidate)
            index += 1
        yield header, "\n".join(body)


class AdminFrameHeaderTests(CacheIsolatedAPITestCase):
    """The admin (and only the admin) may be framed by this origin."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = get_user_model().objects.create_user(
            username="frame-staff",
            password="frame-test-pass-123",
            is_staff=True,
            is_superuser=True,
            is_active=True,
        )

    def setUp(self):
        self.client.force_login(self.staff)

    def test_admin_popup_response_is_sameorigin(self):
        response = self.client.get(reverse("admin:login") + "?_popup=1")
        self.assertIn(response.status_code, (200, 302))
        self.assertEqual(response["X-Frame-Options"], "SAMEORIGIN")

    def test_admin_index_is_sameorigin(self):
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Frame-Options"], "SAMEORIGIN")

    def test_admin_model_popup_page_is_sameorigin(self):
        response = self.client.get(reverse("admin:categories_category_add") + "?_popup=1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Frame-Options"], "SAMEORIGIN")

    def test_storefront_page_stays_deny(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Frame-Options"], "DENY")

    def test_api_stays_deny(self):
        response = self.client.get("/api/v1/products/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Frame-Options"], "DENY")

    def test_only_one_x_frame_options_value_is_sent(self):
        """Never SAMEORIGIN and DENY together (browsers honour the stricter)."""
        response = self.client.get(reverse("admin:index"))
        values = [
            value for key, value in response.items() if key.lower() == "x-frame-options"
        ]
        self.assertEqual(values, ["SAMEORIGIN"])

    def test_csp_frame_ancestors_is_relaxed_to_self_for_admin_only(self):
        from apps.core import middleware

        response = self.client.get(reverse("admin:index"))
        response["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none'"
        processed = middleware.AdminFrameOptionsMiddleware(lambda request: response)(
            response.wsgi_request
        )
        self.assertEqual(
            processed["Content-Security-Policy"],
            "default-src 'self'; frame-ancestors 'self'",
        )


class AdminNginxFrameTests(SimpleTestCase):
    """The edge must not add a second, conflicting X-Frame-Options."""

    def test_admin_locations_send_sameorigin_and_hide_the_upstream_header(self):
        for path in NGINX_FILES:
            source = strip_comments(path.read_text(encoding="utf-8"))
            admin_blocks = [
                (header, body) for header, body in location_blocks(source) if "/admin/" in header
            ]
            self.assertTrue(admin_blocks, f"{path.name}: no /admin/ location found")
            for header, body in admin_blocks:
                with self.subTest(config=path.name, location=header):
                    self.assertNotIn(
                        'X-Frame-Options "DENY"',
                        body,
                        f"{path.name}: '{header}' still emits DENY -- the "
                        f"popup iframe stays blank",
                    )
                    self.assertRegex(
                        body,
                        r'add_header\s+X-Frame-Options\s+"SAMEORIGIN"\s+always\s*;',
                        f"{path.name}: '{header}' must send SAMEORIGIN",
                    )
                    self.assertRegex(
                        body,
                        r"proxy_hide_header\s+X-Frame-Options\s*;",
                        f"{path.name}: '{header}' must hide Django's X-Frame-Options "
                        f"so the response never carries two different values",
                    )

    def test_no_location_sends_both_frame_values(self):
        for path in NGINX_FILES:
            source = strip_comments(path.read_text(encoding="utf-8"))
            for header, body in location_blocks(source):
                with self.subTest(config=path.name, location=header):
                    self.assertFalse(
                        'X-Frame-Options "DENY"' in body
                        and 'X-Frame-Options "SAMEORIGIN"' in body,
                        f"{path.name}: '{header}' sends both DENY and SAMEORIGIN",
                    )
