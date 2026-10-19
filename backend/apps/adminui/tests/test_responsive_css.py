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
from django.contrib import admin
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, SimpleTestCase

from apps.banners.models import Banner
from apps.products.models import Brand, Product

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
        cls.desktop = _rules(_media_block(cls.css, "(min-width: 1025px)"))
        cls.tablet_wide = _rules(
            _media_block(cls.css, "(min-width: 768px) and (max-width: 1024px)")
        )
        cls.narrow_desktop = _rules(_media_block(cls.css, "(max-width: 1439px)"))

    def _effective(self, selector, prop):
        """The value the cascade gives on a phone: the 767px rule wins."""
        if prop in self.phone.get(selector, {}):
            return self.phone[selector][prop]
        return self.base.get(selector, {}).get(prop)

    def test_numeric_changelist_widgets_are_explicitly_ltr_and_mobile_numeric(self):
        request = RequestFactory().get("/admin/")
        request.user = AnonymousUser()
        cases = (
            (Product, ("price", "compare_at_price", "stock_quantity")),
            (Brand, ("display_order",)),
            (Banner, ("ordering",)),
        )
        for model, field_names in cases:
            formset = admin.site._registry[model].get_changelist_formset(request)
            for field_name in field_names:
                with self.subTest(model=model.__name__, field=field_name):
                    widget = formset.form.base_fields[field_name].widget
                    self.assertEqual(widget.attrs.get("dir"), "ltr")
                    self.assertEqual(widget.attrs.get("inputmode"), "numeric")

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
        self.assertIn('"#result_list, .cusin-items-table, .inline-group .tabular table"', self.js)

    def test_the_first_link_cell_is_carded_too(self):
        """Django renders the link column as <th> in every body row. A card
        layout that only styles <td> would leave the main link cell as a
        table cell inside a block row."""
        self.assertEqual(self.phone["#result_list tbody th"]["display"], "flex")
        self.assertEqual(self.phone["#result_list tbody th::before"]["content"], "attr(data-label)")

    def test_the_row_link_is_a_44px_tap_target_in_the_card(self):
        self.assertEqual(self.phone["#result_list tbody th a"]["min-height"], "44px")

    def test_desktop_changelists_use_the_full_results_box_with_a_fixed_grid(self):
        table = self.desktop[
            "body.cusin-admin #container #changelist .results #result_list"
        ]
        self.assertEqual(table["width"], "100%")
        self.assertEqual(table["min-width"], "0")
        self.assertEqual(table["max-width"], "100%")
        self.assertEqual(table["table-layout"], "fixed")
        cells = self.desktop[
            "body.cusin-admin #container #changelist #result_list tbody td"
        ]
        self.assertEqual(cells["min-width"], "0")
        self.assertEqual(cells["white-space"], "normal")
        self.assertEqual(cells["overflow-wrap"], "anywhere")
        self.assertEqual(
            self.base["#changelist .results"]["overflow-x"],
            "auto",
            "at widths <=1024px, horizontal scrolling stays in the results box",
        )

    def test_desktop_order_status_badges_fit_their_columns(self):
        for selector in (
            "body.cusin-admin.app-orders.model-order #result_list td.field-status_badge .cusin-badge",
            "body.cusin-admin.app-orders.model-order #result_list td.field-payment_badge .cusin-badge",
            "body.cusin-admin.app-orders.model-order #result_list td.field-refund_badge .cusin-badge",
        ):
            with self.subTest(selector=selector):
                badge = self.desktop[selector]
                self.assertEqual(badge["box-sizing"], "border-box")
                self.assertEqual(badge["display"], "inline-block")
                self.assertEqual(badge["max-width"], "100%")
                self.assertEqual(badge["font-size"], "14px")
                self.assertEqual(badge["white-space"], "normal")
                self.assertEqual(badge["overflow-wrap"], "normal")
                self.assertEqual(badge["word-break"], "normal")
                self.assertEqual(badge["hyphens"], "none")

    def test_desktop_user_changelist_wraps_only_between_words(self):
        for selector in (
            "body.cusin-admin.app-accounts.model-user #container #changelist #result_list thead th",
            "body.cusin-admin.app-accounts.model-user #container #changelist #result_list tbody td",
            "body.cusin-admin.app-accounts.model-user #container #changelist #result_list tbody th",
        ):
            with self.subTest(selector=selector):
                rules = self.desktop[selector]
                self.assertEqual(rules["overflow-wrap"], "normal")
                self.assertEqual(rules["word-break"], "normal")
                self.assertEqual(rules["hyphens"], "none")

    def test_global_changelist_headers_and_cells_use_word_level_breaks(self):
        for selector in (
            "body.cusin-admin #container #changelist #result_list thead th",
            "body.cusin-admin #container #changelist #result_list tbody td",
            "body.cusin-admin #container #changelist #result_list tbody th",
        ):
            with self.subTest(selector=selector):
                rules = self.base[selector]
                self.assertEqual(rules["word-break"], "normal")
                self.assertEqual(rules["overflow-wrap"], "normal")
                self.assertEqual(rules["hyphens"], "none")

        nowrap = self.base["body.cusin-admin #container #changelist #result_list .cusin-nowrap"]
        self.assertEqual(nowrap["white-space"], "nowrap")
        self.assertEqual(nowrap["overflow-wrap"], "normal")

    def test_changelist_codes_and_phones_are_isolated_ltr_tokens(self):
        for selector in (
            "body.cusin-admin.app-products.model-product #container #changelist #result_list .cusin-product-summary__sku",
            "body.cusin-admin.app-products.model-productvariant #container #changelist #result_list td.field-sku",
            ".cusin-customer__phone",
            "body.cusin-admin.app-accounts.model-user #container #changelist #result_list td.field-username",
            "body.cusin-admin.app-accounts.model-user #container #changelist #result_list td.field-email",
            "body.cusin-admin.app-accounts.model-user #container #changelist #result_list td.field-phone",
            "body.cusin-admin.app-discounts.model-coupon #container #changelist #result_list td.field-code",
        ):
            with self.subTest(selector=selector):
                rules = self.base[selector]
                self.assertEqual(rules["direction"], "ltr")
                self.assertEqual(rules["unicode-bidi"], "isolate")
                self.assertEqual(rules["white-space"], "nowrap")

    def test_order_number_amount_and_date_stay_on_one_titled_line(self):
        for selector in (".cusin-order-number", ".cusin-order-amount", ".cusin-order-date"):
            with self.subTest(selector=selector):
                self.assertEqual(self.base[selector]["white-space"], "nowrap")
                self.assertEqual(self.base[selector]["overflow"], "hidden")
                self.assertEqual(self.base[selector]["text-overflow"], "ellipsis")
        order_number = self.base[".cusin-order-number"]
        self.assertEqual(order_number["direction"], "ltr")
        self.assertEqual(order_number["unicode-bidi"], "isolate")
        self.assertIn("monospace", order_number["font-family"])
        self.assertEqual(self.base[".cusin-order-amount"]["direction"], "ltr")

    def test_secondary_order_columns_are_hidden_below_1440px(self):
        for column in (
            "shipping_method_cell", "stock_restored_badge", "refund_badge",
            "created_at_jalali",
        ):
            for selector in (
                f"body.cusin-admin.app-orders.model-order #container #changelist #result_list .column-{column}",
                f"body.cusin-admin.app-orders.model-order #container #changelist #result_list .field-{column}",
            ):
                with self.subTest(selector=selector):
                    self.assertEqual(self.narrow_desktop[selector]["display"], "none !important")

        widths = {
            "action-checkbox-column": "4%", "column-order_number_cell": "16%",
            "column-customer_cell": "18%", "column-status_badge": "13%",
            "column-payment_badge": "13%", "column-last_attempt_cell": "9%",
            "column-total_fa": "14%", "column-cusin-row-actions": "13%",
        }
        for column, width in widths.items():
            selector = f"body.cusin-admin.app-orders.model-order #result_list th.{column}"
            with self.subTest(selector=selector):
                self.assertEqual(self.narrow_desktop[selector]["width"], width)

    def test_all_six_desktop_changelists_reserve_explicit_column_widths(self):
        lists = {
            "app-products.model-product": {
                "action-checkbox-column": "4%", "column-product_summary": "30%",
                "column-price": "15%", "column-compare_at_price": "15%",
                "column-stock_quantity": "17%", "column-is_active": "4%",
                "column-is_featured": "5%", "column-cusin-row-actions": "10%",
            },
            "app-orders.model-order": {
                "action-checkbox-column": "3.5%", "column-order_number_cell": "12%",
                "column-customer_cell": "15%", "column-status_badge": "9%",
                "column-payment_badge": "9%", "column-last_attempt_cell": "10%",
                "column-total_fa": "10%", "column-shipping_method_cell": "6%",
                "column-stock_restored_badge": "3.5%", "column-refund_badge": "7%",
                "column-created_at_jalali": "8%", "column-cusin-row-actions": "7%",
            },
            "app-categories.model-category": {
                "action-checkbox-column": "5%", "column-tree_name": "38%",
                "column-subtree_product_count": "14%", "column-active_badge": "11%",
                "column-ordering": "14%", "column-add_subcategory": "10%",
                "column-cusin-row-actions": "8%",
            },
            "app-accounts.model-user": {
                "action-checkbox-column": "4%", "column-username": "15%",
                "column-email": "15%", "column-first_name": "7%",
                "column-last_name": "9%", "column-is_staff": "9%",
                "column-phone": "14%", "column-orders_count": "7%",
                "column-date_joined_jalali": "10%", "column-cusin-row-actions": "10%",
            },
            "app-discounts.model-coupon": {
                "action-checkbox-column": "4%", "column-code": "14%",
                "column-discount_summary": "12%", "column-status_badge": "9%",
                "column-usage_summary": "15%", "column-minimum_order_amount": "16%",
                "column-start_date": "10%", "column-expiration_date": "10%",
                "column-cusin-row-actions": "10%",
            },
            "app-reviews.model-review": {
                "action-checkbox-column": "4%", "column-product": "20%",
                "column-user": "17%", "column-rating": "8%", "column-status": "10%",
                "column-is_verified_purchase": "13%", "column-created_at": "16%",
                "column-cusin-row-actions": "12%",
            },
        }
        for body_classes, columns in lists.items():
            for column, expected_width in columns.items():
                selector = f"body.cusin-admin.{body_classes} #result_list th.{column}"
                with self.subTest(selector=selector):
                    self.assertEqual(self.desktop[selector]["width"], expected_width)

    def test_orders_rows_grow_to_fit_and_actions_stay_inside_the_row_at_1024(self):
        """1024px used to mix desktop widths with the coarse-pointer card
        layout: the two-line status badge and the customer's phone line
        spilled below the row, and the 44px action buttons (… / edit)
        painted outside the row card. Rows must grow with their content,
        and the actions must wrap inside their own cell."""
        row = self.base["#result_list tbody tr"]
        self.assertEqual(row["height"], "auto")
        self.assertEqual(row["max-height"], "none")
        cell = self.base["#result_list tbody tr > td"]
        self.assertEqual(cell["height"], "auto")
        self.assertEqual(cell["max-height"], "none")

        actions = self.base[".cusin-row-actions"]
        self.assertEqual(actions["flex-wrap"], "wrap")
        self.assertEqual(actions["min-width"], "0")
        self.assertEqual(actions["max-width"], "100%")

        # The tablet grid is fixed, like the >=1025 one.
        table = self.tablet_wide[
            "body.cusin-admin #container #changelist .results #result_list"
        ]
        self.assertEqual(table["table-layout"], "fixed")
        self.assertEqual(table["width"], "100%")
        self.assertEqual(table["min-width"], "0")
        cards = self.tablet_wide[
            "body.cusin-admin #container #changelist #result_list tbody td"
        ]
        self.assertEqual(cards["height"], "auto")
        self.assertEqual(cards["max-height"], "none")
        self.assertEqual(cards["white-space"], "normal")
        tablet_actions = self.tablet_wide[
            "body.cusin-admin #container #changelist #result_list tbody td.cusin-row-actions"
        ]
        self.assertEqual(tablet_actions["flex-wrap"], "wrap")
        self.assertEqual(tablet_actions["min-width"], "0")

        # A coarse pointer only enlarges the tap targets; the phone card
        # layout is max-width: 767px, never `pointer: coarse`.
        self.assertIn(
            "@media (pointer: coarse), (max-width: 767px) {",
            self.css,
            "touch tap targets must still apply on coarse-pointer desktops",
        )
        self.assertNotIn("@media (pointer: coarse), (max-width: 767px) {\n  .content", self.css)
        self.assertIn("@media (max-width: 767px) {\n  .content { padding: 14px 12px 48px; }", self.css)

    def test_desktop_row_actions_stay_compact_and_product_numeric_inputs_fit_nine_digits(self):
        actions = self.desktop[
            "body.cusin-admin #container #changelist #result_list tbody td.cusin-row-actions"
        ]
        self.assertEqual(actions["min-width"], "0")
        self.assertEqual(actions["flex-wrap"], "wrap")
        for selector in (
            "body.cusin-admin #container #changelist #result_list .cusin-row-actions .cusin-row-edit",
            "body.cusin-admin #container #changelist #result_list .cusin-row-actions .cusin-row-more",
        ):
            with self.subTest(selector=selector):
                button = self.desktop[selector]
                self.assertEqual(button["width"], "40px")
                self.assertEqual(button["min-width"], "40px")
                self.assertEqual(button["min-height"], "40px")

        product = "body.cusin-admin.app-products.model-product #result_list"
        for field in ("price", "compare_at_price", "stock_quantity"):
            with self.subTest(field=field):
                control = self.desktop[f"{product} td.field-{field} input"]
                self.assertEqual(control["min-width"], "108px")
                self.assertEqual(control["max-width"], "120px")
                self.assertEqual(control["box-sizing"], "border-box")
        numeric = self.base[
            'body.cusin-admin #container #changelist #result_list tbody td input[type="number"]'
        ]
        self.assertEqual(numeric["direction"], "ltr")
        self.assertEqual(numeric["text-align"], "left")
        self.assertEqual(numeric["font-variant-numeric"], "tabular-nums")

    def test_stock_badges_and_thumbnails_stay_inside_product_cells(self):
        badge = self.base[
            "body.cusin-admin.app-products.model-product #result_list td.field-stock_quantity .cusin-badge"
        ]
        self.assertEqual(badge["box-sizing"], "border-box")
        self.assertEqual(badge["display"], "inline-block")
        self.assertEqual(badge["max-width"], "100%")
        self.assertEqual(badge["white-space"], "normal")
        self.assertEqual(badge["overflow-wrap"], "normal")
        self.assertEqual(badge["word-break"], "normal")
        self.assertEqual(badge["hyphens"], "none")
        widget = self.base[
            "body.cusin-admin.app-products.model-product #result_list td.field-stock_quantity .cusin-stock-edit"
        ]
        self.assertEqual(widget["display"], "flex")
        self.assertEqual(widget["flex-direction"], "column")
        for field in ("price", "compare_at_price", "stock_quantity"):
            with self.subTest(field=field):
                numeric_input = self.base[
                    f"body.cusin-admin.app-products.model-product #result_list td.field-{field} input"
                ]
                self.assertEqual(numeric_input["box-sizing"], "border-box")
                self.assertEqual(numeric_input["width"], "100%")
                self.assertEqual(numeric_input["min-width"], "0")
                self.assertEqual(numeric_input["max-width"], "100%")
        product_link = self.base[
            "body.cusin-admin.app-products.model-product #result_list tbody .field-product_summary > a"
        ]
        self.assertEqual(product_link["display"], "block")
        self.assertEqual(product_link["min-width"], "0")
        self.assertEqual(product_link["max-width"], "100%")
        thumbnail = self.base[
            "body.cusin-admin.app-products.model-product #result_list .cusin-product-summary__thumbnail img"
        ]
        self.assertEqual(thumbnail["width"], "48px !important")
        self.assertEqual(thumbnail["max-width"], "100%")
        self.assertEqual(thumbnail["height"], "48px !important")

    def test_product_headers_wrap_between_words_and_use_short_labels(self):
        selector = (
            "body.cusin-admin.app-products.model-product #container #changelist "
            "#result_list thead th"
        )
        headers = self.desktop[selector]
        self.assertEqual(headers["overflow-wrap"], "normal")
        self.assertEqual(headers["word-break"], "normal")
        self.assertEqual(headers["hyphens"], "none")
        self.assertEqual(headers["padding-inline"], "2px")
        self.assertEqual(
            self.desktop[
                "body.cusin-admin.app-products.model-product #container #changelist "
                "#result_list thead th .text a"
            ]["padding"],
            "0",
        )
        self.assertEqual(Product._meta.get_field("sku").verbose_name, "SKU")
        self.assertEqual(Product._meta.get_field("compare_at_price").verbose_name, "قیمت قبل از تخفیف")
        self.assertEqual(Product._meta.get_field("is_featured").verbose_name, "ویژه")
        self.assertEqual(admin.site._registry[Product].stock_column.short_description, "وضعیت")

    def test_product_names_are_clamped_to_two_word_safe_lines(self):
        product_name = self.base[
            "body.cusin-admin.app-products.model-product #result_list .cusin-product-summary__name"
        ]
        self.assertEqual(product_name["-webkit-line-clamp"], "2")
        self.assertEqual(product_name["-webkit-box-orient"], "vertical")
        self.assertEqual(product_name["max-height"], "3.4em")
        self.assertEqual(product_name["line-height"], "1.7")
        self.assertEqual(product_name["overflow-wrap"], "normal")
        self.assertEqual(product_name["word-break"], "normal")
        self.assertEqual(product_name["hyphens"], "none")

    def test_product_sku_is_ltr_monospace_and_never_wraps(self):
        sku = self.base[
            "body.cusin-admin.app-products.model-product #result_list .cusin-product-summary__sku"
        ]
        self.assertEqual(sku["direction"], "ltr")
        self.assertEqual(sku["unicode-bidi"], "isolate")
        self.assertEqual(sku["white-space"], "nowrap")
        self.assertIn("monospace", sku["font-family"])

    def test_normal_sidebar_and_menu_labels_use_ink_and_keep_active_and_danger_distinct(self):
        ink = "#111827"
        for selector in (
            "body.cusin-admin #container #cusin-drawer .cusin-drawer-dash:not(.is-active)",
            "body.cusin-admin #container #cusin-drawer .cusin-nav-group > summary",
            "body.cusin-admin #container #cusin-drawer .cusin-nav-link:not(.is-active)",
            "body.cusin-admin #container #cusin-drawer .cusin-drawer-foot a",
            "body.cusin-admin .cusin-menu-panel .cusin-menu-item:not(.is-danger):not(:hover):not(:focus-visible):not([aria-current=\"page\"])",
            "body.cusin-admin #cusin-user-menu [role=\"menuitem\"]:not(.is-danger):not(:hover):not(:focus-visible)",
        ):
            with self.subTest(selector=selector):
                self.assertEqual(self.base[selector]["color"], ink)
        self.assertEqual(
            self.base["body.cusin-admin #container #cusin-drawer .cusin-nav-link.is-active"]["color"],
            "var(--cg-olive-hover)",
        )
        self.assertEqual(self.base[".cusin-menu-item.is-danger"]["color"], "var(--cg-danger-text)")

    def test_product_and_image_import_pages_enforce_readable_type_and_mobile_bounds(self):
        page_selector = "body.cusin-admin.cusin-import-page #content"
        typography = self.base[f"{page_selector} *"]
        self.assertEqual(typography["font-size"], "max(14px, 1em) !important")
        self.assertEqual(self.base[f"{page_selector} > h1"]["font-size"], "1.5rem !important")
        self.assertEqual(self.base[f"{page_selector} h2"]["font-size"], "1.0625rem !important")

        file_input = self.base[f'{page_selector} input[type="file"]']
        self.assertEqual(file_input["width"], "100%")
        self.assertEqual(file_input["min-width"], "0")
        self.assertEqual(file_input["max-width"], "100%")
        self.assertEqual(file_input["box-sizing"], "border-box")
        table = self.base[f"{page_selector} table"]
        self.assertEqual(table["width"], "100%")
        self.assertEqual(table["table-layout"], "fixed")
        self.assertEqual(self.base[f"{page_selector} td"]["overflow-wrap"], "anywhere")

        import_templates = (
            "product_import_form.html",
            "product_import_mapping.html",
            "product_import_sheet.html",
            "product_import_preview.html",
            "product_image_import.html",
            "product_image_import_preview.html",
        )
        template_dir = BASE / "apps" / "products" / "templates" / "admin" / "products"
        for template_name in import_templates:
            with self.subTest(template=template_name):
                source = (template_dir / template_name).read_text(encoding="utf-8")
                self.assertIn(
                    "{% block bodyclass %}{{ block.super }} cusin-import-page{% endblock %}",
                    source,
                )

    def test_filter_panel_groups_are_compact_and_active_chips_can_clear_filters(self):
        summary = self.base["#changelist-filter details > summary"]
        self.assertEqual(summary["min-height"], "34px")
        self.assertEqual(summary["padding"], "4px 6px")
        self.assertEqual(self.base["#changelist-filter li a"]["min-height"], "32px")
        self.assertEqual(self.base["#changelist-filter ul"]["gap"], "4px")
        self.assertEqual(self.base["#changelist-filter-extra-actions"]["display"], "none !important")
        self.assertEqual(self.base[".cusin-filter-panel.is-side-sheet"]["border-radius"], "16px 0 0 16px")
        self.assertEqual(self.base[".cusin-filter-chip--clear"]["background"], "#fff2f0")

        filter_template = BASE / "templates" / "admin" / "filter.html"
        source = filter_template.read_text(encoding="utf-8")
        self.assertIn('<details data-filter-title="{{ title }}">', source)
        self.assertNotIn('<details data-filter-title="{{ title }}" open>', source)
        self.assertIn("{{ choice.display }}", source)
        self.assertIn("filterNav.querySelector(\"#changelist-filter-extra-actions\")", self.js)
        self.assertIn("function stripLeadingArrows", self.js)
        self.assertIn("حذف همهٔ فیلترها", self.js)
        self.assertIn("function clearFilterUrl", self.js)

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
        self.assertEqual(self.base[".inline-group .tabular"]["overflow-x"], "auto")
        self.assertEqual(self.base["body.cusin-admin #container .inline-group .tabular"]["direction"], "ltr")
        self.assertEqual(self.base["body.cusin-admin #container .inline-group .tabular > fieldset.module"]["overflow"], "visible")
        self.assertEqual(self.base[".inline-group .tabular table"]["width"], "max-content")
        self.assertEqual(self.phone[".inline-group .tabular"]["overflow-x"], "auto")

    def test_inline_tabular_rows_reflow_as_labeled_phone_cards(self):
        row = self.phone[".inline-group .tabular tbody tr.form-row"]
        self.assertEqual(row["display"], "grid")
        self.assertEqual(row["grid-template-columns"], "minmax(0, 1fr)")
        self.assertEqual(self.phone[".inline-group .tabular tbody tr.form-row > td::before"]["content"], "attr(data-label)")
        self.assertEqual(self.phone[".inline-group .tabular tbody tr.form-row > td.original"]["display"], "none !important")
        self.assertIn(".inline-group .tabular table", self.js)
        self.assertIn("MutationObserver", self.js)

    def test_help_text_overrides_django_aligned_row_indentation_without_overflow(self):
        for selector in (
            "body.cusin-admin fieldset.module.aligned .form-row .help",
            "body.cusin-admin fieldset.module.aligned .form-row .helptext",
        ):
            with self.subTest(selector=selector):
                help_rule = self.base[selector]
                self.assertEqual(help_rule["display"], "block")
                self.assertEqual(help_rule["width"], "100%")
                self.assertEqual(help_rule["max-width"], "100%")
                self.assertEqual(help_rule["margin"], "0")
                self.assertEqual(help_rule["white-space"], "normal")

    def test_variant_inline_sku_input_is_ltr_with_enough_text_room(self):
        selector = (
            "body.cusin-admin.app-products.model-product #container #variants-group "
            ".tabular tbody td.field-sku input[type=\"text\"]"
        )
        rules = self.desktop[selector]
        self.assertEqual(rules["direction"], "ltr")
        self.assertEqual(rules["text-align"], "left")
        self.assertEqual(rules["padding-inline"], "6px")

    def test_wide_product_variants_fit_their_inline_card_without_original_label_cells(self):
        table = self.desktop[
            "body.cusin-admin #container #variants-group .tabular table"
        ]
        self.assertEqual(table["table-layout"], "fixed")
        self.assertEqual(table["width"], "100%")
        self.assertEqual(table["min-width"], "100%")
        self.assertEqual(table["max-width"], "100%")
        for selector in (
            "body.cusin-admin #container .inline-group .tabular thead th.original",
            "body.cusin-admin #container .inline-group .tabular tbody tr.form-row > td.original",
        ):
            with self.subTest(selector=selector):
                self.assertEqual(self.desktop[selector]["display"], "none !important")
        widths = {
            "sku": "15%",
            "price": "13.5%",
            "stock_quantity": "15%",
            "is_active": "9%",
            "attribute_values": "35.5%",
            "last-child": "12%",
        }
        for field, width in widths.items():
            selector = (
                f"body.cusin-admin #container #variants-group .tabular tbody td.field-{field}"
                if field != "last-child"
                else "body.cusin-admin #container #variants-group .tabular tbody td.delete"
            )
            with self.subTest(field=field):
                self.assertEqual(self.desktop[selector]["width"], width)

    def test_image_gallery_cards_remain_bounded_on_small_screens(self):
        self.assertEqual(self.phone[".cusin-gallery"]["grid-template-columns"], "minmax(0, 1fr)")
        self.assertEqual(self.phone[".cusin-gallery-card"]["box-sizing"], "border-box")
        self.assertEqual(self.phone[".cusin-gallery-card"]["max-width"], "100%")

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
