"""
The admin half of the bulk image import: the real button on the product
changelist, the real upload page, the dry-run preview (which must write
NOTHING), the confirm step (which writes everything in one transaction),
the CSV report download, cancel, and staff-only access.

Everything is driven through real multipart POSTs against the real
templates; the ZIPs are real ZIP bytes and the images real PNGs.
"""
import io
import os
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.products.models import ProductImage

from .helpers import make_product
from .test_image_import import build_zip, png_bytes, zip_upload

TEMP_MEDIA = tempfile.mkdtemp(prefix="cusin-test-image-import-admin-")
PLAIN_STATIC = {
    "STORAGES": {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
}


@override_settings(MEDIA_ROOT=TEMP_MEDIA, **PLAIN_STATIC)
class ImageImportAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.staff = user_model.objects.create_superuser(
            username="owner", email="owner@example.com", password="pass-12345"
        )
        cls.visitor = user_model.objects.create_user(
            username="visitor", email="visitor@example.com", password="pass-12345"
        )
        cls.add_url = reverse("admin:products_product_image_import")

    def setUp(self):
        shutil.rmtree(TEMP_MEDIA, ignore_errors=True)
        os.makedirs(TEMP_MEDIA, exist_ok=True)
        self.client.force_login(self.staff)

    def tearDown(self):
        shutil.rmtree(TEMP_MEDIA, ignore_errors=True)
        for leftover in os.listdir(tempfile.gettempdir()):
            if leftover.startswith("cusin-image-import-"):
                shutil.rmtree(os.path.join(tempfile.gettempdir(), leftover), ignore_errors=True)

    def test_the_button_is_on_the_product_list_and_points_at_the_page(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("admin:products_product_changelist"))
        content = response.content.decode()
        self.assertIn("ورود گروهی تصاویر (فایل زیپ)", content)
        self.assertIn(self.add_url, content)
        self.assertIn("راهنمای نام‌گذاری", content)

    def test_the_upload_page_spells_out_the_naming_rules(self):
        response = self.client.get(self.add_url)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("SOOLE-001.jpg", content)
        self.assertIn("SOOLE-001 (2).jpg", content)
        self.assertIn("jpeg", content.lower())
        self.assertIn("۵ مگابایت", content)

    def test_the_page_is_staff_only(self):
        self.client.force_login(self.visitor)
        response = self.client.get(self.add_url)
        self.assertIn(response.status_code, (302, 403))
        if response.status_code == 302:
            self.assertIn("/admin/login/", response["Location"])

    def test_the_dry_run_shows_the_plan_and_writes_nothing(self):
        product = make_product(name="کاسه بلور", sku="SOOLE-001")
        payload = build_zip([
            ("SOOLE-001.jpg", png_bytes((1, 1, 1))),
            ("SOOLE-002.jpg", png_bytes((2, 2, 2))),  # unknown SKU
            ("notes.txt", b"junk"),  # ignored
        ])
        response = self.client.post(self.add_url, {"zip": zip_upload(payload), "mode": "add"})
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("هنوز چیزی ذخیره نشده", content)
        self.assertIn("کاسه بلور", content)
        self.assertIn("SOOLE-002.jpg", content)
        self.assertIn("notes.txt", content)
        self.assertIn("data:image/jpeg;base64,", content)  # a real preview thumb
        # Nothing written, and no product image row.
        self.assertEqual(ProductImage.objects.count(), 0)
        self.assertFalse(
            os.path.exists(os.path.join(TEMP_MEDIA, "products")),
            "the dry run must not write into MEDIA_ROOT",
        )

    def test_confirm_writes_the_images_and_a_success_message(self):
        product = make_product(name="کاسه بلور", sku="SOOLE-001")
        payload = build_zip([
            ("SOOLE-001.jpg", png_bytes((1, 1, 1))),
            ("SOOLE-001-2.jpg", png_bytes((2, 2, 2))),
        ])
        self.client.post(self.add_url, {"zip": zip_upload(payload), "mode": "add"})
        response = self.client.post(self.add_url, {"confirm": "1"}, follow=True)
        content = response.content.decode()
        self.assertEqual(response.status_code, 200)
        self.assertIn("تصاویر ذخیره شد", content)
        self.assertEqual(product.images.count(), 2)
        self.assertTrue(product.images.order_by("ordering").first().is_primary)

    def test_confirm_without_a_preview_is_refused(self):
        response = self.client.post(self.add_url, {"confirm": "1"}, follow=True)
        self.assertIn("پیش‌نمایشی برای تأیید وجود ندارد", response.content.decode())
        self.assertEqual(ProductImage.objects.count(), 0)

    def test_replace_mode_via_the_page_swaps_the_images(self):
        product = make_product(name="دیگ", sku="POT-9")
        product.images.create(image="products/old.jpg", ordering=0, is_primary=True)
        payload = build_zip([("POT-9.jpg", png_bytes((3, 3, 3)))])
        preview = self.client.post(
            self.add_url, {"zip": zip_upload(payload), "mode": "replace"}
        )
        self.assertIn("جایگزینی تصاویر موجود", preview.content.decode())
        self.client.post(self.add_url, {"confirm": "1"})
        product.refresh_from_db()
        self.assertEqual(product.images.count(), 1)
        self.assertNotIn("old.jpg", product.images.get().image.name)

    def test_skip_existing_via_the_page(self):
        with_image = make_product(name="با تصویر", sku="HAS-9")
        with_image.images.create(image="products/has.jpg", ordering=0, is_primary=True)
        without = make_product(name="بی تصویر", sku="NONE-9")
        payload = build_zip([
            ("HAS-9.jpg", png_bytes((4, 4, 4))),
            ("NONE-9.jpg", png_bytes((5, 5, 5))),
        ])
        preview = self.client.post(
            self.add_url, {"zip": zip_upload(payload), "mode": "add", "skip_existing": "1"}
        )
        self.assertIn("نادیده گرفته می‌شوند", preview.content.decode())
        self.client.post(self.add_url, {"confirm": "1"})
        self.assertEqual(with_image.images.count(), 1)
        self.assertEqual(without.images.count(), 1)

    def test_cancel_writes_nothing_and_forgets_the_preview(self):
        product = make_product(name="لغو", sku="CANCEL-1")
        payload = build_zip([("CANCEL-1.jpg", png_bytes((6, 6, 6)))])
        self.client.post(self.add_url, {"zip": zip_upload(payload), "mode": "add"})
        response = self.client.post(self.add_url, {"cancel": "1"}, follow=True)
        self.assertIn("عملیات لغو شد", response.content.decode())
        self.assertEqual(product.images.count(), 0)
        # A later confirm cannot resurrect the canceled upload.
        self.client.post(self.add_url, {"confirm": "1"}, follow=True)
        self.assertEqual(product.images.count(), 0)

    def test_a_hostile_zip_is_refused_with_an_error_page(self):
        make_product(name="امن", sku="SAFE-9")
        payload = build_zip([{"name": "../escape.jpg", "payload": png_bytes()}])
        response = self.client.post(self.add_url, {"zip": zip_upload(payload), "mode": "add"})
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("بارگذاری انجام نشد", content)
        self.assertIn("ناامن", content.replace("\u200c", ""))
        self.assertFalse(os.path.exists(os.path.join(TEMP_MEDIA, "products")))
        # The temp stash must be gone too.
        stash = os.path.join(tempfile.gettempdir(), "cusin-product-image-imports")
        self.assertEqual([name for name in os.listdir(stash)] if os.path.isdir(stash) else [], [])

    def test_the_csv_report_downloads_and_describes_the_run(self):
        make_product(name="گزارش", sku="REP-9")
        payload = build_zip([
            ("REP-9.jpg", png_bytes((7, 7, 7))),
            ("NOPE-1.jpg", png_bytes((8, 8, 8))),
        ])
        self.client.post(self.add_url, {"zip": zip_upload(payload), "mode": "add"})
        response = self.client.get(self.add_url + "?report=csv")
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])
        text = response.content.decode("utf-8-sig")
        self.assertIn("REP-9.jpg", text)
        self.assertIn("گزارش", text)
        self.assertIn("NOPE-1.jpg", text)

    def test_another_upload_replaces_the_stashed_zip(self):
        """The previous ZIP must not linger (or be reusable)."""
        make_product(name="یکی", sku="ONE-9")
        first = build_zip([("ONE-9.jpg", png_bytes((1, 1, 1)))])
        self.client.post(self.add_url, {"zip": zip_upload(first), "mode": "add"})
        stash = os.path.join(tempfile.gettempdir(), "cusin-product-image-imports")
        self.assertEqual(len(os.listdir(stash)), 1)

        second = build_zip([("ONE-9-2.jpg", png_bytes((2, 2, 2)))])
        self.client.post(self.add_url, {"zip": zip_upload(second), "mode": "add"})
        self.assertEqual(len(os.listdir(stash)), 1)

    def test_no_file_selected_shows_a_friendly_error(self):
        response = self.client.post(self.add_url, {"mode": "add"})
        self.assertIn("فایلی انتخاب نشده است", response.content.decode())
