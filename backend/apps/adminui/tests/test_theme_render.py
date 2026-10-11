"""Part A: the branded shell renders on real admin pages, the sprite is
complete, every referenced asset exists on disk, and ADMIN_THEME_ENABLED
falls back to the unmodified stock admin instantly.
"""
import copy
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.core.admin_2fa import configure_admin_2fa

from .helpers import PLAIN_STATIC, make_order, make_product, make_superuser

BACKEND_DIR = Path(settings.BASE_DIR)
STATIC_DIR = BACKEND_DIR / "static" / "admin_theme"

# Pages every admin user of this project will hit, incl. the custom
# import/export machinery that must keep working inside the shell (A5).
CHANGELIST_URL_NAMES = [
    "admin:orders_order_changelist",
    "admin:products_product_changelist",
    "admin:accounts_user_changelist",
    "admin:payments_payment_changelist",
    "admin:discounts_coupon_changelist",
    "admin:banners_banner_changelist",
    "admin:notifications_notificationlog_changelist",
    "admin:reviews_review_changelist",
    "admin:categories_category_changelist",
]

CUSTOM_PAGE_URL_NAMES = [
    "admin:products_product_import",          # Excel/CSV import step 1
    "admin:products_product_image_import",    # bulk image import
]


@override_settings(**PLAIN_STATIC)
class ThemeRenderTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = make_superuser(username="themeowner", phone="+989000001111")
        make_order(product=make_product())

    def setUp(self):
        self.client.force_login(self.admin)

    def _assert_shell(self, response, require_drawer=True):
        html = response.content.decode()
        self.assertEqual(response.status_code, 200)
        self.assertIn("dir=\"rtl\"", html)
        self.assertIn("admin_theme/css/theme.css", html)
        self.assertIn("admin_theme/js/theme.js", html)
        self.assertIn("cusin-topbar", html)
        # the inline sprite is baked into the shell
        self.assertIn("id=\"cusin-i-", html)
        if require_drawer:
            self.assertIn("cusin-drawer", html)

    def test_index_renders_themed_shell(self):
        self._assert_shell(self.client.get(reverse("admin:index")))

    def test_every_changelist_renders_themed_shell(self):
        for name in CHANGELIST_URL_NAMES:
            with self.subTest(page=name):
                self._assert_shell(self.client.get(reverse(name)))

    def test_custom_import_export_pages_render_themed_shell(self):
        # Pre-existing behaviour: these views render without
        # each_context(), so is_nav_sidebar_enabled is absent and the
        # drawer is hidden exactly like in the stock admin. The branded
        # shell (topbar, breadcrumbs, palette, sprite, theme.css) still
        # wraps them -- that is what A5 requires.
        for name in CUSTOM_PAGE_URL_NAMES:
            with self.subTest(page=name):
                self._assert_shell(self.client.get(reverse(name)), require_drawer=False)

    def test_singleton_settings_redirect_lands_on_themed_change_form(self):
        # pre-existing behaviour: changelist redirects to the one row
        response = self.client.get(reverse("admin:core_sitesettings_changelist"))
        self.assertEqual(response.status_code, 302)
        response = self.client.get(response["Location"])
        self._assert_shell(response)

    def test_price_percent_is_post_only_and_redirects_get(self):
        # pre-existing behaviour of the B4c endpoint: GET bounces to changelist
        response = self.client.get(reverse("admin:products_product_price_percent"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("admin:products_product_changelist"))

    def test_orders_changelist_tabs_and_badges_inside_shell(self):
        response = self.client.get(reverse("admin:orders_order_changelist"))
        html = response.content.decode()
        self.assertIn("cusin-tab", html)          # B3a status tabs
        self.assertIn("cusin-badge", html)        # status badges

    def test_login_page_has_logo_and_theme(self):
        self.client.logout()
        response = self.client.get(reverse("admin:login"))
        html = response.content.decode()
        self.assertEqual(response.status_code, 200)
        self.assertIn("admin_theme/css/theme.css", html)
        self.assertIn("admin_theme/img/", html)   # brand mark/logo
        # login must NOT carry the staff drawer or palette triggers
        self.assertNotIn("cusin-drawer-toggle", html)
        self.assertNotIn("cusin-search-trigger", html)

    def test_2fa_login_step_renders_inside_shell(self):
        """The django-otp second step inherits admin/login.html -- prove
        the themed shell wraps it (A5 'login incl. 2FA step')."""
        ctx = override_settings(ADMIN_2FA_REQUIRED=True)
        ctx.enable()
        configure_admin_2fa()

        def restore():
            ctx.disable()
            configure_admin_2fa()

        self.addCleanup(restore)

        from django_otp.plugins.otp_totp.models import TOTPDevice

        TOTPDevice.objects.create(user=self.admin, name="default", confirmed=True)
        self.client.logout()
        response = self.client.post(
            reverse("admin:login"),
            {"username": "themeowner", "password": "a-strong-passw0rd!"},
        )
        # bounced back to the login page, now showing the OTP step
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("otp_token", html)
        self.assertIn("admin_theme/css/theme.css", html)
        # the OTP template empties {% block nav-sidebar %} -> no drawer,
        # and the shell must not render a dangling drawer toggle
        self.assertNotIn("cusin-drawer-toggle", html)


@override_settings(**PLAIN_STATIC)
class ThemeFallbackTests(TestCase):
    """ADMIN_THEME_ENABLED=False must drop the shell with zero code
    changes elsewhere: stock templates win because backend/templates is
    removed from TEMPLATES['DIRS'] (config/settings/base.py)."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = make_superuser(username="fallbackowner", phone="+989000002222")
        make_order(product=make_product())

    def setUp(self):
        self.client.force_login(self.admin)
        templates = copy.deepcopy(settings.TEMPLATES)
        templates[0]["DIRS"] = []  # exactly what base.py does when disabled
        self.fallback = override_settings(TEMPLATES=templates, ADMIN_THEME_ENABLED=False)
        self.fallback.enable()
        self.addCleanup(self.fallback.disable)

    def test_index_renders_stock_admin(self):
        response = self.client.get(reverse("admin:index"))
        html = response.content.decode()
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("admin_theme/css/theme.css", html)
        self.assertNotIn("cusin-topbar", html)
        self.assertNotIn("cusin-drawer", html)
        self.assertIn("app-accounts module", html)   # stock app list
        self.assertIn("مدیریت کازین گالری", html)      # stock branding kept

    def test_changelists_still_render_stock(self):
        for name in CHANGELIST_URL_NAMES:
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)
                html = response.content.decode()
                self.assertNotIn("admin_theme/", html)
        # stock sidebar is back on ordinary changelists
        response = self.client.get(reverse("admin:orders_order_changelist"))
        self.assertIn("nav-sidebar", response.content.decode())

    def test_part_b_features_keep_working_without_theme(self):
        # quick search is a JSON endpoint mounted independently of DIRS
        response = self.client.get(
            reverse("admin_quick_search"), {"q": "سفارش", "limit": "5"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        # orders changelist (app-dir template, stock-compatible)
        response = self.client.get(reverse("admin:orders_order_changelist"))
        self.assertEqual(response.status_code, 200)
        # price-percent endpoint stays POST-only (GET -> changelist)
        response = self.client.get(reverse("admin:products_product_price_percent"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("admin:products_product_changelist"))


class SpriteIntegrityTests(SimpleTestCase):
    """Every icon name referenced anywhere must exist in the single
    inline sprite (A6) -- templates, Python icon maps and theme.js."""

    maxDiff = None

    def setUp(self):
        self.sprite = (
            BACKEND_DIR / "apps" / "adminui" / "templates" / "adminui" / "_sprite.html"
        ).read_text(encoding="utf-8")
        self.symbol_ids = re.findall(r'<symbol[^>]+id="cusin-i-([a-z0-9-]+)"', self.sprite)

    def test_sprite_has_no_duplicate_symbols_and_all_have_viewbox(self):
        self.assertEqual(len(self.symbol_ids), len(set(self.symbol_ids)))
        self.assertGreaterEqual(len(self.symbol_ids), 55)
        symbols = re.findall(r"<symbol[^>]+>", self.sprite)
        self.assertEqual(len(symbols), len(self.symbol_ids))
        for tag in symbols:
            self.assertIn("viewBox=", tag)

    def _referenced_names(self):
        names = set()
        icon_tag = re.compile(r'cusin_icon\s+"([a-z0-9-]+)"')
        use_href = re.compile(r"#cusin-i-([a-z0-9-]+)")
        py_icon_key = re.compile(r'"icon":\s*"([a-z0-9-]+)"')

        template_roots = [
            BACKEND_DIR / "templates",
            BACKEND_DIR / "apps" / "adminui" / "templates",
        ]
        template_roots += list((BACKEND_DIR / "apps").glob("*/templates"))
        for root in template_roots:
            for path in root.rglob("*.html"):
                text = path.read_text(encoding="utf-8")
                names |= set(icon_tag.findall(text))
                names |= set(use_href.findall(text))

        py_files = [
            BACKEND_DIR / "apps" / "adminui" / "dashboard.py",
            BACKEND_DIR / "apps" / "adminui" / "context_processors.py",
            BACKEND_DIR / "apps" / "adminui" / "templatetags" / "adminui_extras.py",
            BACKEND_DIR / "apps" / "orders" / "admin.py",
            BACKEND_DIR / "apps" / "products" / "admin.py",
            BACKEND_DIR / "apps" / "accounts" / "admin.py",
            BACKEND_DIR / "apps" / "payments" / "admin.py",
        ]
        for path in py_files:
            names |= set(py_icon_key.findall(path.read_text(encoding="utf-8")))

        # Python icon maps imported directly (nav sidebar + shipping icons)
        from apps.adminui.nav import FALLBACK_ICON, MODEL_ICONS
        from apps.orders.admin import OrderAdmin

        names |= set(MODEL_ICONS.values())
        names.add(FALLBACK_ICON)
        names |= set(OrderAdmin._SHIP_ICONS.values())

        # theme.js may reference sprite symbols too
        js = (STATIC_DIR / "js" / "theme.js").read_text(encoding="utf-8")
        names |= set(use_href.findall(js))
        return names

    def test_every_referenced_icon_exists_in_sprite(self):
        missing = self._referenced_names() - set(self.symbol_ids)
        self.assertEqual(missing, set(), f"icons referenced but not in sprite: {sorted(missing)}")

    def test_sprite_uses_currentcolor_strokes(self):
        self.assertIn('stroke="currentColor"', self.sprite)


class ThemeAssetTests(SimpleTestCase):
    """Assets referenced by the shell exist on disk and are self-hosted
    (A2 Vazirmatn, A8 whitenoise-served)."""

    def test_referenced_static_files_exist(self):
        refs = set()
        pat = re.compile(r'static\s+"(admin_theme/[^"]+)"')
        roots = [BACKEND_DIR / "templates", BACKEND_DIR / "apps" / "adminui" / "templates"]
        roots += list((BACKEND_DIR / "apps").glob("*/templates"))
        for root in roots:
            for path in root.rglob("*.html"):
                refs |= set(pat.findall(path.read_text(encoding="utf-8")))
        self.assertTrue(refs, "no admin_theme static refs found -- scan broken?")
        for ref in sorted(refs):
            with self.subTest(asset=ref):
                self.assertTrue(
                    (BACKEND_DIR / "static" / ref).is_file(),
                    f"{ref} referenced by templates but missing on disk",
                )

    def test_fonts_are_self_hosted(self):
        css = (STATIC_DIR / "css" / "theme.css").read_text(encoding="utf-8")
        self.assertIn("@font-face", css)
        self.assertIn("Vazirmatn", css)
        font_urls = re.findall(r'url\((["\']?)([^)"\']+\.woff2)\1\)', css)
        self.assertTrue(font_urls)
        for _, url in font_urls:
            with self.subTest(font=url):
                self.assertNotIn("http", url)  # no CDN
                resolved = (STATIC_DIR / "css" / url).resolve()
                self.assertTrue(resolved.is_file(), f"font {url} missing on disk")
                self.assertTrue(str(resolved).startswith(str(STATIC_DIR)))

    def test_no_emoji_or_icon_fonts_in_theme(self):
        css = (STATIC_DIR / "css" / "theme.css").read_text(encoding="utf-8")
        js = (STATIC_DIR / "js" / "theme.js").read_text(encoding="utf-8")
        emoji = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF]")
        self.assertFalse(emoji.search(css))
        self.assertFalse(emoji.search(js))
        for banned in ("font-awesome", "fontawesome", "material-icons", "fonts.googleapis"):
            self.assertNotIn(banned, css.lower())
            self.assertNotIn(banned, js.lower())
