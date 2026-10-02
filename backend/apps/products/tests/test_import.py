"""
Bulk product import tests (Phase B - Store management).

Tests the shared engine (apps/products/importing.py) and both of its
front-ends: the management command and the admin import view. Focus is
on the safety contract: per-row errors with row numbers, and
all-or-nothing (any bad row -> nothing saved).
"""
import io
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.categories.models import Category
from apps.products.importing import (
    import_products_from_rows,
    read_rows,
    template_csv,
)
from apps.products.models import Brand, Product

TEMP_MEDIA = tempfile.mkdtemp(prefix="cusin-test-media-import-")

PLAIN_STATIC = {
    "STORAGES": {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
}

HEADER = [
    "name", "slug", "sku", "category_slug", "brand_name", "price",
    "compare_at_price", "discount_percentage", "stock_quantity",
    "low_stock_threshold", "short_description", "description",
    "is_active", "is_featured",
]


def row(**overrides):
    base = {
        "name": "Pan", "slug": "pan", "sku": "SKU-1", "category_slug": "cookware",
        "brand_name": "", "price": "100000", "compare_at_price": "",
        "discount_percentage": "0", "stock_quantity": "5",
        "low_stock_threshold": "2", "short_description": "", "description": "",
        "is_active": "true", "is_featured": "false",
    }
    base.update(overrides)
    return base


def csv_bytes(rows, header=HEADER):
    import csv

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=header)
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    return buffer.getvalue().encode("utf-8-sig")


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class ImportBase(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Cookware", slug="cookware")

    def tearDown(self):
        shutil.rmtree(TEMP_MEDIA, ignore_errors=True)


class EngineTests(ImportBase):
    def test_creates_products(self):
        rows = [
            row(sku="A", slug="a", name="A pan"),
            row(sku="B", slug="b", name="B pan", brand_name=""),
        ]
        result = import_products_from_rows(rows, HEADER)
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.created, 2)
        self.assertEqual(result.updated, 0)
        self.assertEqual(Product.objects.count(), 2)
        product = Product.objects.get(sku="A")
        self.assertEqual(product.price, 100000)
        self.assertEqual(product.category, self.category)
        self.assertTrue(product.is_active)

    def test_existing_sku_is_updated_not_duplicated(self):
        Product.objects.create(
            name="Old", slug="old-pan", sku="SKU-1", category=self.category, price=50000
        )
        result = import_products_from_rows(
            [row(price="250000", name="New name")], HEADER
        )
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.updated, 1)
        self.assertEqual(result.created, 0)
        self.assertEqual(Product.objects.count(), 1)
        product = Product.objects.get(sku="SKU-1")
        self.assertEqual(product.price, 250000)
        self.assertEqual(product.name, "New name")

    def test_persian_digits_are_normalized(self):
        result = import_products_from_rows(
            [row(price="۱۲۰۰۰۰", stock_quantity="٣")], HEADER
        )
        self.assertTrue(result.ok, result.errors)
        product = Product.objects.get(sku="SKU-1")
        self.assertEqual(product.price, 120000)
        self.assertEqual(product.stock_quantity, 3)

    def test_any_invalid_row_blocks_the_whole_import(self):
        rows = [
            row(sku="OK1", slug="ok1"),
            row(sku="BAD", slug="bad", price="not-a-number"),
            row(sku="OK2", slug="ok2", category_slug="does-not-exist"),
        ]
        result = import_products_from_rows(rows, HEADER)
        self.assertFalse(result.ok)
        # Row numbers reference the spreadsheet (header = row 1).
        self.assertTrue(any("ردیف 3" in e for e in result.errors), result.errors)
        self.assertTrue(any("ردیف 4" in e for e in result.errors), result.errors)
        # NOTHING was written, including the valid row.
        self.assertEqual(Product.objects.count(), 0)

    def test_missing_required_column_is_rejected(self):
        header = [c for c in HEADER if c != "price"]
        rows = [{k: v for k, v in row().items() if k != "price"}]
        result = import_products_from_rows(rows, header)
        self.assertFalse(result.ok)
        self.assertTrue(any("price" in e and "ستون" in e for e in result.errors))
        self.assertEqual(Product.objects.count(), 0)

    def test_duplicate_sku_in_file_is_rejected(self):
        rows = [row(sku="DUP", slug="d1"), row(sku="DUP", slug="d2")]
        result = import_products_from_rows(rows, HEADER)
        self.assertFalse(result.ok)
        self.assertTrue(any("بیش از یک بار" in e for e in result.errors))
        self.assertEqual(Product.objects.count(), 0)

    def test_slug_collision_with_other_product_is_rejected(self):
        Product.objects.create(
            name="Owner", slug="taken-slug", sku="OTHER", category=self.category, price=1
        )
        result = import_products_from_rows([row(slug="taken-slug")], HEADER)
        self.assertFalse(result.ok)
        self.assertTrue(any("شناسهٔ" in e for e in result.errors))
        self.assertEqual(Product.objects.count(), 1)

    def test_compare_at_price_below_price_rejected(self):
        result = import_products_from_rows(
            [row(price="100000", compare_at_price="90000")], HEADER
        )
        self.assertFalse(result.ok)
        self.assertEqual(Product.objects.count(), 0)

    def test_brand_and_category_created_when_present(self):
        Brand.objects.create(name="Kuzin", slug="kuzin")
        result = import_products_from_rows([row(brand_name="Kuzin")], HEADER)
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(Product.objects.get(sku="SKU-1").brand.name, "Kuzin")

    def test_unknown_brand_rejected(self):
        result = import_products_from_rows([row(brand_name="Nope")], HEADER)
        self.assertFalse(result.ok)
        self.assertTrue(any("brand" in e for e in result.errors))
        self.assertEqual(Product.objects.count(), 0)

    def test_dry_run_writes_nothing(self):
        result = import_products_from_rows([row()], HEADER, dry_run=True)
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(Product.objects.count(), 0)
        self.assertEqual(result.created, 1)


class ReadRowsTests(ImportBase):
    def test_reads_csv_with_bom(self):
        upload = SimpleUploadedFile("p.csv", csv_bytes([row()]), "text/csv")
        rows, header = read_rows(upload)
        self.assertEqual(header, HEADER)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["sku"], "SKU-1")

    def test_reads_xlsx(self):
        from openpyxl import Workbook

        workbook = Workbook()
        sheet = workbook.active
        sheet.append(HEADER)
        sheet.append([row()[c] for c in HEADER])
        buffer = io.BytesIO()
        workbook.save(buffer)
        upload = SimpleUploadedFile("p.xlsx", buffer.getvalue(),
                                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        rows, header = read_rows(upload)
        self.assertEqual(header, HEADER)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["sku"], "SKU-1")

    def test_rejects_unknown_extension(self):
        upload = SimpleUploadedFile("p.txt", b"name", "text/plain")
        with self.assertRaises(ValueError):
            read_rows(upload)

    def test_template_matches_expected_columns(self):
        upload = SimpleUploadedFile("t.csv", template_csv().encode("utf-8-sig"), "text/csv")
        rows, header = read_rows(upload)
        self.assertEqual(header, HEADER)
        self.assertEqual(len(rows), 1)


class ManagementCommandTests(ImportBase):
    def _write_csv(self, rows, name="import.csv"):
        path = f"/tmp/{name}"
        with open(path, "wb") as handle:
            handle.write(csv_bytes(rows))
        return path

    def test_import_via_command(self):
        out = io.StringIO()
        call_command("import_products", self._write_csv([row()]), stdout=out)
        self.assertEqual(Product.objects.count(), 1)
        self.assertIn("1 created", out.getvalue())

    def test_command_rejects_bad_file_without_saving(self):
        path = self._write_csv([row(), row(sku="X", slug="x", price="bad")], "bad.csv")
        with self.assertRaises(CommandError):
            call_command("import_products", path)
        self.assertEqual(Product.objects.count(), 0)

    def test_dry_run_flag(self):
        out = io.StringIO()
        call_command("import_products", self._write_csv([row()]), "--dry-run", stdout=out)
        self.assertEqual(Product.objects.count(), 0)
        self.assertIn("would be imported", out.getvalue())

    def test_write_template(self):
        call_command("import_products", "--write-template", "/tmp/tpl.csv")
        with open("/tmp/tpl.csv", "rb") as handle:
            content = handle.read()
        self.assertIn(b"name,slug,sku", content)


@override_settings(MEDIA_ROOT=TEMP_MEDIA, **PLAIN_STATIC)
class AdminImportViewTests(ImportBase):
    def setUp(self):
        super().setUp()
        self.superuser = get_user_model().objects.create_superuser(
            username="owner-import", password="x", phone="+989000000003"
        )
        self.client.force_login(self.superuser)

    def test_import_view_creates_products(self):
        upload = SimpleUploadedFile("p.csv", csv_bytes([row()]), "text/csv")
        response = self.client.post(
            reverse("admin:products_product_import"), {"file": upload}, follow=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Product.objects.count(), 1)

    def test_import_view_shows_row_errors_and_saves_nothing(self):
        upload = SimpleUploadedFile(
            "p.csv", csv_bytes([row(price="oops")]), "text/csv"
        )
        response = self.client.post(
            reverse("admin:products_product_import"), {"file": upload}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "واردکرد انجام نشد")
        self.assertContains(response, "ردیف 2")
        self.assertEqual(Product.objects.count(), 0)

    def test_template_download(self):
        response = self.client.get(reverse("admin:products_product_import_template"))
        self.assertEqual(response.status_code, 200)
        body = b"".join(response.streaming_content)
        self.assertIn(b"name,slug,sku", body)
