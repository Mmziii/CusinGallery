"""
Item 14 -- the two printed documents: the customer invoice and the
admin's print page.

* Codes stay LATIN. Persian-digit conversion was applied to the whole
  string, so «CG-20261014-9D9B» printed as «CG-۲۰۲۶۱۰۱۴-۹D۹B» -- half
  Latin letters, half Persian digits, unreadable and unsearchable, and
  useless to a customer who has to quote it back. Order numbers, SKUs,
  tracking codes and coupon codes are identifiers, not amounts.
* Amounts get thousands separators: «1935000» vs «۱٬۹۳۵٬۰۰۰ تومان».
* Both documents open with the shop's own name, phone and address from
  «تنظیمات فروشگاه» -- a printed document with no letterhead is not a
  receipt, and the values were already sitting in SiteSettings unused.
"""
from __future__ import annotations

from django.test import TestCase
from django.urls import reverse

from apps.adminui.admin_dates import jalali_date
from apps.core.models import SiteSettings
from apps.orders.models import Order

from apps.adminui.tests.helpers import make_order

# Persian digits -- must NOT appear inside an order number, SKU, tracking
# code or coupon code.
PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"


def has_persian_digit(text: str) -> bool:
    return any(ch in PERSIAN_DIGITS for ch in text)


class _DocTests(TestCase):
    def setUp(self):
        self.order = make_order(
            total=1_935_000, subtotal=1_900_000, shipping_cost=50_000,
            tracking_code="TRACK-1234-AB",
        )
        self.order.refresh_from_db()
        self.item = self.order.items.first()
        self.site = SiteSettings.load()
        self.site.shop_name = "گالری کازین"
        self.site.phone = "021-88776655"
        self.site.address = "تهران، خیابان ولیعصر، پلاک ۱۲۳"
        self.site.save()

    def invoice_html(self) -> str:
        self.client.force_login(self.order.user)
        response = self.client.get(reverse("order-invoice", args=[self.order.pk]))
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def print_html(self) -> str:
        from apps.adminui.tests.helpers import make_superuser

        self.client.force_login(make_superuser())
        response = self.client.get(
            reverse("admin:orders_order_print", args=[self.order.pk])
        )
        self.assertEqual(response.status_code, 200)
        return response.content.decode()


class LatinCodeTests(_DocTests):
    def test_the_invoice_keeps_the_order_number_latin(self):
        html = self.invoice_html()
        self.assertIn(self.order.order_number, html)
        self.assertIn(f'<bdi dir="ltr">{self.order.order_number}</bdi>', html)

    def test_the_invoice_keeps_the_sku_latin(self):
        html = self.invoice_html()
        self.assertIn(self.item.sku, html)
        self.assertIn(f'<bdi dir="ltr">{self.item.sku}</bdi>', html)

    def test_the_invoice_keeps_the_tracking_code_latin(self):
        html = self.invoice_html()
        self.assertIn(self.order.tracking_code, html)

    def test_the_phone_stays_readable_in_persian_digits(self):
        """A phone number is a number, not an identifier: Persian digits,
        but isolated so it does not get mirrored in the RTL flow."""
        html = self.invoice_html()
        self.assertIn("۰۲۱-۸۸۷۷۶۶۵۵", html)

    def test_no_code_on_the_invoice_is_half_persian(self):
        """A code must be all-Latin -- never «CG-۲۰۲۶۱۰۱۴-۹D۹B»."""
        html = self.invoice_html()
        for code in (self.order.order_number, self.item.sku, self.order.tracking_code):
            with self.subTest(code=code):
                self.assertIn(code, html)
                # every digit run in a code stays ASCII
                for cell in _between_bdi(html):
                    if code in cell:
                        self.assertFalse(
                            has_persian_digit(cell), f"{cell!r} has Persian digits"
                        )

    def test_the_print_page_keeps_codes_latin(self):
        html = self.print_html()
        self.assertIn(self.order.order_number, html)
        self.assertIn(self.item.sku, html)
        self.assertIn(self.order.tracking_code, html)
        for cell in _between_bdi(html):
            if cell.strip() == "۰۲۱-۸۸۷۷۶۶۵۵":
                continue  # the shop's phone: a number, deliberately Persian
            self.assertFalse(has_persian_digit(cell), f"{cell!r} has Persian digits")


def _between_bdi(html: str):
    """Yield the contents of every ``<bdi …>…</bdi>`` element."""
    start = 0
    while True:
        open_at = html.find("<bdi", start)
        if open_at == -1:
            return
        gt = html.find(">", open_at)
        close_at = html.find("</bdi>", gt)
        if close_at == -1:
            return
        yield html[gt + 1:close_at]
        start = close_at + 6


class AmountFormattingTests(_DocTests):
    def test_the_print_page_groups_amounts(self):
        html = self.print_html()
        self.assertIn("۱٬۹۳۵٬۰۰۰ تومان", html)
        self.assertNotIn("1935000", html)

    def test_the_print_page_groups_the_line_totals(self):
        html = self.print_html()
        self.assertIn("۱٬۹۰۰٬۰۰۰ تومان", html)

    def test_the_invoice_groups_amounts(self):
        html = self.invoice_html()
        self.assertIn("۱٬۹۳۵٬۰۰۰", html)
        self.assertNotIn("1935000", html)

    def test_a_zero_shipping_cost_still_reads_free_not_empty(self):
        self.order.shipping_cost = 0
        self.order.save(update_fields=["shipping_cost"])
        self.assertIn("رایگان", self.invoice_html())


class LetterheadTests(_DocTests):
    def test_the_invoice_opens_with_the_shop_name_phone_and_address(self):
        html = self.invoice_html()
        self.assertIn("گالری کازین", html)
        self.assertIn("۰۲۱-۸۸۷۷۶۶۵۵", html)
        self.assertIn("خیابان ولیعصر", html)

    def test_the_print_page_opens_with_the_shop_name_phone_and_address(self):
        html = self.print_html()
        self.assertIn("گالری کازین", html)
        self.assertIn("۰۲۱-۸۸۷۷۶۶۵۵", html)
        self.assertIn("خیابان ولیعصر", html)

    def test_an_unset_shop_name_falls_back_to_the_brand(self):
        self.site.shop_name = ""
        self.site.save(update_fields=["shop_name"])
        self.assertEqual(self.site.display_name, "کازین گالری")
        self.assertIn("کازین گالری", self.invoice_html())
        self.assertIn("کازین گالری", self.print_html())

    def test_a_placeholder_shop_name_is_not_printed(self):
        """The seeded «[نام فروشگاه را وارد کنید]» is an instruction, not a
        letterhead -- printing it would put a bracketed sentence on the
        customer's receipt."""
        self.site.shop_name = "[نام فروشگاه را از پنل مدیریت وارد کنید]"
        self.site.save(update_fields=["shop_name"])
        self.assertEqual(self.site.display_name, "کازین گالری")
        html = self.invoice_html()
        self.assertNotIn("[نام فروشگاه", html)
        self.assertIn("کازین گالری", html)

    def test_a_placeholder_phone_is_not_printed(self):
        self.site.phone = "+98 21 0000 0000"
        self.site.address = ""
        self.site.save(update_fields=["phone", "address"])
        html = self.invoice_html()
        self.assertNotIn("0000 0000", html)
        self.assertNotIn("تلفن:", html)

    def test_the_documents_still_show_the_order_and_the_jalali_date(self):
        for html in (self.invoice_html(), self.print_html()):
            self.assertIn(self.order.order_number, html)
            self.assertIn(jalali_date(self.order.created_at, with_time=True), html)

    def test_the_print_page_shows_the_delivery_window(self):
        import datetime as dt

        from apps.adminui.admin_dates import jalali_range

        self.order.estimated_delivery_min = dt.date(2026, 10, 18)
        self.order.estimated_delivery_max = dt.date(2026, 10, 20)
        self.order.save(update_fields=[
            "estimated_delivery_min", "estimated_delivery_max",
        ])
        html = self.print_html()
        self.assertIn("تحویل", html)
        self.assertIn(
            jalali_range(dt.date(2026, 10, 18), dt.date(2026, 10, 20)), html
        )


class CodeIsolationTests(TestCase):
    """Amounts are Persian; codes are not. Both on the same document."""

    def test_persian_digits_are_still_used_for_amounts(self):
        order = make_order(total=1_935_000)
        order.refresh_from_db()
        self.client.force_login(order.user)
        html = self.client.get(
            reverse("order-invoice", args=[order.pk])
        ).content.decode()
        self.assertIn("تومان", html)
        self.assertTrue(has_persian_digit(html))
