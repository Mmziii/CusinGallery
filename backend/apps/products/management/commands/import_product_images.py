"""
Bulk product image import from a ZIP (or a folder) -- matched by SKU.

Usage:
    python manage.py import_product_images photos.zip
    python manage.py import_product_images photos.zip --dry-run
    python manage.py import_product_images photos.zip --mode replace
    python manage.py import_product_images photos.zip --skip-existing
    python manage.py import_product_images /srv/photos/ --dry-run

The exact same engine drives the admin page («ورود گروهی تصاویر (فایل زیپ)»)
-- apps/products/image_import.py -- so the CLI and the admin behave
identically, including the naming rules, the safety limits (zip-slip,
symlinks, nested archives, zip bombs) and the all-or-nothing transaction.
"""
import os
import shutil
import tempfile

from django.core.management.base import BaseCommand, CommandError

from apps.products.image_import import (
    FolderImageSource,
    ImageImportLimits,
    ZipImageSource,
    apply_plan,
    build_plan,
    fa_digits,
)


class Command(BaseCommand):
    help = (
        "Import product images from a ZIP file (or a folder) named after each "
        "product's SKU. Images of one product are ordered by the numeric suffix "
        "in the file name and the first becomes the primary image. Existing "
        "images are kept (--mode add, default), replaced (--mode replace), or "
        "products that already have an image are skipped (--skip-existing). "
        "Nothing is written on --dry-run."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "source",
            help="Path to a .zip file, or to a folder containing the images.",
        )
        parser.add_argument(
            "--mode",
            choices=("add", "replace"),
            default="add",
            help="add (default): keep existing images; replace: remove them first.",
        )
        parser.add_argument(
            "--skip-existing",
            action="store_true",
            help="Leave products that already have an image untouched.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate and report what would happen, without writing anything.",
        )

    def handle(self, *args, **options):
        path = options["source"]
        if not os.path.exists(path):
            raise CommandError(f"مسیر پیدا نشد: {path}")

        limits = ImageImportLimits.from_settings()
        source = FolderImageSource(path, limits=limits) if os.path.isdir(path) else ZipImageSource(path, limits=limits)

        extract_dir = tempfile.mkdtemp(prefix="cusin-image-import-cli-")
        try:
            try:
                plan = build_plan(
                    source,
                    mode=options["mode"],
                    skip_existing=options["skip_existing"],
                    extract_dir=extract_dir,
                    thumbs=False,
                )
            except ValueError as exc:
                raise CommandError(str(exc))

            if not plan.ok:
                self.stderr.write(self.style.ERROR("ورود تصاویر رد شد -- هیچ‌چیز ذخیره نشد:"))
                for message in plan.errors:
                    self.stderr.write(self.style.ERROR(f"  {message}"))
                raise CommandError(f"{len(plan.errors)} خطا.")

            counts = plan.counts()
            self.stdout.write(
                "پیش‌نمایش: "
                f"{fa_digits(counts['add'])} تصویر برای {fa_digits(counts['products'])} محصول، "
                f"{fa_digits(counts['duplicate'])} تکراری، "
                f"{fa_digits(counts['skip'])} رد‌شده (تصویر دارد)، "
                f"{fa_digits(counts['unmatched'])} کد کالای ناشناخته، "
                f"{fa_digits(counts['invalid'])} نامعتبر، "
                f"{fa_digits(counts['ignored'])} نادیده‌گرفته‌شده، "
                f"{fa_digits(counts['unsafe'])} ناامن."
            )
            for group in plan.writing_groups:
                self.stdout.write(
                    f"  {group.product.sku} | {group.product.name}: "
                    f"{fa_digits(group.new_count)} تصویر"
                    + (
                        f" (جایگزین {fa_digits(group.existing_count)} تصویر فعلی)"
                        if group.effect == "replace"
                        else " (مجموع پس از این: "
                        f"{fa_digits(group.existing_count + group.new_count)})"
                    )
                )
            for item in plan.unmatched[:20]:
                self.stdout.write(f"  [بدون کد کالا] {item.member}")
            for item in plan.invalid[:20]:
                self.stdout.write(self.style.WARNING(f"  [نامعتبر] {item.member} -- {item.reason}"))

            if options["dry_run"]:
                self.stdout.write(
                    self.style.SUCCESS("فقط بررسی شد (--dry-run)؛ هیچ‌چیزی ذخیره نشد.")
                )
                return

            if counts["add"] == 0:
                self.stdout.write(
                    self.style.SUCCESS("چیزی برای ذخیره نبود؛ همهٔ تصاویر تکراری یا رد‌شده بودند.")
                )
                return

            try:
                result = apply_plan(plan)
            except Exception as exc:
                raise CommandError(f"ذخیره انجام نشد و هیچ تغییری اعمال نشد: {exc}")
            self.stdout.write(
                self.style.SUCCESS(
                    f"ذخیره شد: {fa_digits(result['created'])} تصویر برای "
                    f"{fa_digits(result['products'])} محصول"
                    + (
                        f" ({fa_digits(result['replaced'])} تصویر قبلی جایگزین شد)."
                        if result["replaced"]
                        else "."
                    )
                )
            )
        finally:
            shutil.rmtree(extract_dir, ignore_errors=True)
