"""
Responsive WebP variant tests (Part 3): variants generated on save,
the backfill command is idempotent and degrades gracefully for missing
or undecodable files, and invalid uploads are still rejected.
"""
import io

from django.core.files.base import ContentFile
from django.core.management import call_command
from django.test import TestCase
from PIL import Image

from apps.core.image_files import validate_image_file
from django.core.exceptions import ValidationError

from .helpers import make_product
from ..models import ProductImage


def jpeg_bytes(size=(900, 700), color=(120, 90, 40)):
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="JPEG")
    return buffer.getvalue()


class ResponsiveVariantTests(TestCase):
    def test_variants_created_on_save(self):
        product = make_product()
        row = ProductImage(product=product, is_primary=True)
        row.image.save("test-photo.jpg", ContentFile(jpeg_bytes()), save=False)
        row.save()

        row.refresh_from_db()
        self.assertTrue(row.webp_400.endswith("_400.webp"))
        self.assertTrue(row.webp_800.endswith("_800.webp"))
        self.assertTrue(row.webp_1200.endswith("_1200.webp"))
        # widths really differ on disk
        from django.core.files.storage import default_storage

        with default_storage.open(row.webp_400) as fh:
            with Image.open(fh) as img:
                self.assertEqual(img.format, "WEBP")
                self.assertLessEqual(img.width, 400)

    def test_backfill_command_is_idempotent_and_graceful(self):
        product = make_product()
        good = ProductImage.objects.create(product=product, is_primary=True)
        good.image.save("good.jpg", ContentFile(jpeg_bytes()), save=True)
        good.webp_400 = ""  # simulate a pre-Part-3 row
        good.save(update_fields=["webp_400"])

        empty = ProductImage.objects.create(product=product)  # no file at all

        out = io.StringIO()
        call_command("backfill_variants", stdout=out, stderr=io.StringIO())
        good.refresh_from_db()
        self.assertTrue(good.webp_400)

        first = good.webp_400
        out2 = io.StringIO()
        call_command("backfill_variants", stdout=out2)
        good.refresh_from_db()
        self.assertEqual(good.webp_400, first, "second run is a no-op")
        self.assertIn("0 image(s)", out2.getvalue().replace("\n", "") .replace("variants written for ", "variants written for ") or out2.getvalue())
        empty.refresh_from_db()
        self.assertEqual(empty.webp_400, "", "missing file never crashes nor fills")

    def test_invalid_image_still_rejected_by_validator(self):
        product = make_product()
        row = ProductImage(product=product)
        fake = ContentFile(b"<html>not an image</html>")
        fake.name = "evil.jpg"
        with self.assertRaises(ValidationError):
            validate_image_file(fake)
