"""A7: phone-width audit of the admin theme, as source tests.

These read static/admin_theme/css/theme.css and check the declarations that
make phone widths work: the drawer, changelist cards, no fixed widths that
overflow the viewport, and 44px tap targets. They do not measure layout; a
real browser check at 320px and 375px is listed in docs/LAUNCH_CHECKLIST.md
section 10. The print label and invoice pages must stay outside the theme;
a test below asserts that too."""
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

BASE = Path(settings.BASE_DIR)
THEME_CSS = BASE / "static" / "admin_theme" / "css" / "theme.css"
THEME_JS = BASE / "static" / "admin_theme" / "js" / "theme.js"

TAP_TARGET_MIN_PX = 44


def _strip_comments(css):
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _media_block(css, query):
    """Return the body of the first ``@media <query>`` block (brace-matched)."""
    start = css.index(f"@media {query}")
    open_brace = css.index("{", start)
    depth = 0
    for index in range(open_brace, len(css)):
        if css[index] == "{":
            depth += 1
        elif css[index] == "}":
            depth -= 1
            if depth == 0:
                return css[open_brace + 1:index]
    raise AssertionError(f"unclosed @media {query}")


def _without_media(css):
    """Remove every @media block, leaving only the base rules."""
    while "@media" in css:
        start = css.index("@media")
        open_brace = css.index("{", start)
        depth = 0
        for index in range(open_brace, len(css)):
            if css[index] == "{":
                depth += 1
            elif css[index] == "}":
                depth -= 1
                if depth == 0:
                    css = css[:start] + css[index + 1:]
                    break
        else:
            raise AssertionError("unclosed @media block")
    return css


def _rules(flat_css):
    """selector -> {property: value} for a block of flat rules.

    Grouped selectors are split on commas, so each selector is a key.
    Later declarations for the same selector win, as in the cascade."""
    rules = {}
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", flat_css):
        body = match.group(2)
        decls = {}
        for decl in body.split(";"):
            if ":" in decl:
                prop, value = decl.split(":", 1)
                decls[prop.strip()] = value.strip()
        for selector in match.group(1).split(","):
            key = " ".join(selector.split())
            if key:
                rules.setdefault(key, {}).update(decls)
    return rules


class ResponsiveCssTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.css = _strip_comments(THEME_CSS.read_text(encoding="utf-8"))
        cls.js = THEME_JS.read_text(encoding="utf-8")
        cls.base = _rules(_without_media(cls.css))
        cls.tablet = _rules(_media_block(cls.css, "(max-width: 1024px)"))
        cls.phone = _rules(_media_block(cls.css, "(max-width: 767px)"))

    def _effective(self, selector, prop):
        """The value the cascade gives on a phone: the 767px rule wins."""
        if prop in self.phone.get(selector, {}):
            return self.phone[selector][prop]
        return self.base.get(selector, {}).get(prop)

    # --- drawer -----------------------------------------------------------

    def test_drawer_is_off_canvas_below_1024px(self):
        drawer = self.tablet[".cusin-drawer"]
        self.assertEqual(drawer["position"], "fixed")
        self.assertEqual(drawer["transform"], "translateX(-105%)")
        self.assertEqual(self.tablet['[dir="rtl"] .cusin-drawer']["transform"], "translateX(105%)")
        self.assertEqual(self.tablet[".cusin-drawer.is-open"]["transform"], "none !important")

    def test_drawer_width_never_exceeds_a_small_phone_viewport(self):
        width = self.tablet[".cusin-drawer"]["width"]
        self.assertEqual(width, "min(var(--cusin-sidebar-w), calc(100vw - 48px))")

    def test_script_toggles_the_class_the_css_opens_the_drawer_with(self):
        self.assertIn('classList.toggle("is-open"', self.js)
        self.assertIn(".is-open", self.css)

    # --- changelist cards -------------------------------------------------

    def test_changelist_header_is_hidden_and_rows_become_cards_below_768px(self):
        self.assertEqual(self.phone["#result_list thead"]["display"], "none")
        self.assertIn("border-radius", self.phone["#result_list tr"])
        self.assertEqual(self.phone["#result_list td::before"]["content"], "attr(data-label)")

    def test_the_card_label_is_mirrored_from_the_header_by_the_script(self):
        self.assertIn('setAttribute("data-label"', self.js)
        self.assertIn('querySelectorAll("#result_list, .cusin-items-table")', self.js)

    def test_the_first_link_cell_is_carded_too(self):
        """Django renders the link column as <th> in every body row. A card
        layout that only styles <td> would leave the main link cell as a
        table cell inside a block row."""
        self.assertEqual(self.phone["#result_list tbody th"]["display"], "flex")
        self.assertEqual(self.phone["#result_list tbody th::before"]["content"], "attr(data-label)")

    def test_the_row_link_is_a_44px_tap_target_in_the_card(self):
        self.assertEqual(self.phone["#result_list tbody th a"]["min-height"], "44px")

    # --- no horizontal scroll --------------------------------------------

    def test_fixed_width_stock_inputs_shrink_to_the_phone_width(self):
        for selector in (".vTextField", ".vLargeTextField", "select", "textarea",
                         'input[type="text"]'):
            with self.subTest(selector=selector):
                self.assertEqual(self.phone[selector]["max-width"], "100%")
                self.assertEqual(self.phone[selector]["box-sizing"], "border-box")
        self.assertEqual(self.phone[".vTextField"]["width"], "100%")

    def test_images_never_exceed_the_container(self):
        self.assertEqual(self.phone["img"]["max-width"], "100%")

    def test_wide_order_items_table_scrolls_inside_its_own_box(self):
        self.assertEqual(self.base[".cusin-table-scroll"]["overflow-x"], "auto")
        order_form = (
            BASE / "apps" / "orders" / "templates" / "admin" / "orders"
            / "order_change_form.html"
        ).read_text(encoding="utf-8")
        wrapper = order_form.split('class="cusin-table-scroll"', 1)[1]
        self.assertIn('class="cusin-items-table"', wrapper.split("</table>", 1)[0])

    def test_inline_tabular_tables_scroll_inside_their_box(self):
        self.assertEqual(self.phone[".inline-group .tabular"]["overflow-x"], "auto")

    def test_palette_box_is_bounded_by_the_viewport(self):
        self.assertEqual(self.base[".cusin-palette-box"]["width"], "min(640px, 94vw)")

    # --- 44px tap targets --------------------------------------------------

    def test_phone_tap_targets_are_at_least_44px(self):
        targets = (
            ".paginator a:link", ".paginator a:visited", ".paginator .this-page",
            "#changelist-filter li a", ".button", 'input[type="submit"]',
            ".submit-row a", "a.deletelink", ".inline-deletelink",
            "#changelist .actions select",
            ".cusin-drawer-toggle", ".cusin-drawer-dash", ".cusin-nav-link",
        )
        for selector in targets:
            with self.subTest(selector=selector):
                value = self._effective(selector, "min-height")
                if value is None:
                    value = self._effective(selector, "height")
                self.assertIsNotNone(value, f"{selector} has no min-height on phones")
                match = re.match(r"(\d+)px$", value)
                self.assertIsNotNone(match, f"{selector} min-height {value!r} is not px")
                self.assertGreaterEqual(int(match.group(1)), TAP_TARGET_MIN_PX)

    # --- print and invoice stay untouched ---------------------------------

    def test_print_and_invoice_pages_do_not_load_the_admin_theme(self):
        for template in (
            BASE / "apps" / "orders" / "templates" / "admin" / "orders" / "order_print.html",
            BASE / "apps" / "orders" / "templates" / "orders" / "invoice.html",
        ):
            with self.subTest(template=template.name):
                source = template.read_text(encoding="utf-8")
                self.assertNotIn("admin_theme", source)
                self.assertNotIn("admin/base.html", source)
