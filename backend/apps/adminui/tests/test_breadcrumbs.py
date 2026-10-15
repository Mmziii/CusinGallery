"""#6 The breadcrumb trail must not repeat itself.

Django's admin templates each render their own trail, and a single-model
app is named after the model it contains:

    شروع › سفارش‌ها › سفارش‌ها › CG-20261015-75CED575

«سفارش‌ها» is both the app (apps/orders/apps.py verbose_name) and the
model's plural, so the trail said the same word twice.

The theme now builds one trail itself (apps/adminui/breadcrumbs.py) and
drops the app crumb when it would only repeat the model crumb. Because
templates/admin/base.html no longer declares a ``breadcrumbs`` block, the
blocks Django's change_form / change_list / delete_confirmation /
object_history / delete_selected_confirmation templates define have
nothing to override and are not rendered at all.
"""
from __future__ import annotations

import re

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.adminui.breadcrumbs import build_crumbs
from apps.accounts.models import User

from .helpers import PLAIN_STATIC, make_order, make_product, make_superuser

CRUMB = re.compile(r'<div class="breadcrumbs">(.*?)</div>', re.S)


def crumb_texts(html):
    """The labels of the one trail on the page (separators skipped)."""
    match = CRUMB.search(html)
    assert match is not None, "no breadcrumb trail rendered"
    inner = match.group(1)
    labels = []
    for element in re.finditer(r"<(a|span)([^>]*)>(.*?)</\1>", inner, re.S):
        attributes, text = element.group(2), element.group(3)
        if "cusin-crumb-sep" in attributes:
            continue
        text = text.strip()
        if text:
            labels.append(text)
    return labels


class FakeOptions:
    """Just enough of ``Model._meta`` for build_crumbs."""

    def __init__(self, app_label, model_name, app_verbose, model_plural):
        self.app_label = app_label
        self.model_name = model_name
        self.verbose_name_plural = model_plural
        self.verbose_name = model_plural
        self.app_config = type("Cfg", (), {"verbose_name": app_verbose})()


class FakeRequest:
    def __init__(self, url_name=""):
        self.resolver_match = type("M", (), {"url_name": url_name})()
        self.path = "/admin/"


class BuildCrumbsTests(SimpleTestCase):
    """The builder is a pure function, so it is tested directly."""

    def crumbs(self, **context):
        context.setdefault("request", FakeRequest())
        return [crumb["label"] for crumb in build_crumbs(context)]

    @staticmethod
    def opts(app_verbose="سفارش‌ها", model_plural="سفارش‌ها", **kwargs):
        return FakeOptions(
            kwargs.get("app_label", "orders"),
            kwargs.get("model_name", "order"),
            app_verbose,
            model_plural,
        )

    def test_a_single_model_app_is_named_once(self):
        self.assertEqual(self.crumbs(opts=self.opts()), ["شروع", "سفارش‌ها"])

    def test_the_duplicate_is_caught_across_zwnj_and_spacing(self):
        """«سفارش‌ها» is written with an invisible joiner in one label and
        without it in the other -- the owner sees the same word."""
        self.assertEqual(
            self.crumbs(opts=self.opts("سفارش‌ها", "سفارش‌ها")),
            ["شروع", "سفارش‌ها"],
        )

    def test_an_app_named_after_something_else_keeps_its_crumb(self):
        labels = self.crumbs(
            opts=self.opts("حساب کاربری", "کاربران", app_label="accounts",
                           model_name="user"),
            request=FakeRequest("accounts_user_change"),
        )
        self.assertEqual(labels, ["شروع", "حساب کاربری", "کاربران"])

    def test_a_page_without_a_model_falls_back_to_its_title(self):
        self.assertEqual(
            self.crumbs(title="ورود گروهی تصاویر"),
            ["شروع", "ورود گروهی تصاویر"],
        )

    def test_the_object_is_the_last_crumb(self):
        order = type("O", (), {"pk": 7, "__str__": lambda self: "CG-1"})()
        labels = self.crumbs(
            opts=self.opts(), original=order,
            request=FakeRequest("orders_order_change"),
        )
        self.assertEqual(labels, ["شروع", "سفارش‌ها", "CG-1"])

    def test_add_pages_say_what_is_being_added(self):
        labels = self.crumbs(
            opts=self.opts("محصولات", "محصولات", app_label="products",
                           model_name="product"),
            add=True, request=FakeRequest("products_product_add"),
        )
        self.assertEqual(labels, ["شروع", "محصولات", "افزودن محصولات"])

    def test_history_and_delete_name_the_action(self):
        order = type("O", (), {"pk": 7, "__str__": lambda self: "CG-1"})()
        for url_name, last in (("orders_order_history", "تاریخچه"),
                               ("orders_order_delete", "حذف")):
            with self.subTest(url_name=url_name):
                self.assertEqual(
                    self.crumbs(opts=self.opts(), original=order,
                                request=FakeRequest(url_name)),
                    ["شروع", "سفارش‌ها", "CG-1", last],
                )

    def test_deleting_selected_rows_is_named(self):
        labels = self.crumbs(
            opts=self.opts(), deleted_objects=[],
            request=FakeRequest("orders_order_changelist"),
        )
        self.assertEqual(labels, ["شروع", "سفارش‌ها", "حذف موارد انتخاب‌شده"])

    def test_the_model_crumb_is_a_link_away_from_its_own_list(self):
        crumbs = build_crumbs(
            {"opts": self.opts(), "original": None,
             "request": FakeRequest("orders_order_change")}
        )
        self.assertEqual(crumbs[1]["url"], "/admin/orders/order/")
        # ...and plain text ON the list
        crumbs = build_crumbs(
            {"opts": self.opts(), "request": FakeRequest("orders_order_changelist")}
        )
        self.assertEqual(crumbs[1]["url"], "")


@override_settings(**PLAIN_STATIC)
class BreadcrumbPageTests(TestCase):
    """The rendered pages: one trail, no repeated word."""

    def setUp(self):
        self.admin = make_superuser(username="crumb-owner", phone="+989000060001")
        self.client.force_login(self.admin)

    def test_the_order_change_page_does_not_repeat_the_app_name(self):
        order = make_order()
        html = self.client.get(
            reverse("admin:orders_order_change", args=[order.pk])
        ).content.decode()
        self.assertEqual(html.count('class="breadcrumbs"'), 1)
        labels = crumb_texts(html)
        self.assertEqual(labels.count("سفارش‌ها"), 1, labels)
        self.assertEqual(labels, ["شروع", "سفارش‌ها", order.order_number])

    def test_the_order_list_does_not_repeat_the_app_name(self):
        html = self.client.get(reverse("admin:orders_order_changelist")).content.decode()
        self.assertEqual(crumb_texts(html), ["شروع", "سفارش‌ها"])

    def test_the_product_list_does_not_repeat_the_app_name(self):
        make_product()
        html = self.client.get(
            reverse("admin:products_product_changelist")
        ).content.decode()
        self.assertEqual(crumb_texts(html), ["شروع", "محصولات"])

    def test_an_app_named_after_something_else_still_shows_both(self):
        user = User.objects.create_user(username="09120000001", password="x")
        html = self.client.get(
            reverse("admin:accounts_user_change", args=[user.pk])
        ).content.decode()
        labels = crumb_texts(html)
        self.assertEqual(labels[:3], ["شروع", "حساب کاربری", "کاربران"])

    def test_the_first_crumb_is_a_link_home(self):
        html = self.client.get(reverse("admin:orders_order_changelist")).content.decode()
        match = CRUMB.search(html)
        self.assertIn('href="/admin/"', match.group(1))

    def test_a_custom_admin_page_still_gets_a_trail(self):
        html = self.client.get(
            reverse("admin:products_product_image_import")
        ).content.decode()
        labels = crumb_texts(html)
        self.assertEqual(labels[0], "شروع")
        self.assertEqual(labels[1], "محصولات")
        self.assertTrue(labels[-1])

    def test_the_separator_is_spaced_so_the_trail_does_not_run_together(self):
        css = open(
            "static/admin_theme/css/theme.css", encoding="utf-8"
        ).read()
        block = css.split(".cusin-crumb-sep {", 1)[1].split("}", 1)[0]
        self.assertIn("margin", block)
