"""
Part R5 item 9: rebuild the FrequentlyBoughtTogether table.

    python manage.py rebuild_frequently_bought_together [--max-per-product 8] [--min-count 1]

Mines PAID orders (payment_status = paid): every pair of distinct
products bought within one order increments that pair's co_count, in
BOTH directions (buying A with B also counts for B's suggestions).

The rebuild is FULL and idempotent: the table is cleared and rewritten
inside one transaction, so running it twice in a row yields the exact
same result and it can be pointed at by the production scheduler as
often as desired (daily in docker-compose.prod.yml). Products deleted
from the catalog drop out automatically (their FK rows go with them),
and stale pairs never outlive the rebuild.

The storefront only ever shows these pairs as a FALLBACK for products
that have no manual complements, and only rows pointing at active,
in-stock products (see ProductDetailSerializer.get_complements). No
bundle pricing/stock logic exists anywhere.
"""
from collections import Counter, defaultdict
from itertools import combinations

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.orders.models import Order, OrderItem
from apps.products.models import FrequentlyBoughtTogether


class Command(BaseCommand):
    help = (
        "Rebuild the frequently-bought-together table from PAID orders. "
        "Full idempotent rebuild; safe to run repeatedly."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--max-per-product",
            type=int,
            default=8,
            help="Keep only the strongest N pairs per product (default 8).",
        )
        parser.add_argument(
            "--min-count",
            type=int,
            default=1,
            help="Drop pairs co-purchased fewer times than this (default 1).",
        )

    def handle(self, *args, **options):
        max_per_product = options["max_per_product"]
        min_count = options["min_count"]

        # product_id per PAID order (SET_NULL product FKs -> skip Nones).
        products_per_order = defaultdict(set)
        rows = OrderItem.objects.filter(
            order__payment_status=Order.PaymentStatus.PAID,
            product_id__isnull=False,
        ).values_list("order_id", "product_id")
        for order_id, product_id in rows:
            products_per_order[order_id].add(product_id)

        pair_counts = Counter()
        for product_ids in products_per_order.values():
            for a, b in combinations(sorted(product_ids), 2):
                pair_counts[(a, b)] += 1
                pair_counts[(b, a)] += 1

        # Keep the strongest N per product, ordered by co_count desc.
        best_per_product = defaultdict(list)
        for (a, b), count in pair_counts.items():
            if count < min_count:
                continue
            best_per_product[a].append((count, b))
        new_rows = [
            FrequentlyBoughtTogether(product_id=a, complement_id=b, co_count=count)
            for a, pairs in best_per_product.items()
            for count, b in sorted(pairs, key=lambda pair: (-pair[0], pair[1]))[:max_per_product]
        ]

        with transaction.atomic():
            FrequentlyBoughtTogether.objects.all().delete()
            FrequentlyBoughtTogether.objects.bulk_create(new_rows)

        self.stdout.write(
            self.style.SUCCESS(
                f"Rebuilt frequently-bought-together: {len(new_rows)} pairs "
                f"from {len(products_per_order)} paid orders."
            )
        )
