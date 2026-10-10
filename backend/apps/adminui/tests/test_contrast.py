"""A7 contrast guard: parse the brand/semantic color tokens straight out
of static/admin_theme/css/theme.css and assert WCAG 2.1 contrast >= 4.5:1
for every main text/background pair the panel actually renders.

No browser involved -- this is a pure CSS-source computation, the same
relative-luminance formula screen readers' contrast checkers use.
"""
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

CSS_PATH = Path(settings.BASE_DIR) / "static" / "admin_theme" / "css" / "theme.css"


def _channel(c: float) -> float:
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(hex_color: str) -> float:
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 3:
        hex_color = "".join(ch * 2 for ch in hex_color)
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast(fg: str, bg: str) -> float:
    l1, l2 = luminance(fg), luminance(bg)
    if l1 < l2:
        l1, l2 = l2, l1
    return (l1 + 0.05) / (l2 + 0.05)


class CssContrastTests(SimpleTestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.css = CSS_PATH.read_text(encoding="utf-8")
        # theme.css redefines tokens for dark mode; the LIGHT palette is
        # everything before the first dark-scheme media query, the DARK
        # palette everything after it. Parse them separately (first
        # occurrence wins inside each half).
        split = cls.css.index("@media (prefers-color-scheme: dark)")
        cls.light_css, cls.dark_css = cls.css[:split], cls.css[split:]
        cls.tokens = cls._first_tokens(cls.light_css)
        cls.dark_tokens = cls._first_tokens(cls.dark_css)

    @staticmethod
    def _first_tokens(css_text):
        tokens = {}
        for name, value in re.findall(
            r"(--(?:cg|cusin)-[a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{3,8})\s*;", css_text
        ):
            tokens.setdefault(name, value)
        return tokens

    def token(self, name):
        value = self.tokens.get(name)
        self.assertIsNotNone(value, f"token {name} missing from theme.css")
        return value

    def assert_ratio(self, fg_hex, bg_hex, minimum=4.5, label=""):
        ratio = contrast(fg_hex, bg_hex)
        self.assertGreaterEqual(
            ratio, minimum,
            f"{label}: contrast {ratio:.2f}:1 below {minimum}:1 "
            f"({fg_hex} on {bg_hex})",
        )

    def test_brand_tokens_are_the_agreed_palette(self):
        """The palette is a hard project constraint (storefront variables
        match): olive #637037, dark green #2F3A18, gold #CEB464, ivory
        #FAF7F0, ink #1E2412."""
        self.assertEqual(self.token("--cg-olive").lower(), "#637037")
        self.assertEqual(self.token("--cg-green-dark").lower(), "#2f3a18")
        self.assertEqual(self.token("--cg-gold").lower(), "#ceb464")
        self.assertEqual(self.token("--cg-ivory").lower(), "#faf7f0")
        self.assertEqual(self.token("--cg-ink").lower(), "#1e2412")

    def test_main_text_pairs_pass_wcag_aa(self):
        ivory = self.token("--cg-ivory")
        ink = self.token("--cg-ink")
        olive = self.token("--cg-olive")
        dark = self.token("--cg-green-dark")
        gold = self.token("--cg-gold")

        self.assert_ratio(ink, ivory, 4.5, "ink on ivory (body text)")
        self.assert_ratio(olive, ivory, 4.5, "olive on ivory (links/headings)")
        self.assert_ratio("#ffffff", olive, 4.5, "white on olive (buttons)")
        self.assert_ratio("#ffffff", dark, 4.5, "white on dark green (topbar)")
        # gold is only ever used on dark green (brand rule) --
        # it must be legible there and is never small text on light bg
        self.assert_ratio(gold, dark, 4.5, "gold on dark green (decor/accents)")

    def test_semantic_text_tokens_pass_on_light_surfaces(self):
        """Every semantic text token claims >=4.5:1 on ivory AND white
        surfaces in the CSS comment -- enforce it."""
        for name in (
            "--cg-success-text", "--cg-danger-text", "--cg-warning-text",
            "--cg-info-text", "--cg-muted-text",
        ):
            for bg_name, bg in (
                ("ivory", self.token("--cg-ivory")),
                ("white surface", "#ffffff"),
                ("surface-2", self.token("--cusin-surface-2")),
            ):
                with self.subTest(token=name, on=bg_name):
                    self.assert_ratio(self.token(name), bg, 4.5, f"{name} on {bg_name}")

    def test_badge_text_on_badge_backgrounds(self):
        """Stock/refund/payment badges put semantic text on pastel chips;
        the literal backgrounds come from theme.css (asserted present so
        the test fails loudly if they change)."""
        pairs = {
            "stock-ok": ("--cg-success-text", "#e4f1e9"),
            "stock-low": ("--cg-warning-text", "#fbf3de"),
            "stock-out": ("--cg-danger-text", "#f9e7e3"),
        }
        for chip, (token_name, bg) in pairs.items():
            with self.subTest(badge=chip):
                self.assertIn(bg, self.css, f"badge background {bg} changed in theme.css")
                self.assert_ratio(self.token(token_name), bg, 4.5, f"{chip} badge")

    def test_gold_is_not_used_as_small_text_on_light_backgrounds(self):
        """Brand rule: gold only on dark green or as decoration. Guard the
        obvious violation pattern -- gold as a text color on a light
        surface selector."""
        offenders = re.findall(
            r"color:\s*var\(--cg-gold\)\s*;[^}]*background:\s*(?:var\(--cg-ivory\)|#fff|#ffffff|var\(--cusin-surface\))",
            self.css,
        )
        self.assertEqual(offenders, [], "gold text on a light background found")

    def test_dark_mode_main_pairs_pass_wcag_aa(self):
        """The dark palette must be legible too: body text, muted text
        and the semantic colors on the dark surfaces."""
        bg = self.dark_tokens["--cusin-bg"]
        surface = self.dark_tokens["--cusin-surface"]
        for text_token in ("--cusin-text", "--cusin-muted", "--cusin-link",
                           "--cg-success-text", "--cg-danger-text",
                           "--cg-warning-text", "--cg-gold"):
            # tokens the dark block does not override keep their light value
            fg = self.dark_tokens.get(text_token) or self.tokens[text_token]
            for bg_name, bg_hex in (("bg", bg), ("surface", surface)):
                with self.subTest(token=text_token, on=bg_name):
                    self.assert_ratio(
                        fg, bg_hex, 4.5,
                        f"dark {text_token} on {bg_name}",
                    )

    def test_luminance_math_is_correct_on_known_values(self):
        # sanity check of the implementation itself (WCAG reference values)
        self.assertAlmostEqual(luminance("#000000"), 0.0, places=4)
        self.assertAlmostEqual(luminance("#ffffff"), 1.0, places=4)
        self.assertAlmostEqual(contrast("#000000", "#ffffff"), 21.0, places=1)
        self.assertAlmostEqual(contrast("#767676", "#ffffff"), 4.54, places=2)
