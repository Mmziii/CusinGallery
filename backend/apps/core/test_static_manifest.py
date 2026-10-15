"""Production static cache-busting contracts.

Production uses a strict manifest; development and tests intentionally use
non-manifest storage so pages render before collectstatic has run.
"""
import re
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.staticfiles.storage import staticfiles_storage
from django.core.management import call_command
from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from django.test import Client

BACKEND_DIR = Path(settings.BASE_DIR)
NGINX_FILES = (
    BACKEND_DIR.parent / "nginx" / "conf.d" / "cusin.conf",
    BACKEND_DIR.parent / "nginx" / "prod.d" / "cusin.conf",
    BACKEND_DIR.parent / "nginx" / "prod.d" / "00-bootstrap-http.conf.example",
)
MANIFEST_BACKEND = "whitenoise.storage.CompressedManifestStaticFilesStorage"


class StaticManifestTests(SimpleTestCase):
    def test_development_storage_does_not_require_collectstatic(self):
        self.assertNotEqual(settings.STORAGES["staticfiles"]["BACKEND"], MANIFEST_BACKEND)
        self.assertNotIn("STATICFILES_STORAGE", dir(settings))

    def test_collectstatic_manifest_renders_hashed_login_assets_that_exist(self):
        """Exercise Django's real CSS post-processing and the rendered login
        template, not just the storage class name. A bad url() in theme.css
        must fail collectstatic instead of being hidden with strict=False."""
        with tempfile.TemporaryDirectory(prefix="cusin-static-manifest-") as temp_root:
            storages_setting = {
                **settings.STORAGES,
                "staticfiles": {"BACKEND": MANIFEST_BACKEND},
            }
            with override_settings(
                STORAGES=storages_setting,
                STATIC_ROOT=Path(temp_root),
                DEBUG=False,
            ):
                call_command("collectstatic", interactive=False, verbosity=0)
                storage = staticfiles_storage
                self.assertEqual(storage.__class__.__name__, "CompressedManifestStaticFilesStorage")

                response = Client().get(reverse("admin:login"))
                self.assertEqual(response.status_code, 200)
                html = response.content.decode("utf-8")
                references = {
                    "theme.css": re.search(
                        r'href="([^"]*/admin_theme/css/theme\.[a-f0-9]{12}\.css)"', html
                    ),
                    "theme.js": re.search(
                        r'src="([^"]*/admin_theme/js/theme\.[a-f0-9]{12}\.js)"', html
                    ),
                }
                for label, match in references.items():
                    with self.subTest(asset=label):
                        self.assertIsNotNone(match, f"login page did not link hashed {label}")
                        url_path = urlsplit(match.group(1)).path
                        relative = url_path.removeprefix(settings.STATIC_URL)
                        asset = Path(temp_root) / relative
                        self.assertTrue(asset.is_file(), f"hashed asset is missing: {asset}")

    def test_all_nginx_static_rules_cache_only_hashed_assets_for_30_days(self):
        # The pattern is QUOTED: it contains `{12}`, and nginx's
        # brace-counting config parser otherwise cuts the location at that
        # brace (pcre2_compile() failed: missing closing parenthesis). See
        # apps/core/test_nginx_configs.py, which enforces the quoting rule.
        hashed_location = r'location ~* "^/static/(.+\.[a-f0-9]{12}\.[^/]+)$" {'
        for path in NGINX_FILES:
            source = path.read_text(encoding="utf-8")
            with self.subTest(config=path.name, parent=path.parent.name):
                # Keep the URL pattern tied to Django's 12-hex-character
                # manifest suffix and require the long-cache header there.
                self.assertIn(hashed_location, source)
                block_start = source.index(hashed_location) + len(hashed_location)
                block_end = source.index("\n    }", block_start)
                hashed = source[block_start:block_end]
                self.assertIn("alias /app/staticfiles/$1;", hashed)
                self.assertIn("expires 30d;", hashed)
                self.assertIn("public, immutable", hashed)
                # The ordinary /static/ prefix must never inherit that TTL.
                unhash = re.search(r"location /static/\s*\{([^}]*)\}", source, re.S)
                self.assertIsNotNone(unhash, "unhashed static location is missing")
                self.assertNotIn("expires 30d", unhash.group(1))
                self.assertIn("expires off", unhash.group(1))
                self.assertIn("no-cache, must-revalidate", unhash.group(1))
