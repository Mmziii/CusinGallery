"""
Product admin tests (Phase B - Store management).

Exercises the admin through real HTTP posts (changelist actions and the
change form with image inlines) -- the same requests the shop owner's
browser sends.
"""
import io
import shutil
import tempfile

from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from PIL import Image

from apps.categories.models import Category
from apps.payments.tests.helpers import make_product
from apps.products.models import Product, ProductImage

TEMP_MEDIA = tempfile.mkdtemp(prefix="cusin-test-media-admin-")

# Rendering the admin UI needs {% static %} to resolve. Production uses
# whitenoise's manifest storage (built by collectstatic at container
# boot), but tests must not depend on a prebuilt manifest -- so use the
# plain storage backend here. This changes nothing about what is tested.
PLAIN_STATIC = {
    "STORAGES": {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
}


def uploaded_png(name="photo.png"):
    buffer = io.BytesIO()
    Image.new("RGB", (640, 480), (30, 90, 160)).save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


@override_settings(MEDIA_ROOT=TEMP_MEDIA, **PLAIN_STATIC)
class ProductAdminBase(TestCase):
    def setUp(self):
        self.superuser = get_user_model().objects.create_superuser(
            username="owner", password="x", phone="+989000000002"
        )
        self.client.force_login(self.superuser)
        self.category = Category.objects.create(name="Cookware", slug="cookware")

    def tearDown(self):
        shutil.rmtree(TEMP_MEDIA, ignore_errors=True)


class BulkActionTests(ProductAdminBase):
    def setUp(self):
        super().setUp()
        self.p1 = make_product(category=self.category, slug="p-one", sku="SKU-ONE")
        self.p2 = make_product(category=self.category, slug="p-two", sku="SKU-TWO")

    def _run_action(self, action):
        return self.client.post(
            reverse("admin:products_product_changelist"),
            {
                "action": action,
                ACTION_CHECKBOX_NAME: [self.p1.pk, self.p2.pk],
                "index": 0,
            },
            follow=True,
        )

    def test_deactivate_and_activate_actions(self):
        response = self._run_action("deactivate_products")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Product.objects.filter(pk__in=[self.p1.pk, self.p2.pk, ]).filter(is_active=True).exists())

        response = self._run_action("activate_products")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            Product.objects.filter(pk__in=[self.p1.pk, self.p2.pk], is_active=True).count(), 2
        )

    def test_feature_and_unfeature_actions(self):
        response = self._run_action("mark_featured")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            Product.objects.filter(pk__in=[self.p1.pk, self.p2.pk], is_featured=True).count(), 2
        )

        response = self._run_action("unmark_featured")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            Product.objects.filter(pk__in=[self.p1.pk, self.p2.pk], is_featured=True).exists()
        )

    def test_changelist_shows_stock_warnings(self):
        Product.objects.filter(pk=self.p1.pk).update(stock_quantity=0)
        Product.objects.filter(pk=self.p2.pk).update(stock_quantity=3, low_stock_threshold=5)

        response = self.client.get(reverse("admin:products_product_changelist"))
        html = response.content.decode()
        self.assertIn("ناموجود", html)
        self.assertIn("موجودی کم", html)


class ImageInlineTests(ProductAdminBase):
    def _add_payload(self, **overrides):
        payload = {
            "name": "Test Pan",
            "slug": "test-pan",
            "sku": "SKU-PAN",
            "category": self.category.pk,
            "price": 120000,
            "discount_percentage": 0,
            "stock_quantity": 10,
            "low_stock_threshold": 5,
            "short_description": "",
            "description": "",
            "images-TOTAL_FORMS": "1",
            "images-INITIAL_FORMS": "0",
            "images-MIN_NUM_FORMS": "0",
            "images-MAX_NUM_FORMS": "1000",
            "variants-TOTAL_FORMS": "0",
            "variants-INITIAL_FORMS": "0",
            "variants-MIN_NUM_FORMS": "0",
            "variants-MAX_NUM_FORMS": "1000",
            "_save": "Save",
        }
        payload.update(overrides)
        return payload

    def test_image_without_primary_flag_is_auto_assigned(self):
        payload = self._add_payload(
            **{
                "images-0-image": uploaded_png(),
                "images-0-alt_text": "front",
                "images-0-ordering": "0",
                "images-0-id": "",
                "images-0-product": "",
            }
        )
        response = self.client.post(reverse("admin:products_product_add"), payload, follow=True)
        self.assertEqual(response.status_code, 200)

        product = Product.objects.get(slug="test-pan")
        image = ProductImage.objects.get(product=product)
        self.assertTrue(image.is_primary)          # auto-assigned
        self.assertTrue(image.thumbnail)           # thumbnail generated

    def test_two_primary_images_are_rejected_with_a_clear_error(self):
        payload = self._add_payload(
            **{
                "images-TOTAL_FORMS": "2",
                "images-0-image": uploaded_png("a.png"),
                "images-0-alt_text": "",
                "images-0-ordering": "0",
                "images-0-id": "",
                "images-0-product": "",
                "images-0-is_primary": "on",
                "images-1-image": uploaded_png("b.png"),
                "images-1-alt_text": "",
                "images-1-ordering": "1",
                "images-1-id": "",
                "images-1-product": "",
                "images-1-is_primary": "on",
            }
        )
        response = self.client.post(reverse("admin:products_product_add"), payload)
        self.assertContains(response, "فقط یک تصویر را به‌عنوان تصویر اصلی")
        self.assertFalse(Product.objects.filter(slug="test-pan").exists())

    def test_explicit_primary_choice_is_kept(self):
        payload = self._add_payload(
            **{
                "images-TOTAL_FORMS": "2",
                "images-0-image": uploaded_png("a.png"),
                "images-0-alt_text": "",
                "images-0-ordering": "0",
                "images-0-id": "",
                "images-0-product": "",
                "images-1-image": uploaded_png("b.png"),
                "images-1-alt_text": "",
                "images-1-ordering": "1",
                "images-1-id": "",
                "images-1-product": "",
                "images-1-is_primary": "on",
            }
        )
        response = self.client.post(reverse("admin:products_product_add"), payload, follow=True)
        self.assertEqual(response.status_code, 200)

        product = Product.objects.get(slug="test-pan")
        images = list(product.images.order_by("ordering"))
        self.assertEqual([img.is_primary for img in images], [False, True])
