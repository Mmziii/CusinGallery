"""#16 Readability of the admin panel's numbers and names.

Three small, owner-visible annoyances found on the live site:

1. the editable product list prints bare prices («910000»). A grouped,
   Persian-digit hint («۹۱۰٬۰۰۰ تومان») belongs under the input.
2. the order list's customer column printed the account's USERNAME, which
   is an internal artifact -- the owner needs the customer's name and a
   phone number to call.
3. the Excel downloads relied on the server's mime registry, which on a
   plain Linux box guesses application/zip; Excel then refuses to open
   them. Name the Office content type explicitly.
"""
from __future__ import annotations

import re

from django.test import TestCase
from django.urls import reverse

from .helpers import make_product, make_superuser

OFFICE_XLSX = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
PRICE_HINT = re.compile(
    r'<span class="cusin-price-hint"[^>]*>([^<]*)</span>'
)


class PriceHintTests(TestCase):
    """«910000» in a cell nobody can read at a glance."""

    price_url = reverse("admin:products_product_changelist")

    def setUp(self):
        self.admin = make_superuser()
        self.client.force_login(self.admin)

    def hints(self, html):
        return PRICE_HINT.findall(html)

    def test_the_price_input_shows_the_amount_the_owner_reads(self):
        make_product(price=910000)
        html = self.client.get(self.price_url).content.decode()
        self.assertIn('value="910000"', html.replace("&#x27;", "'") or html)
        hints = self.hints(html)
        self.assertTrue(hints, "no price hint rendered")
        self.assertIn("۹۱۰٬۰۰۰ تومان", hints)
        self.assertIn("cusin-price-edit", html)

    def test_bare_digits_are_never_the_only_rendering(self):
        """The raw value stays in the input (the form must POST it), but it
        is no longer the only thing on screen."""
        make_product(price=1250000)
        html = self.client.get(self.price_url).content.decode()
        self.assertIn("۱٬۲۵۰٬۰۰۰ تومان", self.hints(html))
        self.assertIn("cusin-price-edit", html)

    def test_a_blank_compare_at_price_does_not_read_as_zero(self):
        make_product(price=50000)
        html = self.client.get(self.price_url).content.decode()
        hints = self.hints(html)
        # price is 50,000 -> one readable hint, the empty compare-at price
        # shows the placeholder instead of «۰ تومان».
        self.assertIn("۵۰٬۰۰۰ تومان", hints)
        self.assertEqual(len(hints), 2, hints)
        self.assertEqual(hints.count("—"), 1, hints)

    def test_the_hint_is_attached_to_the_input_it_describes(self):
        make_product(price=300000)
        html = self.client.get(self.price_url).content.decode()
        blocks = re.findall(r'<div class="cusin-price-edit">(.+?)</div>', html)
        self.assertEqual(len(blocks), 2, blocks)  # price + compare_at_price
        self.assertIn('<input', blocks[0])
        self.assertIn("cusin-price-hint", blocks[0])

    def test_the_hint_keeps_up_with_typing(self):
        """Server-side markup alone would show a stale amount as soon as
        the owner edits the cell."""
        js = (
            self.admin and open(
                "static/admin_theme/js/theme.js", encoding="utf-8"
            ).read()
        )
        self.assertIn("function initPriceHints", js)
        self.assertIn('addEventListener("input", sync)', js)
        self.assertIn("initPriceHints();", js)

    def test_the_hint_is_styled_to_sit_under_the_input(self):
        css = open(
            "static/admin_theme/css/theme.css", encoding="utf-8"
        ).read()
        self.assertIn(".cusin-price-hint", css)
        self.assertIn("cusin-price-edit", css)


class OrderCustomerColumnTests(TestCase):
    """The order list identified a customer by their login name."""

    def setUp(self):
        self.admin = make_superuser()
        self.client.force_login(self.admin)

    def test_the_list_shows_the_name_and_a_phone_number(self):
        from apps.adminui.tests.helpers import make_order
        from apps.accounts.models import User

        customer = User.objects.create_user(
            username="09120001122",
            phone="09120001122",
            first_name="زهرا",
            last_name="احمدی",
            password="x",
        )
        order = make_order(user=customer)
        order.shipping_phone = "09123334455"
        order.save(update_fields=["shipping_phone"])

        html = self.client.get(reverse("admin:orders_order_changelist")).content.decode()
        cell = re.search(
            r'<td class="field-customer_cell">(.*?)</td>', html, re.S
        )
        self.assertIsNotNone(cell, "no customer column rendered")
        self.assertIn("زهرا احمدی", cell.group(1))
        # The courier's number is the shipping phone, not the account's;
        # it is shown in Persian digits (Task 4: name on one line, the
        # phone on a second muted line).
        self.assertIn("۰۹۱۲۳۳۳۴۴۵۵", cell.group(1))
        self.assertIn("cusin-customer", cell.group(1))

    def test_the_username_is_no_longer_the_label(self):
        from apps.adminui.tests.helpers import make_order
        from apps.accounts.models import User

        customer = User.objects.create_user(
            username="cusin-4421",
            phone="09120001122",
            first_name="علی",
            last_name="رضایی",
            password="x",
        )
        make_order(user=customer)
        html = self.client.get(reverse("admin:orders_order_changelist")).content.decode()
        cell = re.search(
            r'<td class="field-customer_cell">(.*?)</td>', html, re.S
        )
        self.assertIsNotNone(cell)
        self.assertIn("علی رضایی", cell.group(1))
        self.assertNotIn("cusin-4421", cell.group(1))

    def test_a_customer_without_a_name_still_shows_something(self):
        from apps.adminui.tests.helpers import make_order

        order = make_order()
        order.shipping_phone = ""
        order.save(update_fields=["shipping_phone"])
        html = self.client.get(reverse("admin:orders_order_changelist")).content.decode()
        cell = re.search(
            r'<td class="field-customer_cell">(.*?)</td>', html, re.S
        )
        self.assertIsNotNone(cell)
        self.assertIn("cusin-customer__name", cell.group(1))
        # no crash, and something legible is shown for the name
        self.assertNotEqual(
            re.search(
                r'cusin-customer__name"[^>]*>([^<]*)<', cell.group(1)
            ).group(1).strip(),
            "",
        )

    def test_the_column_is_sortable(self):
        from apps.adminui.tests.helpers import make_order

        make_order()
        response = self.client.get(
            reverse("admin:orders_order_changelist"), {"o": "1"}
        )
        self.assertEqual(response.status_code, 200)


class ExcelContentTypeTests(TestCase):
    """The downloaded .xlsx files must announce the Office type, not
    whatever the server's mime registry guesses for a zip archive."""

    def setUp(self):
        self.admin = make_superuser()
        self.client.force_login(self.admin)

    def _type(self, url, params):
        response = self.client.get(url, params)
        self.assertEqual(response.status_code, 200)
        return response["Content-Type"]

    def test_the_catalog_export_is_an_office_file(self):
        make_product()
        self.assertIn(
            OFFICE_XLSX,
            self._type(reverse("admin:products_product_export"), {"format": "xlsx"}),
        )

    def test_the_import_template_is_an_office_file(self):
        self.assertIn(
            OFFICE_XLSX,
            self._type(
                reverse("admin:products_product_import_template"),
                {"format": "xlsx"},
            ),
        )

    def test_the_price_stock_template_is_an_office_file(self):
        self.assertIn(
            OFFICE_XLSX,
            self._type(
                reverse("admin:products_product_update_template"),
                {"format": "xlsx"},
            ),
        )

    def test_the_csv_download_is_untouched(self):
        make_product()
        content_type = self._type(
            reverse("admin:products_product_export"), {"format": "csv"}
        )
        self.assertIn("text/csv", content_type)
