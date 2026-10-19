"""Task 1: retention command (raw events only, batched, idempotent)."""
import datetime as dt
from io import StringIO

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from ..models import Event
from .helpers import make_product

OLD = timezone.now() - dt.timedelta(days=400)
RECENT = timezone.now() - dt.timedelta(days=10)


class PruneAnalyticsEventsTests(TestCase):
    def setUp(self):
        product = make_product()
        Event.objects.create(event_type=Event.Type.PRODUCT_VIEW, product=product, created_at=OLD)
        Event.objects.create(event_type=Event.Type.PRODUCT_VIEW, product=product, created_at=RECENT)

    def test_events_older_than_the_window_are_deleted(self):
        out = StringIO()
        call_command("prune_analytics_events", stdout=out)
        self.assertEqual(Event.objects.count(), 1)
        self.assertEqual(Event.objects.get().created_at.date(), RECENT.date())
        self.assertIn("حذف شد", out.getvalue())

    def test_dry_run_deletes_nothing(self):
        call_command("prune_analytics_events", "--dry-run", stdout=StringIO())
        self.assertEqual(Event.objects.count(), 2)

    def test_the_window_is_configurable(self):
        call_command("prune_analytics_events", "--days", "1", stdout=StringIO())
        self.assertEqual(Event.objects.count(), 0)

    @override_settings(ANALYTICS_RETENTION_DAYS=5)
    def test_the_setting_is_the_default(self):
        call_command("prune_analytics_events", stdout=StringIO())
        # With a 5-day window even the "recent" 10-day-old row is raw
        # history now -- both go.
        self.assertEqual(Event.objects.count(), 0)

    def test_running_twice_is_safe(self):
        call_command("prune_analytics_events", stdout=StringIO())
        call_command("prune_analytics_events", stdout=StringIO())
        self.assertEqual(Event.objects.count(), 1)
