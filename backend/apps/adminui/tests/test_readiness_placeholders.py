"""
Readiness: a placeholder is MISSING (store-launch blockers).

The card used to test ``bool((site.phone or "").strip())``. A fresh install
seeds «+98 21 0000 0000» and «[نشانی واقعی فروشگاه را از پنل مدیریت وارد
کنید]», both non-empty, so the card reported the store's contact info as
COMPLETE while customers were looking at a fake phone number. These tests
pin the new behaviour: placeholders fail the card, each missing item is
named in Persian, and the legal pages are checked too.
"""
from unittest import mock

from django.test import TestCase, override_settings

from apps.core.models import SiteSettings
from apps.core.testing import CacheIsolationMixin, frozen_clock

from .helpers import PLAIN_STATIC, make_superuser

# Saturday 2026-10-10 12:00 Tehran (dashboard aggregates are clock-based;
# the readiness card is not, but the rest of the index is).
FROZEN = __import__("datetime").datetime(
    2026, 10, 10, 12, 0,
    tzinfo=__import__("datetime").timezone(__import__("datetime").timedelta(hours=3, minutes=30)),
)

SEED_PHONE = "+98 21 0000 0000"
REAL_PHONE = "+98 21 2842 1975"
REAL_MOBILE = "+989121234567"

PERSIAN = "آاءأؤبپتثجچحخدذرزژسشصضطظعغفقکلمنوهی"


def assert_persian(testcase, text, what=""):
    """Fail on English/broken owner-facing copy.

    Mirrors apps/orders/tests/test_persian_errors.assert_persian: a message
    the owner reads must be Persian, not a leftover English sentence and
    not an empty string.
    """
    testcase.assertTrue(text, f"{what}: empty message")
    letters = sum(1 for ch in text if ch in PERSIAN)
    words = [w for w in text.replace("«", " ").replace("»", " ").split() if w.isascii()]
    testcase.assertTrue(
        letters > 2 * len(words),
        f"{what}: not Persian enough ({letters} Persian letters vs "
        f"{len(words)} ASCII words): {text!r}",
    )


def readiness_by_id(payload=None):
    from apps.adminui.dashboard import readiness_checks

    return {item["id"]: item for item in (payload or readiness_checks())}


@override_settings(**PLAIN_STATIC)
class SiteProfilePlaceholderTests(CacheIsolationMixin, TestCase):
    def _fill(self, **fields):
        site = SiteSettings.load()
        for name, value in fields.items():
            setattr(site, name, value)
        site.save()
        return site

    def test_seeded_placeholders_fail_the_card(self):
        """The bug: seeded values are non-empty but are NOT content."""
        site = SiteSettings.load()
        self.assertTrue(str(site.phone).strip())
        self.assertTrue(str(site.address).strip())
        card = readiness_by_id()["site_profile"]
        self.assertFalse(card["ok"])

    def test_card_names_each_missing_item_in_persian(self):
        card = readiness_by_id()["site_profile"]
        assert_persian(self, card["detail"], "site_profile detail")
        missing = {item["field"]: item for item in card["missing"]}
        self.assertIn("phone", missing)
        self.assertIn("address", missing)
        for field in ("phone", "address"):
            assert_persian(self, missing[field]["label"], f"{field} label")
            assert_persian(self, missing[field]["reason"], f"{field} reason")
        # The seeded phone is a sample number, and the card says so.
        self.assertIn("نمونه", missing["phone"]["reason"])
        # The Persian labels are what the owner sees on the card.
        self.assertIn("تلفن پشتیبانی", card["detail"])
        self.assertIn("نشانی فروشگاه", card["detail"])

    def test_card_passes_once_real_values_are_in(self):
        self._fill(phone=REAL_PHONE, address="تهران، خیابان ولیعصر، پلاک ۱۰")
        card = readiness_by_id()["site_profile"]
        self.assertTrue(card["ok"])
        # Required items are done; only optional ones can still be listed.
        self.assertEqual([i for i in card["missing"] if i["required"]], [])
        self.assertNotIn("تلفن پشتیبانی", card["detail"])

    def test_optional_fields_still_pass_but_are_mentioned(self):
        self._fill(phone=REAL_PHONE, address="تهران، خیابان ولیعصر، پلاک ۱۰")
        card = readiness_by_id()["site_profile"]
        self.assertTrue(card["ok"])
        # working_hours/pickup_* are optional: mentioned, not blocking.
        self.assertIn("ساعات پاسخگویی", card["detail"])
        self.assertTrue(card["missing"])

    def test_a_zero_phone_alone_is_enough_to_fail(self):
        self._fill(phone="02100000000", address="تهران، خیابان ولیعصر، پلاک ۱۰")
        self.assertFalse(readiness_by_id()["site_profile"]["ok"])

    def test_a_real_number_with_zeros_passes(self):
        self._fill(phone="+98912000567", address="تهران، خیابان ولیعصر، پلاک ۱۰")
        self.assertTrue(readiness_by_id()["site_profile"]["ok"])

    def test_index_renders_the_missing_list(self):
        admin = make_superuser(username="ready-ph", phone="+989000017001")
        self.client.force_login(admin)
        with frozen_clock(FROZEN):
            response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        # The seeded placeholder phone must never be shown as "your phone".
        self.assertNotIn(SEED_PHONE, html)
        # ...and each missing item is listed, in Persian.
        self.assertIn("تلفن پشتیبانی", html)
        self.assertIn("cusin-readiness-missing", html)


@override_settings(**PLAIN_STATIC)
class LegalPageReadinessTests(CacheIsolationMixin, TestCase):
    def test_card_exists(self):
        card = readiness_by_id()["legal_pages"]
        assert_persian(self, card["label"], "legal_pages label")

    def test_sample_pages_fail_and_name_themselves(self):
        card = readiness_by_id()["legal_pages"]
        self.assertFalse(card["ok"])
        assert_persian(self, card["detail"], "legal_pages detail")
        self.assertTrue(card["missing"])
        for page in card["missing"]:
            assert_persian(self, page["label"], "page label")

    def test_card_passes_when_no_page_is_marked(self):
        from pathlib import Path
        import tempfile

        directory = Path(tempfile.mkdtemp())
        (directory / "TermsPage.jsx").write_text(
            "export default function T() {\n"
            "  return <InfoPageLayout placeholder={false}>متن حقوقی واقعی"
            "</InfoPageLayout>;\n}\n",
            encoding="utf-8",
        )
        with mock.patch("apps.core.placeholders.LEGAL_PAGES_DIR", directory):
            card = readiness_by_id()["legal_pages"]
        self.assertTrue(card["ok"])

    def test_missing_frontend_sources_never_read_as_done(self):
        from pathlib import Path
        import tempfile

        absent = Path(tempfile.gettempdir()) / "no-frontend-here"
        with mock.patch("apps.core.placeholders.LEGAL_PAGES_DIR", absent):
            card = readiness_by_id()["legal_pages"]
        self.assertFalse(card["ok"])
