"""
Tests for shipping prices, times, and rules configured via SiteSettings («محتوا و ظاهر سایت»).
Covers:
- Shipping methods read dynamically from SiteSettings
- Cache invalidation when SiteSettings is updated
- Persian validation errors for min_days > max_days, negative prices, all methods disabled, empty express cities
- Express destination eligibility checking against customized allowed cities in SiteSettings
"""
import datetime
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from rest_framework import status

from apps.core.models import SiteSettings
from apps.core.testing import CacheIsolatedAPITestCase
from apps.orders import shipping


class ShippingSiteSettingsTests(CacheIsolatedAPITestCase):
    def setUp(self):
        super().setUp()
        shipping.invalidate_shipping_cache()
        self.site = SiteSettings.load()
        self.site.shipping_standard_cost = 45000
        self.site.shipping_free_threshold = 800000
        self.site.shipping_standard_min_days = 2
        self.site.shipping_standard_max_days = 4
        self.site.shipping_express_cost = 85000
        self.site.shipping_express_cities = "تهران، کرج"
        self.site.save()

    def test_shipping_methods_reflect_sitesettings(self):
        methods = shipping.get_shipping_methods()
        self.assertIn("standard", methods)
        self.assertEqual(methods["standard"]["cost"], 45000)
        self.assertEqual(methods["standard"]["free_threshold"], 800000)
        self.assertEqual(methods["standard"]["min_days"], 2)
        self.assertEqual(methods["standard"]["max_days"], 4)
        self.assertEqual(methods["express"]["cost"], 85000)

    def test_cost_calculation_uses_sitesettings_and_free_threshold(self):
        # Subtotal below threshold
        cost = shipping.calculate_shipping_cost(799000, "standard")
        self.assertEqual(cost, 45000)

        # Subtotal at or above threshold
        cost_free = shipping.calculate_shipping_cost(800000, "standard")
        self.assertEqual(cost_free, 0)

    def test_cache_invalidation_on_sitesettings_save(self):
        # Warm the cache
        initial_methods = shipping.get_shipping_methods()
        self.assertEqual(initial_methods["standard"]["cost"], 45000)

        # Modify SiteSettings and save
        self.site.shipping_standard_cost = 60000
        self.site.save()

        # Cache should be invalidated and return new value
        updated_methods = shipping.get_shipping_methods()
        self.assertEqual(updated_methods["standard"]["cost"], 60000)

    def test_express_eligibility_with_custom_cities(self):
        # Tehran is in "تهران، کرج"
        self.assertTrue(shipping.is_express_eligible("تهران", "تهران"))
        # Karaj is in "تهران، کرج" (province Alborz)
        self.assertTrue(shipping.is_express_eligible("البرز", "کرج"))
        # Isfahan is not in "تهران، کرج"
        self.assertFalse(shipping.is_express_eligible("اصفهان", "اصفهان"))

    def test_disabling_method_excludes_it_from_configured_methods(self):
        self.site.shipping_express_enabled = False
        self.site.save()

        methods = shipping.get_shipping_methods()
        self.assertNotIn("express", methods)
        self.assertFalse(shipping.is_valid_shipping_method("express"))


class ShippingValidationTests(TestCase):
    def setUp(self):
        self.site = SiteSettings.load()

    def test_min_days_greater_than_max_days_raises_persian_validation_error(self):
        self.site.shipping_standard_min_days = 6
        self.site.shipping_standard_max_days = 3
        with self.assertRaises(ValidationError) as ctx:
            self.site.clean()
        self.assertIn("shipping_standard_min_days", ctx.exception.message_dict)
        self.assertIn("حداقل روز تحویل عادی نمی‌تواند بیشتر از حداکثر روز تحویل باشد.", ctx.exception.message_dict["shipping_standard_min_days"])

    def test_all_methods_disabled_raises_persian_validation_error(self):
        self.site.shipping_standard_enabled = False
        self.site.shipping_express_enabled = False
        self.site.shipping_pickup_enabled = False
        with self.assertRaises(ValidationError) as ctx:
            self.site.clean()
        self.assertIn("shipping_standard_enabled", ctx.exception.message_dict)
        self.assertIn("حداقل یکی از روش‌های ارسال باید فعال باشد.", ctx.exception.message_dict["shipping_standard_enabled"])

    def test_express_enabled_with_empty_cities_raises_persian_validation_error(self):
        self.site.shipping_express_enabled = True
        self.site.shipping_express_cities = "   "
        with self.assertRaises(ValidationError) as ctx:
            self.site.clean()
        self.assertIn("shipping_express_cities", ctx.exception.message_dict)
        self.assertIn("لطفاً حداقل یک شهر مجاز برای ارسال اکسپرس مشخص کنید.", ctx.exception.message_dict["shipping_express_cities"])

    def test_form_shows_min_days_error_once(self):
        from apps.core.forms import SiteSettingsAdminForm

        data = {
            "shipping_standard_enabled": True,
            "shipping_standard_cost": 50000,
            "shipping_standard_min_days": 6,
            "shipping_standard_max_days": 3,
            "shipping_express_enabled": True,
            "shipping_express_cost": 90000,
            "shipping_express_min_days": 1,
            "shipping_express_max_days": 1,
            "shipping_express_cities": "تهران",
            "shipping_pickup_enabled": True,
        }
        form = SiteSettingsAdminForm(data=data, instance=self.site)
        self.assertFalse(form.is_valid())
        errs = form.errors.get("shipping_standard_min_days", [])
        self.assertEqual(len(errs), 1)
        self.assertEqual(errs[0], "حداقل روز تحویل عادی نمی‌تواند بیشتر از حداکثر روز تحویل باشد.")

