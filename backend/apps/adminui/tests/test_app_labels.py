"""Item 5 of follow-up 2: the admin shows Persian app and fieldset names.

Breadcrumbs and the dashboard app list take their names from each AppConfig's
verbose_name, and the product fieldsets from ProductAdmin.fieldsets. The
checks below read the registry and the rendered pages, so a name that comes
back in English fails the test. Changing a verbose_name never needs a
migration; test_no_migration_is_needed guards that.
"""
import re

from django.apps import apps
from django.conf import settings
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from io import StringIO

from apps.adminui.otp_apps import OtpStaticAdminConfig, OtpTotpAdminConfig

from .helpers import PLAIN_STATIC, make_superuser

PERSIAN_RE = re.compile(r"[\u0600-\u06FF]")
LATIN_RE = re.compile(r"[A-Za-z]")

# English names that must not reach a rendered admin page any more.
ENGLISH_APP_LABELS = (
    "Products", "Categories", "Accounts", "Banners", "Cart", "Core",
    "Discounts", "Orders", "Payments", "Reviews", "Wishlist",
    "OTP_STATIC", "OTP_TOTP", "Otp_Static", "Otp_Totp",
)
ENGLISH_FIELDSET_TITLES = ("Description", "Pricing", "Inventory", "Flags")


def _is_project_or_otp(app_config):
    return app_config.name.startswith("apps.") or app_config.name.startswith(
        "django_otp.plugins."
    )


class AppVerboseNameTests(SimpleTestCase):

    def test_every_project_and_otp_app_has_a_persian_verbose_name(self):
        checked = [a for a in apps.get_app_configs() if _is_project_or_otp(a)]
        self.assertGreaterEqual(len(checked), 13)
        for app_config in checked:
            with self.subTest(app=app_config.name):
                name = str(app_config.verbose_name)
                self.assertRegex(name, PERSIAN_RE)
                self.assertNotRegex(name, LATIN_RE)

    def test_otp_plugins_are_registered_through_the_named_configs(self):
        self.assertIsInstance(apps.get_app_config("otp_static"), OtpStaticAdminConfig)
        self.assertIsInstance(apps.get_app_config("otp_totp"), OtpTotpAdminConfig)
        # same label and name as the plugin: no migration or model state changes
        self.assertEqual(apps.get_app_config("otp_static").name, "django_otp.plugins.otp_static")
        self.assertIn("apps.adminui.otp_apps.OtpStaticAdminConfig", settings.INSTALLED_APPS)
        self.assertIn("apps.adminui.otp_apps.OtpTotpAdminConfig", settings.INSTALLED_APPS)



class MigrationStateTests(TestCase):

    def test_no_migration_is_needed_for_the_renames(self):
        # makemigrations --check exits non-zero (SystemExit) when models have
        # unmigrated changes; a verbose_name on an AppConfig must not cause one.
        out = StringIO()
        call_command("makemigrations", "--check", "--dry-run", stdout=out, stderr=out)


class RenderedLabelTests(TestCase):

    @override_settings(**PLAIN_STATIC)
    def test_dashboard_app_list_and_breadcrumbs_show_no_english_app_names(self):
        self.client.force_login(make_superuser())
        for url in (reverse("admin:index"), reverse("admin:products_product_changelist")):
            html = self.client.get(url).content.decode("utf-8")
            for label in ENGLISH_APP_LABELS:
                with self.subTest(url=url, label=label):
                    self.assertNotRegex(html, rf">\s*{re.escape(label)}\s*<")

    @override_settings(**PLAIN_STATIC)
    def test_product_breadcrumb_shows_the_persian_app_name(self):
        self.client.force_login(make_superuser())
        html = self.client.get(reverse("admin:products_product_changelist")).content.decode("utf-8")
        self.assertIn("محصولات", html)

    @override_settings(**PLAIN_STATIC)
    def test_product_form_fieldsets_are_persian(self):
        self.client.force_login(make_superuser())
        html = self.client.get(reverse("admin:products_product_add")).content.decode("utf-8")
        for title in ("اطلاعات اصلی", "توضیحات", "قیمت‌گذاری", "موجودی", "وضعیت و نمایش"):
            with self.subTest(title=title):
                self.assertIn(title, html)
        for title in ENGLISH_FIELDSET_TITLES:
            with self.subTest(english=title):
                self.assertNotRegex(html, rf">\s*{title}\s*<")
