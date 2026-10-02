"""
Banners / daily deals admin tests (Phase B - Store management).

Verifies the live-status columns reflect the same window logic as the
public API, and that daily-deal validation (deal price below regular
price, end after start) blocks bad data entered through the admin.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.banners.models import Banner, DailyDeal
from apps.payments.tests.helpers import make_product

PLAIN_STATIC = {
    "STORAGES": {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
}


@override_settings(**PLAIN_STATIC)
class BannerAdminBase(TestCase):
    def setUp(self):
        self.superuser = get_user_model().objects.create_superuser(
            username="owner-banners", password="x", phone="+989000000005"
        )
        self.client.force_login(self.superuser)


class BannerStatusTests(BannerAdminBase):
    def test_changelist_badges_match_api_window_logic(self):
        now = timezone.now()
        Banner.objects.create(title="Live one", image="banners/live.jpg", is_active=True)
        Banner.objects.create(
            title="Ended one", image="banners/ended.jpg", is_active=True,
            start_date=now - timezone.timedelta(days=5),
            end_date=now - timezone.timedelta(days=1),
        )
        Banner.objects.create(
            title="Future one", image="banners/future.jpg", is_active=True,
            start_date=now + timezone.timedelta(days=1),
        )

        response = self.client.get(reverse("admin:banners_banner_changelist"))
        html = response.content.decode()
        self.assertIn("در حال نمایش", html)
        self.assertIn("پایان‌یافته", html)
        self.assertIn("زمان‌بندی‌شده", html)


class DailyDealValidationTests(BannerAdminBase):
    def test_deal_price_not_below_regular_price_is_rejected(self):
        product = make_product(price=100000)
        now = timezone.now()
        payload = {
            "product": product.pk,
            "sale_price": "120000",  # higher than regular price -> invalid
            "starts_at_0": now.strftime("%Y-%m-%d"),
            "starts_at_1": now.strftime("%H:%M:%S"),
            "ends_at_0": (now + timezone.timedelta(days=1)).strftime("%Y-%m-%d"),
            "ends_at_1": (now + timezone.timedelta(days=1)).strftime("%H:%M:%S"),
            "is_active": "on",
            "_save": "Save",
        }
        response = self.client.post(reverse("admin:banners_dailydeal_add"), payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(DailyDeal.objects.count(), 0)

    def test_deal_ending_before_start_is_rejected(self):
        product = make_product(price=100000)
        now = timezone.now()
        payload = {
            "product": product.pk,
            "sale_price": "80000",
            "starts_at_0": now.strftime("%Y-%m-%d"),
            "starts_at_1": now.strftime("%H:%M:%S"),
            "ends_at_0": (now - timezone.timedelta(days=1)).strftime("%Y-%m-%d"),
            "ends_at_1": (now - timezone.timedelta(days=1)).strftime("%H:%M:%S"),
            "is_active": "on",
            "_save": "Save",
        }
        response = self.client.post(reverse("admin:banners_dailydeal_add"), payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(DailyDeal.objects.count(), 0)

    def test_valid_deal_is_saved(self):
        product = make_product(price=100000)
        now = timezone.now()
        payload = {
            "product": product.pk,
            "sale_price": "80000",
            "starts_at_0": now.strftime("%Y-%m-%d"),
            "starts_at_1": now.strftime("%H:%M:%S"),
            "ends_at_0": (now + timezone.timedelta(days=1)).strftime("%Y-%m-%d"),
            "ends_at_1": (now + timezone.timedelta(days=1)).strftime("%H:%M:%S"),
            "is_active": "on",
            "_save": "Save",
        }
        response = self.client.post(
            reverse("admin:banners_dailydeal_add"), payload, follow=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(DailyDeal.objects.count(), 1)
