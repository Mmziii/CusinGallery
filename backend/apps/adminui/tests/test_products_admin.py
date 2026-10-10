"""B4: products changelist inline editing (same validation as the form),
duplicate action, bulk percentage price change (preview / apply /
rollback / CSV / permissions) and the enhanced change form assets.
"""
from unittest import mock

from django.contrib.admin.models import LogEntry
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.products.models import Product

from .helpers import PLAIN_STATIC, make_product, make_staff, make_superuser

CHANGELIST = "admin:products_product_changelist"
PERCENT_URL = "admin:products_product_price_percent"


def formset_prefix_fields():
    return {
        "form-TOTAL_FORMS": "1",
        "form-INITIAL_FORMS": "1",
        "form-MIN_NUM_FORMS": "0",
        "form-MAX_NUM_FORMS": "1000",
    }


@override_settings(**PLAIN_STATIC)
class ProductListEditableTests(TestCase):
    maxDiff = None

    def setUp(self):
        self.admin = make_superuser(username="prodowner", phone="+989000030001")
        self.client.force_login(self.admin)
        self.product = make_product(
            name="ماهی‌تابه", price=100000, compare_at_price=120000,
            stock_quantity=5,
        )

    def test_changelist_renders_editable_inputs(self):
        response = self.client.get(reverse(CHANGELIST))
        html = response.content.decode()
        self.assertIn("form-0-price", html)
        self.assertIn("form-0-stock_quantity", html)
        self.assertIn("form-0-is_active", html)
        # the name cell stays the row link
        self.assertIn(reverse("admin:products_product_change", args=[self.product.pk]), html)

    def _post_row(self, **overrides):
        data = formset_prefix_fields()
        data.update({
            "form-0-id": str(self.product.pk),
            "form-0-price": str(self.product.price),
            "form-0-compare_at_price": (
                "" if self.product.compare_at_price is None
                else str(self.product.compare_at_price)
            ),
            "form-0-stock_quantity": str(self.product.stock_quantity),
        })
        if self.product.is_active:
            data["form-0-is_active"] = "on"
        if self.product.is_featured:
            data["form-0-is_featured"] = "on"
        data.update(overrides)
        data["_save"] = "ذخیره"
        return self.client.post(reverse(CHANGELIST), data)

    def test_inline_save_updates_values(self):
        response = self._post_row(**{
            "form-0-price": "250000",
            "form-0-compare_at_price": "300000",
            "form-0-stock_quantity": "8",
        })
        self.assertEqual(response.status_code, 302)
        self.product.refresh_from_db()
        self.assertEqual(self.product.price, 250000)
        self.assertEqual(self.product.compare_at_price, 300000)
        self.assertEqual(self.product.stock_quantity, 8)

    def test_inline_save_rejects_compare_below_price_like_the_form(self):
        """The changelist must enforce exactly the change form's rule."""
        response = self._post_row(**{
            "form-0-price": "100000",
            "form-0-compare_at_price": "5",
        })
        self.assertEqual(response.status_code, 200)  # redisplayed with errors
        self.assertIn(
            "قیمت قبل از تخفیف نمی‌تواند کمتر از قیمت فروش باشد",
            response.content.decode(),
        )
        self.product.refresh_from_db()
        self.assertEqual(self.product.price, 100000)  # nothing saved

    def test_inline_save_rejects_invalid_number(self):
        response = self._post_row(**{"form-0-price": "نهصد"})
        self.assertEqual(response.status_code, 200)
        self.product.refresh_from_db()
        self.assertEqual(self.product.price, 100000)

    def test_stock_filters_legacy_and_new(self):
        # threshold is LOW_STOCK_THRESHOLD=3 by default
        make_product(name="کتری", stock_quantity=0)     # out
        make_product(name="فنجان", stock_quantity=2)    # low, in stock
        # self.product has stock 5 -> above threshold
        url = reverse(CHANGELIST)
        r = self.client.get(url, {"low_stock": "1"})   # legacy: <= threshold
        self.assertEqual(r.context["cl"].result_count, 2)
        r = self.client.get(url, {"low_stock": "2"})   # new: exactly zero
        self.assertEqual(r.context["cl"].result_count, 1)
        r = self.client.get(url, {"low_stock": "3"})   # new: low but in stock
        self.assertEqual(r.context["cl"].result_count, 1)
        r = self.client.get(url, {"low_stock": "0"})   # legacy: above threshold
        self.assertEqual(r.context["cl"].result_count, 1)

    def test_has_image_filter(self):
        url = reverse(CHANGELIST)
        r = self.client.get(url, {"has_image": "0"})
        self.assertEqual(r.context["cl"].result_count, 1)
        r = self.client.get(url, {"has_image": "1"})
        self.assertEqual(r.context["cl"].result_count, 0)

    def test_stock_badge_rendered(self):
        make_product(name="کتری", stock_quantity=0)
        html = self.client.get(reverse(CHANGELIST)).content.decode()
        self.assertIn("cusin-badge", html)
        self.assertIn("ناموجود", html)


@override_settings(**PLAIN_STATIC)
class DuplicateProductTests(TestCase):
    maxDiff = None

    def setUp(self):
        self.admin = make_superuser(username="dupowner", phone="+989000030002")
        self.client.force_login(self.admin)
        self.product = make_product(
            name="قابلمه گرانیتی", slug="ghablame-granite", sku="GRN-1",
            price=850000, compare_at_price=900000, short_description="کوتاه",
        )
        self.complement = make_product(name="قاشق", slug="spoon", sku="SPN-1")
        self.product.complements.add(self.complement)

    def _run_action(self, client=None, products=None):
        client = client or self.client
        return client.post(
            reverse(CHANGELIST),
            {
                "action": "duplicate_product",
                "_selected_action": [str(p.pk) for p in products or [self.product]],
                "select_across": "0",
            },
            follow=True,
        )

    def test_duplicate_creates_inactive_copy_with_unique_suffixes(self):
        self.assertEqual(Product.objects.count(), 2)
        self._run_action()
        self.assertEqual(Product.objects.count(), 3)
        copy = Product.objects.exclude(pk__in=[self.product.pk, self.complement.pk]).get()
        self.assertFalse(copy.is_active)
        self.assertEqual(copy.name, "قابلمه گرانیتی (کپی)")
        self.assertEqual(copy.slug, "ghablame-granite-copy")
        self.assertEqual(copy.sku, "GRN-1-copy")
        self.assertEqual(copy.price, self.product.price)
        self.assertEqual(copy.compare_at_price, self.product.compare_at_price)
        self.assertEqual(list(copy.complements.values_list("pk", flat=True)),
                         [self.complement.pk])
        # images and variants are NOT copied (by design)
        self.assertEqual(copy.images.count(), 0)
        self.assertEqual(copy.variants.count(), 0)
        # audit trail
        self.assertTrue(
            LogEntry.objects.filter(object_id=str(copy.pk)).exists()
        )

    def test_duplicate_twice_gets_numbered_suffixes(self):
        self._run_action()
        self._run_action()
        self.assertEqual(Product.objects.count(), 4)
        names = set(Product.objects.values_list("name", flat=True))
        self.assertIn("قابلمه گرانیتی (کپی)", names)
        self.assertIn("قابلمه گرانیتی (کپی ۲)", names)
        skus = set(Product.objects.values_list("sku", flat=True))
        self.assertIn("GRN-1-copy", skus)
        self.assertIn("GRN-1-copy-2", skus)

    def test_duplicate_requires_add_permission(self):
        staff = make_staff(
            permissions=["products.view_product", "products.change_product"],
            username="+989000031001", phone="+989000031001",
        )
        self.client.force_login(staff)
        response = self._run_action()
        self.assertEqual(Product.objects.count(), 2)  # nothing copied
        self.assertIn(
            "برای کپی محصول به دسترسی «افزودن محصول» نیاز دارید",
            response.content.decode(),
        )


@override_settings(**PLAIN_STATIC)
class PricePercentTests(TestCase):
    maxDiff = None

    def setUp(self):
        self.admin = make_superuser(username="pctowner", phone="+989000030003")
        self.client.force_login(self.admin)
        # sku order decides row order in the flow
        self.p1 = make_product(name="کتری", slug="kettle", sku="KT-1",
                               price=690000, compare_at_price=800000)
        self.p2 = make_product(name="قوری", slug="teapot", sku="KT-2",
                               price=1050, compare_at_price=None)

    def _step1(self):
        """The changelist action confirmation page (step 1)."""
        return self.client.post(
            reverse(CHANGELIST),
            {
                "action": "change_price_percentage",
                "_selected_action": [str(self.p1.pk), str(self.p2.pk)],
                "select_across": "0",
            },
        )

    def test_step1_renders_form_with_ids_and_roundings(self):
        response = self._step1()
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("تغییر درصدی قیمت", html)
        self.assertIn(f"{self.p1.pk},{self.p2.pk}", html)
        self.assertIn("گرد به ۱۰۰ تومان", html)
        self.assertIn("admin_theme/css/theme.css", html)  # themed shell

    def _preview(self, percent="10", rounding="none", ids=None, extra=None):
        data = {
            "ids": ids if ids is not None else f"{self.p1.pk},{self.p2.pk}",
            "percent": percent,
            "rounding": rounding,
        }
        if extra:
            data.update(extra)
        return self.client.post(reverse(PERCENT_URL), data)

    def test_preview_shows_before_after_without_writing(self):
        response = self._preview()
        self.assertEqual(response.status_code, 200)
        rows = response.context["rows"]
        self.assertEqual(len(rows), 2)
        by_sku = {r["product"].sku: r for r in rows}
        self.assertEqual(by_sku["KT-1"]["price_after"], 759000)   # +10%
        self.assertEqual(by_sku["KT-1"]["compare_after"], 880000)
        self.assertEqual(by_sku["KT-2"]["price_after"], 1155)     # 1050*1.1
        self.assertIsNone(by_sku["KT-2"]["compare_after"])
        self.p1.refresh_from_db()
        self.assertEqual(self.p1.price, 690000)  # nothing applied yet

    def test_preview_displays_plus_sign_for_positive_percent(self):
        response = self._preview()
        self.assertIn("+۱۰٪", response.content.decode())

    def test_rounding_modes(self):
        rows = self._preview(percent="10", rounding="100").context["rows"]
        by_sku = {r["product"].sku: r for r in rows}
        self.assertEqual(by_sku["KT-1"]["price_after"], 759000)  # already multiple
        self.assertEqual(by_sku["KT-2"]["price_after"], 1200)    # 1155 -> 1200
        rows = self._preview(percent="10", rounding="1000").context["rows"]
        by_sku = {r["product"].sku: r for r in rows}
        self.assertEqual(by_sku["KT-2"]["price_after"], 1000)    # 1155 -> 1000

    def test_negative_percent(self):
        rows = self._preview(percent="-50", rounding="none").context["rows"]
        by_sku = {r["product"].sku: r for r in rows}
        self.assertEqual(by_sku["KT-1"]["price_after"], 345000)

    def test_persian_digits_accepted(self):
        rows = self._preview(percent="۱۰", rounding="none").context["rows"]
        by_sku = {r["product"].sku: r for r in rows}
        self.assertEqual(by_sku["KT-1"]["price_after"], 759000)

    def test_compare_stays_above_price_after_scaling(self):
        """1000 -> 1100 vs 1001 -> 1100 after rounding: still valid."""
        self.p2.price = 1000
        self.p2.compare_at_price = 1001
        self.p2.save(update_fields=["price", "compare_at_price"])
        response = self._preview(
            percent="10", rounding="100", ids=f"{self.p2.pk}"
        )
        row = response.context["rows"][0]
        self.assertEqual(row["price_after"], 1100)
        self.assertEqual(row["compare_after"], 1100)
        response = self._preview(
            percent="10", rounding="100", ids=f"{self.p2.pk}",
            extra={"apply": "1"},
        )
        self.assertEqual(response.status_code, 302)  # full_clean passes
        self.p2.refresh_from_db()
        self.assertEqual(self.p2.price, 1100)

    def test_apply_writes_all_rows_and_logs_each(self):
        response = self._preview(percent="10", rounding="none", extra={"apply": "1"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse(CHANGELIST))
        self.p1.refresh_from_db()
        self.p2.refresh_from_db()
        self.assertEqual(self.p1.price, 759000)
        self.assertEqual(self.p1.compare_at_price, 880000)
        self.assertEqual(self.p2.price, 1155)
        for product, before, after in ((self.p1, 690000, 759000), (self.p2, 1050, 1155)):
            logs = LogEntry.objects.filter(object_id=str(product.pk))
            self.assertEqual(logs.count(), 1)
            self.assertIn("تغییر درصدی قیمت", logs.first().change_message)
            self.assertIn(f"{before:,} → {after:,}", logs.first().change_message)

    def test_apply_is_all_or_nothing(self):
        """If one product cannot be saved, NOTHING is saved."""
        original = (self.p1.price, self.p2.price)
        with mock.patch.object(
            Product, "full_clean",
            side_effect=[None, ValidationError("boom")],
        ):
            response = self._preview(percent="10", extra={"apply": "1"})
        self.assertEqual(response.status_code, 302)
        self.p1.refresh_from_db()
        self.p2.refresh_from_db()
        self.assertEqual((self.p1.price, self.p2.price), original)
        response = self.client.get(reverse(CHANGELIST))
        self.assertIn("هیچ محصولی ذخیره نشد", response.content.decode())

    def test_csv_download_has_bom_and_rows(self):
        response = self._preview(percent="10", rounding="100", extra={"csv": "1"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("price-changes.csv", response["Content-Disposition"])
        text = response.content.decode("utf-8-sig")
        self.assertTrue(response.content.decode("utf-8").startswith("\ufeff"))
        lines = text.splitlines()
        self.assertIn("قیمت قبل", lines[0])
        self.assertEqual(len(lines), 3)  # header + 2 rows
        self.assertIn("KT-1", text)
        self.assertIn("759000", text)

    def test_invalid_percent_and_ids_are_rejected(self):
        for percent in ("1000", "-100", "abc", ""):
            with self.subTest(percent=percent):
                response = self._preview(percent=percent)
                self.assertEqual(response.status_code, 302)  # back to changelist
                self.p1.refresh_from_db()
                self.assertEqual(self.p1.price, 690000)
        response = self._preview(ids="")
        self.assertEqual(response.status_code, 302)
        response = self._preview(rounding="7")
        self.assertEqual(response.status_code, 302)

    def test_view_only_staff_is_denied(self):
        staff = make_staff(permissions=["products.view_product"],
                           username="+989000031002", phone="+989000031002")
        self.client.force_login(staff)
        response = self._preview()
        self.assertEqual(response.status_code, 403)

    def test_get_redirects_to_changelist(self):
        response = self.client.get(reverse(PERCENT_URL))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse(CHANGELIST))


@override_settings(**PLAIN_STATIC)
class ProductChangeFormAssetsTests(TestCase):
    def setUp(self):
        self.admin = make_superuser(username="formowner", phone="+989000030004")
        self.client.force_login(self.admin)

    def test_change_form_carries_b4d_assets(self):
        product = make_product()
        response = self.client.get(
            reverse("admin:products_product_change", args=[product.pk])
        )
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("admin_theme/js/product_form.js", html)
        self.assertIn("cusin-anchor-nav", html)
        self.assertIn("cusin-preview-card", html)
        # the stock form itself is untouched
        self.assertIn("id_price", html)
        self.assertIn("id_name", html)
        # SEO counters, Ctrl+S and the unsaved-changes guard live in the
        # progressively-enhanced JS, not the server HTML
        from pathlib import Path

        from django.conf import settings

        js = (Path(settings.BASE_DIR) / "static" / "admin_theme" / "js"
              / "product_form.js").read_text(encoding="utf-8")
        self.assertIn("cusin-counter", js)
        self.assertIn("beforeunload", js)
        self.assertIn("keydown", js)  # Ctrl+S binding

    def test_add_form_also_gets_assets(self):
        response = self.client.get(reverse("admin:products_product_add"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("admin_theme/js/product_form.js", response.content.decode())
