"""
Item 10 -- the admin has to fit on the widths Windows actually reports.

At 125% display scaling a 1366px screen reports 1092 CSS px; at 150% it
reports 911. A 1920px screen reports 1536 / 1280. Those are NOT phones --
they keep the two-column desktop layout -- but the type scale and paddings
tuned for 1920 CSS px overflow their cards and clip their labels there.

Two things are pinned here:

* the stylesheet carries a "one step down" block covering those widths,
  and it does not leak into the phone layout or the full-size desktop;
* the changelist row menu (the «…» button) no longer squeezes itself into
  the gap beside its trigger. That squeeze is what clipped
  «ویرایش / چاپ / حذف» down to «وی / چا / حذ» and pushed the menu off the
  left edge. It now flips to the trigger's other side instead.

The real browser check (clipped text, off-screen menus, sidebar overlap)
lives in e2e/admin-desktop-fit.spec.js at 1280/1366/1536/1920 -- it needs
a running stack and a browser, which CI for this repo has.
"""
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

CSS_PATH = Path(settings.BASE_DIR) / "static" / "admin_theme" / "css" / "theme.css"
JS_PATH = Path(settings.BASE_DIR) / "static" / "admin_theme" / "js" / "theme.js"


def strip_comments(css: str) -> str:
    return re.sub(r"/\*[\s\S]*?\*/", "", css)


def media_block(css: str, header: str) -> str:
    """The body of one @media block, by its exact header line."""
    index = css.index(header)
    depth = 0
    out = []
    for chunk in css[index:]:
        if chunk == "{":
            depth += 1
            if depth == 1:
                continue
        elif chunk == "}":
            depth -= 1
            if depth == 0:
                break
        if depth >= 1:
            out.append(chunk)
    return "".join(out)


class ZoomedDesktopCssTests(SimpleTestCase):
    """The one-step-down block exists, is bounded, and steps down."""

    def setUp(self):
        raw = CSS_PATH.read_text(encoding="utf-8")
        self.css = strip_comments(raw)

    def test_a_block_covers_the_zoomed_desktop_range(self):
        """769px..1600px: below is the phone/tablet drawer layout, above is
        a genuine 1920@100% desktop that must keep the full scale."""
        self.assertIn("@media (min-width: 769px) and (max-width: 1600px)", self.css)

    def test_the_zoomed_block_leaves_the_phone_layout_alone(self):
        block = media_block(self.css, "@media (min-width: 769px) and (max-width: 1600px)")
        # The drawer/tablet layout kicks in at 1024px; this block must not
        # restyle it -- its whole job is the DESKTOP layout, one step down.
        self.assertNotIn(".cusin-drawer-scrim", block)
        self.assertNotIn("is-open", block)

    def test_type_scale_and_paddings_step_down(self):
        block = media_block(self.css, "@media (min-width: 769px) and (max-width: 1600px)")
        for selector in (".cusin-card", ".form-row", "#result_list td", ".cusin-topbar"):
            with self.subTest(selector=selector):
                self.assertIn(selector, block)
        # "One step" means smaller, not absent: the values must be there.
        self.assertIn("font-size: 0.9375rem", block)
        self.assertIn("padding", block)

    def test_the_sidebar_narrows_too(self):
        """A 264px sidebar + a 911px viewport leaves almost nothing for the
        content column -- it has to give some back."""
        block = media_block(self.css, "@media (min-width: 769px) and (max-width: 1600px)")
        self.assertIn("--cusin-sidebar-w", block)
        self.assertIn("232px", block)

    def test_a_second_step_exists_for_the_tightest_desktops(self):
        """911..1100 CSS px == 150% on 1366, or 125% on a small laptop."""
        self.assertIn("@media (min-width: 769px) and (max-width: 1100px)", self.css)

    def test_the_full_size_desktop_keeps_its_scale(self):
        """1920 @100% must NOT be shrunk -- the block stops at 1600px."""
        self.assertIn("max-width: 1600px", self.css)
        self.assertNotIn("max-width: 1920px", self.css)

    def test_stylesheet_braces_balance(self):
        self.assertEqual(self.css.count("{"), self.css.count("}"))


class RowMenuPositioningTests(SimpleTestCase):
    """The «…» menu must never be squeezed or pushed off-screen."""

    def setUp(self):
        self.js = JS_PATH.read_text(encoding="utf-8")
        code = re.sub(r"/\*[\s\S]*?\*/", "", self.js)
        self.code = "\n".join(
            re.sub(r"(^|\s)//.*$", "", line) for line in code.splitlines()
        )

    def test_the_panel_is_no_longer_squeezed_to_the_gap_beside_its_trigger(self):
        """That clamp is what clipped «ویرایش» to «وی»."""
        self.assertNotIn("anchoredWidth", self.code)
        self.assertNotIn('panel.style.minWidth = Math.min(220, panelWidth)', self.code)

    def test_natural_width_is_measured_before_constraining(self):
        self.assertIn("panel.scrollWidth", self.code)
        self.assertIn('panel.style.width = "auto"', self.code)

    def test_the_menu_flips_side_when_the_preferred_one_has_no_room(self):
        self.assertIn("startRoom", self.code)
        self.assertIn("endRoom", self.code)
        self.assertIn("useStartSide", self.code)
        # Both directions of the flip (RTL opens leftward by default).
        self.assertIn("triggerRect.right - panelWidth", self.code)
        self.assertIn("left = useStartSide ? triggerRect.left : triggerRect.right - panelWidth", self.code)

    def test_it_is_still_clamped_into_the_viewport_as_a_last_resort(self):
        """Flipping is preferred, but nothing may ever leave the viewport."""
        self.assertIn(
            "left = Math.max(margin, Math.min(left, viewportWidth - panelWidth - margin));",
            self.code,
        )
        self.assertIn(
            "top = Math.max(margin, Math.min(top, viewportHeight - panelHeight - margin));",
            self.code,
        )

    def test_both_axes_are_kept_in_view(self):
        """The complaint was «opens off-screen left», but the last row of a
        long changelist had the same problem downwards."""
        self.assertIn("viewportHeight - triggerRect.bottom - margin", self.code)
        self.assertIn("triggerRect.top - panelHeight - 6 >= margin", self.code)

    def test_js_balances(self):
        self.assertEqual(self.js.count("{"), self.js.count("}"))


class PlaywrightSpecContractTests(SimpleTestCase):
    """The browser check is part of the deliverable: it must exist and
    cover exactly the widths and surfaces the owner reported."""

    def setUp(self):
        path = (
            Path(settings.BASE_DIR).parent / "e2e" / "admin-desktop-fit.spec.js"
        )
        self.spec = path.read_text(encoding="utf-8") if path.is_file() else ""

    def test_the_spec_exists(self):
        self.assertTrue(self.spec, "e2e/admin-desktop-fit.spec.js is missing")

    def test_it_runs_all_four_desktop_widths(self):
        for width in (1280, 1366, 1536, 1920):
            with self.subTest(width=width):
                self.assertIn(f"width: {width}", self.spec)

    def test_it_covers_dashboard_and_both_changelists_and_change_forms(self):
        for surface in ("dashboard", "product-list", "order-list",
                        "product-form", "order-form"):
            with self.subTest(surface=surface):
                self.assertIn(surface, self.spec)

    def test_it_fails_on_clipped_text(self):
        self.assertIn("CLIPPED_TEXT", self.spec)
        self.assertIn("clipped", self.spec)

    def test_it_fails_on_off_screen_menus(self):
        self.assertIn("off-screen left", self.spec)
        self.assertIn("off-screen right", self.spec)

    def test_it_checks_the_sidebar_against_the_topbar(self):
        self.assertIn("headerBottom", self.spec)
        self.assertIn("drawerHeadTop", self.spec)
