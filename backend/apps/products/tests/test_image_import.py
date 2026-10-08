"""
Bulk product image import from a ZIP, matched by SKU (feature tests).

Real behaviour only: the ZIPs are real ZIP bytes written by zipfile, the
images are real PNGs decoded by Pillow, the writes go through the real
ProductImage.save() path (thumbnail + WebP variants) against a temporary
MEDIA_ROOT, and the admin flow is driven by real multipart POSTs through
the real templates.

Covered here: every naming pattern, Persian digits, hyphen SKUs, the
folder-per-product form, ordering + primary image, ignored junk, add /
replace / skip-existing, re-upload idempotency, invalid files that do not
break the rest, dry-run writing nothing, zip-slip / symlink / nested
archive / zip-bomb / limit rejection, and rollback cleaning up both rows
and the files it wrote.
"""
import io
import os
import shutil
import tempfile
import zipfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from apps.products.image_import import (
    ZipImageSource,
    apply_plan,
    build_plan,
    ignored_reason,
    member_problem,
    sku_key,
    split_sku_and_suffix,
)

from .helpers import make_product

TEMP_MEDIA = tempfile.mkdtemp(prefix="cusin-test-image-import-")
PLAIN_STATIC = {
    "STORAGES": {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
}


from contextlib import contextmanager


@contextmanager
def _no_settings():
    yield


def png_bytes(color=(200, 30, 30), size=(400, 400), fmt="PNG"):
    """A small but REAL image (Pillow encodes it; the validator decodes it)."""
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format=fmt)
    return buffer.getvalue()


def build_zip(entries, name="images.zip"):
    """entries: list of (member name, bytes|None) -- None makes a directory
    entry; a member may also be a dict for the hostile shapes."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for entry in entries:
            if isinstance(entry, dict):
                info = zipfile.ZipInfo(entry["name"])
                info.external_attr = entry.get("external_attr", 0)
                archive.writestr(info, entry.get("payload", b""))
                continue
            member_name, payload = entry
            if payload is None:
                archive.writestr(zipfile.ZipInfo(member_name.rstrip("/") + "/"), b"")
            else:
                archive.writestr(member_name, payload)
    return buffer.getvalue()


def zip_upload(payload, name="images.zip"):
    return SimpleUploadedFile(name, payload, content_type="application/zip")


@override_settings(MEDIA_ROOT=TEMP_MEDIA, **PLAIN_STATIC)
class ImageImportTestCase(TestCase):
    """Shared plumbing: a temp MEDIA_ROOT and a helper that runs one import
    exactly like the admin/CLI does (build plan -> apply)."""

    def setUp(self):
        shutil.rmtree(TEMP_MEDIA, ignore_errors=True)
        os.makedirs(TEMP_MEDIA, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(TEMP_MEDIA, ignore_errors=True)

    def build_only(self, entries, *, mode="add", skip_existing=False, thumbs=False, **limit_overrides):
        """Write the ZIP to disk (the importer reads a real file) and run the
        DRY RUN: this is exactly what the preview does, and it must not
        write anything."""
        path = os.path.join(TEMP_MEDIA, "upload.zip")
        with open(path, "wb") as handle:
            handle.write(build_zip(entries))
        extract_dir = tempfile.mkdtemp(dir=TEMP_MEDIA, prefix="extract-")
        try:
            with override_settings(**limit_overrides) if limit_overrides else _no_settings():
                return build_plan(
                    ZipImageSource(path), mode=mode,
                    skip_existing=skip_existing, extract_dir=extract_dir, thumbs=thumbs,
                )
        finally:
            shutil.rmtree(extract_dir, ignore_errors=True)

    def run_import(self, entries, *, mode="add", skip_existing=False, thumbs=False, **limit_overrides):
        """Dry run, then apply. The extracted files must outlive the plan, so
        the temp directory is kept until both steps are done -- exactly like
        the admin view, which applies before cleaning its temp dir up."""
        path = os.path.join(TEMP_MEDIA, "upload.zip")
        with open(path, "wb") as handle:
            handle.write(build_zip(entries))
        extract_dir = tempfile.mkdtemp(dir=TEMP_MEDIA, prefix="extract-")
        try:
            with override_settings(**limit_overrides) if limit_overrides else _no_settings():
                plan = build_plan(
                    ZipImageSource(path), mode=mode,
                    skip_existing=skip_existing, extract_dir=extract_dir, thumbs=thumbs,
                )
                if not plan.ok:
                    return plan, None
                result = apply_plan(plan) if plan.counts()["add"] else None
                return plan, result
        finally:
            shutil.rmtree(extract_dir, ignore_errors=True)

    plan_only = build_only

    def stored_files(self):
        """Every file currently in MEDIA_ROOT (to prove cleanup)."""
        found = []
        for directory, _dirs, files in os.walk(TEMP_MEDIA):
            for name in files:
                if name == "upload.zip":
                    continue
                found.append(os.path.relpath(os.path.join(directory, name), TEMP_MEDIA))
        return sorted(found)


class SkuMatchingTests(ImageImportTestCase):
    def setUp(self):
        super().setUp()
        self.product = make_product(name="کاسه بلور", sku="SOOLE-001")

    def status_by_member(self, plan):
        return {item.member: item.status for item in plan.files}

    def test_every_naming_pattern_matches_the_same_product(self):
        entries = [
            ("SOOLE-001.jpg", png_bytes((10, 10, 10))),
            ("SOOLE-001-2.jpg", png_bytes((20, 20, 20))),
            ("SOOLE-001_3.jpg", png_bytes((30, 30, 30))),
            ("SOOLE-001 (4).jpg", png_bytes((40, 40, 40))),
            ("SOOLE-001/5.jpg", png_bytes((50, 50, 50))),
            ("SOOLE-001/6.jpg", png_bytes((60, 60, 60))),
        ]
        plan = self.plan_only(entries)
        statuses = self.status_by_member(plan)
        self.assertEqual(statuses["SOOLE-001.jpg"], "add")
        for name in ("SOOLE-001-2.jpg", "SOOLE-001_3.jpg", "SOOLE-001 (4).jpg",
                     "SOOLE-001/5.jpg", "SOOLE-001/6.jpg"):
            self.assertEqual(statuses[name], "add", name)
        self.assertEqual([item.suffix for item in plan.files], [1, 2, 3, 4, 5, 6])
        self.assertEqual(len(plan.writing_groups), 1)
        self.assertEqual(plan.writing_groups[0].product, self.product)

    def test_persian_digits_in_file_names_are_normalized(self):
        plan = self.plan_only([("SOOLE-۰۰۱-۲.jpg", png_bytes((11, 22, 33)))])
        item = plan.files[0]
        self.assertEqual(item.status, "add")
        self.assertEqual(item.suffix, 2)
        self.assertEqual(item.product_id, self.product.pk)

    def test_case_and_surrounding_spaces_do_not_matter(self):
        plan = self.plan_only([("  soole-001 .JPG", png_bytes((7, 7, 7)))])
        self.assertEqual(plan.files[0].status, "add")
        self.assertEqual(plan.files[0].product_id, self.product.pk)

    def test_the_whole_name_is_tried_before_a_numeric_suffix(self):
        """A SKU ending in a number must win over suffix parsing."""
        other = make_product(name="قابلمه", sku="SOOLE")
        plan = self.plan_only([("SOOLE-001.jpg", png_bytes((9, 9, 9)))])
        self.assertEqual(plan.files[0].product_id, self.product.pk)
        self.assertNotEqual(plan.files[0].product_id, other.pk)
        self.assertEqual(plan.files[0].suffix, 1)

        # ...and with only SOOLE in the catalog, the same name IS suffix 1.
        self.product.delete()
        plan = self.plan_only([("SOOLE-001.jpg", png_bytes((9, 9, 9)))])
        self.assertEqual(plan.files[0].product_id, other.pk)
        self.assertEqual(plan.files[0].suffix, 1)

    def test_split_helper_is_sku_lookup_first_then_suffix(self):
        index, by_object = {}, {}
        index["soole-001"] = "A"
        index["soole"] = "B"
        self.assertEqual(split_sku_and_suffix("SOOLE-001.jpg", index), ("A", 1))
        self.assertEqual(split_sku_and_suffix("SOOLE-2.jpg", index), ("B", 2))
        self.assertEqual(split_sku_and_suffix("SOOLE (3).jpg", index), ("B", 3))
        self.assertEqual(split_sku_and_suffix("nope-1.jpg", index), (None, None))
        self.assertEqual(sku_key(" SOOLE-۰۰۱ "), "soole-001")

    def test_folder_per_product_without_a_numeric_name_is_image_one(self):
        plan = self.plan_only([("SOOLE-001/نمای-جلو.jpg", png_bytes((3, 3, 3)))])
        self.assertEqual(plan.files[0].status, "add")
        self.assertEqual(plan.files[0].suffix, 1)

    def test_unknown_sku_is_reported_as_unmatched(self):
        plan = self.plan_only([("NOPE-9.jpg", png_bytes((5, 5, 5)))])
        self.assertEqual(plan.files[0].status, "unmatched")
        self.assertEqual(plan.counts()["add"], 0)


class IgnoredJunkTests(ImageImportTestCase):
    def test_junk_and_non_images_are_ignored_with_reasons(self):
        make_product(name="ماگ", sku="MUG-001")
        plan = self.plan_only([
            ("__MACOSX/._MUG-001.jpg", png_bytes()),
            (".DS_Store", b"junk"),
            ("Thumbs.db", b"junk"),
            (".hidden-MUG-001.jpg", png_bytes()),
            ("notes.txt", b"hello"),
            ("backup.zip", b"PK\x03\x04"),
            ("folder/", None),
            ("MUG-001.jpg", png_bytes((1, 2, 3))),
        ])
        reasons = {item.member: item.reason for item in plan.ignored}
        self.assertIn("__MACOSX/._MUG-001.jpg", reasons)
        self.assertIn(".DS_Store", reasons)
        self.assertIn("Thumbs.db", reasons)
        self.assertIn(".hidden-MUG-001.jpg", reasons)
        self.assertIn("notes.txt", reasons)
        self.assertIn("backup.zip", reasons)
        self.assertIn("folder/", reasons)
        self.assertEqual(plan.counts()["add"], 1)
        self.assertEqual(plan.counts()["ignored"], 7)
        self.assertEqual(ignored_reason("MUG-001.jpg"), "")
        self.assertEqual(member_problem("MUG-001.jpg"), "")


class OrderingAndPrimaryTests(ImageImportTestCase):
    def test_order_by_suffix_and_first_becomes_primary(self):
        product = make_product(name="سرویس", sku="SET-1")
        plan, result = self.run_import([
            ("SET-1_3.jpg", png_bytes((3, 3, 3))),
            ("SET-1.jpg", png_bytes((1, 1, 1))),
            ("SET-1-2.jpg", png_bytes((2, 2, 2))),
        ])
        self.assertEqual(result["created"], 3)
        images = list(product.images.order_by("ordering"))
        self.assertEqual(len(images), 3)
        # File name 3 was written first but the SUFFIX decides the order.
        self.assertTrue(images[0].is_primary)
        self.assertEqual([image.ordering for image in images], [0, 1, 2])
        self.assertEqual(
            sum(1 for image in images if image.is_primary), 1
        )
        # The primary is the one whose content came from SET-1.jpg
        with open(os.path.join(TEMP_MEDIA, images[0].image.name), "rb") as handle:
            self.assertEqual(handle.read(), png_bytes((1, 1, 1)))

    def test_add_mode_keeps_the_existing_primary_and_appends_after_it(self):
        product = make_product(name="قوری", sku="TEAPOT-7")
        existing = product.images.create(image=f"products/keep-{product.pk}.jpg",
                                         is_primary=True, ordering=0)
        plan, result = self.run_import([("TEAPOT-7-9.jpg", png_bytes((77, 77, 77)))])
        self.assertEqual(result["created"], 1)
        existing.refresh_from_db()
        self.assertTrue(existing.is_primary)
        new = product.images.exclude(pk=existing.pk).get()
        self.assertFalse(new.is_primary)
        self.assertEqual(new.ordering, 1)

    def test_replace_mode_removes_the_old_rows_and_makes_the_new_first_primary(self):
        product = make_product(name="دیگ", sku="POT-2")
        product.images.create(image="products/old.jpg", is_primary=True, ordering=0)
        plan, result = self.run_import(
            [("POT-2-2.jpg", png_bytes((2, 2, 2))), ("POT-2.jpg", png_bytes((1, 1, 1)))],
            mode="replace",
        )
        self.assertEqual(result["replaced"], 1)
        self.assertEqual(result["created"], 2)
        images = list(product.images.order_by("ordering"))
        self.assertEqual(len(images), 2)
        self.assertTrue(images[0].is_primary)
        self.assertEqual([image.ordering for image in images], [0, 1])


class ModeTests(ImageImportTestCase):
    def test_add_is_the_default_and_never_touches_existing_images(self):
        product = make_product(name="کاسه", sku="BOWL-1")
        product.images.create(image="products/existing.jpg", ordering=0)
        plan, result = self.run_import([("BOWL-1-2.jpg", png_bytes((4, 4, 4)))])
        self.assertEqual(plan.mode, "add")
        self.assertEqual(result["created"], 1)
        self.assertEqual(product.images.count(), 2)

    def test_skip_existing_leaves_products_with_images_alone(self):
        with_image = make_product(name="با تصویر", sku="HAS-1")
        with_image.images.create(image="products/has.jpg", ordering=0)
        without = make_product(name="بی تصویر", sku="NONE-1")
        plan, result = self.run_import(
            [("HAS-1.jpg", png_bytes((8, 8, 8))), ("NONE-1.jpg", png_bytes((9, 9, 9)))],
            skip_existing=True,
        )
        self.assertEqual(with_image.images.count(), 1)
        self.assertEqual(without.images.count(), 1)
        self.assertEqual(result["created"], 1)
        skipped = [item for item in plan.files if item.status == "skip"]
        self.assertEqual([item.sku for item in skipped], ["HAS-1"])
        self.assertEqual(plan.counts()["skip"], 1)

    def test_re_uploading_the_same_zip_adds_nothing_the_second_time(self):
        product = make_product(name="لیوان", sku="GLASS-1")
        entries = [
            ("GLASS-1.jpg", png_bytes((1, 1, 1))),
            ("GLASS-1-2.jpg", png_bytes((2, 2, 2))),
        ]
        _plan, first = self.run_import(entries)
        self.assertEqual(first["created"], 2)

        plan2, second = self.run_import(entries)
        self.assertIsNone(second)  # nothing to write
        self.assertEqual(product.images.count(), 2)
        self.assertEqual(plan2.counts()["add"], 0)
        self.assertEqual(plan2.counts()["duplicate"], 2)
        self.assertTrue(
            all("از قبل برای این محصول" in item.reason for item in plan2.duplicates)
        )

    def test_duplicate_content_inside_one_zip_is_kept_once(self):
        product = make_product(name="بشقاب", sku="PLATE-1")
        payload = png_bytes((5, 5, 5))
        plan, result = self.run_import([
            ("PLATE-1.jpg", payload),
            ("PLATE-1-2.jpg", payload),  # same bytes, different slot
        ])
        self.assertEqual(result["created"], 1)
        self.assertEqual(plan.counts()["duplicate"], 1)


class ValidationTests(ImageImportTestCase):
    def test_an_invalid_file_is_reported_and_the_others_still_import(self):
        product = make_product(name="کتری", sku="KETTLE-1")
        plan, result = self.run_import([
            ("KETTLE-1.jpg", b"this is not an image"),
            ("KETTLE-1-2.jpg", png_bytes((6, 6, 6))),
        ])
        self.assertEqual(result["created"], 1)
        self.assertEqual(product.images.count(), 1)
        invalid = plan.invalid
        self.assertEqual([item.member for item in invalid], ["KETTLE-1.jpg"])
        self.assertIn("تصویر معتبر نیست", invalid[0].reason)

    def test_a_text_file_renamed_to_jpg_is_rejected_by_content(self):
        make_product(name="کاربردی", sku="TXT-1")
        plan, result = self.run_import([("TXT-1.jpg", b"<?php echo 1; ?>")])
        self.assertIsNone(result)
        self.assertEqual(plan.counts()["invalid"], 1)
        self.assertEqual(plan.counts()["add"], 0)

    def test_files_over_the_size_limit_are_rejected(self):
        make_product(name="بزرگ", sku="BIG-1")
        plan = self.plan_only(
            [("BIG-1.jpg", png_bytes((1, 1, 1)))],
            PRODUCT_IMAGE_IMPORT_MAX_FILE_SIZE=100,
        )
        self.assertEqual(plan.counts()["invalid"], 1)
        self.assertIn("بیش از", plan.invalid[0].reason)

    def test_imported_images_get_a_thumbnail_and_webp_variants(self):
        product = make_product(name="گلدان", sku="VASE-1")
        _plan, result = self.run_import([("VASE-1.jpg", png_bytes((9, 9, 9), size=(1200, 1200)))])
        self.assertEqual(result["created"], 1)
        image = product.images.get()
        self.assertTrue(image.thumbnail)
        self.assertTrue(os.path.exists(os.path.join(TEMP_MEDIA, image.thumbnail.name)))
        self.assertTrue(image.webp_400 and image.webp_800 and image.webp_1200)
        for name in (image.webp_400, image.webp_800, image.webp_1200):
            self.assertTrue(os.path.exists(os.path.join(TEMP_MEDIA, name)), name)


class ZipSafetyTests(ImageImportTestCase):
    def test_path_traversal_and_absolute_paths_are_rejected(self):
        make_product(name="امن", sku="SAFE-1")
        plan = self.plan_only([
            {"name": "../outside.jpg", "payload": png_bytes()},
            {"name": "/etc/outside.jpg", "payload": png_bytes()},
            {"name": "C:\\Windows\\outside.jpg", "payload": png_bytes()},
            {"name": "sub/../../outside.jpg", "payload": png_bytes()},
        ])
        self.assertEqual(plan.counts()["unsafe"], 4)
        self.assertEqual(plan.counts()["add"], 0)
        # Nothing escaped: no file was written outside MEDIA_ROOT either.
        self.assertEqual(self.stored_files(), [])
        self.assertTrue(all("فایل زیپ" in item.reason for item in plan.unsafe))

    def test_one_unsafe_member_rejects_the_whole_zip(self):
        """A ZIP that tries to escape is refused as a whole: the good image
        next to the hostile one is NOT imported either."""
        product = make_product(name="همراه", sku="ALONG-1")
        plan, result = self.run_import([
            ("ALONG-1.jpg", png_bytes((1, 1, 1))),
            {"name": "../../escape.jpg", "payload": png_bytes((2, 2, 2))},
        ])
        self.assertFalse(plan.ok)
        self.assertIsNone(result)  # nothing was applied
        self.assertEqual(product.images.count(), 0)
        self.assertEqual(plan.unsafe[0].member, "../../escape.jpg")
        self.assertIn("مسیر ناامن", plan.errors[0])
        # The report still names the good file the owner would have to fix.
        self.assertEqual(self.stored_files(), [])

    def test_symlink_members_are_rejected(self):
        make_product(name="لینک", sku="LINK-1")
        plan = self.plan_only([
            {"name": "LINK-1.jpg", "payload": png_bytes(), "external_attr": (0o120777 << 16)},
        ])
        self.assertEqual(plan.counts()["unsafe"], 1)
        self.assertIn("symlink", plan.unsafe[0].reason)

    def test_nested_archives_are_ignored(self):
        plan = self.plan_only([("photos.zip", b"PK\x03\x04rest")])
        self.assertEqual(plan.counts()["ignored"], 1)
        self.assertIn("تودرتو", plan.ignored[0].reason)

    def test_too_many_files_is_rejected_before_anything_is_read(self):
        make_product(name="زیاد", sku="MANY-1")
        entries = [(f"MANY-1-{index}.jpg", png_bytes()) for index in range(6)]
        plan = self.plan_only(entries, PRODUCT_IMAGE_IMPORT_MAX_FILES=5)
        self.assertFalse(plan.ok)
        self.assertIn("تعداد فایل‌های داخل زیپ", plan.errors[0])
        self.assertIsNone(self.run_import(entries, PRODUCT_IMAGE_IMPORT_MAX_FILES=5)[1])

    def test_total_uncompressed_size_limit_is_enforced(self):
        make_product(name="حجیم", sku="HUGE-1")
        entries = [("HUGE-1.jpg", png_bytes((1, 2, 3), size=(300, 300)))]
        plan = self.plan_only(entries, PRODUCT_IMAGE_IMPORT_MAX_TOTAL_UNCOMPRESSED=50)
        self.assertFalse(plan.ok)
        self.assertIn("حجم باز‌شدهٔ زیپ", plan.errors[0])

    def test_the_zip_filename_size_limit_is_enforced(self):
        make_product(name="زیپ", sku="ZIP-1")
        plan = self.plan_only([("ZIP-1.jpg", png_bytes())], PRODUCT_IMAGE_IMPORT_MAX_ZIP_SIZE=20)
        self.assertFalse(plan.ok)
        self.assertIn("حجم فایل زیپ", plan.errors[0])

    def test_a_probable_zip_bomb_is_rejected_by_the_ratio(self):
        make_product(name="بمب", sku="BOMB-1")
        # A large run of identical bytes compresses enormously (ratio ≫ 2).
        payload = b"\x89PNG\r\n\x1a\n" + b"\x00" * 400_000
        plan = self.plan_only([("BOMB-1.jpg", payload)], PRODUCT_IMAGE_IMPORT_MAX_RATIO=2)
        self.assertFalse(plan.ok)
        self.assertIn("زیپ‌بمب", plan.errors[0])

    def test_a_single_member_with_a_bomb_ratio_is_reported_as_invalid(self):
        make_product(name="عضو", sku="MEMBER-1")
        payload = png_bytes((1, 1, 1), size=(600, 600))
        plan = self.plan_only(
            [("MEMBER-1.jpg", payload)], PRODUCT_IMAGE_IMPORT_MAX_RATIO=2
        )
        # Both the member ratio check and the whole-ZIP check fire; either
        # way nothing is written and the reason names the problem.
        if plan.ok:
            self.assertEqual(plan.counts()["invalid"], 1)
            self.assertIn("زیپ‌بمب", plan.invalid[0].reason)
        else:
            self.assertIn("زیپ‌بمب", plan.errors[0])


class DryRunTests(ImageImportTestCase):
    def test_a_dry_run_writes_nothing_at_all(self):
        product = make_product(name="خشک", sku="DRY-1")
        plan = self.plan_only(
            [("DRY-1.jpg", png_bytes((4, 4, 4))), ("DRY-1-2.jpg", png_bytes((5, 5, 5)))],
            mode="add",
        )
        self.assertEqual(plan.counts()["add"], 2)
        self.assertEqual(product.images.count(), 0)
        # The plan needed the images on disk only inside its temp directory,
        # which the caller already removed.
        self.assertEqual(self.stored_files(), [])

    def test_the_preview_can_include_thumbnails_without_writing_anything(self):
        product = make_product(name="پیش", sku="PREV-1")
        plan = self.plan_only([("PREV-1.jpg", png_bytes((6, 6, 6)))], thumbs=True)
        item = plan.added[0]
        self.assertTrue(item.thumb.startswith("data:image/jpeg;base64,"))
        self.assertEqual(product.images.count(), 0)

    def test_the_report_rows_describe_every_file(self):
        make_product(name="گزارش", sku="REP-1")
        plan = self.plan_only([
            ("REP-1.jpg", png_bytes((1, 1, 1))),
            ("UNKNOWN.jpg", png_bytes((2, 2, 2))),
            ("notes.txt", b"x"),
        ])
        rows = plan.report_rows()
        by_file = {row["file"]: row for row in rows}
        self.assertEqual(by_file["REP-1.jpg"]["status"], "add")
        self.assertEqual(by_file["REP-1.jpg"]["sku"], "REP-1")
        self.assertIn("گزارش", by_file["REP-1.jpg"]["product"])
        self.assertEqual(by_file["UNKNOWN.jpg"]["status"], "unmatched")
        self.assertEqual(by_file["notes.txt"]["status"], "ignored")


class RollbackTests(ImageImportTestCase):
    def test_a_failure_rolls_back_rows_and_removes_the_written_files(self):
        from apps.products import image_import
        from apps.products.models import ProductImage as RealProductImage

        product = make_product(name="شکست", sku="FAIL-1")
        entries = [
            ("FAIL-1.jpg", png_bytes((1, 1, 1))),
            ("FAIL-1-2.jpg", png_bytes((2, 2, 2))),
            ("FAIL-1-3.jpg", png_bytes((3, 3, 3))),
        ]
        path = os.path.join(TEMP_MEDIA, "upload.zip")
        with open(path, "wb") as handle:
            handle.write(build_zip(entries))
        extract_dir = tempfile.mkdtemp(dir=TEMP_MEDIA, prefix="extract-")
        try:
            plan = build_plan(ZipImageSource(path), extract_dir=extract_dir)
            calls = {"n": 0}
            original_save = RealProductImage.save

            def flaky_save(self, *args, **kwargs):
                calls["n"] += 1
                if calls["n"] == 3:  # explode on the third image
                    raise RuntimeError("storage exploded")
                return original_save(self, *args, **kwargs)

            with self.assertRaises(RuntimeError):
                with self._patch_save(image_import, flaky_save):
                    apply_plan(plan)
        finally:
            shutil.rmtree(extract_dir, ignore_errors=True)

        self.assertEqual(product.images.count(), 0)
        self.assertEqual(self.stored_files(), [])

    def test_a_failed_replace_does_not_delete_the_old_files(self):
        make_product(name="قدیمی", sku="OLD-1")
        product = make_product(name="قدیمی۲", sku="OLD-2")
        # The product REALLY has files on disk (written through the storage).
        from django.core.files.base import ContentFile

        old_image = product.images.create(ordering=0, is_primary=True)
        old_image.image.save("old-keep.png", ContentFile(png_bytes((30, 30, 30))), save=True)
        product.refresh_from_db()
        old_name = product.images.get().image.name
        self.assertTrue(os.path.exists(os.path.join(TEMP_MEDIA, old_name)))

        from apps.products import image_import
        from apps.products.models import ProductImage as RealProductImage

        entries = [("OLD-2.jpg", png_bytes((1, 1, 1)))]
        path = os.path.join(TEMP_MEDIA, "upload.zip")
        with open(path, "wb") as handle:
            handle.write(build_zip(entries))
        extract_dir = tempfile.mkdtemp(dir=TEMP_MEDIA, prefix="extract-")
        try:
            plan = build_plan(ZipImageSource(path), mode="replace", extract_dir=extract_dir)
            original_save = RealProductImage.save

            def exploding_save(self, *args, **kwargs):
                raise RuntimeError("boom")

            with self.assertRaises(RuntimeError):
                with self._patch_save(image_import, exploding_save):
                    apply_plan(plan)
        finally:
            shutil.rmtree(extract_dir, ignore_errors=True)

        # The old row and its file survived the rollback...
        self.assertEqual(product.images.count(), 1)
        self.assertTrue(os.path.exists(os.path.join(TEMP_MEDIA, old_name)))

    @staticmethod
    def _patch_save(image_import_module, replacement):
        """Swap ProductImage.save inside the engine only (the model class is
        shared, so this patches the reference the engine calls through)."""
        from contextlib import contextmanager
        from unittest import mock

        from apps.products.models import ProductImage as RealProductImage

        class Patched(RealProductImage):
            save = replacement

            class Meta:
                proxy = True
                app_label = "products"

        @contextmanager
        def _cm():
            with mock.patch.object(image_import_module, "ProductImage", Patched):
                yield

        return _cm()
