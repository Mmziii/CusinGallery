"""Source test: a closed element must stay closed (the palette-stays-open bug).

Root cause that this guards against: `.cusin-palette { display: flex }` is an
author rule, and an author rule beats the browser's default `[hidden]
{ display: none }`. The palette therefore stayed visible after it was
"closed" with the hidden attribute.

The test scans:
  * the templates, for elements rendered with a bare `hidden` attribute;
  * the scripts, for `<variable>.hidden = ...` assignments and the selector
    the variable was found with;
and maps each one to its CSS classes or data attributes. For every element
that a theme.css rule gives a `display` value, a base-level
`[hidden] { display: none !important }` override must exist. The override
lives outside any media query because a closed element must stay closed at
every width. The jsdom tests (cssVisibility.test.js) check the same thing
from the rendered result."""
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from .test_responsive_css import _rules, _strip_comments, _without_media

BASE = Path(settings.BASE_DIR)
THEME_CSS = BASE / "static" / "admin_theme" / "css" / "theme.css"
ADMIN_JS = BASE / "static" / "admin_theme" / "js"

TAG_RE = re.compile(r"<([a-zA-Z][\w-]*)([^>]*)>")
QUOTED_RE = re.compile(r"\"[^\"]*\"|'[^']*'")
ASSIGN_RE = re.compile(r"\b(\w+)\.hidden\s*=(?!=)")
DECL_RE = re.compile(
    r"(?:var|let|const)\s+(\w+)\s*=\s*[^;]*?querySelector(?:All)?\(\s*[\"']([^\"']+)[\"']"
)
DATA_ATTR_RE = re.compile(r"\[(data-[\w-]+)\]")


def _template_files():
    roots = [BASE / "templates"] + sorted((BASE / "apps").glob("*/templates"))
    for root in roots:
        yield from root.rglob("*.html")


def _hidden_elements_in_templates():
    """Yield (classes, data_attributes) for every tag with a bare hidden attribute."""
    for path in _template_files():
        source = path.read_text(encoding="utf-8")
        for _tag, attrs in TAG_RE.findall(source):
            if 'type="hidden"' in attrs:
                continue
            bare = QUOTED_RE.sub('""', attrs)
            if not re.search(r"(?:^|\s)hidden(?=\s|/|$)", bare):
                continue
            class_match = re.search(r'class="([^"]*)"', attrs)
            classes = class_match.group(1).split() if class_match else []
            data_attrs = re.findall(r"(data-[\w-]+)", attrs)
            yield path.name, classes, data_attrs


def _script_toggled_selectors():
    """Map each `<var>.hidden =` in the scripts to the selector that var came from."""
    found = {}
    for path in sorted(ADMIN_JS.glob("*.js")):
        source = path.read_text(encoding="utf-8")
        declared = dict(DECL_RE.findall(source))
        for variable in set(ASSIGN_RE.findall(source)):
            if variable in declared:
                found.setdefault(path.name, {})[variable] = declared[variable]
    return found


def _token_pattern(token):
    if token.startswith("data-"):
        return re.compile(r"\[" + re.escape(token) + r"(?:[=\]])")
    return re.compile(r"\." + re.escape(token) + r"(?![\w-])")


class HiddenAttributeTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.css = _strip_comments(THEME_CSS.read_text(encoding="utf-8"))
        cls.base = _rules(_without_media(cls.css))
        cls.all_rules = _rules(cls.css)
        # selectors that set display anywhere in theme.css (base or media)
        cls.display_selectors = [
            selector for selector, decls in cls.all_rules.items() if "display" in decls
        ]

    def _targets(self):
        """name -> set of class/data tokens that identify one hidden element."""
        targets = {}
        for template, classes, data_attrs in _hidden_elements_in_templates():
            tokens = set(classes) | set(data_attrs)
            if tokens:
                targets[f"{template} {sorted(tokens)}"] = tokens
        toggled = _script_toggled_selectors()
        for script, variables in toggled.items():
            for variable, selector in variables.items():
                attrs = set(DATA_ATTR_RE.findall(selector))
                self.assertTrue(
                    attrs,
                    f"{script}: `{variable}.hidden` comes from {selector!r}, "
                    "which has no data attribute to find it by",
                )
                targets[f"{script}:{variable} {sorted(attrs)}"] = attrs
        return targets

    def test_sanity_the_scan_finds_the_known_hidden_elements(self):
        """Without this the test could pass by finding nothing."""
        names = " ".join(self._targets())
        self.assertIn("cusin-palette", names)  # palette root in base.html
        self.assertIn("cusin-drawer-scrim", names)  # drawer scrim in base.html
        self.assertIn("cusin-preview-old", names)  # compare-at price in the product form
        self.assertIn("data-cusin-palette", names)  # toggled by theme.js
        self.assertIn("data-cusin-drawer-scrim", names)  # toggled by theme.js
        self.assertIn("data-cusin-preview-compare", names)  # toggled by product_form.js

    def test_the_hidden_attribute_wins_at_the_base_level(self):
        """The override must be outside any media query, so a closed element
        stays closed at every width (the drawer scrim had its override only
        inside a media query)."""
        self.assertEqual(
            self.base.get("[hidden]", {}).get("display"),
            "none !important",
            "theme.css needs a base-level `[hidden] { display: none !important; }`",
        )

    def test_no_hidden_element_has_a_display_rule_without_the_override(self):
        overridden = self.base.get("[hidden]", {}).get("display") == "none !important"
        for name, tokens in sorted(self._targets().items()):
            with self.subTest(element=name):
                patterns = [_token_pattern(token) for token in tokens]
                displayed = [
                    selector
                    for selector in self.display_selectors
                    if any(pattern.search(selector) for pattern in patterns)
                ]
                if displayed:
                    self.assertTrue(
                        overridden,
                        f"{name} is rendered hidden, but theme.css sets display on it "
                        f"({displayed}) and has no base-level [hidden] override",
                    )
