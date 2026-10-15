"""Multi-line ``{# … #}`` comments are NOT comments.

Django tokenizes a template with::

    tag_re = re.compile(r"({%.*?%}|{{.*?}}|{#.*?#})")

-- note the missing ``re.DOTALL``. ``{#`` therefore only reaches a ``#}``
on the SAME LINE; the moment a comment wraps, the lexer never matches it
and the whole block, markers included, is emitted as ordinary text:

    {# Title, sentence, then the missing items -- each shown ONCE. The
       text is one flex column of its own so the sub-list spans the
       full row instead of becoming a narrow column beside the icon. #}

landed verbatim on the dashboard's readiness card, and the same happened
on the order change page and on the image-import preview (three
instances, all of them comments written during the last round).

Use ``{% comment %}…{% endcomment %}`` for anything that wraps. This test
scans every template so the next one is caught before it ships.
"""
from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.adminui.tests.helpers import PLAIN_STATIC, make_superuser

REPO_ROOT = Path(settings.BASE_DIR).parent

#: Directories that never hold project templates (vendored deps, caches).
SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", "staticfiles"}

OPEN_COMMENT = re.compile(r"\{#")


def repo_templates():
    """Every template the project ships (.html anywhere, plus anything
    under a ``templates/`` directory)."""
    for path in sorted(REPO_ROOT.rglob("*")):
        if not path.is_file():
            continue
        if SKIP_DIRS & set(path.parts):
            continue
        if path.suffix == ".html" or "templates" in path.parts:
            if path.suffix in {".html", ".txt", ".xml", ".csv", ".md", ".json"}:
                yield path


def broken_comments():
    """[(path, line number, snippet)] for every comment that wraps."""
    problems = []
    for path in repo_templates():
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in OPEN_COMMENT.finditer(text):
            start = match.start()
            end = text.find("#}", start)
            if end == -1:
                problems.append(
                    (path, text[:start].count("\n") + 1, "unclosed {# (no #} at all)")
                )
                continue
            block = text[start:end + 2]
            if "\n" in block:
                problems.append(
                    (
                        path,
                        text[:start].count("\n") + 1,
                        " ".join(block.split())[:80],
                    )
                )
    return problems


class TemplateCommentSyntaxTests(SimpleTestCase):
    def test_no_comment_wraps_onto_a_second_line(self):
        problems = broken_comments()
        self.assertEqual(
            problems,
            [],
            "multi-line {# … #} is rendered as visible text; use "
            "{% comment %}…{% endcomment %} instead:\n"
            + "\n".join(f"  {p.relative_to(REPO_ROOT)}:{line}: {snip}"
                        for p, line, snip in problems),
        )

    def test_the_scanner_sees_the_templates_it_is_meant_to_guard(self):
        """A green test that looked at nothing would be worthless."""
        paths = list(repo_templates())
        self.assertGreater(len(paths), 20, paths[:5])
        self.assertTrue(
            any(p.name == "index.html" for p in paths),
            "the dashboard template is not being scanned",
        )

    def test_the_scanner_catches_the_bug_it_exists_for(self):
        sample = (
            "<div>\n"
            "{# a comment that\n"
            "   wraps onto a second line #}\n"
            "</div>\n"
        )
        path = Path(settings.BASE_DIR) / "test_zz_comment_probe.html"
        try:
            path.write_text(sample, encoding="utf-8")
            found = [p for p, _line, _snip in broken_comments() if p == path]
            self.assertEqual(len(found), 1)
        finally:
            path.unlink(missing_ok=True)


@override_settings(**PLAIN_STATIC)
class RenderedPagesHaveNoCommentTextTests(TestCase):
    """The three pages that actually shipped the text."""

    def setUp(self):
        self.admin = make_superuser(username="comment-owner", phone="+989000070001")
        self.client.force_login(self.admin)

    def assert_no_comment_markers(self, html, what):
        self.assertNotIn("{#", html, f"{what}: a Django comment leaked into the page")
        self.assertNotIn("#}", html, f"{what}: a Django comment leaked into the page")

    def test_the_dashboard_readiness_card_is_clean(self):
        html = self.client.get(reverse("admin:index")).content.decode()
        self.assert_no_comment_markers(html, "dashboard")
        self.assertNotIn("each shown ONCE", html)
        self.assertNotIn("one flex column of its own", html)

    def test_the_order_change_page_is_clean(self):
        from apps.adminui.tests.helpers import make_order

        order = make_order()
        html = self.client.get(
            reverse("admin:orders_order_change", args=[order.pk])
        ).content.decode()
        self.assert_no_comment_markers(html, "order change page")
        self.assertNotIn("the payment rule forbids", html)

    def test_the_image_import_preview_is_clean(self):
        from apps.products.tests.test_image_import import (
            build_zip,
            png_bytes,
            zip_upload,
        )
        from apps.products.tests.helpers import make_product

        make_product(name="کاسه", sku="SOOLE-001")
        payload = build_zip([("SOOLE-001.jpg", png_bytes((1, 1, 1)))])
        html = self.client.post(
            reverse("admin:products_product_image_import"),
            {"zip": zip_upload(payload), "mode": "add"},
        ).content.decode()
        self.assert_no_comment_markers(html, "image import preview")
        self.assertIn("تأیید و ذخیره", html)
