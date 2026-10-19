"""Follow-up 3 regressions for the admin theme (items 1, 2, 3, 5 and 6).

These are source tests: they read theme.css and assert the declarations that
fix each defect, with the cascade worked out by hand (later rule wins, and the
specificity of each selector is compared with the stock Django rule it must
beat). A passing test proves the declaration exists and would win the cascade;
it does not measure pixels. The measured checks (header position, contrast in
normal/hover/focus, overflow, the 9-digit KPI) are in
e2e/admin-layout.spec.js and were run in a real browser.
"""
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from .test_contrast import contrast
from .test_layout_regressions import _resolve_light_tokens
from .test_responsive_css import _rules, _strip_comments, _without_media

THEME_CSS = Path(settings.BASE_DIR) / "static" / "admin_theme" / "css" / "theme.css"

# Stock Django admin specificities that the theme has to beat (see the CSS
# notes in theme.css and the rule names in the stock files).
STOCK_A_LINK = (0, 1, 1)          # base.css 107: `a:link, a:visited`
STOCK_DELETE_LINK = (0, 2, 2)     # base.css 754-766: `a.deletelink:link/:visited/:hover/:focus`


def _specificity(selector):
    """(ids, classes+attributes+pseudo-classes, type selectors) for one selector."""
    text = re.sub(r"\"[^\"]*\"|'[^']*'", '""', selector)
    ids = len(re.findall(r"#[\w-]+", text))
    classes = len(re.findall(r"\.[\w-]+", text)) + len(re.findall(r"\[[^\]]*\]", text))
    classes += len(re.findall(r":(?!:)[\w-]+", text))
    types = len(re.findall(r"(?:^|[\s>+~])[a-zA-Z][\w-]*", text))
    return (ids, classes, types)


def _all_rules():
    """Every rule, media blocks included (later declarations win, as in the cascade)."""
    css = THEME_CSS.read_text(encoding="utf-8")
    return _rules(_strip_comments(css))


def _base_rules():
    """The desktop rules only (media blocks removed), so a phone or print override
    cannot hide the desktop declaration these tests are about."""
    css = THEME_CSS.read_text(encoding="utf-8")
    return _rules(_without_media(_strip_comments(css)))


def _tokens():
    return _resolve_light_tokens(THEME_CSS.read_text(encoding="utf-8"))


def _colour(tokens, value):
    """Resolve a `var(--token)` or a hex colour from the light palette."""
    if value.startswith("var("):
        resolved = tokens.get(value[4:-1])
        assert resolved is not None, f"unresolved colour {value}"
        return resolved
    return value


class ResultHeaderRowTests(SimpleTestCase):
    """Item 1 (merge blocker): the changelist header is a normal first row of the
    `.results` scroll box. A sticky header with a 100px offset sat on top of the
    first two body rows once the box became a scroll container."""

    def test_result_header_cells_are_not_sticky(self):
        rule = _base_rules()["#result_list thead th"]
        self.assertEqual(rule.get("position"), "static")
        self.assertNotIn("top", rule)
        self.assertNotIn("z-index", rule)

    def test_no_result_header_rule_is_sticky_at_any_width(self):
        for selector, rule in _all_rules().items():
            if "result_list thead" in selector:
                with self.subTest(selector=selector):
                    self.assertNotEqual(rule.get("position"), "sticky")

    def test_results_box_is_still_the_horizontal_scroll_container(self):
        # Owner decision: keep the in-box horizontal scroll, drop the sticky header.
        self.assertEqual(_base_rules()["#changelist .results"]["overflow-x"], "auto")


class DeleteLinkContrastTests(SimpleTestCase):
    """Item 2 (owner review): every «حذف» control must use the SAME solid
    danger style as the delete confirmation page.

    The old tint (#f9e7e3) was a pale pink with the danger text on top; the
    confirmation page was already solid #b42318 with white text. Now the
    `.deletelink` rules (and the `--delete-button-bg` token that stock
    base.css/forms.css use) resolve to that solid colour everywhere.
    """

    STATES = ("", ":link", ":visited", ":hover", ":focus", ":active")

    def test_every_state_has_white_text(self):
        rules = _base_rules()
        for state in self.STATES:
            selector = f".submit-row a.deletelink{state}"
            with self.subTest(selector=selector):
                self.assertEqual(rules[selector]["color"], "#ffffff")

    def test_every_state_beats_the_stock_link_rules(self):
        # The plain selector only has to match forms.css `.submit-row a.deletelink`
        # (0,2,1): theme.css loads after the stock sheets, so a tie goes to the theme.
        # The link states must beat base.css `a.deletelink:link/:visited/:hover/:focus` (0,2,2).
        self.assertGreaterEqual(_specificity(".submit-row a.deletelink"), (0, 2, 1))
        for state in self.STATES[1:]:
            selector = f".submit-row a.deletelink{state}"
            with self.subTest(selector=selector):
                self.assertGreaterEqual(_specificity(selector), STOCK_DELETE_LINK)

    def test_normal_and_hover_are_the_solid_danger_colours(self):
        tokens = _tokens()
        rules = _base_rules()
        self.assertEqual(
            _colour(tokens, rules[".submit-row a.deletelink"]["background"]),
            tokens["--cg-danger"],
        )
        self.assertEqual(
            _colour(tokens, rules[".submit-row a.deletelink:hover"]["background"]),
            tokens["--cg-danger-hover"],
        )

    def test_every_state_meets_4_5_to_1(self):
        tokens = _tokens()
        rules = _base_rules()
        normal_bg = _colour(tokens, rules[".submit-row a.deletelink"]["background"])
        hover_bg = _colour(tokens, rules[".submit-row a.deletelink:hover"]["background"])
        fg = _colour(tokens, rules[".submit-row a.deletelink:hover"]["color"])
        for label, bg in (("normal", normal_bg), ("hover", hover_bg)):
            with self.subTest(state=label):
                self.assertGreaterEqual(contrast(fg, bg), 4.5, f"{fg} on {bg}")


class PrintButtonContrastTests(SimpleTestCase):
    """The print action is now a neutral white control with near-black text.
    Stock base.css `a:link, a:visited` (0,1,1) beats one-class button rules
    on anchors, so every state must repeat the text color at higher specificity."""

    ANCHOR_STATES = (":link", ":visited", ":hover", ":focus")

    def test_every_anchor_variant_beats_the_stock_link_rule_in_every_state(self):
        for variant in ("dark", "danger", "ghost"):
            for state in self.ANCHOR_STATES:
                selector = f"a.cusin-btn--{variant}{state}"
                with self.subTest(selector=selector):
                    self.assertIn(selector, _base_rules())
                    self.assertGreater(_specificity(selector), STOCK_A_LINK)

    def test_print_button_text_is_near_black_in_every_state(self):
        rules = _base_rules()
        for state in self.ANCHOR_STATES:
            selector = f"a.cusin-btn--dark{state}"
            with self.subTest(selector=selector):
                self.assertEqual(rules[selector]["color"], "var(--cusin-text)")

    def test_print_button_text_meets_aa_in_every_state(self):
        tokens = _tokens()
        rules = _base_rules()
        text = _colour(tokens, rules["a.cusin-btn--dark:link"]["color"])
        normal_bg = _colour(tokens, rules[".cusin-btn--dark"]["background"])
        hover_bg = _colour(tokens, rules[".cusin-btn--dark:hover"]["background"])
        for label, bg in (("normal", normal_bg), ("hover", hover_bg), ("focus", normal_bg)):
            with self.subTest(state=label):
                self.assertGreaterEqual(contrast(text, bg), 4.5, f"{text} on {bg}")

    def test_danger_and_ghost_anchors_keep_their_text_colour(self):
        tokens = _tokens()
        rules = _base_rules()
        white = "#ffffff"
        danger_bg = _colour(tokens, rules[".cusin-btn--danger"]["background"])
        self.assertEqual(_colour(tokens, rules["a.cusin-btn--danger:link"]["color"]), white)
        self.assertGreaterEqual(contrast(white, danger_bg), 4.5)
        ghost_text = _colour(tokens, rules["a.cusin-btn--ghost:link"]["color"])
        ghost_bg = _colour(tokens, rules[".cusin-btn--ghost"]["background"])
        self.assertGreaterEqual(contrast(ghost_text, ghost_bg), 4.5)


class OrderFormOverflowTests(SimpleTestCase):
    """Item 5: at 320 and 375 the order form was 12px wider than the viewport.
    The cause is the order-number title in the status card: a flex row with no
    wrap and an unbreakable order number (258px card, 302px of content). The
    items and inline tables already scroll inside their own wrappers."""

    def test_summary_title_wraps_and_breaks_long_words(self):
        rule = _base_rules()[".cusin-summary-title"]
        self.assertEqual(rule.get("flex-wrap"), "wrap")
        self.assertEqual(rule.get("overflow-wrap"), "anywhere")

    def test_wide_items_tables_scroll_inside_their_wrapper(self):
        self.assertEqual(_base_rules()[".cusin-table-scroll"]["overflow-x"], "auto")


class KpiNineDigitTests(SimpleTestCase):
    """Item 6: at 1280 a KPI tile was 129px wide (2 columns), so a 9-digit amount
    such as «۱۲۳٬۴۵۶٬۷۸۹ تومان» wrapped onto two lines. The tiles now use
    `repeat(auto-fit, minmax(180px, 1fr))`, so a narrow card stacks one column
    and nothing is wrapped, clipped or ellipsised."""

    def test_kpi_grid_stacks_tiles_narrower_than_180px(self):
        rule = _base_rules()[".cusin-kpi-grid"]
        self.assertEqual(
            rule["grid-template-columns"],
            "repeat(auto-fit, minmax(min(180px, 100%), 1fr))",
        )

    def test_kpi_text_is_never_clipped_or_ellipsised(self):
        for selector, rule in _all_rules().items():
            if "cusin-kpi" not in selector:
                continue
            with self.subTest(selector=selector):
                self.assertNotEqual(rule.get("text-overflow"), "ellipsis")
                self.assertNotEqual(rule.get("overflow"), "hidden")
                self.assertNotEqual(rule.get("overflow-x"), "hidden")
