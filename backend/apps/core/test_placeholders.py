"""
Placeholder detection tests (store-readiness): a seeded «+98 21 0000 0000»
or a bracketed «[نشانی واقعی فروشگاه …]» must read as MISSING everywhere --
readiness card, public API, invoice, SMS -- and must never be rendered to
a customer.

Before this change the readiness card only called ``.strip()`` on the two
fields, so a freshly installed store reported «تلفن و نشانی در «تنظیمات
سایت» تکمیل شده» while the storefront was happily showing a fake phone
number and the legal pages were still marked «نمونه (placeholder)».
"""
import tempfile
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from rest_framework import status

from apps.core.testing import CacheIsolatedAPITestCase

from .placeholders import (
    LEGAL_PAGES,
    clean_value,
    is_placeholder,
    is_placeholder_phone,
    is_set,
    missing_site_items,
    missing_site_labels,
    placeholder_legal_pages,
)

# The exact seed values written by apps/core/migrations/0002.
SEED_PHONE = "+98 21 0000 0000"
SEED_BRACKETED = "[نشانی واقعی فروشگاه را از پنل مدیریت وارد کنید]"

REAL_PHONE = "+98 21 2842 1975"
REAL_MOBILE = "+989121234567"

PLAIN_STATIC = {
    "STORAGES": {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    }
}


class PlaceholderValueTests(SimpleTestCase):
    """The predicate itself: what counts as "not filled in"."""

    def test_seed_phone_is_a_placeholder(self):
        """«+98 21 0000 0000» must NOT count as a phone number."""
        self.assertTrue(is_placeholder_phone(SEED_PHONE))
        self.assertTrue(is_placeholder(SEED_PHONE))

    def test_bracketed_sentence_is_a_placeholder(self):
        self.assertTrue(is_placeholder(SEED_BRACKETED))
        self.assertTrue(is_placeholder("[ساعات کاری را وارد کنید]"))

    def test_empty_and_none_are_missing(self):
        for value in ("", "   ", None):
            self.assertTrue(is_placeholder(value), repr(value))
            self.assertFalse(is_set(value), repr(value))

    def test_real_values_are_kept(self):
        for value in (REAL_PHONE, REAL_MOBILE, "تهران، خیابان ولیعصر، پلاک ۱۰",
                      "شنبه تا چهارشنبه ۹ تا ۱۷", "@cusin_gallery", "cusin.ir"):
            self.assertFalse(is_placeholder(value), repr(value))
            self.assertTrue(is_set(value), repr(value))

    def test_a_real_number_with_zeros_is_not_a_placeholder(self):
        # «912 000 567» has four zeros but the subscriber digits are real --
        # a blanket "contains 0000" rule would blank a customer-visible
        # phone number, which is worse than missing one.
        self.assertFalse(is_placeholder_phone("+98912000567"))
        self.assertFalse(is_placeholder_phone("912 000 567"))

    def test_zero_only_numbers_are_placeholders(self):
        for value in ("+98 21 0000 0000", "02100000000", "0000 0000",
                      "021-0000-0000", "+9891 000 0000"):
            self.assertTrue(is_placeholder_phone(value), repr(value))

    def test_non_phone_text_is_never_a_phone_placeholder(self):
        self.assertFalse(is_placeholder_phone("پلاک ۱۰"))
        self.assertFalse(is_placeholder_phone(""))

    def test_clean_value_blanks_placeholders_only(self):
        self.assertEqual(clean_value(SEED_PHONE), "")
        self.assertEqual(clean_value(SEED_BRACKETED), "")
        self.assertEqual(clean_value(None), "")
        self.assertEqual(clean_value(REAL_PHONE), REAL_PHONE)
        self.assertEqual(clean_value("  تهران  "), "تهران")


class SiteSettingsPlaceholderTests(TestCase):
    """The model-level helpers the dashboard and templates call."""

    def setUp(self):
        from apps.core.models import SiteSettings

        self.site = SiteSettings.load()

    def test_seeded_store_lists_phone_and_address_as_missing(self):
        # The migration seeds the placeholder values, so a fresh install
        # must report them -- that is the whole point of the bug fix.
        self.assertEqual(self.site.phone, SEED_PHONE)
        labels = missing_site_labels(self.site)
        self.assertIn("تلفن پشتیبانی", labels)
        self.assertIn("نشانی فروشگاه", labels)

    def test_missing_items_carry_a_persian_reason(self):
        by_field = {item["field"]: item for item in missing_site_items(self.site)}
        self.assertIn("phone", by_field)
        # Phone gets the specific "sample number" wording.
        self.assertIn("نمونه", by_field["phone"]["reason"])
        for item in missing_site_items(self.site):
            # Persian, no English leftovers, no raw value leaked as a label.
            self.assertTrue(item["label"].strip())
            self.assertTrue(item["reason"].strip())
            self.assertNotIn("placeholder", item["label"])

    def test_an_empty_field_is_reported_as_empty_not_as_sample(self):
        from apps.core.models import SiteSettings

        site = SiteSettings.load()
        site.instagram = ""
        site.save()
        by_field = {item["field"]: item for item in missing_site_items(site)}
        self.assertIn("خالی", by_field["instagram"]["reason"])
        self.assertEqual(by_field["instagram"]["value"], "")

    def test_missing_items_empty_once_filled(self):
        self.site.phone = REAL_PHONE
        self.site.address = "تهران، خیابان ولیعصر، پلاک ۱۰"
        self.site.working_hours = "شنبه تا چهارشنبه ۹ تا ۱۷"
        self.site.pickup_address = "تهران، خیابان ولیعصر، پلاک ۱۰"
        self.site.pickup_hours = "شنبه تا چهارشنبه ۹ تا ۱۷"
        self.site.instagram = "@cusin_gallery"
        self.site.telegram = "@cusin_gallery"
        self.site.whatsapp = REAL_MOBILE
        self.site.save()
        self.assertEqual(missing_site_items(self.site), [])

    def test_model_helpers_agree_with_the_module(self):
        self.assertFalse(self.site.is_set("phone"))
        self.assertEqual(self.site.display("phone"), "")
        self.site.phone = REAL_PHONE
        self.site.save()
        self.assertTrue(self.site.is_set("phone"))
        self.assertEqual(self.site.display("phone"), REAL_PHONE)

    def test_model_still_stores_the_raw_value(self):
        # Blanking is a DISPLAY decision, never a data-loss one: the owner
        # must still see what is in the field when they open the form.
        self.assertEqual(self.site.phone, SEED_PHONE)


@override_settings(**PLAIN_STATIC)
class PublicApiPlaceholderTests(CacheIsolatedAPITestCase):
    """The storefront must never be handed a placeholder to render."""

    url = reverse("site-settings")

    def _set(self, **fields):
        from apps.core.models import SiteSettings

        site = SiteSettings.load()
        for name, value in fields.items():
            setattr(site, name, value)
        site.save()
        return site

    def test_seeded_placeholders_are_not_served(self):
        self.assertEqual(self._set(phone=SEED_PHONE).phone, SEED_PHONE)
        body = self.client.get(self.url).data
        self.assertEqual(body["phone"], "")
        self.assertEqual(body["address"], "")

    def test_no_bracketed_sentence_reaches_the_storefront(self):
        self._set(address=SEED_BRACKETED, working_hours="[ساعات کاری را وارد کنید]")
        body = self.client.get(self.url).data
        self.assertEqual(body["address"], "")
        self.assertEqual(body["working_hours"], "")
        self.assertNotIn("[", str(body))
        self.assertNotIn("]", str(body))

    def test_real_values_are_served_untouched(self):
        self._set(phone=REAL_PHONE, address="تهران، خیابان ولیعصر، پلاک ۱۰",
                  working_hours="شنبه تا چهارشنبه ۹ تا ۱۷",
                  instagram="@cusin_gallery", whatsapp=REAL_MOBILE)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["phone"], REAL_PHONE)
        self.assertEqual(response.data["address"], "تهران، خیابان ولیعصر، پلاک ۱۰")
        self.assertEqual(response.data["working_hours"], "شنبه تا چهارشنبه ۹ تا ۱۷")
        self.assertEqual(response.data["instagram"], "@cusin_gallery")
        self.assertEqual(response.data["whatsapp"], REAL_MOBILE)

    def test_real_number_containing_zeros_survives(self):
        # Regression guard for over-eager "contains 0000" detection.
        self._set(whatsapp="+98912000567")
        self.assertEqual(self.client.get(self.url).data["whatsapp"], "+98912000567")


class LegalPagePlaceholderTests(SimpleTestCase):
    """Trust pages marked «نمونه (placeholder)» are launch blockers."""

    def _write_pages(self, directory, sources):
        for filename, source in sources.items():
            (directory / filename).write_text(source, encoding="utf-8")

    def test_current_repo_pages_are_flagged(self):
        found = placeholder_legal_pages()
        slugs = {page["slug"] for page in found}
        # The pages ship as sample copy today; when the owner replaces one
        # this shrinks, which is the intended signal -- not a failure.
        self.assertTrue(slugs)
        self.assertTrue(slugs <= {slug for slug, _l, _p, _f in LEGAL_PAGES})
        for page in found:
            self.assertTrue(page["label"].strip())
            self.assertTrue(page["path"].startswith("/"))
            self.assertIn("نمونه", page["reason"])

    def test_page_that_turned_the_flag_off_is_not_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            self._write_pages(directory, {
                "TermsPage.jsx": (
                    "export default function TermsPage() {\n"
                    "  return <InfoPageLayout placeholder={false}>متن حقوقی واقعی"
                    "</InfoPageLayout>;\n"
                    "}\n"
                ),
            })
            with mock.patch("apps.core.placeholders.LEGAL_PAGES_DIR", directory):
                slugs = {p["slug"] for p in placeholder_legal_pages()}
        self.assertNotIn("terms", slugs)

    def test_page_that_only_removed_the_notice_is_still_flagged(self):
        """Turning off the banner without rewriting «[متن نمونه …]»."""
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            self._write_pages(directory, {
                "TermsPage.jsx": (
                    "export default function TermsPage() {\n"
                    "  return <InfoPageLayout placeholder={false}>"
                    "[متن نمونه — بعداً جایگزین شود]</InfoPageLayout>;\n"
                    "}\n"
                ),
            })
            with mock.patch("apps.core.placeholders.LEGAL_PAGES_DIR", directory):
                slugs = {p["slug"] for p in placeholder_legal_pages()}
        self.assertIn("terms", slugs)

    def test_instructions_in_a_comment_do_not_count_as_done(self):
        """Every header comment mentions `placeholder={false}` as the
        step to take -- reading comments would call all of them done."""
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            self._write_pages(directory, {
                "TermsPage.jsx": (
                    "/* OWNER: replace this sample text, then set "
                    "placeholder={false} */\n"
                    "// see docs: placeholder={false}\n"
                    "export default function TermsPage() {\n"
                    "  return <InfoPageLayout>متن نمونه</InfoPageLayout>;\n"
                    "}\n"
                ),
            })
            with mock.patch("apps.core.placeholders.LEGAL_PAGES_DIR", directory):
                slugs = {p["slug"] for p in placeholder_legal_pages()}
        self.assertIn("terms", slugs)

    def test_falls_back_to_settings_when_sources_are_absent(self):
        # A backend-only production image has no frontend/ directory; a
        # missing source must never read as "everything is fine".
        missing = Path(tempfile.gettempdir()) / "no-frontend-here"
        with mock.patch("apps.core.placeholders.LEGAL_PAGES_DIR", missing):
            with override_settings(LEGAL_PAGES_PLACEHOLDER=["terms", "privacy"]):
                slugs = {p["slug"] for p in placeholder_legal_pages()}
        self.assertEqual(slugs, {"terms", "privacy"})

    def test_fallback_defaults_to_all_pages(self):
        missing = Path(tempfile.gettempdir()) / "no-frontend-here"
        with mock.patch("apps.core.placeholders.LEGAL_PAGES_DIR", missing):
            with override_settings(LEGAL_PAGES_PLACEHOLDER=[]):
                slugs = {p["slug"] for p in placeholder_legal_pages()}
        self.assertEqual(slugs, {slug for slug, _l, _p, _f in LEGAL_PAGES})


class NoPlaceholderFilterTests(SimpleTestCase):
    """The template filter used by the invoice / print page."""

    def test_filter_blanks_placeholders(self):
        from apps.core.templatetags.site_extras import no_placeholder

        self.assertEqual(no_placeholder(SEED_PHONE), "")
        self.assertEqual(no_placeholder(SEED_BRACKETED), "")
        self.assertEqual(no_placeholder(None), "")
        self.assertEqual(no_placeholder(REAL_PHONE), REAL_PHONE)


class StorefrontSourcePlaceholderTests(SimpleTestCase):
    """No bracketed editor's note may reach the rendered storefront.

    The trust pages used to ship sentences like «[متن نمونه — دربارهٔ
    فروشگاه خودتان بنویسید]» inside the JSX body. Those are notes to the
    OWNER; customers saw them verbatim between real sentences. The owner
    notice banner already says the page is sample copy, so the inline
    markers are simply noise in the rendered output.
    """

    SOURCE_DIR = (
        Path(__file__).resolve().parents[3]
        / "frontend" / "src" / "pages" / "info"
    )

    def test_no_bracketed_sample_marker_is_rendered(self):
        import re

        if not self.SOURCE_DIR.is_dir():
            self.skipTest("frontend sources not available in this checkout")
        offenders = []
        for path in sorted(self.SOURCE_DIR.glob("*.jsx")):
            source = path.read_text(encoding="utf-8")
            # Drop /* … */ and // … comments: a note in a comment is fine,
            # the same text inside JSX is what customers read.
            code = re.sub(r"/\*[\s\S]*?\*/", "", source)
            code = "\n".join(
                re.sub(r"(^|\s)//.*$", "", line) for line in code.splitlines()
            )
            for match in re.finditer(r"\[[^\]\n]{0,80}\]", code):
                offenders.append(f"{path.name}: {match.group(0)}")
        self.assertEqual(
            offenders, [], "sample markers rendered to customers: "
            + "; ".join(offenders)
        )
