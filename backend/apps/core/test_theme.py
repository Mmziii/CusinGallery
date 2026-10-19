"""
Theme settings (Task 2): presets, custom overrides, the WCAG contrast guard
and the pre-paint injection into the storefront shell.

The most important assertions are the two safety rules the owner-facing
feature promises:

* the default preset reproduces the CURRENT look exactly (deploying the
  feature must not restyle the shop by itself), and
* a palette whose text is below 4.5:1 is refused with a Persian message
  naming the pair -- the row is not saved.

The storefront wiring (CSS variables / header / buttons) is covered by the
frontend's vitest files; here we test the tokens the backend emits and the
inline block spa.py puts in <head>.
"""
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.accounts.tests.helpers import make_user
from apps.core.models import SiteSettings
from apps.core.testing import CacheIsolationMixin
from apps.core.theme import (
    DEFAULT_PRESET,
    MIN_CONTRAST,
    PAIR_LABELS,
    THEME_PRESETS,
    contrast_issues,
    contrast_ratio,
    effective_theme,
    normalize_hex,
    theme_defaults,
    theme_payload,
    validate_hex_color,
)


class ColorMathTests(TestCase):
    def test_contrast_ratio_known_values(self):
        self.assertAlmostEqual(contrast_ratio("#000000", "#ffffff"), 21.0, places=2)
        self.assertAlmostEqual(contrast_ratio("#ffffff", "#ffffff"), 1.0, places=2)
        # White text on the brand green: the 5.4:1 figure in variables.css.
        self.assertAlmostEqual(contrast_ratio("#ffffff", "#637037"), 5.38, places=2)

    def test_normalize_hex_expands_shorthand_and_lowercases(self):
        self.assertEqual(normalize_hex("#ABC"), "#aabbcc")
        self.assertEqual(normalize_hex("  #7A4B2A "), "#7a4b2a")
        self.assertEqual(normalize_hex("red", fallback=""), "")
        self.assertEqual(normalize_hex("", fallback="#123456"), "#123456")

    def test_validate_hex_color_accepts_blank_and_rejects_junk(self):
        validate_hex_color("")  # no error
        validate_hex_color("#637037")
        validate_hex_color("#abc")
        with self.assertRaises(ValidationError) as raised:
            validate_hex_color("سبز")
        self.assertEqual(
            raised.exception.messages,
            ["رنگ را به شکل کد شش‌رقمی وارد کنید؛ مثال: #637037."],
        )


class PresetTests(TestCase):
    def test_four_presets_in_the_requested_order(self):
        self.assertEqual(
            list(THEME_PRESETS),
            ["olive_gold", "cream_brown", "navy_gold", "green_cream"],
        )
        self.assertEqual(THEME_PRESETS["olive_gold"]["label"], "زیتونی و طلایی")
        self.assertEqual(THEME_PRESETS["cream_brown"]["label"], "کرم و قهوه‌ای")
        self.assertEqual(THEME_PRESETS["navy_gold"]["label"], "سرمه‌ای و طلایی")
        self.assertEqual(THEME_PRESETS["green_cream"]["label"], "سبز و کرم")

    def test_the_default_preset_reproduces_the_current_look(self):
        theme = theme_payload(SiteSettings.load())
        self.assertEqual(theme["preset"], DEFAULT_PRESET)
        self.assertEqual(
            theme["colors"],
            {
                "primary": "#637037",
                "accent": "#CEB464",
                "background": "#FAF7F0",
                "text": "#1E2412",
                "header_background": "#FFFFFF",
                "header_text": "#1E2412",
                "button_text": "#FFFFFF",
            },
        )
        css = theme["css_variables"]
        self.assertEqual(css["--brand-green"], "#637037")
        self.assertEqual(css["--brand-gold-deep"], "#8A6D1F")
        self.assertEqual(css["--color-bg"], "#FAF7F0")
        self.assertEqual(css["--radius-md"], "12px")
        self.assertEqual(css["--font-size-base"], "1rem")
        self.assertEqual(css["--shadow-md"], "0 6px 24px rgba(30, 36, 18, 0.10)")

    def test_every_preset_passes_the_contrast_guard(self):
        for key in THEME_PRESETS:
            with self.subTest(preset=key):
                self.assertEqual(contrast_issues({"theme_preset": key}), [])

    def test_blank_override_inherits_the_preset(self):
        theme = effective_theme(
            {"theme_preset": "cream_brown", "theme_primary": "", "theme_text": ""}
        )
        self.assertEqual(theme["primary"], "#7A4B2A")
        self.assertEqual(theme["text"], "#33251A")

    def test_override_replaces_only_that_color_and_derives_safe_shades(self):
        theme = effective_theme({"theme_preset": "olive_gold", "theme_primary": "#123456"})
        self.assertEqual(theme["primary"], "#123456")
        self.assertEqual(theme["accent"], "#CEB464")  # untouched preset value
        self.assertNotEqual(theme["primary_dark"], "#4A5A27")
        # A darker primary means MORE contrast with white text, never less.
        self.assertGreater(
            contrast_ratio(theme["primary_dark"], "#FFFFFF"),
            contrast_ratio("#123456", "#FFFFFF"),
        )

    def test_css_variables_are_complete_and_only_public_tokens(self):
        css = theme_payload(SiteSettings.load())["css_variables"]
        required = {
            "--brand-green",
            "--brand-green-mid",
            "--brand-green-dark",
            "--brand-green-tint",
            "--brand-gold",
            "--brand-gold-deep",
            "--brand-ivory",
            "--brand-ink",
            "--color-primary",
            "--color-primary-dark",
            "--color-accent",
            "--color-bg",
            "--color-text",
            "--color-header-bg",
            "--color-header-text",
            "--color-header-brand",
            "--color-button-text",
            "--color-border",
            "--radius-sm",
            "--radius-md",
            "--radius-lg",
            "--shadow-sm",
            "--shadow-md",
            "--shadow-lg",
            "--font-size-base",
        }
        self.assertTrue(required.issubset(css))
        for name in css:
            self.assertTrue(name.startswith("--"), name)

    def test_payload_has_no_private_model_fields(self):
        payload = theme_payload(SiteSettings.load())
        self.assertEqual(
            set(payload),
            {
                "preset",
                "preset_label",
                "colors",
                "button_radius",
                "base_font_size",
                "card_shadow",
                "css_variables",
            },
        )
        self.assertNotIn("id", payload)
        self.assertNotIn("updated_at", payload)


class ContrastGuardTests(TestCase):
    def test_text_on_background_is_reported_with_ratio_and_pair(self):
        issues = contrast_issues(
            {"theme_preset": "olive_gold", "theme_background": "#FFFFFF", "theme_text": "#FFFFFF"}
        )
        self.assertEqual(len(issues), 1)
        issue = issues[0]
        self.assertEqual(issue["key"], "text_on_background")
        self.assertEqual(issue["label"], PAIR_LABELS["text_on_background"])
        self.assertLess(issue["ratio"], MIN_CONTRAST)
        self.assertIn("کنتراست «متن روی پس‌زمینه»", issue["message"])
        self.assertIn("۴٫۵ به ۱", issue["message"])
        # Persian digits, not ASCII.
        self.assertNotIn("4.5", issue["message"])

    def test_button_text_on_primary_pair(self):
        issues = contrast_issues(
            {
                "theme_preset": "olive_gold",
                "theme_primary": "#FFFFFF",
                "theme_button_text": "#FFFFFF",
            }
        )
        self.assertEqual([issue["key"] for issue in issues], ["button_text_on_primary"])
        self.assertIn("متن دکمه روی رنگ اصلی", issues[0]["message"])
        self.assertEqual(issues[0]["foreground"], "#ffffff")

    def test_header_text_on_header_background_pair(self):
        issues = contrast_issues(
            {
                "theme_preset": "olive_gold",
                "theme_header_background": "#FFFFFF",
                "theme_header_text": "#F7F7F7",
            }
        )
        self.assertEqual(
            [issue["key"] for issue in issues], ["header_text_on_header_background"]
        )

    def test_three_failing_pairs_are_all_reported(self):
        issues = contrast_issues(
            {
                "theme_preset": "olive_gold",
                "theme_background": "#FFFFFF",
                "theme_text": "#FFFFFF",
                "theme_primary": "#FFFFFF",
                "theme_button_text": "#FFFFFF",
                "theme_header_background": "#FFFFFF",
                "theme_header_text": "#FFFFFF",
            }
        )
        self.assertEqual(len(issues), 3)


class ShapeAndDefaultsTests(TestCase):
    def test_radius_font_and_shadow_choices_map_to_tokens(self):
        none = effective_theme(
            {
                "theme_preset": "olive_gold",
                "theme_button_radius": "none",
                "theme_base_font_size": "small",
                "theme_card_shadow": "none",
            }
        )
        self.assertEqual(none["css_variables"]["--radius-md"], "0")
        self.assertEqual(none["css_variables"]["--font-size-base"], "0.9375rem")
        self.assertEqual(none["css_variables"]["--shadow-md"], "none")

        large = effective_theme(
            {
                "theme_preset": "olive_gold",
                "theme_button_radius": "large",
                "theme_base_font_size": "large",
                "theme_card_shadow": "soft",
            }
        )
        self.assertEqual(large["css_variables"]["--radius-md"], "20px")
        self.assertEqual(large["css_variables"]["--font-size-base"], "1.125rem")
        self.assertNotEqual(large["css_variables"]["--shadow-md"], "none")

    def test_unknown_choice_values_fall_back_to_defaults(self):
        theme = effective_theme(
            {
                "theme_preset": "not-a-preset",
                "theme_button_radius": "huge",
                "theme_base_font_size": "tiny",
                "theme_card_shadow": "hard",
            }
        )
        self.assertEqual(theme["preset"], DEFAULT_PRESET)
        self.assertEqual(theme["button_radius"], "medium")
        self.assertEqual(theme["base_font_size"], "normal")
        self.assertEqual(theme["card_shadow"], "soft")

    def test_theme_defaults_restore_the_original_look(self):
        defaults = theme_defaults()
        self.assertEqual(defaults["theme_preset"], "olive_gold")
        self.assertEqual(defaults["theme_button_radius"], "medium")
        self.assertEqual(defaults["theme_base_font_size"], "normal")
        self.assertEqual(defaults["theme_card_shadow"], "soft")
        for field in (
            "theme_primary",
            "theme_accent",
            "theme_background",
            "theme_text",
            "theme_header_background",
            "theme_header_text",
            "theme_button_text",
        ):
            self.assertEqual(defaults[field], "")

    def test_accent_color_gets_a_text_safe_sibling(self):
        theme = effective_theme({"theme_preset": "olive_gold", "theme_accent": "#F5E7A0"})
        # The raw accent stays decorative...
        self.assertEqual(theme["css_variables"]["--brand-gold"], "#f5e7a0")
        # ... while --color-accent (used for links/labels) is dark enough.
        safe = theme["css_variables"]["--color-accent"]
        self.assertEqual(theme["accent_text"], safe)
        self.assertGreaterEqual(contrast_ratio(safe, theme["background"]), MIN_CONTRAST)


ADMIN_URL = "admin:core_sitesettings_change"


def _admin_theme_post(**theme):
    """A minimal valid change-form POST carrying the theme fields."""
    data = {
        "site_name": "کازین گالری",
        "theme_preset": "olive_gold",
        "theme_primary": "",
        "theme_accent": "",
        "theme_background": "",
        "theme_text": "",
        "theme_header_background": "",
        "theme_header_text": "",
        "theme_button_text": "",
        "theme_button_radius": "medium",
        "theme_base_font_size": "normal",
        "theme_card_shadow": "soft",
        "floating_enabled": "on",
        "trust_items-TOTAL_FORMS": "0",
        "trust_items-INITIAL_FORMS": "0",
        "trust_items-MIN_NUM_FORMS": "0",
        "trust_items-MAX_NUM_FORMS": "1000",
        "_save": "ذخیره",
    }
    data.update(theme)
    return data


class ThemeAdminTests(CacheIsolationMixin, TestCase):
    def setUp(self):
        self.user = make_user(
            phone="+989300000701", password="admin-pw-12345!",
            is_staff=True, is_superuser=True,
        )
        self.client.force_login(self.user)

    def test_admin_page_has_the_theme_fieldset_fields_and_preview(self):
        response = self.client.get(reverse(ADMIN_URL, args=[1]))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("ظاهر سایت (تم)", html)
        for field in (
            "theme_preset",
            "theme_primary",
            "theme_background",
            "theme_header_background",
            "theme_button_radius",
            "theme_base_font_size",
            "theme_card_shadow",
        ):
            self.assertIn(f'name="{field}"', html)
        self.assertIn('id="cusin-theme-presets"', html)
        self.assertIn('id="cusin-theme-preview-frame"', html)
        self.assertIn("بازگشت به تنظیمات پیش‌فرض", html)
        # The preset labels are the owner's Persian wording.
        self.assertIn("زیتونی و طلایی", html)
        self.assertIn("کرم و قهوه‌ای", html)

    def test_valid_custom_palette_is_saved_and_published(self):
        response = self.client.post(
            reverse(ADMIN_URL, args=[1]),
            _admin_theme_post(
                theme_preset="cream_brown",
                theme_primary="#7A4B2A",
                theme_background="#FFFDF8",
                theme_text="#2B2118",
                theme_button_radius="large",
                theme_base_font_size="large",
                theme_card_shadow="none",
            ),
        )
        self.assertEqual(response.status_code, 302)
        site = SiteSettings.load()
        self.assertEqual(site.theme_preset, "cream_brown")
        self.assertEqual(site.theme_primary, "#7a4b2a")
        self.assertEqual(site.theme_button_radius, "large")

        theme = self.client.get(reverse("site-content")).data["theme"]
        self.assertEqual(theme["preset"], "cream_brown")
        self.assertEqual(theme["colors"]["primary"], "#7a4b2a")
        self.assertEqual(theme["css_variables"]["--color-bg"], "#fffdf8")
        self.assertEqual(theme["css_variables"]["--radius-md"], "20px")
        self.assertEqual(theme["css_variables"]["--font-size-base"], "1.125rem")
        self.assertEqual(theme["css_variables"]["--shadow-md"], "none")

    def test_low_contrast_palette_is_refused_and_nothing_is_saved(self):
        response = self.client.post(
            reverse(ADMIN_URL, args=[1]),
            _admin_theme_post(
                theme_background="#FFFFFF",
                theme_text="#FFFFFF",
            ),
        )
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("کنتراست «متن روی پس‌زمینه»", html)
        self.assertIn("۴٫۵ به ۱", html)

        site = SiteSettings.load()
        self.assertEqual(site.theme_background, "")
        self.assertEqual(site.theme_text, "")
        self.assertEqual(site.theme_preset, "olive_gold")

    def test_button_text_contrast_failure_is_named_in_the_error(self):
        response = self.client.post(
            reverse(ADMIN_URL, args=[1]),
            _admin_theme_post(theme_primary="#FFFFFF", theme_button_text="#FFFFFF"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("کنتراست «متن دکمه روی رنگ اصلی»", response.content.decode())

    def test_invalid_hex_is_refused_with_a_persian_message(self):
        response = self.client.post(
            reverse(ADMIN_URL, args=[1]),
            _admin_theme_post(theme_primary="سبز"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "رنگ را به شکل کد شش‌رقمی وارد کنید؛ مثال: #637037.",
            response.content.decode(),
        )
        self.assertEqual(SiteSettings.load().theme_primary, "")

    def test_reset_restores_the_default_theme(self):
        site = SiteSettings.load()
        site.theme_preset = "navy_gold"
        site.theme_primary = "#123456"
        site.theme_button_radius = "none"
        site.theme_card_shadow = "none"
        site.save()

        response = self.client.post(reverse("admin:core_sitesettings_reset_theme"))
        self.assertEqual(response.status_code, 302)

        site.refresh_from_db()
        self.assertEqual(site.theme_preset, "olive_gold")
        self.assertEqual(site.theme_primary, "")
        self.assertEqual(site.theme_button_radius, "medium")
        self.assertEqual(site.theme_card_shadow, "soft")
        # And the public payload is back to the original look.
        theme = self.client.get(reverse("site-content")).data["theme"]
        self.assertEqual(theme["colors"]["primary"], "#637037")

    def test_reset_rejects_get(self):
        self.assertEqual(
            self.client.get(reverse("admin:core_sitesettings_reset_theme")).status_code,
            405,
        )


class SpaThemeInjectionTests(CacheIsolationMixin, TestCase):
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
        self.assertLess(html.index('id="cusin-theme-vars"'), html.index("</head>"))

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
