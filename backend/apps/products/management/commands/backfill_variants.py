"""
Backfill responsive WebP variants for ProductImage rows that predate
(or bypassed) the upload hook (Part 3).

Idempotent: rows that already have webp_400 are skipped; re-running only
ever fills gaps. Graceful: a missing or undecodable source file prints a
warning and is skipped -- the command never aborts the whole run.
"""
from django.core.management.base import BaseCommand

from apps.core.image_files import make_responsive_variants
from apps.products.models import ProductImage


class Command(BaseCommand):
    help = "Generate 400/800/1200px WebP variants for product images that lack them."

    def handle(self, *args, **options):
        from apps.banners.models import Banner

        rows = list(ProductImage.objects.exclude(image="").filter(webp_400="")) + list(
            Banner.objects.exclude(image="").filter(webp_400="")
        )
        done = skipped = 0
        for row in rows:
            if not row.image:
                skipped += 1
                continue
            try:
                variants = make_responsive_variants(row.image)
            except Exception as exc:  # defensive: never kill the batch
                self.stderr.write(f"image #{row.pk}: {type(exc).__name__} -- skipped")
                skipped += 1
                continue
            if not variants:
                self.stderr.write(f"image #{row.pk}: source missing/undecodable -- skipped")
                skipped += 1
                continue
            row.webp_400 = variants.get(400, "")
            row.webp_800 = variants.get(800, "")
            row.webp_1200 = variants.get(1200, "")
            row.save(update_fields=["webp_400", "webp_800", "webp_1200", "updated_at"])
            done += 1
        self.stdout.write(self.style.SUCCESS(f"variants written for {done} image(s), {skipped} skipped."))
