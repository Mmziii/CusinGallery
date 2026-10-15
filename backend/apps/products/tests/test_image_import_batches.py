"""
Batched, resumable bulk image import (the 502 fix).

On the 1-vCPU production server a 176-image ZIP (1.7 MB) saved NOTHING:
the whole apply step ran inside one web request, gunicorn's `--timeout 60`
killed the worker mid-import, and the owner got a bare 502 with no
explanation and no rows.

The import is now a job: the dry run stores a work list, confirm STARTS it,
and the admin page drives it 20 images per request, each batch its own
transaction, with a progress bar and resume-after-reload.

Covered here, driven through real requests against the real view:
  * confirm writes nothing by itself -- it only starts the job
  * one request writes at most one batch
  * the JSON progress payload carries «در حال ذخیره: ۴۰ از ۱۷۶»
  * reloading the page resumes from the last committed batch
  * a 200-image ZIP imports completely (and in more than one batch)
  * a failure inside a batch is reported in Persian on the page, never 502
  * replace mode still swaps images across batches
"""
import io
import os
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from unittest import mock

from apps.products import image_import as image_import_module
from apps.products.image_import import (
    DEFAULT_BATCH_SIZE,
    fa_digits,
    ZipImageSource,
    apply_job_batch,
    build_plan,
    job_progress,
    new_job,
)
from apps.products.models import ProductImage

from .helpers import make_product
from .test_image_import import build_zip, png_bytes, zip_upload

TEMP_MEDIA = tempfile.mkdtemp(prefix="cusin-test-image-batches-")
PLAIN_STATIC = {
    "STORAGES": {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
}


@override_settings(MEDIA_ROOT=TEMP_MEDIA, **PLAIN_STATIC)
class BatchedImageImportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.staff = user_model.objects.create_superuser(
            username="owner", email="owner@example.com", password="pass-12345"
        )
        cls.add_url = reverse("admin:products_product_image_import")

    def setUp(self):
        shutil.rmtree(TEMP_MEDIA, ignore_errors=True)
        os.makedirs(TEMP_MEDIA, exist_ok=True)
        shutil.rmtree(self.stash_dir(), ignore_errors=True)
        self.client.force_login(self.staff)

    def tearDown(self):
        shutil.rmtree(TEMP_MEDIA, ignore_errors=True)
        shutil.rmtree(self.stash_dir(), ignore_errors=True)
        for leftover in os.listdir(tempfile.gettempdir()):
            if leftover.startswith("cusin-image-import-"):
                shutil.rmtree(os.path.join(tempfile.gettempdir(), leftover), ignore_errors=True)

    @staticmethod
    def stash_dir():
        return os.path.join(tempfile.gettempdir(), "cusin-product-image-imports")

    # -- helpers ---------------------------------------------------------

    def upload(self, entries, **extra):
        payload = build_zip(entries)
        data = {"zip": zip_upload(payload), "mode": "add"}
        data.update(extra)
        return self.client.post(self.add_url, data)

    def step(self, **headers):
        follow = headers.pop("follow", False)
        return self.client.post(self.add_url, {"step": "1"}, follow=follow, **headers)

    def step_json(self):
        return self.step(HTTP_X_REQUESTED_WITH="XMLHttpRequest")

    @staticmethod
    def many(product_count=20, images_each=10):
        """(products, zip entries, expected image count)."""
        products = []
        entries = []
        for index in range(product_count):
            sku = f"BULK-{index:04d}"
            products.append(make_product(name=f"کالا {index}", sku=sku))
            for image_index in range(images_each):
                suffix = "" if image_index == 0 else f"-{image_index}"
                entries.append((f"{sku}{suffix}.jpg", png_bytes((index % 255, image_index, 9))))
        return products, entries, product_count * images_each

    # -- unit level ------------------------------------------------------

    def test_a_batch_never_writes_more_than_the_batch_size(self):
        product = make_product(name="تک", sku="ONE-1")
        path = os.path.join(TEMP_MEDIA, "upload.zip")
        with open(path, "wb") as handle:
            handle.write(build_zip([(f"ONE-1-{n}.jpg", png_bytes((n, 1, 1))) for n in range(1, 8)]))
        extract = tempfile.mkdtemp(dir=TEMP_MEDIA, prefix="extract-")
        try:
            plan = build_plan(ZipImageSource(path), extract_dir=extract)
            job = new_job(plan, token="0" * 32, batch_size=3)
            self.assertEqual(job["total"], 7)
            apply_job_batch(job, ZipImageSource(path), extract_dir=extract)
            self.assertEqual(job["done"], 3, "one batch = batch_size images")
            self.assertEqual(job["status"], "running")
            self.assertEqual(product.images.count(), 3)
            apply_job_batch(job, ZipImageSource(path), extract_dir=extract)
            self.assertEqual(job["done"], 6)
            apply_job_batch(job, ZipImageSource(path), extract_dir=extract)
            self.assertEqual(job["done"], 7)
            self.assertEqual(job["status"], "done")
            self.assertEqual(product.images.count(), 7)
        finally:
            shutil.rmtree(extract, ignore_errors=True)

    def test_progress_label_is_persian_with_persian_digits(self):
        job = {"total": 176, "done": 40, "status": "running", "error": ""}
        self.assertEqual(job_progress(job)["label"], "در حال ذخیره: ۴۰ از ۱۷۶")
        self.assertEqual(job_progress(job)["percent"], 23)

    def test_a_broken_image_is_rejected_at_plan_time_and_never_queued(self):
        """One bad file must not stop the good ones, nor leave bytes behind."""
        product = make_product(name="خراب", sku="BAD-1")
        path = os.path.join(TEMP_MEDIA, "upload.zip")
        with open(path, "wb") as handle:
            handle.write(build_zip([("BAD-1-1.jpg", png_bytes((1, 1, 1))),
                                    ("BAD-1-2.jpg", b"not-an-image-at-all")]))
        extract = tempfile.mkdtemp(dir=TEMP_MEDIA, prefix="extract-")
        try:
            plan = build_plan(ZipImageSource(path), extract_dir=extract)
            self.assertEqual(plan.counts()["invalid"], 1)
            job = new_job(plan, token="0" * 32, batch_size=5)
            Queued = [member for step in job["steps"] for member in step["members"]]
            self.assertEqual(Queued, ["BAD-1-1.jpg"])
            apply_job_batch(job, ZipImageSource(path), extract_dir=extract)
            self.assertEqual(job["status"], "done")
            self.assertEqual(product.images.count(), 1)
            self.assertEqual(job["created"], 1)
        finally:
            shutil.rmtree(extract, ignore_errors=True)

    def test_a_member_that_fails_at_write_time_is_reported_in_persian(self):
        """Defence in depth: if validation fails DURING a batch (the file
        changed on disk between the plan and the write) the job records a
        Persian reason and carries on with the rest."""
        product = make_product(name="دیرهنگام", sku="LATE-1")
        path = os.path.join(TEMP_MEDIA, "upload.zip")
        with open(path, "wb") as handle:
            handle.write(build_zip([("LATE-1-1.jpg", png_bytes((1, 1, 1))),
                                    ("LATE-1-2.jpg", png_bytes((2, 2, 2)))]))
        extract = tempfile.mkdtemp(dir=TEMP_MEDIA, prefix="extract-")
        try:
            plan = build_plan(ZipImageSource(path), extract_dir=extract)
            job = new_job(plan, token="0" * 32, batch_size=5)
            real_validate = image_import_module._validate_extracted

            def picky(target):
                if os.path.basename(target).startswith("batch-00000"):
                    return False, "تصویر معتبر نیست (فقط JPEG، PNG، WEBP یا GIF)"
                return real_validate(target)

            image_import_module._validate_extracted = picky
            try:
                apply_job_batch(job, ZipImageSource(path), extract_dir=extract)
            finally:
                image_import_module._validate_extracted = real_validate
            self.assertEqual(job["status"], "done")
            self.assertEqual(len(job["problems"]), 1)
            self.assertTrue(job["problems"][0]["reason"])
            self.assertEqual(job["created"], 1, "the healthy member still saved")
            self.assertEqual(product.images.count(), 1)
        finally:
            shutil.rmtree(extract, ignore_errors=True)

    def test_a_batch_that_explodes_leaves_no_orphaned_files(self):
        """The transaction rolls back AND the bytes it wrote are deleted."""
        make_product(name="انفجار", sku="BOOM-1")
        path = os.path.join(TEMP_MEDIA, "upload.zip")
        with open(path, "wb") as handle:
            handle.write(build_zip([("BOOM-1-1.jpg", png_bytes((1, 1, 1))),
                                    ("BOOM-1-2.jpg", png_bytes((2, 2, 2)))]))
        # Outside MEDIA_ROOT: the plan's own extraction must not be counted
        # as "stored" -- only what the batch wrote is under test here.
        extract = tempfile.mkdtemp(prefix="cusin-batch-extract-")
        try:
            plan = build_plan(ZipImageSource(path), extract_dir=extract)
            job = new_job(plan, token="0" * 32, batch_size=5)
            with mock.patch.object(
                image_import_module.ProductImage, "save", side_effect=RuntimeError("boom")
            ):
                with self.assertRaises(RuntimeError):
                    apply_job_batch(job, ZipImageSource(path), extract_dir=extract)
            self.assertEqual(ProductImage.objects.count(), 0)
            stored = [
                name
                for _dir, _sub, files in os.walk(TEMP_MEDIA)
                for name in files
                if name != "upload.zip"
            ]
            self.assertEqual(stored, [], f"orphaned files after rollback: {stored}")
        finally:
            shutil.rmtree(extract, ignore_errors=True)

    # -- through the admin view ------------------------------------------

    def test_confirm_only_starts_the_job_it_does_not_write(self):
        product = make_product(name="شروع", sku="START-1")
        self.upload([("START-1.jpg", png_bytes((1, 2, 3)))])
        response = self.client.post(self.add_url, {"confirm": "1"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(ProductImage.objects.count(), 0)
        self.assertIn("در حال ذخیره", response.content.decode())

    def test_progress_json_reports_done_over_total(self):
        products, entries, total = self.many(product_count=6, images_each=4)
        self.upload(entries)
        self.client.post(self.add_url, {"confirm": "1"})
        payload = self.step_json().json()
        self.assertEqual(payload["total"], total)
        self.assertEqual(payload["done"], DEFAULT_BATCH_SIZE)
        self.assertFalse(payload["finished"])
        self.assertEqual(
            payload["label"],
            "در حال ذخیره: ۲۰ از " + fa_digits(total),
        )

    def test_reloading_the_page_resumes_instead_of_starting_over(self):
        """The whole point: a reload (or a killed worker) must not lose work."""
        products, entries, total = self.many(product_count=8, images_each=4)
        self.upload(entries)
        self.client.post(self.add_url, {"confirm": "1"})
        self.step()  # one batch, committed
        self.assertEqual(ProductImage.objects.count(), DEFAULT_BATCH_SIZE)

        # "Reload": a plain GET on the page shows the job's progress again.
        page = self.client.get(self.add_url)
        content = page.content.decode()
        self.assertIn("در حال ذخیره", content)
        self.assertIn(f"{DEFAULT_BATCH_SIZE}", content)

        # ...and carrying on does NOT restart from zero.
        self.step_json()
        self.assertEqual(ProductImage.objects.count(), total)

        while True:
            payload = self.step_json().json()
            self.assertNotEqual(payload["status"], "error", payload.get("error"))
            if payload["finished"]:
                break
        self.assertEqual(ProductImage.objects.count(), total)

    def test_a_two_hundred_image_zip_imports_completely(self):
        """The reported failure: 176 images saved nothing. Try 200."""
        products, entries, total = self.many(product_count=20, images_each=10)
        self.assertEqual(total, 200)
        self.upload(entries)
        self.client.post(self.add_url, {"confirm": "1"})

        batches = 0
        payload = None
        while True:
            payload = self.step_json().json()
            batches += 1
            self.assertNotEqual(payload["status"], "error", payload.get("error"))
            if payload["finished"]:
                break
            self.assertLess(batches, 50, "the job did not converge")
        self.assertGreater(batches, 1, "a 200-image import must take several batches")
        self.assertEqual(payload["done"], 200)
        self.assertEqual(ProductImage.objects.count(), 200)
        self.assertEqual(payload["summary"]["created"], 200)
        self.assertEqual(payload["summary"]["products"], 20)
        for product in products:
            self.assertEqual(product.images.count(), 10)
            self.assertEqual(product.images.filter(is_primary=True).count(), 1)

    def test_replace_mode_across_batches_swaps_every_image(self):
        product = make_product(name="جایگزین", sku="SWAP-1")
        product.images.create(image="products/old.jpg", ordering=0, is_primary=True)
        entries = [(f"SWAP-1-{n}.jpg", png_bytes((n, 2, 2))) for n in range(1, 6)]
        self.upload(entries, mode="replace")
        self.client.post(self.add_url, {"confirm": "1"})
        with override_settings(PRODUCT_IMAGE_IMPORT_BATCH_SIZE=2):
            while not self.step_json().json()["finished"]:
                pass
        product.refresh_from_db()
        self.assertEqual(product.images.count(), 5)
        self.assertEqual(product.images.filter(is_primary=True).count(), 1)
        self.assertFalse(any("old.jpg" in image.image.name for image in product.images.all()))

    def test_a_server_error_shows_persian_on_the_page_not_a_502(self):
        """The ZIP disappears mid-job: the page must still render, in Persian."""
        make_product(name="خطا", sku="ERR-1")
        self.upload([("ERR-1.jpg", png_bytes((1, 1, 1)))])
        self.client.post(self.add_url, {"confirm": "1"})
        for name in os.listdir(self.stash_dir()):
            if name.endswith(".zip"):
                os.remove(os.path.join(self.stash_dir(), name))
        response = self.step()
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("دوباره بارگذاری", content)
        self.assertNotIn("Traceback", content)

    def test_the_final_page_links_the_report_and_the_catalog(self):
        make_product(name="پایان", sku="END-1")
        self.upload([("END-1.jpg", png_bytes((1, 1, 1)))])
        self.client.post(self.add_url, {"confirm": "1"})
        response = self.step(follow=True)
        content = response.content.decode()
        self.assertIn("تصاویر ذخیره شد", content)
        report = self.client.get(self.add_url + "?report=csv")
        self.assertEqual(report.status_code, 200)
        self.assertIn("ذخیره شد", report.content.decode("utf-8-sig"))

    def test_the_preview_page_disables_the_confirm_button_while_working(self):
        """The owner must not be able to fire the same job twice."""
        make_product(name="دکمه", sku="BTN-1")
        response = self.upload([("BTN-1.jpg", png_bytes((1, 1, 1)))])
        content = response.content.decode()
        self.assertIn('id="cusin-image-import-confirm-button"', content)
        self.assertIn("confirmButton.disabled = true", content)
        self.assertIn("در حال آماده‌سازی", content)

    def test_cancel_drops_the_job_file_too(self):
        make_product(name="لغو", sku="CANCEL-9")
        self.upload([("CANCEL-9.jpg", png_bytes((1, 1, 1)))])
        self.client.post(self.add_url, {"cancel": "1"}, follow=True)
        self.assertEqual(ProductImage.objects.count(), 0)
        leftovers = os.listdir(self.stash_dir()) if os.path.isdir(self.stash_dir()) else []
        self.assertEqual(leftovers, [])
        # A late step POST cannot resurrect it.
        self.step()
        self.assertEqual(ProductImage.objects.count(), 0)

    def test_an_empty_plan_finishes_immediately(self):
        """A ZIP with nothing to do must not leave the page spinning."""
        make_product(name="بی‌کار", sku="IDLE-1")
        self.upload([("notes.txt", b"junk")])
        response = self.client.post(self.add_url, {"confirm": "1"}, follow=True)
        self.assertEqual(ProductImage.objects.count(), 0)
        self.assertIn("هیچ تصویری ذخیره نشد", response.content.decode())
