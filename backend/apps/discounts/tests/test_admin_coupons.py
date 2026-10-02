"""
Coupon admin tests (Phase B - Store management).

Covers the owner-facing behaviors added to the admin: the annotated
usage column, the live-status badge, the activate/deactivate actions,
and that the model's cross-field validation actually blocks bad coupons
saved through the admin form.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.discounts.models import Coupon, CouponUsage

PLAIN_STATIC = {
    "STORAGES": {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
}


@override_settings(**PLAIN_STATIC)
class CouponAdminBase(TestCase):
    def setUp(self):
        self.superuser = get_user_model().objects.create_superuser(
            username="owner-coupons", password="x", phone="+989000000004"
        )
        self.client.force_login(self.superuser)

    def _add_payload(self, **overrides):
        payload = {
            "code": "SAVE10",
            "discount_type": "percentage",
            "percentage_value": "10",
            "is_active": "on",
            "_save": "Save",
        }
        payload.update(overrides)
        return payload


class CouponAdminFormValidationTests(CouponAdminBase):
    def test_percentage_coupon_requires_percentage_value(self):
        response = self.client.post(
            reverse("admin:discounts_coupon_add"),
            self._add_payload(percentage_value=""),
        )
        self.assertEqual(response.status_code, 200)  # re-rendered with errors
        self.assertFalse(Coupon.objects.filter(code="SAVE10").exists())

    def test_percentage_out_of_range_rejected(self):
        response = self.client.post(
            reverse("admin:discounts_coupon_add"),
            self._add_payload(percentage_value="150"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Coupon.objects.filter(code="SAVE10").exists())

    def test_fixed_coupon_requires_fixed_value(self):
        response = self.client.post(
            reverse("admin:discounts_coupon_add"),
            self._add_payload(discount_type="fixed", percentage_value="", fixed_value=""),
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Coupon.objects.filter(code="SAVE10").exists())

    def test_valid_coupon_saved(self):
        response = self.client.post(
            reverse("admin:discounts_coupon_add"),
            self._add_payload(),
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Coupon.objects.filter(code="SAVE10").exists())


class CouponAdminListTests(CouponAdminBase):
    def test_changelist_shows_usage_and_status(self):
        now = timezone.now()
        live = Coupon.objects.create(
            code="LIVE", discount_type=Coupon.DiscountType.PERCENTAGE,
            percentage_value=10, is_active=True,
        )
        expired = Coupon.objects.create(
            code="OLD", discount_type=Coupon.DiscountType.FIXED,
            fixed_value=5000, is_active=True,
            start_date=now - timezone.timedelta(days=10),
            expiration_date=now - timezone.timedelta(days=1),
        )
        user = get_user_model().objects.create_user(
            username="+989001112233", phone="+989001112233", password="x"
        )
        CouponUsage.objects.create(coupon=live, user=user)

        response = self.client.get(reverse("admin:discounts_coupon_changelist"))
        html = response.content.decode()
        self.assertIn("بار استفاده شده", html)   # LIVE usage count
        self.assertIn("فعال", html)
        self.assertIn("منقضی شده", html)
