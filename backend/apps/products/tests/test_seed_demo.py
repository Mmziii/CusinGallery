"""
seed_demo command tests (Phase B - Store management).

Runs the real command against a temporary MEDIA_ROOT and checks that a
preview-worthy catalog appears (with actual image + thumbnail files on
disk) and that a second run duplicates nothing.
"""
import shutil
import tempfile

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.banners.models import Banner, DailyDeal
from apps.categories.models import Category
from apps.discounts.models import Coupon
from apps.products.models import Brand, Product, ProductImage, ProductVariant

TEMP_MEDIA = tempfile.mkdtemp(prefix="cusin-test-media-seed-")


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class SeedDemoTests(TestCase):
    def tearDown(self):
        shutil.rmtree(TEMP_MEDIA, ignore_errors=True)

    def test_seed_creates_a_preview_catalog_with_images(self):
        call_command("seed_demo")

        self.assertGreaterEqual(Category.objects.count(), 4)
        self.assertGreaterEqual(Brand.objects.count(), 3)
        self.assertGreaterEqual(Product.objects.count(), 8)
        self.assertTrue(Category.objects.filter(parent__isnull=False).exists())

        # Every seeded product carries a primary image whose file exists.
        for product in Product.objects.all():
            primary = product.images.filter(is_primary=True).first()
            self.assertIsNotNone(primary, product.sku)
            self.assertTrue(primary.image.storage.exists(primary.image.name), product.sku)

        # Thumbnails were generated through the normal save() path.
        sample = Product.objects.get(sku="MUG-300")
        thumb = sample.images.filter(is_primary=True).first()
        self.assertTrue(thumb.thumbnail)
        self.assertTrue(thumb.thumbnail.storage.exists(thumb.thumbnail.name))

        # The variant demo exists.
        self.assertGreaterEqual(ProductVariant.objects.filter(product=sample).count(), 2)

        # Storefront preview extras.
        self.assertTrue(Coupon.objects.filter(code="WELCOME10", is_active=True).exists())
        self.assertTrue(Banner.objects.filter(is_active=True).exists())
        now = timezone.now()
        self.assertTrue(
            DailyDeal.objects.filter(is_active=True, starts_at__lte=now, ends_at__gte=now).exists()
        )

    def test_seed_is_idempotent(self):
        call_command("seed_demo")
        counts = {
            "categories": Category.objects.count(),
            "brands": Brand.objects.count(),
            "products": Product.objects.count(),
            "images": ProductImage.objects.count(),
            "coupons": Coupon.objects.count(),
            "banners": Banner.objects.count(),
            "deals": DailyDeal.objects.count(),
        }

        call_command("seed_demo")

        self.assertEqual(Category.objects.count(), counts["categories"])
        self.assertEqual(Brand.objects.count(), counts["brands"])
        self.assertEqual(Product.objects.count(), counts["products"])
        self.assertEqual(ProductImage.objects.count(), counts["images"])
        self.assertEqual(Coupon.objects.count(), counts["coupons"])
        self.assertEqual(Banner.objects.count(), counts["banners"])
        self.assertEqual(DailyDeal.objects.count(), counts["deals"])


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class SeedDemoGalleryTests(TestCase):
    """Part S5 item 3: the demo catalog must SHOW the gallery (3-4 images
    on several products), so the thumbnail row is visible in a preview."""

    def tearDown(self):
        shutil.rmtree(TEMP_MEDIA, ignore_errors=True)

    def test_several_products_get_a_three_or_four_image_gallery(self):
        call_command("seed_demo")

        with_gallery = [
            product for product in Product.objects.all() if product.images.count() >= 3
        ]
        self.assertGreaterEqual(len(with_gallery), 5)
        for product in with_gallery:
            count = product.images.count()
            self.assertIn(count, (3, 4), product.sku)
            # Exactly one primary, and it sorts first by ordering.
            self.assertEqual(product.images.filter(is_primary=True).count(), 1, product.sku)
            self.assertEqual(
                list(product.images.order_by("ordering").values_list("is_primary", flat=True))[0],
                True,
                product.sku,
            )
            # Every image really exists on disk with a generated thumbnail.
            for image in product.images.all():
                self.assertTrue(image.image.storage.exists(image.image.name), product.sku)
                self.assertTrue(image.thumbnail, product.sku)

    def test_gallery_images_of_one_product_are_visibly_different_files(self):
        call_command("seed_demo")

        product = Product.objects.get(sku="PAN-001")
        names = sorted(img.image.name for img in product.images.all())
        self.assertEqual(len(names), len(set(names)), "duplicate gallery file names")

        sizes = {img.image.size for img in product.images.all()}
        self.assertGreater(len(sizes), 1, "all demo views are byte-identical")

    def test_rerun_does_not_duplicate_or_drop_gallery_images(self):
        call_command("seed_demo")
        before = {p.sku: p.images.count() for p in Product.objects.all()}

        call_command("seed_demo")

        after = {p.sku: p.images.count() for p in Product.objects.all()}
        self.assertEqual(before, after)
