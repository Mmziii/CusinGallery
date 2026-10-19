"""
Readiness: a placeholder is MISSING (store-launch blockers).

The card used to test ``bool((site.phone or "").strip())``. A fresh install
seeds «+98 21 0000 0000» and «[نشانی واقعی فروشگاه را از پنل مدیریت وارد
کنید]», both non-empty, so the card reported the store's contact info as
COMPLETE while customers were looking at a fake phone number. These tests
pin the new behaviour: placeholders fail the card, each missing item is
named in Persian, and the legal pages are checked too.
"""
import re

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
        # The Persian labels are what the owner sees -- in the sub-list,
        # not repeated inside the sentence.
        labels = [item["label"] for item in card["missing"]]
        self.assertIn("تلفن پشتیبانی", labels)
        self.assertIn("نشانی فروشگاه", labels)

    def test_the_sentence_does_not_repeat_the_list(self):
        """Each check is shown once: one sentence, then the items."""
        card = readiness_by_id()["site_profile"]
        for item in card["missing"]:
            with self.subTest(item=item["label"]):
                self.assertNotIn(item["label"], card["detail"])

    def test_card_passes_once_real_values_are_in(self):
        self._fill(phone=REAL_PHONE, address="تهران، خیابان ولیعصر، پلاک ۱۰")
        card = readiness_by_id()["site_profile"]
        self.assertTrue(card["ok"])
        # Required items are done; only optional ones can still be listed.
        self.assertEqual([i for i in card["missing"] if i["required"]], [])
        self.assertNotIn(
            "تلفن پشتیبانی", [i["label"] for i in card["missing"]]
        )

    def test_optional_fields_still_pass_but_are_mentioned(self):
        self._fill(phone=REAL_PHONE, address="تهران، خیابان ولیعصر، پلاک ۱۰")
        card = readiness_by_id()["site_profile"]
        self.assertTrue(card["ok"])
        # working_hours/pickup_* are optional: listed, not blocking.
        self.assertIn("ساعات پاسخگویی", [i["label"] for i in card["missing"]])
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
        from apps.core.models import InfoPage

        page = InfoPage.objects.get(slug="about")
        page.body = "<p>[متن نمونه — بعداً جایگزین شود]</p>"
        page.save()

        card = readiness_by_id()["legal_pages"]
        self.assertFalse(card["ok"])
        assert_persian(self, card["detail"], "legal_pages detail")
        self.assertEqual([item["slug"] for item in card["missing"]], ["about"])
        for item in card["missing"]:
            assert_persian(self, item["label"], "page label")
            # named once -- in the list, not spelled out in the sentence
            self.assertNotIn(item["label"], card["detail"])

    def test_card_passes_when_no_page_is_marked(self):
        # The data migration copied the current texts into every row, so a
        # fresh install is complete until the owner empties or unpublishes
        # a page.
        card = readiness_by_id()["legal_pages"]
        self.assertTrue(card["ok"])

    def test_missing_row_is_never_read_as_done(self):
        from apps.core.models import InfoPage

        InfoPage.objects.filter(slug="contact").delete()
        card = readiness_by_id()["legal_pages"]
        self.assertFalse(card["ok"])
        self.assertEqual([item["slug"] for item in card["missing"]], ["contact"])

def outer_li(html, check_id):
    """The inner HTML of one readiness row (``<li data-check=…>``).

    Nested ``<li>``s (the missing-item list) are counted, so the row is
    closed at the matching depth instead of at the first ``</li>``.
    """
    marker = f'data-check="{check_id}"'
    start = html.index(marker)
    open_start = html.rindex("<li", 0, start)
    depth = 0
    cursor = open_start
    while True:
        next_open = html.find("<li", cursor + 1)
        next_close = html.find("</li>", cursor + 1)
        if next_close == -1:
            raise AssertionError("unbalanced <li> in the readiness card")
        if next_open != -1 and next_open < next_close:
            depth += 1
            cursor = next_open
            continue
        if depth == 0:
            return html[open_start:next_close]
        depth -= 1
        cursor = next_close


@override_settings(**PLAIN_STATIC)
class ReadinessCardMarkupTests(CacheIsolationMixin, TestCase):
    """#2 The card used to show «تلفن و نشانی فروشگاه» and «صفحه‌های
    حقوقی/اعتماد» TWICE: once as a run-on sentence, and again as a nested
    list that ended up a ~140px column beside the icon (the row is a flex
    container, so the sub-list was a sibling, not a block)."""

    def dashboard(self):
        admin = make_superuser(username="ready-markup", phone="+989000017002")
        self.client.force_login(admin)
        with frozen_clock(FROZEN):
            response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    @staticmethod
    def css_block(selector):
        """The body of one rule in the theme stylesheet."""
        css = open(
            "static/admin_theme/css/theme.css", encoding="utf-8"
        ).read()
        return css.split(selector + " {", 1)[1].split("}", 1)[0]

    @staticmethod
    def listed_labels(row):
        return re.findall(r"<b>([^<]+)</b>", row)

    @staticmethod
    def sentence(row):
        return re.search(
            r'<span class="cusin-readiness-detail">(.*?)</span>', row, re.S
        ).group(1)

    def assert_named_once(self, row, expected):
        """The items are in the sub-list -- and nowhere else in the row."""
        self.assertIn("cusin-readiness-missing", row)
        labels = self.listed_labels(row)
        for label in expected:
            self.assertIn(label, labels)
        sentence = self.sentence(row)
        for label in labels:
            with self.subTest(label=label):
                self.assertEqual(
                    row.count(f"<b>{label}</b>"), 1,
                    f"«{label}» is not listed exactly once",
                )
                self.assertNotIn(
                    label, sentence, f"«{label}» is repeated in the sentence"
                )

    def test_the_shop_profile_row_names_each_item_once(self):
        row = outer_li(self.dashboard(), "site_profile")
        self.assert_named_once(row, ["تلفن پشتیبانی", "نشانی فروشگاه"])

    def test_the_legal_pages_row_names_them_once_too(self):
        from apps.core.models import InfoPage

        page = InfoPage.objects.get(slug="privacy")
        page.is_published = False
        page.save()
        row = outer_li(self.dashboard(), "legal_pages")
        self.assert_named_once(row, ["حریم خصوصی"])

    def test_the_item_is_one_full_width_block_not_a_row_of_columns(self):
        """Icon + title on the first row, then the sentence, then the
        missing items -- each of them a block, none of them a column
        fighting the others for width."""
        row = outer_li(self.dashboard(), "site_profile")
        head = row.index('class="cusin-readiness-head"')
        icon = row.index("<svg")
        sentence = row.index('class="cusin-readiness-detail"')
        listing = row.index('class="cusin-readiness-missing"')
        self.assertGreater(icon, head, "the icon belongs to the head row")
        self.assertLess(head, sentence, "the title comes before the sentence")
        self.assertLess(sentence, listing, "the sentence comes before the items")
        # the sub-list is NOT inside the head row: it is a block below it
        self.assertIn("</div>", row[head:sentence])
        # ...and the head holds nothing but the icon and the title
        head_block = row[head:row.index("</div>", head)]
        self.assertNotIn("cusin-readiness-missing", head_block)

    def test_no_loose_text_sits_between_the_items_elements(self):
        """A leaked template comment became anonymous text inside the flex
        container, so it took a share of the row's width and squeezed the
        sub-list below its own minimum. Every word must live in a tag."""
        from html.parser import HTMLParser

        class Loose(HTMLParser):
            """Text that is a DIRECT child of the row (depth 1)."""

            def __init__(self):
                super().__init__()
                self.depth = 0
                self.loose = []

            def handle_starttag(self, tag, attrs):
                # A self-closing <use/> is reported by HTMLParser as a
                # start tag AND an end tag, so plain counting stays
                # balanced for both spellings.
                self.depth += 1

            def handle_endtag(self, tag):
                self.depth = max(0, self.depth - 1)

            def handle_data(self, data):
                if self.depth == 1 and data.strip():
                    self.loose.append(data.strip()[:60])

        page = self.dashboard()
        for check in ("gateway", "site_profile", "legal_pages", "https"):
            parser = Loose()
            parser.feed(outer_li(page, check))
            parser.close()
            with self.subTest(check=check):
                self.assertEqual(
                    parser.loose, [],
                    "text outside any element in the readiness row",
                )

    def test_the_sub_list_spans_the_row_instead_of_forming_a_column(self):
        css = open(
            "static/admin_theme/css/theme.css", encoding="utf-8"
        ).read()
        rule = css[css.index(".cusin-readiness-missing {"):]
        rule = rule[: rule.index("}")]
        self.assertIn("grid", rule)
        self.assertIn("auto-fit", rule)
        # min() is what keeps a 15rem track from overflowing a narrower
        # row -- without it the track floors at 240px and pushes the page.
        self.assertIn("minmax(min(15rem, 100%), 1fr)", rule)

    SHRINKABLE = (
        ".cusin-readiness-list li",
        ".cusin-readiness-head",
        ".cusin-readiness-head strong",
        ".cusin-readiness-detail",
        ".cusin-readiness-missing",
        ".cusin-readiness-missing li",
    )

    def test_every_flex_and_grid_child_may_shrink_to_zero(self):
        """A grid/flex item's automatic minimum size is its min-content
        size; without min-width: 0 a wide child pushes the row past the
        viewport (readiness items were measured starting at x = -57)."""
        for selector in self.SHRINKABLE:
            with self.subTest(selector=selector):
                self.assertIn("min-width: 0", self.css_block(selector))

    def test_the_row_box_never_grows_by_its_own_padding(self):
        block = self.css_block(".cusin-readiness-list li")
        self.assertIn("box-sizing: border-box", block)
        self.assertIn("flex-direction: column", block)
        self.assertIsNone(
            re.search(r"(?<![\w-])width\s*:", block),
            "the row must not pin a width",
        )

    def test_no_readiness_rule_pins_a_pixel_width(self):
        for selector in self.SHRINKABLE + (".cusin-readiness-list",):
            with self.subTest(selector=selector):
                self.assertIsNone(
                    re.search(
                        r"(?<![\w-])(min-)?width\s*:\s*\d+px",
                        self.css_block(selector),
                    ),
                    f"{selector} pins a px width",
                )

