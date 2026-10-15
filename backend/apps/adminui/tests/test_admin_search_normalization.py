"""
Item 12 -- Persian/Arabic search normalization in the admin, both ways.

The owner's keyboard is not consistent: Arabic yeh «ي» for Persian «ی»,
Arabic kaf «ك» for Persian «ک», Persian/Arabic digits for ASCII ones, and
nim-fasele typed by one person and not the next. Postgres/SQLite compare
codepoints, so each of those used to return «هیچ موردی یافت نشد» for a row
that was plainly there.

Both directions must work:

* normalize the QUERY  -- typing «علي» finds a product stored as «علی»;
* match the DATA tolerantly -- typing «علی» finds a product stored as
  «علي» (we cannot rewrite what is already saved).

Applies to product, order and user search.
"""
from __future__ import annotations

from django.test import TestCase
from django.urls import reverse

from apps.adminui.search import NormalizedSearchMixin, tolerant_pattern, tolerant_q
from apps.orders.models import Order
from apps.products.search import normalize_text

from .helpers import make_product, make_superuser

# Persian yeh, Arabic yeh, alef-maksura -- all one letter to a Persian reader.
PERSIAN_YEH = "ی"
ARABIC_YEH = "ي"
PERSIAN_KAF = "ک"
ARABIC_KAF = "ك"
# Persian digit 5, Arabic-Indic 5, ASCII 5.
PERSIAN_FIVE = "۵"
ARABIC_FIVE = "٥"
ZWNJ = "‌"


class NormalizerUnitTests(TestCase):
    """`normalize_text` is the storefront's -- the admin reuses it, so the
    two can never disagree about what «the same word» means."""

    def test_arabic_letters_normalize_to_persian(self):
        self.assertEqual(normalize_text(ARABIC_YEH), PERSIAN_YEH)
        self.assertEqual(normalize_text(ARABIC_KAF), PERSIAN_KAF)
        self.assertEqual(normalize_text("ى"), PERSIAN_YEH)   # alef-maksura
        self.assertEqual(normalize_text("ة"), "ه")            # ta-marbuta

    def test_digits_normalize_to_ascii(self):
        self.assertEqual(normalize_text(PERSIAN_FIVE), "5")
        self.assertEqual(normalize_text(ARABIC_FIVE), "5")
        self.assertEqual(normalize_text("۰۹۱۲"), "0912")

    def test_invisibles_and_diacritics_are_dropped(self):
        self.assertEqual(normalize_text(f"کتاب{ZWNJ}ها"), "کتابها")
        self.assertEqual(normalize_text("كِتَاب"), "کتاب")


class TolerantPatternTests(TestCase):
    def test_digits_become_one_class(self):
        pattern = tolerant_pattern("5")
        for variant in ("5", PERSIAN_FIVE, ARABIC_FIVE):
            self.assertIn(variant, pattern)

    def test_yeh_and_kaf_become_classes(self):
        self.assertIn(ARABIC_YEH, tolerant_pattern("ی"))
        self.assertIn(PERSIAN_YEH, tolerant_pattern(ARABIC_YEH))
        self.assertIn(ARABIC_KAF, tolerant_pattern("ک"))

    def test_a_plain_latin_query_needs_no_regex(self):
        """No ambiguity -> the caller keeps using fast icontains."""
        self.assertEqual(tolerant_pattern("kettle"), "")
        self.assertIsNone(tolerant_q(("name",), "kettle"))

    def test_the_pattern_matches_every_spelling(self):
        import re

        pattern = tolerant_pattern("کتاب")
        for spelling in ("کتاب", "كتاب", f"ك{ZWNJ}تاب", "كِتَاب"):
            self.assertTrue(
                re.search(pattern, spelling), f"{spelling!r} should match {pattern!r}"
            )

    def test_empty_and_blank_queries_are_ignored(self):
        self.assertIsNone(tolerant_q(("name",), ""))
        self.assertIsNone(tolerant_q((), "کتاب"))

    def test_prefixes_are_honoured(self):
        clause = tolerant_q(("^name", "=sku"), "کتاب")
        self.assertIsNotNone(clause)
        self.assertIn("name__iexact", str(clause))


class AdminSessionMixin:
    """Logs a superuser into the test client as ``self.user``."""

    def log_in_as_admin(self):
        self.user = make_superuser()
        self.client.force_login(self.user)
        return self.user


class ProductSearchTests(AdminSessionMixin, TestCase):
    url = reverse("admin:products_product_changelist")

    def setUp(self):
        self.log_in_as_admin()

    def _pks(self, term):
        response = self.client.get(self.url, {"q": term})
        self.assertEqual(response.status_code, 200)
        return list(response.context["cl"].queryset.values_list("pk", flat=True))

    def test_arabic_query_finds_a_persian_product(self):
        product = make_product(name="کتری استیل")
        self.assertEqual(self._pks("كتري"), [product.pk])

    def test_persian_query_finds_an_arabic_product(self):
        """The other direction: what is STORED is the odd spelling."""
        product = make_product(name="كتري استيل")
        self.assertEqual(self._pks("کتری"), [product.pk])

    def test_yeh_variants_are_interchangeable(self):
        product = make_product(name="ظروف چینی")
        self.assertEqual(self._pks("چيني"), [product.pk])
        self.assertEqual(self._pks("چیني"), [product.pk])

    def test_persian_digits_find_an_ascii_sku(self):
        product = make_product(name="ست ۵ پارچه", sku="SKU-12345")
        self.assertEqual(self._pks("SKU-۱۲۳۴۵"), [product.pk])
        self.assertEqual(self._pks("SKU-12345"), [product.pk])

    def test_ascii_digits_find_a_persian_sku(self):
        product = make_product(name="ست پنج پارچه", sku="SKU-۵۲۳")
        self.assertEqual(self._pks("523"), [product.pk])

    def test_nim_fasele_is_optional(self):
        product = make_product(name=f"کتاب{ZWNJ}های آشپزی")
        self.assertEqual(self._pks("کتابهای"), [product.pk])
        self.assertEqual(self._pks(f"کتاب{ZWNJ}های"), [product.pk])

    def test_a_plain_search_still_works_and_still_narrows(self):
        make_product(name="کتری استیل")
        make_product(name="قابلمه")
        self.assertEqual(len(self._pks("کتری")), 1)
        # Nothing ambiguous in an English query -- the normal path.
        other = make_product(name="Kettle Deluxe")
        self.assertEqual(self._pks("Deluxe"), [other.pk])

    def test_a_nonsense_query_still_finds_nothing(self):
        make_product(name="کتری استیل")
        self.assertEqual(self._pks("هیچچیزی"), [])


class OrderSearchTests(AdminSessionMixin, TestCase):
    url = reverse("admin:orders_order_changelist")

    def setUp(self):
        self.log_in_as_admin()

    def _pks(self, term):
        response = self.client.get(self.url, {"q": term})
        self.assertEqual(response.status_code, 200)
        return list(response.context["cl"].queryset.values_list("pk", flat=True))

    def test_customer_phone_with_persian_digits_finds_the_order(self):
        from apps.adminui.tests.helpers import make_order

        order = make_order()
        order.shipping_phone = "09123456789"
        order.save(update_fields=["shipping_phone"])
        self.assertEqual(self._pks("۰۹۱۲۳۴۵۶۷۸۹"), [order.pk])
        self.assertEqual(self._pks("09123456789"), [order.pk])

    def test_tracking_code_typed_with_arabic_kaf(self):
        """Order search covers the shipping phone and the tracking code."""
        from apps.adminui.tests.helpers import make_order

        order = make_order()
        order.tracking_code = "كد-1234"
        order.save(update_fields=["tracking_code"])
        self.assertEqual(self._pks("کد"), [order.pk])

    def test_order_number_search_is_unaffected(self):
        from apps.adminui.tests.helpers import make_order

        order = make_order()
        self.assertEqual(self._pks(order.order_number), [order.pk])
        self.assertEqual(self._pks("CG-DOES-NOT-EXIST"), [])

    def test_the_changelist_still_renders(self):
        from apps.adminui.tests.helpers import make_order

        make_order()
        response = self.client.get(self.url, {"q": "كبري"})
        self.assertEqual(response.status_code, 200)


class UserSearchTests(AdminSessionMixin, TestCase):
    url = reverse("admin:accounts_user_changelist")

    def setUp(self):
        self.log_in_as_admin()

    def _pks(self, term):
        response = self.client.get(self.url, {"q": term})
        self.assertEqual(response.status_code, 200)
        return list(response.context["cl"].queryset.values_list("pk", flat=True))

    def test_a_phone_with_persian_digits_finds_the_user(self):
        from apps.accounts.tests.helpers import make_user

        user = make_user(phone="09123456789")
        self.assertEqual(self._pks("۰۹۱۲۳۴۵۶۷۸۹"), [user.pk])
        self.assertEqual(self._pks("09123456789"), [user.pk])

    def test_a_name_spelled_with_arabic_yeh(self):
        from apps.accounts.tests.helpers import make_user

        user = make_user(phone="+989123456780", first_name="علي", last_name="رضايي")
        self.assertEqual(self._pks("علی"), [user.pk])
        self.assertEqual(self._pks("رضایی"), [user.pk])

    def test_the_superuser_can_still_be_found_by_username(self):
        response = self.client.get(self.url, {"q": self.user.get_username()})
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.user.pk, response.context["cl"].queryset.values_list("pk", flat=True))




class WiringTests(TestCase):
    """The mixin is actually installed on the three admins it must serve."""

    def test_product_admin_is_normalized(self):
        from apps.products.admin import ProductAdmin

        self.assertTrue(issubclass(ProductAdmin, NormalizedSearchMixin))

    def test_order_admin_is_normalized(self):
        from apps.orders.admin import OrderAdmin

        self.assertTrue(issubclass(OrderAdmin, NormalizedSearchMixin))

    def test_user_admin_is_normalized(self):
        from apps.accounts.admin import UserAdmin

        self.assertTrue(issubclass(UserAdmin, NormalizedSearchMixin))

    def test_a_backend_without_regexp_falls_back_to_djangos_search(self):
        """No REGEXP function, or a pattern the backend rejects -> Django's
        own search, never a 500 on the page the owner is looking at."""
        from django.db.utils import DatabaseError

        from apps.products.models import Product

        class NoRegexp:
            """A queryset whose every filter() call is rejected."""

            def filter(self, *args, **kwargs):
                raise DatabaseError("no such function: REGEXP")

        class Base:
            def get_search_results(self, request, queryset, search_term):
                return ("fell-back", False)

        class Impl(NormalizedSearchMixin, Base):
            model = Product
            opts = Product._meta

            def get_search_fields(self, request):
                return ("name",)

        self.assertEqual(
            Impl().get_search_results(None, NoRegexp(), "کتاب")[0], "fell-back"
        )
