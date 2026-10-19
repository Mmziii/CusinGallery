"""WCAG source guards for the light-only admin palette.

Every token used for text is checked against each surface/state in which it
appears. Olive is allowed only for explicit accent roles (links, selection,
focus and primary controls); gold remains decorative and is never text.
"""
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from .test_responsive_css import _rules, _strip_comments, _without_media

CSS_PATH = Path(settings.BASE_DIR) / "static" / "admin_theme" / "css" / "theme.css"
WHITE = "#ffffff"
PAGE = "#f5f6f8"
ACTIVE_TINT = "#f1f2f4"


def _channel(channel):
    channel = int(channel, 16) / 255
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def luminance(color):
    color = color.lstrip("#")
    if len(color) == 3:
        color = "".join(part * 2 for part in color)
    red, green, blue = (color[index:index + 2] for index in (0, 2, 4))
    return 0.2126 * _channel(red) + 0.7152 * _channel(green) + 0.0722 * _channel(blue)


def contrast(foreground, background):
    light, dark = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def _tokens(css):
    """Collect literal custom-property values (the palette keeps these direct)."""
    return {
        name: value.lower()
        for name, value in re.findall(
            r"(--(?:cg|cusin)-[a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{3,8})\s*;", css
        )
    }


class CssContrastTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.css = CSS_PATH.read_text(encoding="utf-8")
        cls.flat_css = _without_media(_strip_comments(cls.css))
        cls.tokens = _tokens(cls.flat_css)

    def token(self, name):
        self.assertIn(name, self.tokens, f"missing color token {name}")
        return self.tokens[name]

    def assert_ratio(self, foreground, background, minimum=4.5, label=""):
        ratio = contrast(foreground, background)
        self.assertGreaterEqual(
            ratio, minimum,
            f"{label}: {ratio:.2f}:1 ({foreground} on {background}) is below {minimum}:1",
        )

    def test_light_palette_tokens_are_the_requested_values(self):
        self.assertEqual(self.token("--cusin-bg"), PAGE)
        self.assertEqual(self.token("--cusin-surface"), WHITE)
        self.assertEqual(self.token("--cusin-text"), "#111827")
        self.assertEqual(self.token("--cusin-muted"), "#4b5563")
        self.assertEqual(self.token("--cg-olive"), "#637037")
        self.assertEqual(self.token("--cg-olive-hover"), "#4f5a2c")
        self.assertEqual(self.token("--cg-gold"), "#ceb464")
        self.assertEqual(self.token("--cusin-accent-bg"), ACTIVE_TINT)
        for old_color in ("#faf7f0", "#f1eee4", "#f0ead4", "#2f3a18", "#242c12"):
            with self.subTest(old_color=old_color):
                self.assertNotIn(old_color, self.css.lower(), "legacy dark/ivory surfaces must be gone")

    def test_body_and_secondary_text_meet_seven_to_one_on_white(self):
        self.assert_ratio(self.token("--cusin-text"), WHITE, 7, "body text on white")
        self.assert_ratio(self.token("--cusin-text"), PAGE, 7, "body text on page background")
        self.assert_ratio(self.token("--cusin-muted"), WHITE, 7, "secondary/help text on white")
        self.assert_ratio(self.token("--cusin-muted"), PAGE, 4.5, "secondary text on page background")

    def test_accent_links_focus_and_selected_states_meet_aa(self):
        for text_token in ("--cusin-link", "--cusin-link-hover", "--cg-olive", "--cg-olive-hover"):
            for surface_name, surface in (("white", WHITE), ("page", PAGE), ("active tint", ACTIVE_TINT)):
                with self.subTest(token=text_token, surface=surface_name):
                    self.assert_ratio(self.token(text_token), surface, 4.5, f"{text_token} on {surface_name}")
        # Sidebar normal and hover use near-black; active text uses the dark
        # olive hover tone on the pale accent tint.
        self.assert_ratio(self.token("--cusin-text"), WHITE, 7, "sidebar normal")
        self.assert_ratio(self.token("--cusin-text"), PAGE, 7, "sidebar hover")
        self.assert_ratio(self.token("--cg-olive-hover"), ACTIVE_TINT, 4.5, "sidebar active")
        self.assert_ratio(self.token("--cg-olive"), WHITE, 4.5, "focus ring on white")

    def test_buttons_in_every_state_have_readable_text(self):
        pairs = {
            "primary normal": (WHITE, self.token("--cg-olive")),
            "primary hover": (WHITE, self.token("--cg-olive-hover")),
            "ghost normal": (self.token("--cusin-text"), WHITE),
            "ghost hover": (self.token("--cusin-text"), PAGE),
            "danger normal": (WHITE, self.token("--cg-danger")),
            "danger hover": (WHITE, "#8f1d14"),
            "print normal": (self.token("--cusin-text"), WHITE),
            "print hover": (self.token("--cusin-text"), PAGE),
        }
        for label, (foreground, background) in pairs.items():
            with self.subTest(state=label):
                self.assert_ratio(foreground, background, 4.5, label)

    def test_table_header_help_and_breadcrumb_text_are_readable(self):
        muted = self.token("--cusin-muted")
        self.assert_ratio(muted, PAGE, 4.5, "table header on light header row")
        self.assert_ratio(muted, WHITE, 7, "help text on white form card")
        self.assert_ratio(muted, WHITE, 7, "breadcrumb secondary text on white")
        self.assertIn("#result_list thead th", self.flat_css)
        self.assertIn(".form-row .help", self.flat_css)

    def test_all_status_pills_keep_semantic_color_and_aa_contrast(self):
        pairs = (
            ("--cg-warning-text", "#fbf3de", "warning"),
            ("--cg-info-text", "#e7eef6", "information"),
            ("#49357a", "#eee9f6", "processing"),
            ("--cg-success-text", "#e4f1e9", "success"),
            ("--cg-danger-text", "#f9e7e3", "danger"),
            ("--cusin-muted", "#f1f2f4", "neutral"),
            ("--cg-olive-hover", ACTIVE_TINT, "shipped/selected"),
        )
        for foreground, background, label in pairs:
            if foreground.startswith("--"):
                foreground = self.token(foreground)
            with self.subTest(status=label):
                self.assert_ratio(foreground, background, 4.5, f"{label} badge")

    def test_text_tokens_never_resolve_to_olive_or_gold(self):
        """Only explicit accent roles (links/focus/selected states) use olive.
        Body, secondary and semantic status text can never collapse to either
        brand color, and gold is forbidden in every CSS text declaration."""
        forbidden = {self.token("--cg-olive"), self.token("--cg-gold")}
        body_and_status_tokens = (
            "--cusin-text", "--cusin-muted", "--cg-ink", "--cg-muted-text",
            "--cg-success-text", "--cg-danger-text", "--cg-warning-text", "--cg-info-text",
        )
        for name in body_and_status_tokens:
            with self.subTest(token=name):
                self.assertNotIn(self.token(name), forbidden)
        self.assertNotRegex(self.css, r"(?i)color\s*:\s*var\(\s*--cg-gold\s*\)")
        self.assertNotRegex(self.css, r"(?i)text-(?:fill|stroke)\s*:\s*var\(\s*--cg-gold\s*\)")

    def test_admin_has_no_dark_mode_or_theme_toggle_source(self):
        self.assertNotRegex(self.css, r"(?is)@media\s*\(\s*prefers-color-scheme\s*:\s*dark\s*\)")
        self.assertNotRegex(self.css, r"(?is):root\s*\[\s*data-theme\s*=\s*['\"]dark['\"]\s*\]")
        self.assertNotIn("admin/css/dark_mode.css", self.css)
        self.assertNotIn("theme-toggle", self.css)
        base_template = (Path(settings.BASE_DIR) / "templates" / "admin" / "base.html").read_text(encoding="utf-8")
        theme_script = (Path(settings.BASE_DIR) / "static" / "admin_theme" / "js" / "theme.js").read_text(encoding="utf-8")
        self.assertIn('meta name="color-scheme" content="light"', base_template)
        self.assertNotIn("color_theme_toggle", base_template)
        self.assertNotIn("theme-toggle", base_template)
        self.assertNotRegex(theme_script, r"(?i)dark.?mode|color_theme_toggle")


    def test_delete_confirmation_buttons_are_readable(self):
        """The confirm button was white on #f9e7e3 and cancel white on #f5f6f8.

        Stock base.css styles `.delete-confirmation form input[type="submit"]`
        with `--delete-button-bg` (the pale pink reserved for the row delete
        link) and `.cancel-link` with `--close-button-bg`, both keeping the
        white `--button-fg`. The theme must override both for every model's
        delete page -- Django's stock templates and the product ones share
        `body.delete-confirmation`.
        """
        rules = _rules(self.flat_css)
        confirm = rules[".delete-confirmation form input[type=\"submit\"]"]
        self.assertEqual(confirm["background"], "var(--cg-danger)")
        self.assertEqual(confirm["color"], WHITE)
        self.assertGreaterEqual(
            contrast(WHITE, self.token("--cg-danger")), 4.5,
            "confirm button text on solid red must meet AA",
        )
        hover = rules[".delete-confirmation form input[type=\"submit\"]:hover"]
        self.assertEqual(hover["background"], "var(--cg-danger-hover)")
        self.assertEqual(hover["color"], WHITE)
        self.assertGreaterEqual(
            contrast(WHITE, self.token("--cg-danger-hover")), 4.5, "confirm hover"
        )

        cancel = rules[".delete-confirmation form .cancel-link"]
        self.assertEqual(cancel["background"], "var(--cusin-surface)")
        self.assertEqual(cancel["color"], "var(--cusin-text)")
        self.assertEqual(cancel["border"], "1px solid var(--cusin-border-strong)")
        self.assertGreaterEqual(
            contrast(self.token("--cusin-text"), WHITE), 4.5, "cancel button text"
        )
        hover_cancel = rules[".delete-confirmation form .cancel-link:hover"]
        self.assertEqual(hover_cancel["color"], "var(--cusin-text)")
        self.assertGreaterEqual(
            contrast(self.token("--cusin-text"), PAGE), 4.5, "cancel hover text"
        )

        # Every delete flow (single object, bulk, any model) shares the
        # `delete-confirmation` body class -- including the two product
        # templates this repo ships.
        for template in (
            Path(settings.BASE_DIR) / "apps" / "products" / "templates" / "admin"
            / "products" / "product" / "delete_confirmation.html",
            Path(settings.BASE_DIR) / "apps" / "products" / "templates" / "admin"
            / "products" / "product" / "delete_selected_confirmation.html",
        ):
            source = template.read_text(encoding="utf-8")
            with self.subTest(template=template.name):
                self.assertIn("delete-confirmation", source)
                self.assertIn('class="button cancel-link"', source)

    def test_luminance_math_on_reference_values(self):
        self.assertAlmostEqual(luminance("#000000"), 0.0, places=4)
        self.assertAlmostEqual(luminance("#ffffff"), 1.0, places=4)
        self.assertAlmostEqual(contrast("#000000", "#ffffff"), 21.0, places=1)
        self.assertAlmostEqual(contrast("#767676", "#ffffff"), 4.54, places=2)
