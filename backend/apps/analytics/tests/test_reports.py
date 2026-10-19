"""Task 2: «گزارش‌ها و تحلیل» -- exact calculations on fixture data.

Everything is anchored to a frozen "now" so the 30-day window is
deterministic regardless of when the suite runs.
"""
import datetime as dt

from django.contrib.auth.models import Permission
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.adminui.tests.helpers import PLAIN_STATIC, make_staff, make_superuser
from apps.orders.models import Order
from apps.wishlist.models import WishlistItem

from ..models import Event
from ..reports import PRESETS, build_report, parse_jalali, resolve_range
from .helpers import make_customer, make_event, make_order, make_product

TEHRAN = dt.timezone(dt.timedelta(hours=3, minutes=30))
FIXED = dt.datetime(2026, 10, 10, 12, 0, tzinfo=TEHRAN)


def ago(days=0, hours=0):
    return FIXED.astimezone(dt.timezone.utc) - dt.timedelta(days=days, hours=hours)


def range_30(now=FIXED):
    return resolve_range({"range": "30"}, now=now)


class RangeTests(TestCase):
    def test_presets_resolve_to_tehran_days(self):
        today = resolve_range({"range": "today"}, now=FIXED)
        self.assertEqual(today.start_date, today.end_date)
        self.assertEqual(today.start_input, "1405/07/18")

        week = resolve_range({"range": "7"}, now=FIXED)
        self.assertEqual(week.days, 7)

        year = resolve_range({"range": "year"}, now=FIXED)
        self.assertEqual(year.start_input, "1405/01/01")
        self.assertEqual(year.end_date, today.end_date)

    def test_jalali_custom_range_is_parsed(self):
        r = resolve_range(
            {"range": "custom", "start": "۱۴۰۵/۰۷/۰۱", "end": "1405/07/10"},
            now=FIXED,
        )
        self.assertFalse(r.message)
        self.assertEqual(r.start_input, "1405/07/01")
        self.assertEqual(r.end_input, "1405/07/10")
        self.assertEqual(r.days, 10)

    def test_bad_or_reversed_custom_range_is_explained_in_persian(self):
        broken = resolve_range({"range": "custom", "start": "x", "end": "y"}, now=FIXED)
        self.assertIn("۱۴۰۵/۰۷/۰۱", broken.message)
        self.assertEqual(broken.key, "30")

        reversed_ = resolve_range(
            {"range": "custom", "start": "1405/07/10", "end": "1405/07/01"},
            now=FIXED,
        )
        self.assertEqual(reversed_.start_input, "1405/07/01")
        self.assertIn("جای دو تاریخ عوض شد", reversed_.message)

    def test_parse_jalali_accepts_persian_digits(self):
        self.assertEqual(
            parse_jalali("۱۴۰۵/۰۷/۱۸"),
            dt.date(2026, 10, 10),
        )

    def test_future_end_and_over_long_spans_are_clamped(self):
        future = resolve_range(
            {"range": "custom", "start": "1405/07/01", "end": "1405/09/01"},
            now=FIXED,
        )
        self.assertLessEqual(future.end_date, FIXED.date())
        self.assertIn("آینده", future.message)

        long = resolve_range(
            {"range": "custom", "start": "1400/01/01", "end": "1405/07/10"},
            now=FIXED,
        )
        self.assertLessEqual(long.days, 366)


@override_settings(**PLAIN_STATIC)
class ReportNumberTests(TestCase):
    def setUp(self):
        self.range = range_30()

        self.product_a = make_product(name="قوری چینی", price=100000)
        self.product_b = make_product(name="کتری مسی", price=200000)

        self.new_customer = make_customer(phone="+989171000001")
        self.returning_customer = make_customer(phone="+989171000002")

        # Returning: a paid order BEFORE the range.
        make_order(
            self.returning_customer, self.product_a,
            created_at=ago(days=50), total=100000,
            item={"unit_price": 100000, "quantity": 1, "total_price": 100000},
        )

        # Today: two paid orders, one cancelled paid order (money excluded).
        self.paid_one = make_order(
            self.new_customer, self.product_a, created_at=ago(days=1),
            total=100000,
            item={"unit_price": 100000, "quantity": 1, "total_price": 100000},
        )
        self.paid_two = make_order(
            self.returning_customer, self.product_b, created_at=ago(days=2),
            total=200000,
            item={"unit_price": 200000, "quantity": 1, "total_price": 200000},
        )
        make_order(
            self.new_customer, self.product_b, created_at=ago(days=3),
            total=50000, status=Order.Status.CANCELLED,
            item={"unit_price": 200000, "quantity": 1, "total_price": 50000},
        )

        # Two anonymous sessions: s1 converted, s2 only looked.
        for event_type in (
            Event.Type.PRODUCT_VIEW, Event.Type.ADD_TO_CART,
            Event.Type.CHECKOUT_STARTED, Event.Type.ORDER_PLACED,
            Event.Type.ORDER_PAID,
        ):
            make_event(
                event_type, session_key="session-aaaa1111", created_at=ago(days=1),
                product=self.product_a,
                **({"order": self.paid_one} if event_type.startswith("order") else {}),
            )
        make_event(
            Event.Type.PRODUCT_VIEW, session_key="session-bbbb2222",
            created_at=ago(days=2), product=self.product_b,
        )

    def test_summary_cards(self):
        summary = build_report(self.range)["summary"]
        self.assertEqual(summary["revenue"], 300000)
        self.assertEqual(summary["orders"], 3)
        self.assertEqual(summary["paid_orders"], 2)
        self.assertEqual(summary["aov"], 150000)
        self.assertEqual(summary["sessions"], 2)
        self.assertEqual(summary["paid_sessions"], 1)
        self.assertEqual(summary["conversion"], 50)
        self.assertEqual(summary["new_customers"], 1)
        self.assertEqual(summary["returning_customers"], 1)

    def test_funnel_counts_sessions_and_drop_off(self):
        funnel = {row["key"]: row for row in build_report(self.range)["funnel"]}
        self.assertEqual(funnel[Event.Type.PRODUCT_VIEW]["count"], 2)
        self.assertEqual(funnel[Event.Type.ADD_TO_CART]["count"], 1)
        self.assertEqual(funnel[Event.Type.ORDER_PAID]["count"], 1)
        self.assertEqual(funnel[Event.Type.ADD_TO_CART]["drop"], 50)
        self.assertIsNone(funnel[Event.Type.PRODUCT_VIEW]["drop"])

    def test_abandoned_carts_lists_open_baskets_only(self):
        from apps.cart.models import CartItem
        from apps.cart.services import get_or_create_cart

        shopper = make_customer(phone="+989171000003", first_name="مریم", last_name="کریمی")
        cart = get_or_create_cart(shopper)
        item = CartItem.objects.create(cart=cart, product=self.product_a, quantity=2)
        # The fixture clock is frozen; auto_now timestamps use the real
        # clock, so pin the cart's activity inside the range.
        from apps.cart.models import Cart

        CartItem.objects.filter(pk=item.pk).update(created_at=ago(days=1), updated_at=ago(days=1))
        Cart.objects.filter(pk=cart.pk).update(updated_at=ago(days=1))

        rows = build_report(self.range)["abandoned"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "مریم کریمی")
        self.assertEqual(rows[0]["phone"], "+989171000003")
        self.assertEqual(rows[0]["item_count"], 2)
        self.assertEqual(rows[0]["total"], 200000)
        self.assertEqual(rows[0]["user_url"], reverse("admin:accounts_user_change", args=[shopper.pk]))

        # A completed checkout clears the cart -> no longer abandoned.
        item.delete()
        self.assertEqual(build_report(self.range)["abandoned"], [])

    def test_zero_result_searches_are_separated(self):
        make_event(
            Event.Type.SEARCH, session_key="session-aaaa1111", created_at=ago(days=1),
            search_query="کتری مسی", search_results=3,
        )
        for _ in range(2):
            make_event(
                Event.Type.SEARCH, session_key="session-bbbb2222", created_at=ago(days=2),
                search_query="ماگ سرامیکی", search_results=0,
            )
        searches = build_report(self.range)["searches"]
        self.assertEqual(searches["total"], 3)
        self.assertEqual(searches["zero_total"], 2)
        self.assertEqual(searches["zero"][0]["query"], "ماگ سرامیکی")
        self.assertEqual(searches["zero"][0]["count"], 2)
        # «پرجستجوترین» covers every query, including the ones with no
        # results; the zero-result card is the extra signal on top.
        self.assertIn("ماگ سرامیکی", [row["query"] for row in searches["top"]])

    def test_high_views_low_sales_and_cart_not_bought(self):
        # A third product that is looked at and added to carts but never sold.
        product_c = make_product(name="دیگ سنگی", price=150000)
        for _ in range(10):
            make_event(
                Event.Type.PRODUCT_VIEW, session_key="session-view0001",
                created_at=ago(days=2), product=product_c,
            )
        for _ in range(3):
            make_event(
                Event.Type.ADD_TO_CART, session_key="session-cart0001",
                created_at=ago(days=2), product=product_c,
            )
        products = build_report(self.range)["products"]
        low = {row["product_id"]: row for row in products["low_conversion"]}
        self.assertIn(product_c.pk, low)
        self.assertEqual(low[product_c.pk]["views"], 10)
        self.assertEqual(low[product_c.pk]["sold"], 0)
        # The sold product with the same traffic is NOT flagged.
        self.assertNotIn(self.product_b.pk, low)
        not_bought = {row["product_id"]: row for row in products["cart_not_bought"]}
        self.assertIn(product_c.pk, not_bought)
        self.assertEqual(not_bought[product_c.pk]["gap"], 3)

    def test_best_sellers_and_wishlist(self):
        items = [
            WishlistItem.objects.create(user=self.new_customer, product=self.product_a),
            WishlistItem.objects.create(user=self.returning_customer, product=self.product_a),
        ]
        WishlistItem.objects.filter(pk__in=[item.pk for item in items]).update(
            created_at=ago(days=1),
        )
        products = build_report(self.range)["products"]
        best = {row["product_id"]: row for row in products["best_sellers"]}
        self.assertEqual(best[self.product_a.pk]["qty"], 1)
        self.assertEqual(best[self.product_b.pk]["qty"], 1)
        self.assertEqual(products["most_wishlisted"][0]["product_id"], self.product_a.pk)
        self.assertEqual(products["most_wishlisted"][0]["count"], 2)

    def test_customers_and_coupons(self):
        from apps.discounts.models import Coupon

        coupon = Coupon.objects.create(
            code="OFF10", discount_type=Coupon.DiscountType.PERCENTAGE,
            percentage_value=10,
        )
        order = make_order(
            self.new_customer, self.product_a, created_at=ago(days=1),
            total=90000, subtotal=100000, discount_amount=10000, coupon=coupon,
            item={"unit_price": 100000, "quantity": 1, "total_price": 100000},
        )
        report = build_report(self.range)
        top = report["customers"]["top"]
        self.assertEqual(top[0]["name"], self.returning_customer.get_full_name() or self.returning_customer.username)
        self.assertEqual(report["customers"]["repeat_customers"], 1)
        self.assertEqual(report["customers"]["repeat_rate"], 50)
        self.assertEqual(report["coupons"][0]["code"], "OFF10")
        self.assertEqual(report["coupons"][0]["uses"], 1)
        self.assertEqual(report["coupons"][0]["discount"], 10000)
        self.assertEqual(order.coupon_id, coupon.pk)

    def test_chart_has_one_point_per_day(self):
        chart = build_report(self.range)["chart"]
        self.assertEqual(len(chart["points"]), 30)
        self.assertTrue(chart["has_data"])
        self.assertEqual(sum(point["orders"] for point in chart["points"]), 3)

    def test_query_budget_for_a_90_day_range(self):
        """The page must stay bounded: aggregate queries, no N+1."""
        range_90 = resolve_range({"range": "90"}, now=FIXED)
        # Enough rows that a per-row implementation would explode.
        for index in range(15):
            customer = make_customer(phone=f"+9891711000{index:02d}")
            make_order(
                customer, self.product_a, created_at=ago(days=index + 1),
                    total=100000,
                item={"unit_price": 100000, "quantity": 1, "total_price": 100000},
            )
            make_event(
                Event.Type.PRODUCT_VIEW, session_key=f"budget-session-{index:02d}",
                created_at=ago(days=index + 1), product=self.product_a,
            )
        with CaptureQueriesContext(connection) as captured:
            build_report(range_90)
        self.assertLessEqual(
            len(captured.captured_queries), 30,
            f"reports page ran {len(captured.captured_queries)} queries",
        )


@override_settings(**PLAIN_STATIC)
class ReportPagePermissionTests(TestCase):
    def setUp(self):
        self.url = reverse("admin_reports")

    def _event_perm(self):
        return Permission.objects.get(
            content_type__app_label="analytics", codename="view_event",
        )

    def test_anonymous_is_redirected_to_the_admin_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])

    def test_non_staff_is_403(self):
        customer = make_customer()
        customer.set_password("a-strong-passw0rd!")
        customer.save()
        self.client.force_login(customer)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_staff_without_the_analytics_permission_is_403(self):
        staff = make_staff(permissions=["orders.view_order"], username="rep-noperm",
                           phone="+989171200001")
        self.client.force_login(staff)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_staff_with_the_analytics_permission_sees_only_their_sections(self):
        staff = make_staff(username="rep-ok", phone="+989171200002")
        staff.user_permissions.add(self._event_perm())
        staff = type(staff).objects.get(pk=staff.pk)
        self.client.force_login(staff)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("گزارش‌ها و تحلیل", html)
        # No orders permission -> no summary/funnel/abandoned headings.
        self.assertNotIn("قیف فروش", html)
        self.assertNotIn("سبدهای رها‌شده", html)
        self.assertIn("جستجوها", html)

    def test_superuser_sees_every_section_with_persian_digits(self):
        owner = make_superuser(username="rep-owner", phone="+989171200003")
        self.client.force_login(owner)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        for heading in (
            "خلاصه", "قیف فروش", "سبدهای رها‌شده", "پرفروش‌ترین‌ها",
            "جستجوهای بی‌نتیجه", "مشتریان برتر", "کوپن‌ها",
        ):
            self.assertIn(heading, html)
        # Persian digits, not ASCII, in the rendered summary.
        self.assertIn("۰", html)
        self.assertNotIn(">0<", html)
        self.assertIn("نسخهٔ چاپی / PDF", html)
        self.assertIn("خروجی اکسل", html)
        self.assertIn("خروجی CSV", html)

    def test_every_section_has_an_empty_state(self):
        owner = make_superuser(username="rep-empty", phone="+989171200004")
        self.client.force_login(owner)
        html = self.client.get(self.url).content.decode()
        for text in (
            "هیچ سفارش یا رویدادی ثبت نشده",
            "هنوز رویدادی برای ساخت قیف",
            "سبد رها‌شده‌ای در این بازه نیست",
            "در این بازه سفارشی ثبت نشده",
            "بازدیدی ثبت نشده",
            "کالای پربازدیدِ کم‌فروش پیدا نشد",
            "همهٔ اقلام سبد به خرید رسیده‌اند",
            "کالایی به علاقه‌مندی اضافه نشده",
            "جستجویی ثبت نشده",
            "هیچ جستجوی بی‌نتیجه‌ای",
            "مشتری خریدی نکرده",
            "سفارشی با استان و شهر ثبت نشده",
            "از کوپنی استفاده نشده",
        ):
            with self.subTest(text=text):
                self.assertIn(text, html)

    def test_print_view_is_standalone_and_rtl(self):
        owner = make_superuser(username="rep-print", phone="+989171200005")
        self.client.force_login(owner)
        response = self.client.get(reverse("admin_reports_print"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('dir="rtl"', html)
        self.assertIn("reports_print.css", html)
        self.assertNotIn('id="cusin-drawer"', html)

    def test_custom_range_from_the_url_is_used(self):
        owner = make_superuser(username="rep-range", phone="+989171200006")
        self.client.force_login(owner)
        response = self.client.get(
            self.url, {"range": "custom", "start": "1405/07/01", "end": "1405/07/10"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("۱۴۰۵/۰۷/۰۱", response.content.decode())

    def test_product_names_use_persian_digits(self):
        owner = make_superuser(username="rep-digits", phone="+989171200008")
        self.client.force_login(owner)
        product = make_product(name="سایز 28 کد 9915")
        make_event(Event.Type.PRODUCT_VIEW, product=product, session_key="digits-session-01")

        html = self.client.get(self.url).content.decode()
        self.assertIn("سایز ۲۸ کد ۹۹۱۵", html)
        self.assertNotIn("سایز 28 کد 9915", html)

    def test_product_names_use_persian_digits_on_the_print_page(self):
        owner = make_superuser(username="rep-digits-print", phone="+989171200009")
        self.client.force_login(owner)
        product = make_product(name="سایز 28 کد 9915")
        make_event(Event.Type.PRODUCT_VIEW, product=product, session_key="digits-session-02")

        html = self.client.get(reverse("admin_reports_print")).content.decode()
        self.assertIn("سایز ۲۸ کد ۹۹۱۵", html)
        self.assertNotIn("سایز 28 کد 9915", html)

    def test_preset_chips_are_all_present(self):
        owner = make_superuser(username="rep-chips", phone="+989171200007")
        self.client.force_login(owner)
        html = self.client.get(self.url).content.decode()
        for _key, label in PRESETS:
            self.assertIn(label, html)
