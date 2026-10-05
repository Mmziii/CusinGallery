"""
Part R5 item 9: complementary products («پیشنهاد همراه»).

Two halves, both tested against REAL behavior:

* rebuild_frequently_bought_together: fed by REAL paid orders created
  through the production checkout + payment-callback flow (never by
  hand-flipping payment_status), so "was paid" is a fact the payment
  path produced.
* ProductDetailSerializer.get_complements via GET /products/<slug>/:
  manual complements win, FBT is the fallback, and in BOTH modes
  inactive or out-of-stock products never appear.
"""
from django.core.management import call_command
from django.urls import reverse
from rest_framework import status

from apps.core.testing import CacheIsolatedAPITestCase
from apps.orders import services as order_services
from apps.payments.gateways.mock import _sign
from apps.payments.services import handle_callback, initiate_payment
from apps.payments.tests.helpers import (
    add_to_cart,
    checkout_payload,
    make_user,
)
from apps.products.models import FrequentlyBoughtTogether

from .helpers import make_product, make_variant

CALLBACK = "http://testserver/api/v1/payments/callback/"


def pay_cart(user, products):
    """Check out `products` and pay through the real mock-gateway flow."""
    for product in products:
        add_to_cart(user, product)
    order = order_services.checkout(user, checkout_payload())
    initiated = initiate_payment(user, order.pk, callback_url=CALLBACK)
    authority = initiated["payment"].gateway_transaction_id
    handle_callback({"authority": authority, "status": "ok", "sig": _sign(authority, "ok")})
    order.refresh_from_db()
    assert order.payment_status == "paid"
    return order


class RebuildFBTCommandTests(CacheIsolatedAPITestCase):
    def pairs(self):
        return {
            (row.product_id, row.complement_id): row.co_count
            for row in FrequentlyBoughtTogether.objects.all()
        }

    def test_paid_multi_item_order_creates_symmetric_pairs(self):
        user = make_user()
        a = make_product(name="A", stock_quantity=10)
        b = make_product(name="B", stock_quantity=10)
        c = make_product(name="C", stock_quantity=10)
        pay_cart(user, [a, b, c])

        call_command("rebuild_frequently_bought_together")

        got = self.pairs()
        self.assertEqual(len(got), 6)  # every unordered pair, both directions
        for x, y in [(a, b), (a, c), (b, c)]:
            self.assertEqual(got[(x.id, y.id)], 1)
            self.assertEqual(got[(y.id, x.id)], 1)

    def test_unpaid_orders_are_ignored(self):
        user = make_user()
        a = make_product(name="A", stock_quantity=10)
        b = make_product(name="B", stock_quantity=10)
        for product in (a, b):
            add_to_cart(user, product)
        order = order_services.checkout(user, checkout_payload())
        self.assertEqual(order.payment_status, "unpaid")

        call_command("rebuild_frequently_bought_together")

        self.assertEqual(FrequentlyBoughtTogether.objects.count(), 0)

    def test_rerun_is_idempotent_and_counts_accumulate_across_orders(self):
        a = make_product(name="A", stock_quantity=20)
        b = make_product(name="B", stock_quantity=20)
        pay_cart(make_user(), [a, b])
        call_command("rebuild_frequently_bought_together")
        first = self.pairs()

        call_command("rebuild_frequently_bought_together")
        self.assertEqual(self.pairs(), first)  # idempotent: no doubling

        pay_cart(make_user(), [a, b])  # a second paid order with the pair
        call_command("rebuild_frequently_bought_together")
        self.assertEqual(self.pairs()[(a.id, b.id)], 2)
        self.assertEqual(self.pairs()[(b.id, a.id)], 2)

    def test_max_per_product_keeps_strongest_pairs(self):
        anchor = make_product(name="Anchor", stock_quantity=30)
        others = [make_product(name=f"P{i}", stock_quantity=10) for i in range(4)]

        # anchor+P0 bought together twice, every other pair once
        pay_cart(make_user(), [anchor, others[0]])
        pay_cart(make_user(), [anchor, others[0]])
        pay_cart(make_user(), [anchor] + others[1:])

        call_command("rebuild_frequently_bought_together", "--max-per-product", "2")

        rows = FrequentlyBoughtTogether.objects.filter(product=anchor).order_by("-co_count")
        self.assertEqual(rows.count(), 2)
        self.assertEqual(rows[0].complement_id, others[0].id)
        self.assertEqual(rows[0].co_count, 2)

    def test_stale_rows_are_cleared_on_rebuild(self):
        a = make_product(name="A", stock_quantity=10)
        b = make_product(name="B", stock_quantity=10)
        stale = FrequentlyBoughtTogether.objects.create(product=a, complement=b, co_count=99)

        call_command("rebuild_frequently_bought_together")  # no paid orders at all

        self.assertEqual(FrequentlyBoughtTogether.objects.count(), 0)
        self.assertFalse(
            FrequentlyBoughtTogether.objects.filter(pk=stale.pk).exists()
        )


class ComplementsAPITests(CacheIsolatedAPITestCase):
    def get_complements(self, product):
        response = self.client.get(reverse("product-detail", args=[product.slug]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return [row["slug"] for row in response.json()["complements"]]

    def test_manual_complements_are_returned(self):
        base = make_product(name="Base", slug="base")
        good = make_product(name="Good", slug="good", stock_quantity=5)
        base.complements.add(good)

        self.assertEqual(self.get_complements(base), ["good"])

    def test_manual_complements_hide_inactive_and_out_of_stock(self):
        base = make_product(name="Base", slug="base")
        inactive = make_product(name="Inactive", slug="inactive", is_active=False, stock_quantity=9)
        empty = make_product(name="Empty", slug="empty", stock_quantity=0)
        good = make_product(name="Good", slug="good", stock_quantity=3)
        base.complements.add(inactive, empty, good)

        self.assertEqual(self.get_complements(base), ["good"])

    def test_variant_stock_counts_as_purchasable(self):
        base = make_product(name="Base", slug="base")
        via_variant = make_product(name="Variant Stocked", slug="variant-stocked", stock_quantity=0)
        make_variant(via_variant, stock_quantity=4)
        base.complements.add(via_variant)

        self.assertEqual(self.get_complements(base), ["variant-stocked"])

    def test_fbt_fallback_when_no_manual_complements(self):
        base = make_product(name="Base", slug="base")
        mined = make_product(name="Mined", slug="mined", stock_quantity=7)
        FrequentlyBoughtTogether.objects.create(product=base, complement=mined, co_count=3)

        self.assertEqual(self.get_complements(base), ["mined"])

    def test_fbt_orders_by_co_count(self):
        base = make_product(name="Base", slug="base")
        weak = make_product(name="Weak", slug="weak", stock_quantity=5)
        strong = make_product(name="Strong", slug="strong", stock_quantity=5)
        FrequentlyBoughtTogether.objects.create(product=base, complement=weak, co_count=1)
        FrequentlyBoughtTogether.objects.create(product=base, complement=strong, co_count=9)

        self.assertEqual(self.get_complements(base), ["strong", "weak"])

    def test_fbt_hides_unpurchasable_complements(self):
        base = make_product(name="Base", slug="base")
        sold_out = make_product(name="Sold out", slug="sold-out", stock_quantity=0)
        FrequentlyBoughtTogether.objects.create(product=base, complement=sold_out, co_count=3)

        self.assertEqual(self.get_complements(base), [])

    def test_manual_wins_over_fbt(self):
        base = make_product(name="Base", slug="base")
        manual = make_product(name="Manual", slug="manual", stock_quantity=2)
        mined = make_product(name="Mined", slug="mined", stock_quantity=2)
        base.complements.add(manual)
        FrequentlyBoughtTogether.objects.create(product=base, complement=mined, co_count=9)

        self.assertEqual(self.get_complements(base), ["manual"])

    def test_no_complements_at_all_returns_empty_list(self):
        base = make_product(name="Base", slug="base")
        self.assertEqual(self.get_complements(base), [])
