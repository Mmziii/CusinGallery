"""A4: empty states on every changelist, and the no-results state of search
and filters. The block must appear exactly when the changelist has zero
rows, on every registered model, and must not change the stock paginator
or the normal list rendering."""
from django.contrib import admin
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.orders.models import Order

from .helpers import PLAIN_STATIC, make_order, make_product, make_superuser

MARKER = 'class="cusin-empty-state"'


def changelist_url(model):
    return reverse(
        f"admin:{model._meta.app_label}_{model._meta.model_name}_changelist"
    )


@override_settings(**PLAIN_STATIC)
class EveryChangelistEmptyStateTests(TestCase):
    """Walks the real admin registry: no hand-maintained list of models."""

    def setUp(self):
        self.admin_user = make_superuser(username="emptyowner", phone="+989000070001")
        self.client.force_login(self.admin_user)

    def test_empty_flag_matches_row_count_on_every_registered_changelist(self):
        checked, redirected = [], []
        # superuser: every registered model is viewable
        for model in admin.site._registry:
            url = changelist_url(model)
            response = self.client.get(url)
            if response.status_code != 200:
                # e.g. SiteSettings is a singleton that redirects to its form
                redirected.append((model.__name__, response.status_code))
                continue
            cl = response.context["cl"]
            has_marker = MARKER in response.content.decode()
            self.assertEqual(
                has_marker, cl.result_count == 0,
                f"{model.__name__}: result_count={cl.result_count} "
                f"but empty-state marker present={has_marker}",
            )
            checked.append(model.__name__)
        # the walk really covered the panel (not an empty loop)
        self.assertGreaterEqual(len(checked), 15)
        self.assertIn("Order", checked)
        self.assertIn("Product", checked)
        self.assertIn("User", checked)
        # only the known singleton redirect is allowed
        for name, status in redirected:
            self.assertEqual(name, "SiteSettings", (name, status))
            self.assertEqual(status, 302)

    def test_plain_empty_orders_list_says_nothing_exists_yet(self):
        response = self.client.get(reverse("admin:orders_order_changelist"))
        html = response.content.decode()
        self.assertIn(MARKER, html)
        self.assertIn("هنوز", html)
        self.assertIn("ثبت نشده است", html)
        self.assertNotIn("نتیجه‌ای پیدا نشد", html)
        # the table body is still present in markup but CSS hides it; the
        # paginator count stays truthful
        self.assertIn("0 سفارش", html)

    def test_search_with_no_match_shows_no_results_and_clear_link(self):
        make_product(name="کتری")
        response = self.client.get(
            reverse("admin:products_product_changelist"), {"q": "قابلمه"}
        )
        html = response.content.decode()
        self.assertIn(MARKER, html)
        self.assertIn("نتیجه‌ای پیدا نشد", html)
        self.assertIn("جستجوی «قابلمه»", html)
        self.assertIn("پاک‌کردن جستجو و فیلترها", html)
        self.assertIn('href="?"', html)
        self.assertNotIn("هنوز", html)  # not the "nothing exists" wording

    def test_filter_with_no_match_shows_no_results(self):
        make_product(name="کتری", is_active=True)
        response = self.client.get(
            reverse("admin:products_product_changelist"), {"is_active__exact": "0"}
        )
        html = response.content.decode()
        self.assertIn("نتیجه‌ای پیدا نشد", html)
        self.assertIn("با فیلترهای فعلی", html)
        # the total count is offered so the owner knows data exists
        self.assertIn("در مجموع 1 مورد ثبت شده است", html)

    def test_normal_list_has_no_empty_state(self):
        make_order()
        response = self.client.get(reverse("admin:orders_order_changelist"))
        html = response.content.decode()
        self.assertNotIn(MARKER, html)
        self.assertIn('id="result_list"', html)
        self.assertIn("1 سفارش", html)

    def test_result_count_message_unchanged_for_filtered_lists(self):
        """The stock «N products» line still renders on non-empty lists."""
        make_product(name="A")
        make_product(name="B")
        response = self.client.get(reverse("admin:products_product_changelist"))
        self.assertEqual(response.context["cl"].result_count, 2)
        self.assertIn("2 محصولات", response.content.decode())

    def test_search_term_is_escaped(self):
        response = self.client.get(
            reverse("admin:products_product_changelist"),
            {"q": "<script>alert(1)</script>"},
        )
        html = response.content.decode()
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)


@override_settings(**PLAIN_STATIC)
class EmptyStateTemplateTests(TestCase):
    def test_empty_state_uses_theme_icons_that_exist(self):
        from pathlib import Path

        from django.conf import settings

        sprite = (
            Path(settings.BASE_DIR) / "apps" / "adminui" / "templates"
            / "adminui" / "_sprite.html"
        ).read_text(encoding="utf-8")
        template = (
            Path(settings.BASE_DIR) / "templates" / "admin" / "pagination.html"
        ).read_text(encoding="utf-8")
        for icon in ("search", "box"):
            self.assertIn(f'cusin_icon "{icon}"', template)
            self.assertIn(f'id="cusin-i-{icon}"', sprite)

    def test_paginator_block_keeps_stock_markup(self):
        from pathlib import Path

        from django.conf import settings

        template = (
            Path(settings.BASE_DIR) / "templates" / "admin" / "pagination.html"
        ).read_text(encoding="utf-8")
        for stock_fragment in (
            "{% paginator_number cl i %}",
            '<input type="submit" name="_save" class="default"',
            "{% if show_all_url %}",
        ):
            self.assertIn(stock_fragment, template)

    def test_theme_disabled_falls_back_to_stock_without_empty_state(self):
        from copy import deepcopy

        from django.conf import settings
        from django.template.loader import get_template

        templates = deepcopy(settings.TEMPLATES)
        templates[0]["DIRS"] = []
        with self.settings(TEMPLATES=templates, ADMIN_THEME_ENABLED=False):
            from django.template import engines

            engines._engines = {}
            try:
                source = get_template("admin/pagination.html").template.source
            finally:
                engines._engines = {}
        self.assertNotIn("cusin-empty-state", source)
