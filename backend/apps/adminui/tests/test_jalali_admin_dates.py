"""
Item 13 -- Jalali dates in the admin, with Persian digits, everywhere.

Django's ``fa`` locale translates the month name but not the calendar:
``DATE_FORMAT`` is ``j F Y``, so every date the admin rendered read
«۱۸ اکتبر ۲۰۲۶» / «15 اکتبر 2026». The owner reads Jalali.

Covered here:
* the order change page's «بازهٔ تحویل … روز» (stray «روز», raw ISO dates)
  and its «زودترین تاریخ تحویل»;
* the print page (/admin/orders/order/<id>/print/);
* the customer invoice (orders/templates/orders/invoice.html);
* the list columns of reviews, wishlist, carts, notification log and
  back-in-stock.
"""
from __future__ import annotations

import datetime as dt
import re

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.adminui.admin_dates import jalali_column, jalali_date, jalali_range
from apps.adminui.jalali import gregorian_to_jalali
from apps.adminui.jalali_forms import JalaliDateField, JalaliDateTimeField, JalaliDateInput, JalaliDateTimeInput

from .helpers import make_order, make_product, make_superuser

# Any of these on a Persian page means a date escaped through |date or
# formats.localize (Django's fa locale prints the Gregorian calendar) instead
# of the Jalali helpers. Matched with a digit next to the month name so that
# ordinary Persian words containing the same letters ("مه" in "همه", say) do
# not trip the check.
_MONTHS = (
    "January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December",
    "ژانویه", "فوریه", "مارس", "آوریل", "جون", "جولای", "اوت",
    "سپتامبر", "اکتبر", "نوامبر", "دسامبر",
)
_GREGORIAN_DATE = re.compile(
    r"(?:\d\s*(?:" + "|".join(_MONTHS) + r")"
    r"|(?:[^\w\u0600-\u06FF]|^)(?:" + "|".join(_MONTHS) + r")\s*\d)",
    re.IGNORECASE,
)
# «2026-10-18» -- the ISO form the old delivery window printed verbatim.
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
# A machine-readable ISO date behind a ``title`` tooltip is deliberate
# (Jalali on screen, unambiguous on hover) -- not what the owner reads.
_TITLES = re.compile(r'title="[^"]*"')


def assert_no_gregorian(test: TestCase, html: str, where: str) -> None:
    """Django's date_hierarchy drill-down is deliberately NOT covered: its
    links filter by Gregorian year/month/day in SQL, so putting Jalali
    labels on them would make them filter the wrong rows. Only the rows
    the owner actually reads are checked -- see ``result_table()``."""
    visible = _TITLES.sub("", html)
    match = _GREGORIAN_DATE.search(visible)
    if match is not None:
        test.fail(f"Gregorian date {match.group(0)!r} on the {where}")
    iso = _ISO_DATE.search(visible)
    if iso is not None:
        test.fail(f"ISO Gregorian date {iso.group(0)!r} on the {where}")


def result_table(html: str) -> str:
    """Just the rows of the changelist -- not Django's own chrome."""
    start = html.find('<table id="result_list">')
    if start == -1:
        return html
    return html[start:html.find("</table>", start)]


class JalaliAdminInputTests(TestCase):
    def test_date_field_accepts_latin_and_persian_jalali_formats(self):
        expected = dt.date(2026, 10, 19)
        self.assertEqual(JalaliDateField().clean("1405/07/27"), expected)
        self.assertEqual(JalaliDateField().clean("۱۴۰۵-۰۷-۲۷"), expected)

    def test_gregorian_years_are_parsed_as_gregorian(self):
        self.assertEqual(JalaliDateField().clean("2026-10-19"), dt.date(2026, 10, 19))

    def test_unsupported_years_are_rejected_with_persian_error(self):
        for value in ("1299/01/01", "1600/01/01", "1699/12/31"):
            with self.subTest(value=value), self.assertRaises(ValidationError) as caught:
                JalaliDateField().clean(value)
            self.assertIn("تاریخ نامعتبر است", str(caught.exception))

    def test_datetime_field_converts_to_local_aware_datetime(self):
        with timezone.override("Asia/Tehran"):
            value = JalaliDateTimeField().clean("1405-07-27 10:35")
        self.assertEqual(timezone.localtime(value).date(), dt.date(2026, 10, 19))
        self.assertEqual(timezone.localtime(value).time(), dt.time(10, 35))
        self.assertTrue(timezone.is_aware(value))

    def test_widgets_display_jalali_date_and_tehran_time(self):
        date_widget = JalaliDateInput()
        self.assertEqual(date_widget.format_value(dt.date(2026, 10, 19)), "۱۴۰۵/۰۷/۲۷")
        with timezone.override("Asia/Tehran"):
            value = timezone.make_aware(dt.datetime(2026, 10, 19, 7, 5), dt.timezone.utc)
            self.assertEqual(JalaliDateTimeInput().format_value(value), "۱۴۰۵/۰۷/۲۷ ۱۰:۳۵")

    def test_invalid_jalali_day_is_rejected(self):
        field = JalaliDateField()
        with self.assertRaises(ValidationError):
            field.clean("1405/12/31")

    def test_coupon_admin_date_fields_use_jalali_widgets(self):
        from django.contrib import admin
        from apps.discounts.models import Coupon

        model_admin = admin.site._registry[Coupon]
        form = model_admin.get_form(type("Request", (), {"user": make_superuser()})())
        self.assertIsInstance(form.base_fields["start_date"].widget, JalaliDateTimeInput)
        self.assertIsInstance(form.base_fields["expiration_date"].widget, JalaliDateTimeInput)

    def test_daily_deal_and_banner_admin_date_fields_use_jalali_widgets(self):
        from django.contrib import admin
        from apps.banners.models import DailyDeal, Banner

        user = make_superuser(username="deal_banner_admin", phone="09128889900")
        deal_admin = admin.site._registry[DailyDeal]
        form = deal_admin.get_form(type("Request", (), {"user": user})())
        self.assertIsInstance(form.base_fields["starts_at"].widget, JalaliDateTimeInput)
        self.assertIsInstance(form.base_fields["ends_at"].widget, JalaliDateTimeInput)
        ctx = form.base_fields["starts_at"].widget.get_context("starts_at", None, {})
        self.assertEqual(ctx["widget"]["attrs"].get("data-jalali-with-time"), "true")

        banner_admin = admin.site._registry[Banner]
        b_form = banner_admin.get_form(type("Request", (), {"user": user})())
        self.assertIsInstance(b_form.base_fields["start_date"].widget, JalaliDateTimeInput)
        self.assertIsInstance(b_form.base_fields["end_date"].widget, JalaliDateTimeInput)

    def test_jalali_datepicker_assets_cover_all_requirements(self):
        import os
        from django.conf import settings

        js_path = os.path.join(settings.BASE_DIR, "static/admin_theme/js/jalali_datepicker.js")
        with open(js_path, "r", encoding="utf-8") as f:
            js = f.read()

        # Weekday headers
        for letter in ["ش", "ی", "د", "س", "چ", "پ", "ج"]:
            self.assertIn(letter, js)
        # Persian year digits
        self.assertIn("jalali-date-picker__year", js)
        # Weekday alignment
        self.assertIn("jalaliFirstDayWeekday", js)
        # Today highlighted
        self.assertIn("jalali-date-picker__day--today", js)
        # Time selects in popup
        self.assertIn("jalali-date-picker__time", js)
        self.assertIn("hourSelect", js)
        self.assertIn("minSelect", js)
        # Reposition / flip
        self.assertIn("repositionPopup", js)
        self.assertIn("placeBelow", js)

        css_path = os.path.join(settings.BASE_DIR, "static/admin_theme/css/jalali_datepicker.css")
        with open(css_path, "r", encoding="utf-8") as f:
            css = f.read()
        self.assertIn(".jalali-date-picker__weekdays", css)
        self.assertIn(".jalali-date-picker__day--today", css)
        self.assertIn(".jalali-date-picker__time", css)
        self.assertIn(".datetimeshortcuts", css)


class JalaliRangeTests(TestCase):
    def test_a_two_day_window_prints_both_ends(self):
        start = dt.date(2026, 10, 18)
        end = dt.date(2026, 10, 20)
        text = jalali_range(start, end)
        self.assertIn("تا", text)
        self.assertEqual(text.count("/"), 4)   # two full Jalali dates
        self.assertNotIn("روز", text)

    def test_a_same_day_window_prints_one_date(self):
        """«… تا …» for a single day reads like a bug."""
        day = dt.date(2026, 10, 18)
        text = jalali_range(day, day)
        self.assertNotIn("تا", text)
        self.assertEqual(text.count("/"), 2)   # one full Jalali date

    def test_the_dates_are_jalali_and_persian(self):
        text = jalali_range(dt.date(2026, 10, 18), dt.date(2026, 10, 20))
        jy, _jm, _jd = gregorian_to_jalali(2026, 10, 18)
        self.assertIn(str(jy), text.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")))
        for digit in "۰۱۲۳۴۵۶۷۸۹":
            if digit in text:
                break
        else:
            self.fail(f"no Persian digits in {text!r}")

    def test_a_missing_end_falls_back_to_the_start(self):
        self.assertEqual(jalali_range(dt.date(2026, 10, 18), None),
                         jalali_date(dt.date(2026, 10, 18)))

    def test_both_missing_is_an_em_dash(self):
        self.assertEqual(jalali_range(None, None), "—")


class JalaliColumnTests(TestCase):
    def test_the_column_renders_jalali_with_persian_digits(self):
        column = jalali_column("created_at", "تاریخ ثبت")

        class Row:
            created_at = dt.date(2026, 10, 15)

        text = column(Row())
        self.assertEqual(text.count("/"), 2)
        self.assertIn("۱۴۰۵", text)
        assert_no_gregorian(self, text, "review column")

    def test_the_column_still_sorts_by_its_field(self):
        column = jalali_column("created_at", "تاریخ ثبت")
        self.assertEqual(column.admin_order_field, "created_at")
        self.assertEqual(column.short_description, "تاریخ ثبت")

    def test_an_empty_value_is_an_em_dash(self):
        column = jalali_column("notified_at", "زمان اطلاع‌رسانی")

        class Row:
            notified_at = None

        self.assertEqual(column(Row()), "—")

    def test_a_datetime_column_can_show_the_time(self):
        column = jalali_column("created_at", "زمان", with_time=True)

        class Row:
            created_at = timezone.make_aware(dt.datetime(2026, 10, 15, 14, 30))

        self.assertIn(":", column(Row()))


class _AdminClient(TestCase):
    def setUp(self):
        self.admin = make_superuser()
        self.client.force_login(self.admin)


class OrderChangePageTests(_AdminClient):
    def _order(self, **overrides):
        order = make_order(**overrides)
        order.refresh_from_db()
        return order

    def test_the_delivery_window_is_jalali_without_the_stray_word(self):
        order = self._order()
        order.estimated_delivery_min = dt.date(2026, 10, 18)
        order.estimated_delivery_max = dt.date(2026, 10, 20)
        order.save(update_fields=["estimated_delivery_min", "estimated_delivery_max"])

        html = self.client.get(
            reverse("admin:orders_order_change", args=[order.pk])
        ).content.decode()
        jy, _jm, _jd = gregorian_to_jalali(2026, 10, 18)
        self.assertIn(jalali_date(dt.date(2026, 10, 18)), html)
        self.assertIn(jalali_date(dt.date(2026, 10, 20)), html)
        assert_no_gregorian(self, html, "order change page")
        # The old text appended «روز» to a DATE RANGE, as if «تا» were a
        # duration: «… تا … روز».
        self.assertNotRegex(html, r"تا[^<]*روز")

    def test_a_same_day_window_prints_one_date(self):
        order = self._order()
        day = dt.date(2026, 10, 18)
        order.estimated_delivery_min = day
        order.estimated_delivery_max = day
        order.save(update_fields=["estimated_delivery_min", "estimated_delivery_max"])
        html = self.client.get(
            reverse("admin:orders_order_change", args=[order.pk])
        ).content.decode()
        self.assertIn(jalali_date(day), html)
        self.assertNotRegex(html, r"تا[^<]*روز")

    def test_the_delivery_field_labels_read_persian(self):
        order = self._order()
        html = self.client.get(
            reverse("admin:orders_order_change", args=[order.pk])
        ).content.decode()
        self.assertIn("زودترین تاریخ تحویل", html)
        self.assertIn("دیرترین تاریخ تحویل", html)
        assert_no_gregorian(self, html, "order change page")


class PrintPageTests(_AdminClient):
    def test_the_print_page_uses_jalali(self):
        order = make_order()
        order.estimated_delivery_min = dt.date(2026, 10, 18)
        order.estimated_delivery_max = dt.date(2026, 10, 20)
        order.save(update_fields=["estimated_delivery_min", "estimated_delivery_max"])
        html = self.client.get(
            reverse("admin:orders_order_print", args=[order.pk])
        ).content.decode()
        self.assertIn(jalali_date(order.estimated_delivery_min), html)
        assert_no_gregorian(self, html, "print page")


class InvoiceTests(TestCase):
    def test_the_customer_invoice_uses_jalali(self):
        order = make_order()
        user = order.user
        self.client.force_login(user)
        html = self.client.get(
            reverse("order-invoice", args=[order.pk])
        ).content.decode()
        self.assertIn(jalali_date(order.created_at, with_time=True), html)
        assert_no_gregorian(self, html, "invoice")


class ListColumnTests(_AdminClient):
    def _html(self, url: str, where: str) -> str:
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        html = result_table(response.content.decode())
        assert_no_gregorian(self, html, where)
        return html

    def test_reviews(self):
        from apps.reviews.models import Review

        Review.objects.create(
            product=make_product(), user=self.admin, rating=4,
            title="خوب", body="بدک نبود", status=Review.Status.PENDING,
        )
        self._html(reverse("admin:reviews_review_changelist"), "reviews list")

    def test_wishlist(self):
        from apps.wishlist.models import WishlistItem

        WishlistItem.objects.create(user=self.admin, product=make_product())
        self._html(reverse("admin:wishlist_wishlistitem_changelist"), "wishlist list")

    def test_carts(self):
        from apps.cart.models import Cart

        Cart.objects.create(user=self.admin)
        self._html(reverse("admin:cart_cart_changelist"), "carts list")

    def test_notification_log(self):
        from apps.notifications.models import NotificationLog
        from apps.notifications.services import Events

        NotificationLog.objects.create(
            event=Events.ORDER_CONFIRMED,
            channel=NotificationLog.Channel.SMS,
            status=NotificationLog.Status.SENT,
            recipient_masked="0912***6789",
        )
        self._html(
            reverse("admin:notifications_notificationlog_changelist"),
            "notification log list",
        )

    def test_back_in_stock(self):
        from apps.products.models import BackInStockSubscription

        BackInStockSubscription.objects.create(
            phone="09123456789", product=make_product(),
        )
        self._html(
            reverse("admin:products_backinstocksubscription_changelist"),
            "back-in-stock list",
        )

    def test_the_columns_actually_print_persian_digits(self):
        """Not merely 'no Gregorian' -- the Jalali year must be there."""
        from apps.wishlist.models import WishlistItem

        WishlistItem.objects.create(user=self.admin, product=make_product())
        html = self._html(reverse("admin:wishlist_wishlistitem_changelist"), "wishlist list")
        self.assertIn(jalali_date(dt.date.today()), html)
