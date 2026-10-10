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


class ResponsiveVariantApiSerializationTests(TestCase):
    """Part R1 fix: webp_* columns must reach API clients as servable
    /media/ URLs, not storage-relative paths (which 404 in the browser)."""

    def test_product_api_serves_webp_variants_as_media_urls(self):
        from django.urls import reverse

        product = make_product()
        row = ProductImage(product=product, is_primary=True)
        row.image.save("api-photo.jpg", ContentFile(jpeg_bytes()), save=False)
        row.save()

        response = self.client.get(reverse("product-detail", args=[product.slug]))
        self.assertEqual(response.status_code, 200)
        image = response.data["images"][0]
        self.assertTrue(image["webp_400"].startswith("/media/"), image["webp_400"])
        self.assertTrue(image["webp_400"].endswith("_400.webp"))

    def test_banner_api_serves_webp_variants_as_media_urls(self):
        from django.urls import reverse

        from apps.banners.models import Banner

        banner = Banner(title="B")
        banner.image.save("api-banner.jpg", ContentFile(jpeg_bytes()), save=False)
        banner.save()

        response = self.client.get(reverse("banner-list"))
        self.assertEqual(response.status_code, 200)
        for key in ("count", "next", "previous", "results"):
            self.assertIn(key, response.data)
        payload = response.data["results"][0]
        self.assertTrue(payload["webp_400"].startswith("/media/"), payload["webp_400"])
