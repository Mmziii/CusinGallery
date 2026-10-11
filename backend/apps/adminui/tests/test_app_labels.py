"""Item 5 of follow-up 2: the admin shows Persian app and fieldset names.

Breadcrumbs and the dashboard app list take their names from each AppConfig's
verbose_name, and the product fieldsets from ProductAdmin.fieldsets. The
checks below read the registry and the rendered pages, so a name that comes
back in English fails the test. Changing a verbose_name never needs a
migration; test_no_migration_is_needed guards that.
"""
import datetime as dt
import re

from django.apps import apps
from django.conf import settings
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from io import StringIO

from apps.adminui.jalali import format_jalali_datetime
from apps.adminui.otp_apps import OtpStaticAdminConfig, OtpTotpAdminConfig
from apps.orders.models import Order

from .helpers import PLAIN_STATIC, make_order, make_superuser

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


def _fieldset_titles(model_admin, model, request):
    """Every fieldset title a ModelAdmin (and its inlines) can show, not only the
    static attributes: get_fieldsets() is called for an add form and for an
    existing object, so dynamic titles are included too."""
    obj = model()
    titles = [title for title, _ in (getattr(model_admin, "fieldsets", None) or ())]
    titles += [title for title, _ in (getattr(model_admin, "add_fieldsets", None) or ())]
    titles += [title for title, _ in model_admin.get_fieldsets(request, obj)]
    titles += [title for title, _ in model_admin.get_fieldsets(request, None)]
    for inline_class in model_admin.inlines:
        inline = inline_class(model, admin.site)
        titles += [title for title, _ in (getattr(inline, "fieldsets", None) or ())]
        titles += [title for title, _ in inline.get_fieldsets(request, obj)]
    return [str(title) for title in titles if title]


def latin_only_fieldset_titles(site):
    """'model: title' for every fieldset title in `site` that has Latin letters
    and no Persian letter. A title that is only English fails the admin."""
    request = RequestFactory().get("/")
    request.user = get_user_model()(is_superuser=True, is_staff=True)
    found = []
    for model, model_admin in site._registry.items():
        for title in _fieldset_titles(model_admin, model, request):
            if LATIN_RE.search(title) and not PERSIAN_RE.search(title):
                found.append(f"{model._meta.label}: {title}")
    return sorted(set(found))


def _fieldset_html(html, title):
    """The body of the rendered fieldset whose <h2> is `title`."""
    match = re.search(rf"<h2[^>]*>\s*{re.escape(title)}\s*</h2>(.*?)</fieldset>", html, re.S)
    assert match, f"fieldset «{title}» is not rendered"
    return match.group(1)


class FieldsetTitleScanTests(SimpleTestCase):
    """Item 4 of follow-up 3: a Latin-only fieldset title in any registered
    ModelAdmin fails. The scan covers django-otp's admins too, which ship with
    English titles and are re-registered with Persian ones."""

    def test_no_registered_modeladmin_has_a_latin_only_fieldset_title(self):
        self.assertEqual(latin_only_fieldset_titles(admin.site), [])

    def test_the_scan_reports_a_latin_only_title(self):
        # Proof that the scan can fail: a throwaway site with one English title.
        from django.contrib.auth.models import Group

        class EnglishTitleAdmin(admin.ModelAdmin):
            fieldsets = ((None, {"fields": ("name",)}), ("Gift wrapping", {"fields": ("permissions",)}))

        site = admin.AdminSite(name="scan-proof")
        site.register(Group, EnglishTitleAdmin)
        self.assertEqual(latin_only_fieldset_titles(site), ["auth.Group: Gift wrapping"])

    def test_the_renamed_titles_in_this_round_are_persian(self):
        titles = {
            "orders.Order": ["ارسال و پیگیری", "جمع‌ها", "بازپرداخت", "نشانی ارسال",
                             "روش ارسال", "بسته‌بندی هدیه", "زمان‌ها"],
            "payments.Payment": ["درگاه پرداخت", "زمان‌ها"],
            "discounts.Coupon": ["مقدار", "شرایط", "اعتبار", "محدودیت استفاده"],
            "accounts.User": ["تماس"],
        }
        request = RequestFactory().get("/")
        request.user = get_user_model()(is_superuser=True, is_staff=True)
        for label, expected in titles.items():
            model = apps.get_model(label)
            found = _fieldset_titles(admin.site._registry[model], model, request)
            for title in expected:
                with self.subTest(model=label, title=title):
                    self.assertIn(title, found)


class OrderAdminDisplayTests(TestCase):
    """Item 4 of follow-up 3, rendered: the shipping method shows its Persian
    label, and the two order dates show Jalali dates with Persian digits."""

    CREATED = dt.datetime(2026, 10, 11, 9, 30, tzinfo=dt.timezone.utc)
    UPDATED = dt.datetime(2026, 10, 12, 6, 0, tzinfo=dt.timezone.utc)

    def setUp(self):
        self.order = make_order(shipping_method="express")
        Order.objects.filter(pk=self.order.pk).update(created_at=self.CREATED, updated_at=self.UPDATED)
        self.client.force_login(make_superuser())

    def _html(self):
        url = reverse("admin:orders_order_change", args=[self.order.pk])
        with self.settings(**PLAIN_STATIC):
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        return response.content.decode("utf-8")

    def test_shipping_method_shows_the_persian_label_not_the_key(self):
        block = _fieldset_html(self._html(), "روش ارسال")
        self.assertIn("اکسپرس", block)
        self.assertNotIn("express", block)

    def test_order_dates_are_jalali_with_persian_digits(self):
        html = self._html()
        block = _fieldset_html(html, "زمان‌ها")
        created = format_jalali_datetime(timezone.localtime(self.CREATED))
        updated = format_jalali_datetime(timezone.localtime(self.UPDATED))
        self.assertRegex(created, r"^[۰-۹]{4}/[۰-۹]{2}/[۰-۹]{2} ")
        self.assertIn("تاریخ ایجاد", block)
        self.assertIn("تاریخ ویرایش", block)
        self.assertIn(created, block)
        self.assertIn(updated, block)
        self.assertNotIn("2026", block)
        self.assertNotIn("Oct", block)

