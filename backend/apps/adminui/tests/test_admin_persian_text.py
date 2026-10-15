"""
Item 15 -- English and broken text in the admin.

The panel is Persian; the leftovers below were not. Most are Django's own
strings (field names it derives from a model that declares no
verbose_name, or translations that do not survive an English sentence
shape), and a few are ours.

Checked here:
* Persian labels for Address (province, پیش‌فرض, phone), the User list
  (ایمیل، تلفن), the Payment list (شماره سفارش، مشتری، درگاه), WishlistItem
  (محصول، تاریخ افزودن) and the Cart list (تعداد اقلام);
* the auto-generated «Webp 400/800/1200» fields are read-only with
  Persian labels, and the upload field says the recommended size;
* the review bulk actions are Persian;
* NotificationLog shows «تأیید سفارش», not «order_confirmed»;
* django-otp's models are named in Persian;
* the product FORM says «کد کالا (SKU)»;
* the brand filter offers «بدون برند» instead of a bare «-»;
* the bulk delete action reads «حذف موارد انتخاب‌شده»;
* Latin digits in the admin's own chrome (result count, page numbers,
  selection counter, search results, the dashboard clock) are Persian;
* neither help text speaks developer English («escape»، «checkout»).
"""
from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings
from django.contrib import admin
from django.test import TestCase
from django.urls import reverse

from .helpers import make_order, make_product, make_superuser

PERSIAN = re.compile(r"[\u0600-\u06FF]")
# ASCII digits: the admin must not count in them.
ASCII_DIGITS = re.compile(r"[0-9]")


def visible(html: str) -> str:
    """Roughly what the owner reads: no scripts, no styles, no attributes."""
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(text.split())


class _AdminTests(TestCase):
    def setUp(self):
        self.admin = make_superuser()
        self.client.force_login(self.admin)

    def get_text(self, url: str, **params) -> str:
        response = self.client.get(url, params)
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def assert_persian(self, text: str, where: str) -> None:
        self.assertRegex(text, PERSIAN, f"{where} has no Persian at all")


class ModelLabelTests(_AdminTests):
    """Field-level verbose_names (they surface in BOTH the form and the
    changelist header, so one fix covers both)."""

    def labels_of(self, model, *fields):
        return {
            name: str(model._meta.get_field(name).verbose_name) for name in fields
        }

    def test_address_province_and_is_default_are_persian(self):
        from apps.accounts.models import Address

        labels = self.labels_of(Address, "province", "is_default", "phone")
        self.assertEqual(labels["province"], "استان")
        self.assertEqual(labels["is_default"], "پیش‌فرض")
        self.assertEqual(labels["phone"], "تلفن")

    def test_the_address_form_shows_those_labels(self):
        html = self.get_text(reverse("admin:accounts_address_add"))
        self.assertIn("استان", html)
        self.assertIn("پیش‌فرض", html)
        for english in ("Province", "Is default"):
            self.assertNotIn(english, html)

    def test_user_email_and_phone_are_persian(self):
        from django.contrib.auth import get_user_model

        labels = self.labels_of(get_user_model(), "email", "phone")
        self.assertEqual(labels["email"], "ایمیل")
        self.assertEqual(labels["phone"], "تلفن")

    def test_the_user_list_shows_those_labels(self):
        html = self.get_text(reverse("admin:accounts_user_changelist"))
        self.assertIn("ایمیل", html)
        self.assertIn("تلفن", html)
        for english in ("Email address", ">Phone<"):
            self.assertNotIn(english, html)

    def test_wishlist_columns_are_persian(self):
        from apps.wishlist.models import WishlistItem

        labels = self.labels_of(WishlistItem, "product", "created_at")
        self.assertEqual(labels["product"], "محصول")
        self.assertEqual(labels["created_at"], "تاریخ افزودن")

    def test_the_wishlist_list_shows_those_labels(self):
        from apps.wishlist.models import WishlistItem

        WishlistItem.objects.create(user=self.admin, product=make_product())
        html = self.get_text(reverse("admin:wishlist_wishlistitem_changelist"))
        self.assertIn("محصول", html)
        self.assertIn("تاریخ افزودن", html)
        for english in (">Product<", "Created at"):
            self.assertNotIn(english, html)

    def test_the_cart_list_says_how_many_items_in_persian(self):
        from apps.cart.models import Cart

        Cart.objects.create(user=self.admin)
        html = self.get_text(reverse("admin:cart_cart_changelist"))
        self.assertIn("تعداد اقلام", html)
        self.assertNotIn(">Items<", html)


class PaymentListTests(_AdminTests):
    def test_the_payment_columns_are_persian(self):
        from apps.payments.models import Payment

        order = make_order()
        Payment.objects.create(
            order=order, amount=order.total, status=Payment.Status.SUCCESS,
            gateway="zarinpal", gateway_transaction_id="TX-1",
        )
        html = self.get_text(reverse("admin:payments_payment_changelist"))
        for label in ("شماره سفارش", "مشتری", "درگاه", "مبلغ", "وضعیت"):
            self.assertIn(label, html)
        for english in ("Order number", "Customer", "Gateway"):
            self.assertNotIn(english, html)


class BannerFormTests(_AdminTests):
    url = reverse("admin:banners_banner_add")

    def test_the_webp_fields_are_not_editable(self):
        html = self.get_text(self.url)
        # no writable input for them -- only the read-only display
        for name in ("webp_400", "webp_800", "webp_1200"):
            self.assertNotIn(f'name="{name}"', html)
        self.assertNotIn("Webp 400", html)
        self.assertNotIn("Webp 800", html)
        self.assertNotIn("Webp 1200", html)

    def test_the_webp_variants_are_shown_readonly_in_persian(self):
        html = self.get_text(self.url)
        for label in ("نسخهٔ WebP پهنای ۴۰۰ پیکسل", "نسخهٔ WebP پهنای ۸۰۰ پیکسل",
                      "نسخهٔ WebP پهنای ۱۲۰۰ پیکسل"):
            self.assertIn(label, html)

    def test_the_image_field_says_the_recommended_size(self):
        html = self.get_text(self.url)
        self.assertIn("اندازهٔ پیشنهادی", html)
        self.assertIn("۱۲۰۰×۵۰۰", html)


class BrandFormTests(_AdminTests):
    def test_the_brand_tile_form_matches_the_banner_one(self):
        html = self.get_text(reverse("admin:products_brand_add"))
        for name in ("webp_400", "webp_800", "webp_1200"):
            self.assertNotIn(f'name="{name}"', html)
        self.assertNotIn("Webp 400", html)
        self.assertIn("اندازهٔ پیشنهادی", html)


class ReviewActionTests(_AdminTests):
    def _descriptions(self):
        from apps.reviews.admin import ReviewAdmin

        out = []
        for item in ReviewAdmin.actions:
            name = item if isinstance(item, str) else item.__name__
            fn = getattr(ReviewAdmin, name)
            out.append(
                getattr(fn, "short_description", None)
                or getattr(fn, "description", None)
            )
        return out

    def test_the_bulk_actions_are_persian(self):
        descriptions = self._descriptions()
        self.assertIn("تأیید نظرات انتخاب‌شده", descriptions)
        self.assertIn("رد نظرات انتخاب‌شده", descriptions)
        for english in ("Approve selected reviews", "Reject selected reviews"):
            self.assertNotIn(english, descriptions)

    def test_the_review_changelist_offers_them(self):
        # Django only renders the actions bar when the list has a row.
        from apps.reviews.models import Review

        Review.objects.create(
            product=make_product(), user=self.admin, rating=4,
            title="خوب", body="بدک نبود", status=Review.Status.PENDING,
        )
        html = self.get_text(reverse("admin:reviews_review_changelist"))
        self.assertIn("تأیید نظرات انتخاب‌شده", html)
        self.assertIn("رد نظرات انتخاب‌شده", html)


class NotificationEventTests(_AdminTests):
    def test_the_event_column_is_persian_not_a_machine_code(self):
        from apps.notifications.models import NotificationLog
        from apps.notifications.services import Events

        NotificationLog.objects.create(
            event=Events.ORDER_CONFIRMED,
            channel=NotificationLog.Channel.SMS,
            status=NotificationLog.Status.SENT,
            recipient_masked="0912***6789",
        )
        html = self.get_text(
            reverse("admin:notifications_notificationlog_changelist")
        )
        self.assertIn("تأیید سفارش", html)
        # The code legitimately stays in the filter's URL -- it must not
        # appear in the text the owner reads.
        self.assertNotIn("order_confirmed", visible(html))

    def test_every_event_code_has_a_persian_label(self):
        from apps.notifications.services import EVENT_LABELS, Events

        codes = [
            value for name, value in vars(Events).items()
            if name.isupper() and isinstance(value, str)
        ]
        self.assertTrue(codes)
        for code in codes:
            with self.subTest(code=code):
                self.assertRegex(EVENT_LABELS[code], PERSIAN)


class OtpNamingTests(_AdminTests):
    def test_the_otp_models_are_named_in_persian(self):
        from django_otp.plugins.otp_static.models import StaticDevice
        from django_otp.plugins.otp_totp.models import TOTPDevice

        for model in (StaticDevice, TOTPDevice):
            with self.subTest(model=model.__name__):
                self.assertRegex(str(model._meta.verbose_name_plural), PERSIAN)

    def test_the_otp_pages_show_those_names(self):
        static = self.get_text(reverse("admin:otp_static_staticdevice_changelist"))
        totp = self.get_text(reverse("admin:otp_totp_totpdevice_changelist"))
        self.assertNotIn("TOTP devices", totp)
        self.assertNotIn("Static devices", static)
        self.assertIn("کدهای پشتیبان", static)
        self.assertIn("دستگاه‌های کد یک‌بارمصرف", totp)


class ProductSkuLabelTests(_AdminTests):
    def test_the_form_says_what_sku_means(self):
        html = self.get_text(reverse("admin:products_product_add"))
        self.assertIn("کد کالا (SKU)", html)

    def test_the_changelist_header_stays_short(self):
        """Item 10 fits the product table on a 125%-scaled screen, so the
        narrow SKU column keeps the short header."""
        from apps.products.models import Product

        self.assertEqual(Product._meta.get_field("sku").verbose_name, "SKU")


class BrandFilterTests(_AdminTests):
    def test_products_without_a_brand_are_offered_as_a_choice(self):
        from apps.products.models import Brand

        # Django hides a related filter while it has nothing to choose
        # from, so the brand itself has to exist for the choice to show.
        Brand.objects.create(name="برند نمونه", slug="brand-sample")
        make_product(name="بی‌برند")
        html = self.get_text(reverse("admin:products_product_changelist"))
        self.assertIn("بدون برند", html)
        # Django's bare «-» option (its empty-value marker) is gone from
        # this filter's choices.
        block = html[html.find("data-filter-title=\"برند\""):]
        block = block[:block.find("</details>")] if "</details>" in block else block
        self.assertNotIn(">-<", block)


class DeleteActionTests(_AdminTests):
    def test_the_site_action_is_persian_and_not_broken(self):
        from apps.adminui.admin_actions import delete_selected_persian

        self.assertEqual(delete_selected_persian.short_description, "حذف موارد انتخاب‌شده")
        self.assertNotIn("  ", delete_selected_persian.short_description)

    def test_the_product_list_offers_it_without_the_broken_plural(self):
        make_product()
        html = self.get_text(reverse("admin:products_product_changelist"))
        self.assertIn("حذف موارد انتخاب‌شده", html)
        self.assertNotIn("حذف  ", html)
        self.assertNotIn("محصولات های انتخاب شده", html)


class AdminDigitTests(_AdminTests):
    """Django counts in ASCII. The panel must not."""

    def test_the_result_count_is_persian_and_singular(self):
        """«165 محصولات» -> «۱۶۵ محصول»: Persian counts with the singular."""
        for _ in range(3):
            make_product()
        html = self.get_text(reverse("admin:products_product_changelist"))
        text = visible(html)
        self.assertIn("۳ محصول", text)
        self.assertNotIn("3 محصول", text)

    def test_the_page_links_are_persian(self):
        """The theme builds its «صفحهٔ N» menu from these numbers."""
        from apps.products.admin import ProductAdmin

        original = ProductAdmin.list_per_page
        ProductAdmin.list_per_page = 2
        try:
            for _ in range(5):
                make_product()
            html = self.get_text(reverse("admin:products_product_changelist"))
        finally:
            ProductAdmin.list_per_page = original
        self.assertIn('class="this-page"', html)
        links = re.findall(r'<a href="[^"]*p=\d+"[^>]*>([^<]+)</a>', html)
        self.assertTrue(links, "no page links rendered")
        for label in links:
            with self.subTest(label=label):
                self.assertRegex(label, r"^[\u06F0-\u06F9]+$", "page number not Persian")

    def test_the_search_result_count_is_persian(self):
        """Django prints «1 result»; the overridden template counts in
        Persian. (It only prints the count when the list is narrowed, so
        this checks the template contract directly.)"""
        template = (
            Path(settings.BASE_DIR) / "templates" / "admin" / "search_form.html"
        ).read_text(encoding="utf-8")
        self.assertIn("نتیجه", template)
        self.assertIn("numfa", template)
        self.assertNotIn("blocktranslate count", template)

    def test_the_selection_counter_is_persian(self):
        make_product()
        html = self.get_text(reverse("admin:products_product_changelist"))
        self.assertIn("action-counter", html)
        counter = re.search(
            r'<span class="action-counter"[^>]*>([^<]*)</span>', html
        )
        self.assertIsNotNone(counter)
        self.assertIsNone(
            ASCII_DIGITS.search(counter.group(1)),
            f"ASCII digits in the counter: {counter.group(1)!r}",
        )
        self.assertIn("انتخاب شده", counter.group(1))

    def test_the_dashboard_clock_is_persian(self):
        make_order()
        html = self.get_text(reverse("admin:index"))
        match = re.search(r"آخرین به‌روزرسانی اعداد: ([۰-۹:]+)", html)
        self.assertIsNotNone(match, "the dashboard clock is missing")
        self.assertIsNone(ASCII_DIGITS.search(match.group(1)))

    def test_the_theme_converts_the_counters_django_rewrites(self):
        """actions.js replaces the counter text after load; theme.js must
        Persian-ise that copy too."""
        js = (
            Path(settings.BASE_DIR)
            / "static" / "admin_theme" / "js" / "theme.js"
        ).read_text(encoding="utf-8")
        self.assertIn("initPersianDigits", js)
        self.assertIn(".action-counter", js)
        self.assertIn("MutationObserver", js)


class HelpTextTests(TestCase):
    """Help texts are written for the owner, not for the developer."""

    def test_the_gift_message_help_does_not_say_escape(self):
        from apps.orders.models import Order

        help_text = Order._meta.get_field("gift_message").help_text
        self.assertNotIn("escape", help_text.lower())
        self.assertRegex(help_text, PERSIAN)

    def test_the_pickup_address_help_does_not_say_checkout(self):
        from apps.core.models import SiteSettings

        help_text = SiteSettings._meta.get_field("pickup_address").help_text
        self.assertNotIn("checkout", help_text.lower())
        self.assertRegex(help_text, PERSIAN)

    def test_the_user_phone_help_is_persian(self):
        from django.contrib.auth import get_user_model

        help_text = get_user_model()._meta.get_field("phone").help_text
        self.assertRegex(help_text, PERSIAN)
        self.assertNotIn("RegisterSerializer", help_text)
