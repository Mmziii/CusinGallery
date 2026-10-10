"""
`manage.py import_product_images` -- the CLI half of the ZIP image import.

It must behave exactly like the admin page (same engine): dry-run writes
nothing, add/replace/skip work, a hostile ZIP is refused with a clear
error and nothing written, and a folder can be used instead of a ZIP.
"""
import io
import os
import shutil
import tempfile

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from apps.products.models import ProductImage

from .helpers import make_product
from .test_image_import import build_zip, png_bytes

TEMP_MEDIA = tempfile.mkdtemp(prefix="cusin-test-image-import-cli-")
PLAIN_STATIC = {
    "STORAGES": {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
}


@override_settings(MEDIA_ROOT=TEMP_MEDIA, **PLAIN_STATIC)
class ImageImportCommandTests(TestCase):
    def setUp(self):
        shutil.rmtree(TEMP_MEDIA, ignore_errors=True)
        os.makedirs(TEMP_MEDIA, exist_ok=True)
        self.zip_path = os.path.join(TEMP_MEDIA, "photos.zip")

    def tearDown(self):
        shutil.rmtree(TEMP_MEDIA, ignore_errors=True)

    def write_zip(self, entries):
        with open(self.zip_path, "wb") as handle:
            handle.write(build_zip(entries))
        return self.zip_path

    def run_command(self, *args, **kwargs):
        out, err = io.StringIO(), io.StringIO()
        call_command("import_product_images", *args, stdout=out, stderr=err, **kwargs)
        return out.getvalue(), err.getvalue()

    def test_dry_run_reports_the_plan_and_writes_nothing(self):
        product = make_product(name="کاسه", sku="CLI-1")
        self.write_zip([
            ("CLI-1.jpg", png_bytes((1, 1, 1))),
            ("CLI-1-2.jpg", png_bytes((2, 2, 2))),
            ("NOPE-1.jpg", png_bytes((3, 3, 3))),
        ])
        out, _err = self.run_command(self.zip_path, "--dry-run")
        self.assertIn("۲ تصویر برای ۱ محصول", out)
        self.assertIn("۱ کد کالای ناشناخته", out)
        self.assertIn("CLI-1 | کاسه", out)
        self.assertIn("هیچ‌چیزی ذخیره نشد", out)
        self.assertEqual(product.images.count(), 0)
        self.assertEqual(ProductImage.objects.count(), 0)

    def test_add_mode_writes_the_images(self):
        product = make_product(name="دیگ", sku="CLI-2")
        self.write_zip([
            ("CLI-2-2.jpg", png_bytes((2, 2, 2))),
            ("CLI-2.jpg", png_bytes((1, 1, 1))),
        ])
        out, _err = self.run_command(self.zip_path)
        self.assertIn("ذخیره شد: ۲ تصویر برای ۱ محصول", out)
        images = list(product.images.order_by("ordering"))
        self.assertEqual(len(images), 2)
        self.assertTrue(images[0].is_primary)
        self.assertEqual(images[0].ordering, 0)

    def test_replace_mode(self):
        product = make_product(name="قوری", sku="CLI-3")
        product.images.create(image="products/old-cli.jpg", ordering=0, is_primary=True)
        self.write_zip([("CLI-3.jpg", png_bytes((9, 9, 9)))])
        out, _err = self.run_command(self.zip_path, "--mode", "replace")
        self.assertIn("۱ تصویر قبلی جایگزین شد", out)
        self.assertEqual(product.images.count(), 1)
        self.assertNotIn("old-cli", product.images.get().image.name)

    def test_skip_existing(self):
        with_image = make_product(name="با تصویر", sku="CLI-4")
        with_image.images.create(image="products/has-cli.jpg", ordering=0, is_primary=True)
        without = make_product(name="بی تصویر", sku="CLI-5")
        self.write_zip([
            ("CLI-4.jpg", png_bytes((4, 4, 4))),
            ("CLI-5.jpg", png_bytes((5, 5, 5))),
        ])
        out, _err = self.run_command(self.zip_path, "--skip-existing")
        self.assertIn("۱ رد‌شده (تصویر دارد)", out)
        self.assertEqual(with_image.images.count(), 1)
        self.assertEqual(without.images.count(), 1)

    def test_a_second_run_of_the_same_zip_is_a_no_op(self):
        product = make_product(name="لیوان", sku="CLI-6")
        self.write_zip([("CLI-6.jpg", png_bytes((6, 6, 6)))])
        self.run_command(self.zip_path)
        self.assertEqual(product.images.count(), 1)
        out, _err = self.run_command(self.zip_path)
        self.assertIn("چیزی برای ذخیره نبود", out)
        self.assertEqual(product.images.count(), 1)

    def test_a_hostile_zip_is_refused_without_writing(self):
        product = make_product(name="امن", sku="CLI-7")
        self.write_zip([
            ("CLI-7.jpg", png_bytes((7, 7, 7))),
            {"name": "../escape.jpg", "payload": png_bytes((8, 8, 8))},
        ])
        with self.assertRaises(CommandError):
            self.run_command(self.zip_path)
        self.assertEqual(product.images.count(), 0)

    def test_a_missing_path_is_a_clear_error(self):
        with self.assertRaises(CommandError) as ctx:
            self.run_command(os.path.join(TEMP_MEDIA, "nope.zip"))
        self.assertIn("مسیر پیدا نشد", str(ctx.exception))

    def test_a_folder_can_be_used_instead_of_a_zip(self):
        """`import_product_images /srv/photos/` supports both shapes:
        a folder per product (SKU/1.jpg) and SKU.jpg directly in the root."""
        nested = make_product(name="پوشه", sku="CLI-8")
        direct = make_product(name="مستقیم", sku="CLI-10")
        root = os.path.join(TEMP_MEDIA, "photos")
        os.makedirs(os.path.join(root, "CLI-8"))
        with open(os.path.join(root, "CLI-8", "1.jpg"), "wb") as handle:
            handle.write(png_bytes((11, 11, 11)))
        with open(os.path.join(root, "CLI-8", "2.jpg"), "wb") as handle:
            handle.write(png_bytes((22, 22, 22)))
        with open(os.path.join(root, "CLI-10.jpg"), "wb") as handle:
            handle.write(png_bytes((33, 33, 33)))
        out, _err = self.run_command(root)
        self.assertIn("ذخیره شد: ۳ تصویر", out)
        self.assertEqual(nested.images.count(), 2)
        self.assertTrue(nested.images.order_by("ordering").first().is_primary)
        self.assertEqual(direct.images.count(), 1)

    def test_an_invalid_image_does_not_stop_the_valid_ones(self):
        product = make_product(name="نیمه", sku="CLI-9")
        self.write_zip([
            ("CLI-9.jpg", b"not an image at all"),
            ("CLI-9-2.jpg", png_bytes((12, 12, 12))),
        ])
        out, err = self.run_command(self.zip_path)
        self.assertIn("۱ تصویر برای ۱ محصول", out)
        self.assertIn("[نامعتبر]", out)
        self.assertEqual(product.images.count(), 1)
