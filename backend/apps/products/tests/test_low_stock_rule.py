"""
Item 11 -- ONE low-stock rule: each product's own «آستانهٔ هشدار موجودی کم».

Product.low_stock_threshold (default 5) existed, was editable per product
and was what `pricing.stock_status_for()` used for the storefront's
`stock_status`. Everywhere else -- the admin's «وضعیت موجودی» filter, the
dashboard's «موجودی کم» card, the owner's SMS alert, and the changelist
badge -- the code compared against the GLOBAL `LOW_STOCK_THRESHOLD`
(default 3) instead.

So the same product was «موجودی کم» on the storefront, in its own badge
and in its own `is_low_stock` -- and «موجودی کافی» in the filter the owner
actually uses to restock. Two rules, one number, and the owner could not
tell which one the shop was using.

Now: the global setting is only the default value for a NEW product. Every
comparison is against the product's own field.
"""
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.adminui.dashboard import build_payload
from apps.core.testing import CacheIsolationMixin, frozen_clock
from apps.orders.models import Order
from apps.products.models import Product
from apps.products.pricing import stock_status_for

from ..admin import LowStockFilter
from .helpers import make_product

FROZEN = __import__("datetime").datetime(
    2026, 10, 10, 12, 0,
    tzinfo=__import__("datetime").timezone(
        __import__("datetime").timedelta(hours=3, minutes=30)),
)


class PerProductThresholdTests(TestCase):
    """The model field is the rule; the global setting is only a default."""

    def test_the_default_threshold_is_five(self):
        product = make_product(stock_quantity=99)
        self.assertEqual(product.low_stock_threshold, 5)

    def test_is_low_stock_uses_the_products_own_number(self):
        self.assertTrue(make_product(stock_quantity=8, low_stock_threshold=10).is_low_stock)
        self.assertFalse(make_product(stock_quantity=4, low_stock_threshold=2).is_low_stock)
        self.assertTrue(make_product(stock_quantity=2, low_stock_threshold=2).is_low_stock)

    def test_the_global_setting_does_not_override_an_existing_product(self):
        """LOW_STOCK_THRESHOLD is a default for NEW rows, not a second rule."""
        with override_settings(LOW_STOCK_THRESHOLD=99):
            self.assertFalse(make_product(stock_quantity=8).is_low_stock)
            product = make_product(stock_quantity=8, low_stock_threshold=1)
            self.assertFalse(product.is_low_stock)


class FilterUsesOwnThresholdTests(TestCase):
    url = reverse("admin:products_product_changelist")

    def setUp(self):
        self.admin_user = __import__(
            "apps.accounts.tests.helpers", fromlist=["make_user"]
        ).make_user(phone="+989000040001", password="a-strong-passw0rd!",
                    is_staff=True, is_superuser=True)
        self.client.force_login(self.admin_user)

    def _rows(self, value: str):
        response = self.client.get(self.url, {"low_stock": value})
        self.assertEqual(response.status_code, 200)
        return set(response.context["cl"].queryset.values_list("pk", flat=True))

    def _names(self, value: str):
        return set(
            Product.objects.filter(pk__in=self._rows(value)).values_list("name", flat=True)
        )

    def test_a_product_can_raise_its_own_warning_line(self):
        """Stock 8 is NOT low by default, but is when the owner says 10."""
        strict = make_product(name="ست ظروف", stock_quantity=8, low_stock_threshold=10)
        self.assertEqual(self._names("3"), {"ست ظروف"})
        self.assertIn(strict.pk, self._rows("1"))

    def test_a_product_can_lower_its_own_warning_line(self):
        """Stock 4 IS low by the default 5, but not when the owner says 2."""
        lax = make_product(name="پیش‌بند", stock_quantity=4, low_stock_threshold=2)
        self.assertEqual(self._names("3"), set())
        self.assertEqual(self._names("0"), {"پیش‌بند"})

    def test_the_filter_agrees_with_the_badge_and_the_model(self):
        """The bug: three answers to the same question."""
        products = [
            make_product(name="کتری", stock_quantity=5, low_stock_threshold=5),
            make_product(name="فنجان", stock_quantity=6, low_stock_threshold=5),
            make_product(name="قابلمه", stock_quantity=9, low_stock_threshold=10),
            make_product(name="ماهیتابه", stock_quantity=3, low_stock_threshold=1),
        ]
        low = self._rows("3")   # at/below threshold and above zero
        for product in products:
            with self.subTest(name=product.name):
                self.assertEqual(
                    product.pk in low,
                    product.is_low_stock,
                    f"{product.name}: the filter and is_low_stock disagree",
                )
                self.assertEqual(
                    product.pk in low,
                    stock_status_for(product) == "low_stock",
                    f"{product.name}: the filter and the storefront disagree",
                )

    def test_out_of_stock_is_untouched_by_the_threshold(self):
        """Zero is zero whatever the owner's warning line says."""
        make_product(name="بدون موجودی", stock_quantity=0, low_stock_threshold=50)
        self.assertEqual(self._names("2"), {"بدون موجودی"})
        # ...and it is not counted as merely "low".
        self.assertNotIn("بدون موجودی", self._names("3"))

    def test_the_filter_ignores_the_global_setting(self):
        with override_settings(LOW_STOCK_THRESHOLD=100):
            make_product(name="عادی", stock_quantity=5)   # own threshold 5
            self.assertEqual(self._names("0"), set())     # 5 <= 5 -> low
            self.assertEqual(self._names("3"), {"عادی"})


@override_settings(**{
    "STORAGES": {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    }
})
class DashboardLowStockCardTests(CacheIsolationMixin, TestCase):
    def _count(self):
        with frozen_clock(FROZEN):
            payload = build_payload(14)
        by_id = {card["id"]: card for card in payload["actions"]}
        return by_id["low_stock"]["count"], by_id["low_stock"]["url"]

    def test_the_card_counts_against_each_products_own_threshold(self):
        make_product(stock_quantity=8, low_stock_threshold=10)   # low
        make_product(stock_quantity=4, low_stock_threshold=2)    # not low
        count, _url = self._count()
        self.assertEqual(count, 1)

    def test_the_card_number_matches_the_list_it_links_to(self):
        """The card says N and links to a filtered list -- that list must
        have exactly N rows, or the owner learns not to trust the card."""
        strict = make_product(name="ست", stock_quantity=8, low_stock_threshold=10)
        make_product(name="تک", stock_quantity=4, low_stock_threshold=2)
        count, url = self._count()
        self.assertIn("low_stock=3", url)
        admin = __import__(
            "apps.accounts.tests.helpers", fromlist=["make_user"]
        ).make_user(phone="+989000040002", password="a-strong-passw0rd!",
                    is_staff=True, is_superuser=True)
        self.client.force_login(admin)
        response = self.client.get(url)
        self.assertEqual(response.context["cl"].result_count, count)
        self.assertEqual(count, 1)
        self.assertIn(strict, response.context["cl"].queryset)

    def test_zero_stock_is_never_double_counted(self):
        make_product(stock_quantity=0, low_stock_threshold=5)
        with frozen_clock(FROZEN):
            by_id = {c["id"]: c for c in build_payload(14)["actions"]}
        self.assertEqual(by_id["low_stock"]["count"], 0)
        self.assertEqual(by_id["out_of_stock"]["count"], 1)


class OwnerAlertUsesOwnThresholdTests(CacheIsolationMixin, TestCase):
    """Crossings are detected per product, and the alert says so."""

    def _make_order(self, order_number: str, product, **item_overrides):
        from apps.accounts.tests.helpers import make_user

        user = make_user(phone="+98900004" + str(abs(hash(order_number)) % 1000).zfill(4))
        order = Order.objects.create(
            user=user,
            order_number=order_number,
            status=Order.Status.PENDING,
            payment_status=Order.PaymentStatus.PAID,
            subtotal=product.price,
            total=product.price,
            shipping_recipient_name="سارا احمدی",
            shipping_phone="09121112233",
            shipping_province="تهران",
            shipping_city="تهران",
            shipping_address="خیابان ولیعصر، پلاک ۱۰",
            shipping_postal_code="1234567890",
            shipping_method="standard",
        )
        quantity = item_overrides.pop("quantity", 1)
        order.items.create(
            product=product, product_name=product.name,
            quantity=quantity, unit_price=product.price,
            total_price=product.price * quantity, **item_overrides,
        )
        return order

    def _decrement(self, order):
        """Run the decrement with notify_owner_low_stock replaced by a
        capture, and return the crossings it would have alerted on."""
        import apps.notifications.services as module
        from django.db import transaction

        from apps.orders.inventory import decrement_stock_for_order

        captured = []
        original = module.notify_owner_low_stock
        module.notify_owner_low_stock = lambda o, c: captured.extend(c)
        try:
            with transaction.atomic():
                decrement_stock_for_order(order)
        finally:
            module.notify_owner_low_stock = original
        return captured

    def _crossings(self, stock: int, threshold: int, quantity: int):
        from apps.orders.inventory import decrement_stock_for_order

        product = make_product(stock_quantity=stock, low_stock_threshold=threshold)
        order = self._make_order(
            f"CG-{threshold}-{stock}-{quantity}", product, quantity=quantity
        )
        return self._decrement(order)

    def test_a_product_with_a_high_threshold_alerts_earlier(self):
        # 12 -> 8 with threshold 10: a crossing the global rule (3) missed.
        self.assertEqual(len(self._crossings(12, 10, 4)), 1)

    def test_a_product_with_a_low_threshold_stays_quiet(self):
        # 4 -> 2 with threshold 1: the global rule (3) would have shouted.
        self.assertEqual(len(self._crossings(4, 1, 2)), 0)

    def test_the_alert_names_the_threshold_that_fired(self):
        from apps.notifications.services import _owner_low_stock_text

        text = _owner_low_stock_text("CG-1", [("کتری استیل", 8, 10)])
        self.assertIn("آستانهٔ هشدار این کالا: 10", text)
        self.assertNotIn("آستانه هشدار: 3", text)

    def test_variants_borrow_their_parents_threshold(self):
        """Same fallback as pricing.stock_status_for()."""
        product = make_product(stock_quantity=50, low_stock_threshold=9)
        variant = product.variants.create(sku="V-THRESH-1", stock_quantity=12)
        order = self._make_order("CG-VAR", product, quantity=4, variant=variant)
        captured = self._decrement(order)
        # 12 -> 8, parent threshold 9 -> crossing.
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0][2], 9)


class StockStatusApiTests(TestCase):
    """The storefront rule is already per-product -- lock it in."""

    def test_stock_status_follows_the_products_own_threshold(self):
        self.assertEqual(
            stock_status_for(make_product(stock_quantity=8, low_stock_threshold=10)),
            "low_stock",
        )
        self.assertEqual(
            stock_status_for(make_product(stock_quantity=4, low_stock_threshold=2)),
            "in_stock",
        )
        self.assertEqual(
            stock_status_for(make_product(stock_quantity=0, low_stock_threshold=5)),
            "out_of_stock",
        )
