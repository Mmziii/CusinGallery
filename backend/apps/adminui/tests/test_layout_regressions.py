"""Layout regressions for the admin dashboard and changelists (follow-up 2).

These are source tests and a rendered-page check. They read theme.css and the
templates and assert the declarations that remove each layout defect. They do
not measure layout: a passing test proves the declaration exists, not that the
page lays out correctly. The real widths, overflow and overlap are measured in
a browser by e2e/admin-layout.spec.js (see docs/LAUNCH_CHECKLIST.md section 10).
"""
import re
from pathlib import Path

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse

from .helpers import PLAIN_STATIC, make_superuser
from .test_responsive_css import _rules, _strip_comments, _without_media

BASE = Path(settings.BASE_DIR)
THEME_CSS = BASE / "static" / "admin_theme" / "css" / "theme.css"


def _base_rules():
    """Base (non-media) rules of theme.css: selector -> {property: value}."""
    css = THEME_CSS.read_text(encoding="utf-8")
    return _rules(_without_media(_strip_comments(css)))


def _declared_widths(css_text, selector):
    """Every `width` value declared for `selector` in source order (media
    blocks included), so a later 600px override cannot hide behind a base rule."""
    flat = _strip_comments(css_text)
    values = []
    for match in re.finditer(r"([^{}]+)\{([^{}]*)\}", flat):
        selectors = [" ".join(s.split()) for s in match.group(1).split(",")]
        if selector not in selectors:
            continue
        for decl in re.finditer(r"(?<![-\w])width\s*:\s*([^;]+);", match.group(2)):
            values.append(decl.group(1).strip())
    return values


class DashboardWidthTests(TestCase):
    """Item 1: stock Django pins `.dashboard #content` to 600px; the dashboard
    must fill main.content instead."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.css_text = THEME_CSS.read_text(encoding="utf-8")

    def test_theme_does_not_keep_the_600px_pin(self):
        widths = _declared_widths(self.css_text, ".dashboard #content")
        self.assertTrue(widths, "theme.css must size .dashboard #content")
        self.assertNotIn("600px", widths)

    def test_dashboard_column_fills_its_container(self):
        # The last declared width wins; it must be fluid, not a fixed pixel size.
        widths = _declared_widths(self.css_text, ".dashboard #content")
        self.assertEqual(widths[-1], "100%")

    def test_dashboard_column_has_a_cap_for_very_wide_screens(self):
        rules = _base_rules()
        self.assertIn(".dashboard #content", rules)
        max_width = rules[".dashboard #content"].get("max-width", "")
        self.assertRegex(max_width, r"^\d{4}px$")
        self.assertGreaterEqual(int(max_width[:-2]), 1280)

    @override_settings(**PLAIN_STATIC)
    def test_rendered_dashboard_page_has_the_dashboard_body_class(self):
        # The override is scoped to `.dashboard`; if the page stopped carrying
        # that class the rule would silently stop applying.
        self.client.force_login(make_superuser())
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 200)
        self.assertRegex(response.content.decode("utf-8"), r'<body class="[^"]*\bdashboard\b')
