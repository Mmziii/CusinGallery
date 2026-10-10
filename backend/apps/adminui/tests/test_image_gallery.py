"""A5: product images as a thumbnail grid of cards.

These tests check the REAL rendered change form and a real POST built only
from the field names the page rendered, so a renamed field or a broken
set-primary/ordering rule fails here, not in production."""
import io
import re
import shutil
import tempfile

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.products.models import ProductImage

from .helpers import PLAIN_STATIC, make_product, make_superuser

BADGE = '<span class="cusin-badge stock-ok">تصویر اصلی</span>'
TEMP_MEDIA = tempfile.mkdtemp(prefix="cusin-test-media-gallery-")


def real_png_name(name):
    """Store a genuine PNG under MEDIA_ROOT so the save path (thumbnail,
    WebP variants) can read the file exactly like a production upload."""
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (600, 600), (120, 90, 40)).save(buffer, format="PNG")
    return default_storage.save(name, ContentFile(buffer.getvalue()))


@override_settings(**PLAIN_STATIC)
class ImageGalleryRenderTests(TestCase):
    def setUp(self):
        self.admin = make_superuser(username="galleryowner", phone="+989000080001")
        self.client.force_login(self.admin)
        self.product = make_product(name="قابلمه", slug="ghabeleh", sku="GAL-1")
        self.primary = ProductImage.objects.create(
            product=self.product, image="products/main.jpg",
            is_primary=True, ordering=0, alt_text="نمای اصلی",
        )
        self.second = ProductImage.objects.create(
            product=self.product, image="products/side.jpg",
            is_primary=False, ordering=1,
        )
        self.url = reverse("admin:products_product_change", args=[self.product.pk])

    def _html(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_images_render_as_cards_in_a_grid(self):
        html = self._html()
        self.assertEqual(html.count('class="cusin-gallery"'), 1)
        # 2 saved images + 1 extra blank row + the hidden empty-form template
        self.assertEqual(html.count('class="inline-related cusin-gallery-card'), 4)
        self.assertEqual(html.count('class="inline-related cusin-gallery-card has_original'), 2)
        self.assertEqual(
            html.count('class="inline-related cusin-gallery-card empty-form last-related"'), 1
        )
        self.assertIn('id="images-empty"', html)

    def test_variants_keep_the_stock_table_and_images_use_stacked_cards(self):
        html = self._html()
        self.assertIn('id="images-group"', html)
        self.assertIn('data-inline-type="stacked"', html)
        self.assertIn('id="variants-group"', html)
        self.assertIn('data-inline-type="tabular"', html)

    def test_every_per_image_field_name_is_unchanged(self):
        html = self._html()
        names = set(re.findall(r'name="(images-\d+-[A-Za-z_]+)"', html))
        suffixes = {n.split("-", 2)[2] for n in names}
        expected = {"id", "product", "image", "alt_text", "is_primary",
                    "ordering", "add_images", "DELETE"}
        self.assertEqual(suffixes, expected)
        for management in ("TOTAL_FORMS", "INITIAL_FORMS", "MIN_NUM_FORMS", "MAX_NUM_FORMS"):
            self.assertEqual(html.count(f'name="images-{management}"'), 1)

    def test_primary_badge_only_on_the_primary_image(self):
        html = self._html()
        self.assertEqual(html.count(BADGE), 1)

    def test_every_card_has_a_thumbnail_slot(self):
        html = self._html()
        # one preview per card, including the hidden empty-form template
        self.assertEqual(html.count('class="cusin-gallery-preview'), 4)

    def test_add_images_input_still_accepts_multiple_files(self):
        html = self._html()
        self.assertRegex(html, r'name="images-\d+-add_images"[^>]*multiple')


@override_settings(**PLAIN_STATIC)
class ImageGalleryFallbackTests(TestCase):
    def setUp(self):
        self.admin = make_superuser(username="galleryfb", phone="+989000080003")
        self.client.force_login(self.admin)
        self.product = make_product(name="ماهیتابه", slug="mahitabeh", sku="GAL-3")
        ProductImage.objects.create(
            product=self.product, image="products/x.jpg", is_primary=True, ordering=0,
        )

    def test_theme_disabled_renders_stock_table_for_images(self):
        url = reverse("admin:products_product_change", args=[self.product.pk])
        with self.settings(ADMIN_THEME_ENABLED=False):
            html = self.client.get(url).content.decode()
        self.assertNotIn("cusin-gallery", html)
        self.assertIn('data-inline-type="tabular"', html)
        self.assertIn('id="images-group"', html)
        # the same field names as the card layout, so saved data is identical
        self.assertIn('name="images-0-is_primary"', html)
        self.assertIn('name="images-0-ordering"', html)

    def test_theme_enabled_renders_cards(self):
        url = reverse("admin:products_product_change", args=[self.product.pk])
        with self.settings(ADMIN_THEME_ENABLED=True):
            html = self.client.get(url).content.decode()
        self.assertIn("cusin-gallery", html)


@override_settings(MEDIA_ROOT=TEMP_MEDIA, **PLAIN_STATIC)
class ImageGalleryBehaviourTests(TestCase):
    def setUp(self):
        self.admin = make_superuser(username="galleryops", phone="+989000080002")
        self.client.force_login(self.admin)
        self.product = make_product(name="تابه", slug="tabeh", sku="GAL-2")
        self.first = ProductImage.objects.create(
            product=self.product, image=real_png_name("products/a.png"),
            is_primary=True, ordering=0,
        )
        self.second = ProductImage.objects.create(
            product=self.product, image=real_png_name("products/b.png"),
            is_primary=False, ordering=1,
        )
        self.url = reverse("admin:products_product_change", args=[self.product.pk])

    def _post(self, **overrides):
        """Build the POST from the page itself: every images-* key we send
        must be a name the page rendered."""
        html = self.client.get(self.url).content.decode()
        rendered = set(re.findall(r'name="([^"]+)"', html))

        data = {
            "name": self.product.name,
            "slug": self.product.slug,
            "sku": self.product.sku,
            "category": str(self.product.category_id),
            "discount_percentage": str(self.product.discount_percentage or 0),
            "price": str(self.product.price),
            "stock_quantity": str(self.product.stock_quantity),
            "low_stock_threshold": str(self.product.low_stock_threshold),
            "images-TOTAL_FORMS": "3",
            "images-INITIAL_FORMS": "2",
            "images-MIN_NUM_FORMS": "0",
            "images-MAX_NUM_FORMS": "1000",
            "images-0-id": str(self.first.pk),
            "images-0-product": str(self.product.pk),
            "images-0-alt_text": "",
            "images-0-ordering": "5",
            "images-1-id": str(self.second.pk),
            "images-1-product": str(self.product.pk),
            "images-1-alt_text": "",
            "images-1-ordering": "0",
            "images-1-is_primary": "on",
            # the blank extra row exactly as the browser submits it
            "images-2-id": "",
            "images-2-product": str(self.product.pk),
            "images-2-alt_text": "",
            "images-2-ordering": "0",
            "variants-TOTAL_FORMS": "0",
            "variants-INITIAL_FORMS": "0",
            "variants-MIN_NUM_FORMS": "0",
            "variants-MAX_NUM_FORMS": "1000",
            "_save": "ذخیره",
        }
        data.update(overrides)
        for key in data:
            if key.startswith(("images-", "variants-")):
                self.assertIn(key, rendered, f"{key} is not a field the page renders")
        return self.client.post(self.url, data)

    def test_set_primary_and_ordering_post_correctly(self):
        response = self._post()
        self.assertEqual(response.status_code, 302)
        self.first.refresh_from_db()
        self.second.refresh_from_db()
        self.assertFalse(self.first.is_primary)
        self.assertTrue(self.second.is_primary)
        self.assertEqual(self.first.ordering, 5)
        self.assertEqual(self.second.ordering, 0)
        self.assertEqual(
            ProductImage.objects.filter(product=self.product, is_primary=True).count(), 1
        )

    def test_two_primaries_still_rejected_with_the_same_message(self):
        response = self._post(**{"images-0-is_primary": "on", "images-1-is_primary": "on"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "فقط یک تصویر")
        self.first.refresh_from_db()
        self.second.refresh_from_db()
        self.assertTrue(self.first.is_primary)
        self.assertFalse(self.second.is_primary)


def tearDownModule():
    shutil.rmtree(TEMP_MEDIA, ignore_errors=True)
