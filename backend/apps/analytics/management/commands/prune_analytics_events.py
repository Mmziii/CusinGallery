"""Delete raw behaviour events older than the retention window.

    python manage.py prune_analytics_events [--days N] [--dry-run]

Default window: ``settings.ANALYTICS_RETENTION_DAYS`` (env
``ANALYTICS_RETENTION_DAYS``, default 365).

Design notes
------------
* Only the raw event log is pruned. Orders, customers and cart records
  are untouched, so historical revenue is never lost.
* Deletes run in batches (``BATCH_SIZE``) so a first run on a large table
  does not hold one long transaction/lock.
* Idempotent: a second run immediately afterwards finds nothing.
* Run daily by the production scheduler (docker-compose.prod.yml).
"""
import datetime as dt

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.analytics.models import Event

BATCH_SIZE = 5000


class Command(BaseCommand):
    help = "Delete raw analytics events older than the retention window (default 365 days)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days", type=int, default=None,
            help="Retention window in days (default: ANALYTICS_RETENTION_DAYS).",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Report how many rows would be deleted without deleting them.",
        )
        parser.add_argument(
            "--batch-size", type=int, default=BATCH_SIZE,
            help=f"Rows deleted per batch (default {BATCH_SIZE}).",
        )

    def handle(self, *args, **options):
        days = options.get("days")
        if days is None:
            days = int(getattr(settings, "ANALYTICS_RETENTION_DAYS", 365) or 365)
        if days < 1:
            self.stderr.write(self.style.ERROR("بازهٔ نگهداری باید دست‌کم ۱ روز باشد."))
            return

        cutoff = timezone.now() - dt.timedelta(days=days)
        queryset = Event.objects.filter(created_at__lt=cutoff)
        total = queryset.count()

        if options.get("dry_run"):
            self.stdout.write(
                f"رویدادهای قدیمی‌تر از {days} روز: {total} مورد (حذف نشد — dry-run)."
            )
            return

        batch_size = max(1, int(options.get("batch_size") or BATCH_SIZE))
        deleted = 0
        while True:
            ids = list(queryset.values_list("pk", flat=True)[:batch_size])
            if not ids:
                break
            deleted += Event.objects.filter(pk__in=ids).delete()[0]
            if len(ids) < batch_size:
                break

        self.stdout.write(self.style.SUCCESS(
            f"{deleted} رویداد قدیمی‌تر از {days} روز حذف شد."
        ))
