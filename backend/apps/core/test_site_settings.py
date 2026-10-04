"""
SiteSettings singleton tests (Part 1): one row, public API, admin
behaviour, seeded default.
"""
from django.test import override_settings
from django.urls import reverse
from rest_framework import status

from apps.accounts.tests.helpers import make_user
from apps.core.testing import CacheIsolatedAPITestCase

PLAIN_STATIC = {
    "STORAGES": {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
}


class SiteSettingsTests(CacheIsolatedAPITestCase):
    url = reverse("site-settings")

    def test_seeded_by_migration(self):
        from apps.core.models import SiteSettings

        self.assertEqual(SiteSettings.objects.count(), 1)
        self.assertEqual(SiteSettings.load().pk, 1)

    def test_singleton_enforced_on_save(self):
        from apps.core.models import SiteSettings

        a = SiteSettings.load()
        a.phone = "+98 21 1234 5678"
        a.save()
        b = SiteSettings(phone="+98 21 9999 9999")
        b.save()  # must land on the same row, never create a second
        self.assertEqual(SiteSettings.objects.count(), 1)
        self.assertEqual(SiteSettings.load().phone, "+98 21 9999 9999")

    def test_public_api_returns_the_fields(self):
        from apps.core.models import SiteSettings

        s = SiteSettings.load()
        s.phone = "+98 21 1111 2222"
        s.whatsapp = "+989120000000"
        s.pickup_hours = "شنبه تا چهارشنبه ۹ تا ۱۷"
        s.enamad_html = '<div id="enamad">x</div>'
        s.save()

        response = self.client.get(self.url)  # anonymous
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["phone"], "+98 21 1111 2222")
        self.assertEqual(response.data["whatsapp"], "+989120000000")
        self.assertEqual(response.data["pickup_hours"], "شنبه تا چهارشنبه ۹ تا ۱۷")
        self.assertEqual(response.data["enamad_html"], '<div id="enamad">x</div>')

    @override_settings(**PLAIN_STATIC)
    def test_admin_changelist_redirects_to_the_single_row(self):
        make_user(phone="+989300000001", password="admin-pw-12345!",
                  is_staff=True, is_superuser=True)
        self.client.login(username="+989300000001", password="admin-pw-12345!")
        response = self.client.get(reverse("admin:core_sitesettings_changelist"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/core/sitesettings/1/change/", response["Location"])
