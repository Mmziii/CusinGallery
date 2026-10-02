"""
Image upload handling tests (Phase B - Store management).

Real behavior: validator rejections for non-images, wrong formats and
oversized files, and actual thumbnail generation on disk with bounded
dimensions. Tests run against a temporary MEDIA_ROOT so the repo's
media/ directory stays clean.
"""
import io
import shutil
import tempfile

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from PIL import Image

from apps.payments.tests.helpers import make_product
from apps.products.models import ProductImage

TEMP_MEDIA = tempfile.mkdtemp(prefix="cusin-test-media-")


def png_bytes(size=(900, 700), color=(200, 60, 30)):
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def uploaded_png(name="photo.png", **kwargs):
    return SimpleUploadedFile(name, png_bytes(**kwargs), content_type="image/png")


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class ImageValidationTests(TestCase):
    def setUp(self):
        self.product = make_product()

    def test_valid_image_passes_and_saves(self):
        image = ProductImage(product=self.product, image=uploaded_png())
        image.full_clean()
        image.save()
        self.assertTrue(image.image)

    def test_non_image_bytes_are_rejected(self):
        image = ProductImage(
            product=self.product,
            image=SimpleUploadedFile("evil.png", b"<script>alert(1)</script>", "image/png"),
        )
        with self.assertRaises(ValidationError):
            image.full_clean()

    def test_disallowed_format_is_rejected_even_when_decodable(self):
        buffer = io.BytesIO()
        Image.new("RGB", (100, 100), (1, 2, 3)).save(buffer, format="BMP")
        image = ProductImage(
            product=self.product,
            image=SimpleUploadedFile("art.bmp", buffer.getvalue(), "image/bmp"),
        )
        with self.assertRaises(ValidationError):
            image.full_clean()

    def test_oversized_image_is_rejected(self):
        class SizedFile:
            """Valid PNG content but a reported size above the limit --
            exercises the size branch directly."""

            def __init__(self):
                self._bytes = io.BytesIO(png_bytes())
                self.size = 6 * 1024 * 1024
                self.name = "huge.png"

            def seek(self, *args):
                return self._bytes.seek(*args)

            def read(self, *args):
                return self._bytes.read(*args)

            def tell(self):
                return self._bytes.tell()

        from apps.core.image_files import validate_image_file

        with self.assertRaises(ValidationError) as ctx:
            validate_image_file(SizedFile())
        self.assertIn("too large", str(ctx.exception))

    def tearDown(self):
        shutil.rmtree(TEMP_MEDIA, ignore_errors=True)


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class ThumbnailGenerationTests(TestCase):
    def setUp(self):
        self.product = make_product()

    def test_saving_an_image_generates_a_bounded_thumbnail(self):
        image = ProductImage(product=self.product, image=uploaded_png(size=(1600, 1200)))
        image.save()

        self.assertTrue(image.thumbnail)
        with Image.open(image.thumbnail.path) as thumb:
            self.assertLessEqual(thumb.width, 400)
            self.assertLessEqual(thumb.height, 400)
            self.assertEqual(thumb.format, "JPEG")
        # Aspect preserved: 1600x1200 -> 400x300.
        with Image.open(image.thumbnail.path) as thumb:
            self.assertEqual((thumb.width, thumb.height), (400, 300))

    def test_resave_does_not_regenerate_the_thumbnail(self):
        image = ProductImage(product=self.product, image=uploaded_png())
        image.save()
        first_thumbnail = image.thumbnail.name

        image.alt_text = "updated"
        image.save()

        self.assertEqual(image.thumbnail.name, first_thumbnail)

    def tearDown(self):
        shutil.rmtree(TEMP_MEDIA, ignore_errors=True)
