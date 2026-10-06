"""
Idempotent backfill of the normalized search index (Part R5 item 7).

    python manage.py backfill_search_text

Recomputes Product.search_text / search_name for EVERY product from
name+sku+brand name+category name+short description. Safe to run any
number of times (same input -> same output); it exists so an existing
database gains the search index without a one-shot data migration --
deploy docs (docs/DEPLOY.md) run it once after migrating. New products
keep themselves fresh through Product.save(), and brand/category renames
propagate automatically, so the command is only needed for the pre-R5
rows (or as a repair hammer).
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.products.models import Product
from apps.products.search import build_product_search_fields


class Command(BaseCommand):
    help = (
        "Recompute the normalized Persian search index (search_text/search_name) "
        "for all products. Idempotent."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size", type=int, default=500, help="Rows per bulk_update batch."
        )

    def handle(self, *args, **options):
        batch_size = max(50, options["batch_size"])
        total = changed = 0
        batch = []

        queryset = Product.objects.select_related("brand", "category").order_by("pk")
        with transaction.atomic():
            for product in queryset.iterator(chunk_size=batch_size):
                total += 1
                search_text, search_name = build_product_search_fields(product)
                if product.search_text != search_text or product.search_name != search_name:
                    product.search_text = search_text
                    product.search_name = search_name
                    batch.append(product)
                    changed += 1
                if len(batch) >= batch_size:
                    Product.objects.bulk_update(
                        batch, ["search_text", "search_name"], batch_size=batch_size
                    )
                    batch = []
            if batch:
                Product.objects.bulk_update(
                    batch, ["search_text", "search_name"], batch_size=batch_size
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"backfill_search_text: {changed}/{total} products updated (idempotent)."
            )
        )
