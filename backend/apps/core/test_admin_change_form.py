"""
Admin UX regressions reported from a real browser (post-PR review).

1. Info-page change form threw «Uncaught TypeError: $ is not a function»:
   the admin class replaced `ModelAdmin.media`, which dropped the jQuery
   bundle while the base change form always renders `prepopulate_init.js`.
   The stock media must stay, with jQuery initialised before that script.

2. The info-page changelist printed Gregorian dates in Latin digits
   («19 اکتبر 2026، ساعت 9:16») while the rest of the panel is Jalali.

3. SiteSettings is a singleton: its change page must not offer «حذف»
   (deleting the row wipes every storefront text and the theme), while the
   trust-strip rows stay removable inside the inline.

4. The generic error summary was English because Django's `fa` catalogue has
   no translation for the pluralised string; the change form overlay renders
   the Persian sentence instead. File inputs get a Persian picker script
   (browser-native «Choose File» cannot be translated from a page).
"""
import datetime

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.tests.helpers import make_user
from apps.adminui.admin_dates import jalali_date
from apps.core.models import InfoPage, SiteSettings
from apps.core.testing import CacheIsolationMixin

PLAIN_STATIC = {
    "STORAGES": {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
}


@override_settings(ADMIN_THEME_ENABLED=True)
class AdminChangeFormAssetsTests(CacheIsolationMixin, TestCase):
    def setUp(self):
        self.admin = make_user(
            phone="+989300007801", password="admin-pw-12345!",
            is_staff=True, is_superuser=True,
        )
        self.client.force_login(self.admin)

    def _info_page(self):
        return InfoPage.objects.get(slug="about")

    def test_info_page_form_loads_jquery_before_prepopulate(self):
        html = self.client.get(
            reverse("admin:core_infopage_change", args=[self._info_page().pk])
        ).content.decode()

        # DEBUG=False ships the minified vendor bundle; both names count.
        self.assertRegex(html, r"admin/js/vendor/jquery/jquery(\.min)?\.js")
        self.assertIn("admin/js/jquery.init.js", html)
        self.assertIn("admin/js/prepopulate_init.js", html)
        self.assertLess(
            html.index("admin/js/jquery.init.js"),
            html.index("admin/js/prepopulate_init.js"),
            "prepopulate_init.js runs before django.jQuery exists",
        )
        # The page's own enhancements are still loaded after the stock media.
        self.assertIn("admin_theme/js/rich_text.js", html)

    def test_site_settings_form_also_keeps_jquery_and_its_preview(self):
        html = self.client.get(
            reverse("admin:core_sitesettings_change", args=[1])
        ).content.decode()
        self.assertIn("admin/js/jquery.init.js", html)
        self.assertIn("admin_theme/js/theme_preview.js", html)
        self.assertLess(
            html.index("admin/js/jquery.init.js"),
            html.index("admin/js/prepopulate_init.js"),
        )

    def test_every_admin_page_loads_the_persian_file_picker(self):
        html = self.client.get(
            reverse("admin:core_sitesettings_change", args=[1])
        ).content.decode()
        self.assertIn("admin_theme/js/file_picker.js", html)
        # The logo/favicon inputs are real clearable file inputs.
        for field in ("logo_light", "logo_dark", "favicon"):
            self.assertIn(f'name="{field}"', html)
            self.assertIn(f'id="id_{field}"', html)

        picker = (
            settings.BASE_DIR / "static" / "admin_theme" / "js" / "file_picker.js"
        ).read_text(encoding="utf-8")
        self.assertIn("انتخاب فایل", picker)
        self.assertIn("فایلی انتخاب نشده", picker)
        css = (
            settings.BASE_DIR / "static" / "admin_theme" / "css" / "theme.css"
        ).read_text(encoding="utf-8")
        self.assertIn(".cusin-file-picker__button", css)


@override_settings(ADMIN_THEME_ENABLED=True)
class InfoPageChangelistDateTests(CacheIsolationMixin, TestCase):
    def setUp(self):
        self.admin = make_user(
            phone="+989300007802", password="admin-pw-12345!",
            is_staff=True, is_superuser=True,
        )
        self.client.force_login(self.admin)

    def test_updated_at_is_jalali_with_persian_digits(self):
        fixed = timezone.make_aware(datetime.datetime(2026, 10, 19, 9, 16))
        InfoPage.objects.filter(slug="about").update(updated_at=fixed)

        html = self.client.get(
            reverse("admin:core_infopage_changelist")
        ).content.decode()
        expected = jalali_date(fixed, with_time=True)
        self.assertIn(expected, html)
        self.assertIn("آخرین به‌روزرسانی", html)
        # No Gregorian month name / Latin year reaches the owner.
        self.assertNotIn("اکتبر", html)
        self.assertNotIn("October", html)
        self.assertNotIn("2026", html)


@override_settings(ADMIN_THEME_ENABLED=True)
class SiteSettingsDeleteProtectionTests(CacheIsolationMixin, TestCase):
    def setUp(self):
        self.admin = make_user(
            phone="+989300007803", password="admin-pw-12345!",
            is_staff=True, is_superuser=True,
        )
        self.client.force_login(self.admin)

    def test_change_page_has_no_delete_button(self):
        html = self.client.get(
            reverse("admin:core_sitesettings_change", args=[1])
        ).content.decode()
        self.assertNotIn("deletelink", html)
        self.assertNotIn("delete-confirmation", html)

    def test_delete_view_is_forbidden_and_the_row_survives(self):
        response = self.client.post(
            reverse("admin:core_sitesettings_delete", args=[1])
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(SiteSettings.objects.count(), 1)

    def test_trust_strip_rows_stay_removable_inside_the_inline(self):
        html = self.client.get(
            reverse("admin:core_sitesettings_change", args=[1])
        ).content.decode()
        self.assertIn('name="trust_items-0-DELETE"', html)
        self.assertIn('name="trust_items-TOTAL_FORMS"', html)


@override_settings(ADMIN_THEME_ENABLED=True)
class PersianErrorSummaryTests(CacheIsolationMixin, TestCase):
    def setUp(self):
        self.admin = make_user(
            phone="+989300007804", password="admin-pw-12345!",
            is_staff=True, is_superuser=True,
        )
        self.client.force_login(self.admin)

    def _post_info_page(self, **overrides):
        page = InfoPage.objects.get(slug="about")
        data = {
            "slug": page.slug,
            "title": page.title,
            "body": "",
            "seo_title": "",
            "seo_description": "",
            "is_published": "on",
            "ordering": str(page.ordering),
            "_save": "ذخیره",
        }
        data.update(overrides)
        return self.client.post(
            reverse("admin:core_infopage_change", args=[page.pk]), data
        )

    def test_single_error_sentence_is_persian(self):
        response = self._post_info_page()
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("لطفاً خطای زیر را برطرف کنید.", html)
        self.assertNotIn("Please correct the error below.", html)

    def test_multiple_errors_sentence_is_persian(self):
        response = self._post_info_page(seo_description="ا" * 301)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("لطفاً خطاهای زیر را برطرف کنید.", html)
        self.assertNotIn("Please correct the errors below.", html)
