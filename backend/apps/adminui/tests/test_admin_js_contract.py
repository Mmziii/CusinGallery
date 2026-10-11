"""Contract between the admin scripts and the rendered pages.

The jsdom suites (frontend/src/admin-theme/*.test.js) execute the shipped
scripts against fixtures. These tests assert that the REAL Django pages carry
every id, class and data-attribute those scripts query, so the fixtures cannot
drift away from what production renders. They also check that the scripts are
actually included on those pages."""
import re
from pathlib import Path

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.orders.models import Order

from .helpers import PLAIN_STATIC, make_order, make_product, make_superuser

JS_DIR = Path(settings.BASE_DIR) / "static" / "admin_theme" / "js"

PRODUCT_FORM_IDS = (
    "id_name", "id_slug", "id_price", "id_compare_at_price",
    "id_discount_percentage", "id_stock_quantity", "id_low_stock_threshold",
    "id_short_description", "id_description",
)
PRODUCT_FORM_HOOKS = (
    "data-cusin-anchor-nav", "data-cusin-preview", "data-cusin-preview-name",
    "data-cusin-preview-price", "data-cusin-preview-compare",
    "data-cusin-preview-image",
)


@override_settings(**PLAIN_STATIC)
class ProductFormContractTests(TestCase):
    def setUp(self):
        self.admin = make_superuser(username="contractprod", phone="+989000090001")
        self.client.force_login(self.admin)
        self.product = make_product(name="قابلمه", slug="ghabeleh-c", sku="CON-1")

    def _page(self):
        response = self.client.get(
            reverse("admin:products_product_change", args=[self.product.pk])
        )
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_every_field_id_the_script_uses_exists_inside_the_form(self):
        html = self._page()
        form = html.split('<div id="content-main">', 1)[1].split("</form>", 1)[0]
        for field_id in PRODUCT_FORM_IDS:
            with self.subTest(field=field_id):
                self.assertIn(f'id="{field_id}"', form)

    def test_preview_and_anchor_hooks_are_rendered(self):
        html = self._page()
        for hook in PRODUCT_FORM_HOOKS:
            with self.subTest(hook=hook):
                self.assertIn(hook, html)

    def test_the_enhancement_script_is_included(self):
        html = self._page()
        self.assertIn("admin_theme/js/product_form.js", html)

    def test_default_save_button_exists_for_ctrl_s(self):
        html = self._page()
        buttons = re.findall(r"<input [^>]*>", html)
        save = [b for b in buttons if 'name="_save"' in b and 'class="default"' in b]
        self.assertEqual(len(save), 1, "exactly one default save button")

    def test_script_only_binds_to_the_real_field_ids(self):
        """The enhancement script's own selectors must all be ids the form
        renders (guards against a renamed field silently disabling a feature)."""
        source = (JS_DIR / "product_form.js").read_text(encoding="utf-8")
        used = set(re.findall(r'"#(id_[a-z_]+)"', source))
        used |= set(re.findall(r'id_[a-z_]+', source))
        html = self._page()
        for field_id in used:
            with self.subTest(script_id=field_id):
                self.assertIn(f'id="{field_id}"', html)


@override_settings(**PLAIN_STATIC)
class PaletteContractTests(TestCase):
    def setUp(self):
        self.admin = make_superuser(username="contractpal", phone="+989000090002")
        self.client.force_login(self.admin)

    def test_palette_hooks_and_script_are_on_every_themed_page(self):
        html = self.client.get(reverse("admin:index")).content.decode()
        for hook in (
            "data-cusin-search-open", "data-search-url",
            "data-cusin-palette", "data-cusin-palette-input",
            "data-cusin-palette-results", "data-cusin-palette-close",
        ):
            with self.subTest(hook=hook):
                self.assertIn(hook, html)
        self.assertIn("admin_theme/js/theme.js", html)

    def test_palette_result_classes_match_the_script(self):
        source = (JS_DIR / "theme.js").read_text(encoding="utf-8")
        for cls in ("cusin-prow", "cusin-prow-icon", "cusin-prow-body",
                    "cusin-prow-title", "cusin-prow-sub", "cusin-pgroup-label",
                    "cusin-palette-empty"):
            with self.subTest(cls=cls):
                self.assertIn(cls, source)
        # every sprite symbol the palette names exists in the one sprite
        sprite = (
            Path(settings.BASE_DIR) / "apps" / "adminui" / "templates"
            / "adminui" / "_sprite.html"
        ).read_text(encoding="utf-8")
        for icon in ("receipt", "box", "users", "grid", "dot"):
            with self.subTest(icon=icon):
                self.assertIn(f'id="cusin-i-{icon}"', sprite)


@override_settings(**PLAIN_STATIC)
class QuickStatusContractTests(TestCase):
    def setUp(self):
        self.admin = make_superuser(username="contractord", phone="+989000090003")
        self.client.force_login(self.admin)

    def _quick_form(self, order):
        html = self.client.get(
            reverse("admin:orders_order_change", args=[order.pk])
        ).content.decode()
        self.assertIn('class="cusin-quick-form"', html)
        # the stock "Fulfilment" fieldset also has a tracking_code input, so
        # only the quick-status form block is inspected here
        return html.split('class="cusin-quick-form"', 1)[1].split("</form>", 1)[0]

    def test_courier_order_renders_tracking_field_and_guarded_buttons(self):
        order = make_order(status=Order.Status.PROCESSING, shipping_method="standard")
        form = self._quick_form(order)
        self.assertIn('name="tracking_code"', form)
        self.assertIn('name="next_status" value="shipped"', form)
        self.assertIn('id="cusin-quick-tracking"', form)
        self.assertIn("admin_theme/js/theme.js", self.client.get(
            reverse("admin:orders_order_change", args=[order.pk])
        ).content.decode())

    def test_pickup_order_has_no_tracking_field_so_the_guard_stays_idle(self):
        # Pickup has no carrier, so workflow.check_transition does not require
        # a code; «ارسال شده» then means "ready for pickup" and the form has no
        # tracking input for the guard to read.
        order = make_order(status=Order.Status.PROCESSING, shipping_method="pickup")
        form = self._quick_form(order)
        self.assertNotIn('name="tracking_code"', form)
        self.assertIn('name="next_status" value="shipped"', form)
