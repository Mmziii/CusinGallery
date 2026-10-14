"""Layout regressions for the admin dashboard and changelists (follow-up 2).

These are source tests and a rendered-page check. They read theme.css and the
templates and assert the declarations that remove each layout defect. They do
not measure layout: a passing test proves the declaration exists, not that the
page lays out correctly. The real widths, overflow and overlap are measured in
a browser by e2e/admin-layout.spec.js (see docs/LAUNCH_CHECKLIST.md section 10).
"""
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from .helpers import PLAIN_STATIC, make_superuser
from .test_responsive_css import _media_block, _rules, _strip_comments, _without_media

BASE = Path(settings.BASE_DIR)
THEME_CSS = BASE / "static" / "admin_theme" / "css" / "theme.css"


def _base_rules():
    """Base (non-media) rules of theme.css: selector -> {property: value}."""
    css = THEME_CSS.read_text(encoding="utf-8")
    return _rules(_without_media(_strip_comments(css)))


def _declared_widths(css_text, selector):
    """Every `width` value declared for `selector` in source order (media
    blocks included), so a later 600px override cannot hide behind a base rule."""
    flat = _strip_comments(css_text)
    values = []
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", flat):
        selectors = [" ".join(s.split()) for s in match.group(1).split(",")]
        if selector not in selectors:
            continue
        for decl in re.finditer(r"(?<![-\w])width\s*:\s*([^;]+);", match.group(2)):
            values.append(decl.group(1).strip())
    return values


class DashboardWidthTests(TestCase):
    """Item 1: stock Django pins `.dashboard #content` to 600px; the dashboard
    must fill main.content instead."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.css_text = THEME_CSS.read_text(encoding="utf-8")

    def test_theme_does_not_keep_the_600px_pin(self):
        widths = _declared_widths(self.css_text, ".dashboard #content")
        self.assertTrue(widths, "theme.css must size .dashboard #content")
        self.assertNotIn("600px", widths)

    def test_dashboard_column_fills_its_container(self):
        # The last declared width wins; it must be fluid, not a fixed pixel size.
        widths = _declared_widths(self.css_text, ".dashboard #content")
        self.assertEqual(widths[-1], "100%")

    def test_dashboard_column_has_a_cap_for_very_wide_screens(self):
        rules = _base_rules()
        self.assertIn(".dashboard #content", rules)
        max_width = rules[".dashboard #content"].get("max-width", "")
        self.assertRegex(max_width, r"^\d{4}px$")
        self.assertGreaterEqual(int(max_width[:-2]), 1280)

    @override_settings(**PLAIN_STATIC)
    def test_rendered_dashboard_page_has_the_dashboard_body_class(self):
        # The override is scoped to `.dashboard`; if the page stopped carrying
        # that class the rule would silently stop applying.
        self.client.force_login(make_superuser())
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 200)
        self.assertRegex(response.content.decode("utf-8"), r'<body class="[^"]*\bdashboard\b')


class DashboardLatestOrdersLayoutTests(SimpleTestCase):
    """Item 6: keep all five order columns visible at desktop widths and
    render labeled stacked order cards on phones."""

    def test_order_number_cell_is_ltr_nonbreaking_and_monospace(self):
        rule = _base_rules()[".cusin-orders-table .cusin-order-number"]
        self.assertEqual(rule["direction"], "ltr")
        self.assertEqual(rule["unicode-bidi"], "isolate")
        self.assertEqual(rule["white-space"], "nowrap")
        self.assertIn("monospace", rule["font-family"])
        self.assertEqual(rule["font-size"], "14px")

    def test_recent_orders_table_has_sized_columns_and_card_local_scrolling(self):
        rules = _base_rules()
        self.assertEqual(rules[".cusin-table-scroll"]["overflow-x"], "auto")
        self.assertEqual(rules[".cusin-table-scroll"]["max-width"], "100%")
        self.assertEqual(rules[".cusin-orders-table"]["min-width"], "52rem")
        self.assertEqual(rules[".cusin-orders-table"]["table-layout"], "fixed")
        for index, width in enumerate(("14rem", "8rem", "8rem", "10rem", "12rem"), start=1):
            with self.subTest(column=index):
                column = rules[f".cusin-orders-table th:nth-child({index})"]
                self.assertEqual(column["width"], width)
                self.assertEqual(column["min-width"], width)

    def test_desktop_card_spans_grid_so_all_five_columns_fit_at_1280px_plus(self):
        css = _strip_comments(THEME_CSS.read_text(encoding="utf-8"))
        wide = _rules(_media_block(css, "(min-width: 1280px)"))
        card = 'body.cusin-admin #container .cusin-dash-cols > section[aria-label="آخرین سفارش‌ها"]'
        table = "body.cusin-admin #container .cusin-orders-table"
        self.assertEqual(wide[card]["grid-column"], "1 / -1")
        self.assertEqual(wide[table]["width"], "100%")
        self.assertEqual(wide[table]["max-width"], "100%")

    def test_phone_order_rows_are_stacked_and_labeled_without_a_scrollport(self):
        css = _strip_comments(THEME_CSS.read_text(encoding="utf-8"))
        phone = _rules(_media_block(css, "(max-width: 767px)"))
        scroll = "body.cusin-admin #container .cusin-orders-scroll"
        table = "body.cusin-admin #container .cusin-orders-table"
        body = "body.cusin-admin #container .cusin-orders-table tbody"
        row = "body.cusin-admin #container .cusin-orders-table tbody tr"
        label = "body.cusin-admin #container .cusin-orders-table tbody tr > td::before"
        self.assertEqual(phone[scroll]["overflow-x"], "visible")
        self.assertEqual(phone[table]["display"], "block")
        self.assertEqual(phone[table]["min-width"], "0")
        self.assertEqual(phone[body]["display"], "grid")
        self.assertEqual(phone[row]["display"], "grid")
        self.assertEqual(phone[label]["content"], "attr(data-label)")
        self.assertEqual(phone[label]["font-size"], "14px")

    def test_dashboard_template_marks_ltr_order_numbers_and_every_card_label(self):
        template = (BASE / "templates" / "admin" / "index.html").read_text(encoding="utf-8")
        self.assertIn('class="cusin-mini-table cusin-orders-table"', template)
        self.assertIn('class="cusin-order-number" data-label="شماره" dir="ltr" scope="row"', template)
        self.assertIn('class="cusin-table-scroll cusin-orders-scroll"', template)
        for label in ("شماره", "وضعیت", "پرداخت", "مبلغ", "تاریخ"):
            with self.subTest(label=label):
                self.assertIn(f'data-label="{label}"', template)


class ProductStockHeadingTests(SimpleTestCase):
    """Follow-up 4: the stock badge's heading is distinct from raw quantity."""

    def test_product_stock_badge_uses_a_distinct_heading(self):
        from apps.products.admin import ProductAdmin

        self.assertEqual(ProductAdmin.stock_column.short_description, "وضعیت")


PRODUCT_CHANGELIST_TEMPLATE = (
    BASE / "apps" / "products" / "templates" / "admin" / "products" / "product_change_list.html"
)


def _resolve_light_tokens(css_text):
    """Light-palette custom properties, with var() references resolved."""
    light = _without_media(_strip_comments(css_text))
    raw = {}
    for name, value in re.findall(r"(--[a-z0-9-]+)\s*:\s*([^;]+);", light):
        raw.setdefault(name, value.strip())

    def resolve(value, depth=0):
        match = re.fullmatch(r"var\((--[a-z0-9-]+)\)", value)
        if match and depth < 10 and match.group(1) in raw:
            return resolve(raw[match.group(1)], depth + 1)
        return value

    return {name: resolve(value) for name, value in raw.items()}


class ExcelActionsTests(TestCase):
    """Item 2: the four Excel actions are styled once, in theme.css, with theme
    tokens; the product changelist shows them once; each label has 4.5:1."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.css_text = THEME_CSS.read_text(encoding="utf-8")
        cls.tokens = _resolve_light_tokens(cls.css_text)

    def test_template_has_no_inline_style_block(self):
        source = PRODUCT_CHANGELIST_TEMPLATE.read_text(encoding="utf-8")
        self.assertNotIn("<style", source)
        self.assertNotIn("!important", source)

    def test_button_background_and_label_colours_come_from_theme_tokens(self):
        rules = _base_rules()
        button = rules[".cusin-excel-actions a.cusin-excel-actions__button"]
        self.assertEqual(button["background"], "var(--cg-olive)")
        self.assertEqual(button["color"], "var(--cusin-surface)")
        hover = rules[".cusin-excel-actions a.cusin-excel-actions__button:hover"]
        self.assertEqual(hover["background"], "var(--cg-olive-hover)")

    def test_every_excel_label_meets_4_5_to_1_against_its_background(self):
        from .test_contrast import contrast

        tokens = self.tokens
        rules = _base_rules()
        button = rules[".cusin-excel-actions a.cusin-excel-actions__button"]
        hover = rules[".cusin-excel-actions a.cusin-excel-actions__button:hover"]
        panel = rules[".cusin-excel-actions"]
        templates = rules[".cusin-excel-actions__templates"]
        link = rules[".cusin-excel-actions__templates a"]

        def colour(value):
            resolved = tokens.get(value[4:-1]) if value.startswith("var(") else value
            self.assertIsNotNone(resolved, f"unresolved colour {value}")
            return resolved

        pairs = {
            "button label": (colour(button["color"]), colour(button["background"])),
            "button hover label": (colour(hover["color"]), colour(hover["background"])),
            "template help text": (colour(templates["color"]), colour(panel["background"])),
            "template link": (colour(link["color"]), colour(panel["background"])),
        }
        for label, (fg, bg) in pairs.items():
            with self.subTest(label=label):
                self.assertGreaterEqual(contrast(fg, bg), 4.5, f"{label}: {fg} on {bg}")

    @override_settings(**PLAIN_STATIC)
    def test_product_changelist_renders_each_excel_action_once(self):
        self.client.force_login(make_superuser())
        response = self.client.get(reverse("admin:products_product_changelist"))
        html = response.content.decode("utf-8")
        self.assertEqual(html.count('class="cusin-excel-actions__button"'), 4)
        for name in ("products_product_import", "products_product_export", "products_product_image_import"):
            with self.subTest(url_name=name):
                self.assertIn(f'href="{reverse("admin:" + name)}', html)

    @override_settings(**PLAIN_STATIC)
    def test_object_tools_keep_only_the_add_link(self):
        self.client.force_login(make_superuser())
        html = self.client.get(reverse("admin:products_product_changelist")).content.decode("utf-8")
        match = re.search(r'<ul class="object-tools">(.*?)</ul>', html, re.S)
        self.assertIsNotNone(match, "product changelist must render object tools")
        tools = match.group(1)
        self.assertIn('class="addlink"', tools)
        self.assertEqual(tools.count("<li>"), 1)
        for fragment in ("import", "export", "image-import"):
            self.assertNotIn(fragment, tools)


class ObjectToolsTests(SimpleTestCase):
    """Item 3: stock Django floats `.object-tools` with a -48px top margin; the
    float was drawn over the block-level search card (#toolbar)."""

    def test_theme_stops_the_float(self):
        rules = _base_rules()
        self.assertEqual(rules[".object-tools"]["float"], "none")
        self.assertEqual(rules[".object-tools li"]["float"], "none")


PHONE_QUERY = "(max-width: 767px)"


def _phone_rules():
    """Declarations inside the phone (<= 767px) block of theme.css."""
    css = THEME_CSS.read_text(encoding="utf-8")
    return _rules(_strip_comments(_media_block(css, PHONE_QUERY)))


class PageOverflowTests(SimpleTestCase):
    """Item 4: the page never scrolls sideways. A wide desktop table scrolls
    inside its own results box; phones keep the card layout instead."""

    def test_desktop_results_box_scrolls_horizontally(self):
        self.assertEqual(_base_rules()["#changelist .results"]["overflow-x"], "auto")

    def test_phone_results_box_has_no_scroll_because_rows_are_cards(self):
        self.assertEqual(_phone_rules()["#changelist .results"]["overflow-x"], "visible")

    def test_actions_bar_is_sized_inside_its_card(self):
        self.assertEqual(_base_rules()["#changelist .actions"]["box-sizing"], "border-box")

    def test_phone_submit_row_items_drop_the_inline_start_margin(self):
        # image-import's cancel link carries style="margin-inline-start:10px";
        # on phones the full-width stack must not add that margin.
        rule = _phone_rules()[".submit-row > *"]
        self.assertEqual(rule["margin"], "4px 0 !important")
        self.assertEqual(rule["box-sizing"], "border-box")

    def test_phone_user_menu_opens_from_its_start_edge_within_the_screen(self):
        rule = _phone_rules()[".cusin-usermenu-pop"]
        self.assertEqual(rule["inset-inline-start"], "0")
        self.assertEqual(rule["max-width"], "calc(100vw - 24px)")
