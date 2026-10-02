"""
Coupon validation/calculation unit tests -- apps.discounts.services
driven directly with cart-view fixtures, covering every rule the schema
models: active state, dates, limits, minimum order, percentage/fixed
discounts, max cap, and product/category scoping.
"""
from django.test import TestCase

from .. import services
from ..models import Coupon
from .helpers import (
    in_future,
    in_past,
    make_cart_view,
    make_category,
    make_coupon,
    make_line,
    make_product,
    make_user,
)


class ValidCouponTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.product = make_product(price=100000)
        self.cart_view = make_cart_view([make_line(self.product, quantity=2)])  # 200000

    def test_percentage_discount_is_computed_server_side(self):
        coupon = make_coupon("SAVE10", percentage_value=10)
        result = services.validate_and_calculate(self.user, "SAVE10", self.cart_view)
        self.assertEqual(result.discount_amount, 20000)  # 10% of 200000
        self.assertEqual(result.eligible_subtotal, 200000)
        self.assertEqual(result.coupon.pk, coupon.pk)

    def test_percentage_discount_respects_maximum_discount_amount(self):
        make_coupon("CAPPED", percentage_value=50, maximum_discount_amount=30000)
        result = services.validate_and_calculate(self.user, "CAPPED", self.cart_view)
        # 50% would be 100000; capped at 30000.
        self.assertEqual(result.discount_amount, 30000)

    def test_fixed_discount(self):
        make_coupon("FLAT", discount_type=Coupon.DiscountType.FIXED, fixed_value=45000)
        result = services.validate_and_calculate(self.user, "FLAT", self.cart_view)
        self.assertEqual(result.discount_amount, 45000)

    def test_fixed_discount_cannot_exceed_eligible_subtotal(self):
        make_coupon("BIGFLAT", discount_type=Coupon.DiscountType.FIXED, fixed_value=999999)
        result = services.validate_and_calculate(self.user, "BIGFLAT", self.cart_view)
        self.assertEqual(result.discount_amount, 200000)

    def test_code_lookup_is_case_insensitive_and_trimmed(self):
        make_coupon("MiXeD10", percentage_value=10)
        result = services.validate_and_calculate(self.user, "  mixed10  ", self.cart_view)
        self.assertEqual(result.discount_amount, 20000)

    def test_unavailable_lines_are_excluded_from_the_base(self):
        available = make_line(self.product, quantity=1)
        unavailable = make_line(make_product(price=50000), quantity=3, is_available=False)
        cart_view = make_cart_view([available, unavailable])
        make_coupon("ONLYAVAIL", percentage_value=10)
        result = services.validate_and_calculate(self.user, "ONLYAVAIL", cart_view)
        self.assertEqual(result.eligible_subtotal, 100000)
        self.assertEqual(result.discount_amount, 10000)


class RejectionTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.product = make_product(price=100000)
        self.cart_view = make_cart_view([make_line(self.product)])

    def _assert_rejected(self, code):
        with self.assertRaises(services.CouponError):
            services.validate_and_calculate(self.user, code, self.cart_view)

    def test_unknown_code_is_rejected(self):
        self._assert_rejected("NOPE")

    def test_empty_code_is_rejected(self):
        self._assert_rejected("   ")

    def test_inactive_coupon_is_rejected_with_generic_message(self):
        make_coupon("DISABLED", is_active=False)
        with self.assertRaises(services.CouponError) as ctx:
            services.validate_and_calculate(self.user, "DISABLED", self.cart_view)
        # Same wording as an unknown code -- no existence/disabled leak.
        self.assertIn("not valid", str(ctx.exception.errors["coupon_code"][0]))

    def test_expired_coupon_is_rejected(self):
        make_coupon("OLD", expiration_date=in_past(days=1))
        self._assert_rejected("OLD")

    def test_not_yet_started_coupon_is_rejected(self):
        make_coupon("FUTURE", start_date=in_future(days=1))
        self._assert_rejected("FUTURE")

    def test_coupon_within_its_window_is_accepted(self):
        make_coupon("WINDOW", start_date=in_past(days=1), expiration_date=in_future(days=1))
        result = services.validate_and_calculate(self.user, "WINDOW", self.cart_view)
        self.assertEqual(result.discount_amount, 10000)


class UsageLimitTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.other = make_user()
        self.product = make_product(price=100000)
        self.cart_view = make_cart_view([make_line(self.product)])

    def test_global_usage_limit_blocks_at_limit(self):
        from ..models import CouponUsage

        coupon = make_coupon("ONCE", usage_limit=1)
        CouponUsage.objects.create(coupon=coupon, user=self.other)

        with self.assertRaises(services.CouponError):
            services.validate_and_calculate(self.user, "ONCE", self.cart_view)

    def test_global_usage_limit_allows_below_limit(self):
        from ..models import CouponUsage

        coupon = make_coupon("TWICE", usage_limit=2)
        CouponUsage.objects.create(coupon=coupon, user=self.other)
        result = services.validate_and_calculate(self.user, "TWICE", self.cart_view)
        self.assertEqual(result.discount_amount, 10000)

    def test_per_user_limit_is_per_user(self):
        from ..models import CouponUsage

        coupon = make_coupon("ONCEPERUSER", per_user_usage_limit=1)
        # Another user already used it -- this user still may.
        CouponUsage.objects.create(coupon=coupon, user=self.other)
        result = services.validate_and_calculate(self.user, "ONCEPERUSER", self.cart_view)
        self.assertEqual(result.discount_amount, 10000)

        # ...but not twice.
        CouponUsage.objects.create(coupon=coupon, user=self.user)
        with self.assertRaises(services.CouponError):
            services.validate_and_calculate(self.user, "ONCEPERUSER", self.cart_view)


class MinimumOrderTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.product = make_product(price=100000)

    def test_below_minimum_is_rejected(self):
        make_coupon("MIN500K", minimum_order_amount=500000)
        cart_view = make_cart_view([make_line(self.product, quantity=2)])  # 200000
        with self.assertRaises(services.CouponError) as ctx:
            services.validate_and_calculate(self.user, "MIN500K", cart_view)
        self.assertIn("minimum", str(ctx.exception.errors["coupon_code"][0]))

    def test_at_or_above_minimum_is_accepted(self):
        make_coupon("MIN100K", minimum_order_amount=100000)
        cart_view = make_cart_view([make_line(self.product)])
        result = services.validate_and_calculate(self.user, "MIN100K", cart_view)
        self.assertEqual(result.discount_amount, 10000)


class ScopingTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.cat_a = make_category()
        self.cat_b = make_category()
        self.product_a = make_product(category=self.cat_a, price=100000)
        self.product_b = make_product(category=self.cat_b, price=60000)

    def test_product_scoped_coupon_applies_only_to_matching_lines(self):
        coupon = make_coupon("PRODA", percentage_value=10)
        coupon.applicable_products.add(self.product_a)

        cart_view = make_cart_view([make_line(self.product_a), make_line(self.product_b)])
        result = services.validate_and_calculate(self.user, "PRODA", cart_view)
        self.assertEqual(result.eligible_subtotal, 100000)
        self.assertEqual(result.discount_amount, 10000)

    def test_category_scoped_coupon_applies_to_matching_category_only(self):
        coupon = make_coupon("CATA", percentage_value=10)
        coupon.applicable_categories.add(self.cat_a)

        cart_view = make_cart_view([make_line(self.product_a), make_line(self.product_b)])
        result = services.validate_and_calculate(self.user, "CATA", cart_view)
        self.assertEqual(result.eligible_subtotal, 100000)
        self.assertEqual(result.discount_amount, 10000)

    def test_category_scope_includes_descendant_categories(self):
        child = make_category(parent=self.cat_a)
        grandchild = make_category(parent=child)
        deep_product = make_product(category=grandchild, price=80000)

        coupon = make_coupon("CATADEEP", percentage_value=10)
        coupon.applicable_categories.add(self.cat_a)

        cart_view = make_cart_view([make_line(deep_product), make_line(self.product_b)])
        result = services.validate_and_calculate(self.user, "CATADEEP", cart_view)
        self.assertEqual(result.eligible_subtotal, 80000)
        self.assertEqual(result.discount_amount, 8000)

    def test_scoped_coupon_with_no_matching_lines_is_rejected(self):
        coupon = make_coupon("ONLYB", percentage_value=10)
        coupon.applicable_products.add(self.product_b)

        cart_view = make_cart_view([make_line(self.product_a)])
        with self.assertRaises(services.CouponError):
            services.validate_and_calculate(self.user, "ONLYB", cart_view)

    def test_minimum_order_uses_eligible_subtotal_for_scoped_coupons(self):
        coupon = make_coupon("SCOPEDMIN", percentage_value=10, minimum_order_amount=90000)
        coupon.applicable_products.add(self.product_b)  # eligible = 60000 only

        cart_view = make_cart_view(
            [make_line(self.product_a), make_line(self.product_b)]  # subtotal 160000
        )
        with self.assertRaises(services.CouponError):
            services.validate_and_calculate(self.user, "SCOPEDMIN", cart_view)
