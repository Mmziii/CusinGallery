"""
Theme presets, derived tokens and the WCAG contrast guard (Task 2).

The guard is a hard save-blocker, so these tests pin both directions:
valid defaults/presets save, and a bad pair is refused with a Persian
message naming the pair -- while the database keeps the previous value.
"""
from django.test import TestCase
from django.urls import reverse

from apps.accounts.tests.helpers import make_user
from apps.core.models import SiteSettings
from apps.core.theme import (
    THEME_PRESETS,
    contrast_issues,
    contrast_ratio,
    effective_theme,
    normalize_hex,
    theme_defaults,
)
from apps.core.testing import CacheIsolatedAPITestCase, CacheIsolationMixin


class ColorMathTests(TestCase):
    def test_known_contrast_ratios(self):
        self.assertAlmostEqual(contrast_ratio("#000000", "#ffffff"), 21.0, places=1)
        self.assertAlmostEqual(contrast_ratio("#ffffff", "#ffffff"), 1.0, places=2)
        # The original brand pair documented in variables.css: white on
        # the olive primary is ~5.4:1.
        self.assertGreaterEqual(contrast_ratio("#ffffff", "#637037"), 5.3)

    def test_hex_normalisation(self):
        self.assertEqual(normalize_hex("#abc"), "#aabbcc")
        self.assertEqual(normalize_hex("  #637037 "), "#637037")
        self.assertEqual(normalize_hex("red"), "")
        self.assertEqual(normalize_hex("", "#ffffff"), "#ffffff")


class PresetTests(TestCase):
    def test_the_first_preset_is_the_current_look(self):
        theme = effective_theme({})
        self.assertEqual(theme["preset"], "olive_gold")
        self.assertEqual(theme["primary"], "#637037")
        self.assertEqual(theme["accent"], "#CEB464")
        self.assertEqual(theme["background"], "#FAF7F0")
        self.assertEqual(theme["text"], "#1E2412")
        self.assertEqual(theme["header_background"], "#FFFFFF")
        self.assertEqual(theme["button_text"], "#FFFFFF")
        # The deep gold is the text-safe sibling of the decorative gold.
        self.assertEqual(theme["accent_text"], "#8A6D1F")
        self.assertEqual(theme["css_variables"]["--color-primary"], "#637037")
        self.assertEqual(theme["css_variables"]["--brand-gold"], "#CEB464")

    def test_all_four_requested_presets_exist(self):
        labels = {preset["label"] for preset in THEME_PRESETS.values()}
        self.assertEqual(
            labels,
            {"زیتونی و طلایی", "کرم و قهوه‌ای", "سرمه‌ای و طلایی", "سبز و کرم"},
        )

    def test_every_preset_passes_the_contrast_guard(self):
        for key in THEME_PRESETS:
            with self.subTest(preset=key):
                self.assertEqual(contrast_issues({"theme_preset": key}), [])

    def test_overrides_win_over_the_preset_and_blank_inherits(self):
        source = {
            "theme_preset": "olive_gold",
            "theme_primary": "#123456",
            "theme_accent": "",
            "theme_background": "",
        }
        theme = effective_theme(source)
        self.assertEqual(theme["primary"], "#123456")
        self.assertEqual(theme["primary_dark"], "#0e2740")  # derived dark shade
        self.assertEqual(theme["accent"], THEME_PRESETS["olive_gold"]["accent"])
        self.assertEqual(theme["background"], "#FAF7F0")

    def test_light_custom_accent_gets_a_text_safe_sibling(self):
        theme = effective_theme(
            {"theme_accent": "#FFE9A8", "theme_background": "#FFFFFF"}
        )
        self.assertGreaterEqual(
            contrast_ratio(theme["accent_text"], "#FFFFFF"), 4.5
        )

    def test_radius_font_and_shadow_map_to_real_css_values(self):
        theme = effective_theme(
            {
                "theme_button_radius": "none",
                "theme_base_font_size": "large",
                "theme_card_shadow": "none",
            }
        )
        self.assertEqual(theme["css_variables"]["--radius-md"], "0")
        self.assertEqual(theme["css_variables"]["--font-size-base"], "1.125rem")
        self.assertEqual(theme["css_variables"]["--shadow-md"], "none")

    def test_theme_defaults_reset_values(self):
        defaults = theme_defaults()
        self.assertEqual(defaults["theme_preset"], "olive_gold")
        self.assertEqual(defaults["theme_primary"], "")
        self.assertEqual(defaults["theme_button_radius"], "medium")
        self.assertEqual(defaults["theme_card_shadow"], "soft")


class ContrastGuardTests(TestCase):
    def test_bad_text_background_pair_is_reported_with_persian_text(self):
        issues = contrast_issues(
            {"theme_text": "#FAF7F0", "theme_background": "#FAF7F0"}
        )
        keys = {issue["key"] for issue in issues}
        self.assertIn("text_on_background", keys)
        issue = next(item for item in issues if item["key"] == "text_on_background")
        self.assertIn("کنتراست", issue["message"])
        self.assertIn("متن روی پس‌زمینه", issue["message"])
        self.assertIn("۴٫۵", issue["message"])

    def test_bad_button_pair_is_reported(self):
        issues = contrast_issues(
            {"theme_primary": "#FFFFFF", "theme_button_text": "#FFFFFF"}
        )
        self.assertIn(
            "button_text_on_primary", {issue["key"] for issue in issues}
        )

    def test_bad_header_pair_is_reported(self):
        issues = contrast_issues(
            {"theme_header_background": "#FFFFFF", "theme_header_text": "#FAF7F0"}
        )
        self.assertIn(
            "header_text_on_header_background",
            {issue["key"] for issue in issues},
        )


class ThemeApiTests(CacheIsolatedAPITestCase):
    url = reverse("site-content")

    def test_default_theme_is_in_the_public_payload(self):
        theme = self.client.get(self.url).data["theme"]
        self.assertEqual(theme["preset"], "olive_gold")
        self.assertEqual(theme["colors"]["primary"], "#637037")
        self.assertEqual(
            theme["css_variables"]["--color-header-bg"], "#FFFFFF"
        )

    def test_saved_overrides_change_the_payload(self):
        site = SiteSettings.load()
        site.theme_preset = "navy_gold"
        site.theme_primary = "#2B4C7E"
        site.save()
        theme = self.client.get(self.url).data["theme"]
        self.assertEqual(theme["preset"], "navy_gold")
        self.assertEqual(theme["colors"]["primary"], "#2b4c7e")
        self.assertEqual(theme["colors"]["accent"], "#C9A227")


class ThemeAdminTests(CacheIsolationMixin, TestCase):
    url = reverse("admin:core_sitesettings_change", args=[1])

    def setUp(self):
        self.admin = make_user(
            phone="+989300007001", password="theme-admin-pw-12345!",
            is_staff=True, is_superuser=True,
        )
        self.client.force_login(self.admin)

    def _post(self, **overrides):
        data = {
            "site_name": "کازین گالری",
            "tagline": "شعار",
            "shop_name": "",
            "home_heading": "عنوان",
            "hero_title": "بنر",
            "hero_subtitle": "زیرعنوان",
            "hero_button_text": "دکمه",
            "hero_button_link": "/shop/",
            "section_categories_title": "دسته‌بندی‌ها",
            "section_deals_title": "پیشنهاد امروز",
            "section_featured_title": "محصولات منتخب",
            "section_new_title": "جدیدترین محصولات",
            "section_best_title": "پرفروش‌ترین‌ها",
            "section_reviews_title": "از زبان خریداران",
            "story_title": "داستان",
            "story_text": "متن",
            "footer_about": "درباره",
            "email": "support@cusin.ir",
            "footer_quick_links_title": "دسترسی سریع",
            "footer_help_links_title": "راهنما",
            "footer_trust_title": "نمادها",
            "pickup_address": "",
            "pickup_hours": "",
            "floating_enabled": "on",
            "theme_preset": "olive_gold",
            "theme_button_radius": "medium",
            "theme_base_font_size": "normal",
            "theme_card_shadow": "soft",
            "trust_items-TOTAL_FORMS": "0",
            "trust_items-INITIAL_FORMS": "0",
            "trust_items-MIN_NUM_FORMS": "0",
            "trust_items-MAX_NUM_FORMS": "1000",
            "_save": "ذخیره",
        }
        data.update(overrides)
        return self.client.post(self.url, data)

    def test_theme_fields_are_in_the_form(self):
        html = self.client.get(self.url).content.decode()
        self.assertIn("ظاهر سایت (تم)", html)
        for label in (
            "تم آماده", "رنگ اصلی", "رنگ تأکیدی (طلایی)", "رنگ پس‌زمینه",
            "رنگ متن", "پس‌زمینهٔ هدر", "متن هدر", "متن دکمه",
            "گردی گوشهٔ دکمه‌ها", "اندازهٔ متن پایه", "سایهٔ کارت‌ها",
            "زیتونی و طلایی", "کرم و قهوه‌ای", "سرمه‌ای و طلایی", "سبز و کرم",
        ):
            self.assertIn(label, html)

    def test_valid_theme_saves(self):
        response = self._post(
            theme_preset="cream_brown",
            theme_primary="#7A4B2A",
            theme_button_radius="large",
            theme_base_font_size="large",
            theme_card_shadow="none",
        )
        self.assertEqual(response.status_code, 302)
        site = SiteSettings.load()
        self.assertEqual(site.theme_preset, "cream_brown")
        self.assertEqual(site.theme_primary, "#7a4b2a")
        self.assertEqual(site.theme_button_radius, "large")

    def test_low_contrast_is_refused_with_a_persian_error(self):
        before = SiteSettings.load().theme_background
        response = self._post(
            theme_background="#FAF7F0",
            theme_text="#FAF7F0",
        )
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("کنتراست", html)
        self.assertIn("متن روی پس‌زمینه", html)
        self.assertIn("۴٫۵ به ۱", html)
        self.assertEqual(SiteSettings.load().theme_background, before)

    def test_low_contrast_button_is_refused(self):
        response = self._post(theme_primary="#FFFFFF", theme_button_text="#FFFFFF")
        self.assertEqual(response.status_code, 200)
        self.assertIn("متن دکمه روی رنگ اصلی", response.content.decode())

    def test_malformed_color_is_refused(self):
        response = self._post(theme_primary="red")
        self.assertEqual(response.status_code, 200)
        self.assertIn("کد شش‌رقمی", response.content.decode())
        self.assertEqual(SiteSettings.load().theme_primary, "")

    def test_reset_button_restores_the_default_theme(self):
        site = SiteSettings.load()
        site.theme_preset = "navy_gold"
        site.theme_primary = "#123456"
        site.theme_button_radius = "large"
        site.save()

        response = self.client.post(reverse("admin:core_sitesettings_reset_theme"))
        self.assertEqual(response.status_code, 302)
        site = SiteSettings.load()
        self.assertEqual(site.theme_preset, "olive_gold")
        self.assertEqual(site.theme_primary, "")
        self.assertEqual(site.theme_button_radius, "medium")
        self.assertEqual(site.theme_card_shadow, "soft")

    def test_reset_requires_post(self):
        response = self.client.get(reverse("admin:core_sitesettings_reset_theme"))
        self.assertEqual(response.status_code, 405)


class SpaThemeInjectionTests(CacheIsolationMixin, TestCase):
    """The SPA shell must carry the theme before first paint."""

    def test_home_page_inlines_the_theme_variables_and_bootstrap(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('id="cusin-theme-vars"', html)
        self.assertIn("--color-primary:#637037", html)
        self.assertIn("--color-header-bg:#FFFFFF", html)
        self.assertIn("window.__CUSIN_THEME__=", html)
        # The inline block sits before </head>, i.e. before any stylesheet
        # or script the first paint depends on.
        self.assertLess(
            html.index('id="cusin-theme-vars"'), html.index("</head>")
        )

    def test_a_saved_theme_is_visible_on_the_next_page_request(self):
        site = SiteSettings.load()
        site.theme_primary = "#123456"
        site.save()
        html = self.client.get("/").content.decode()
        self.assertIn("--color-primary:#123456", html)

    def test_unknown_page_still_gets_the_theme_and_a_404(self):
        response = self.client.get("/no-such-page/")
        self.assertEqual(response.status_code, 404)
        self.assertIn('id="cusin-theme-vars"', response.content.decode())
