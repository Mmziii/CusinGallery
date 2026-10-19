"""
Allowlist HTML sanitiser for owner-editable storefront HTML.

The owner edits the info pages and the e-namad/trust-seal snippet from the
admin panel, so their HTML is rendered with ``dangerouslySetInnerHTML`` on
the storefront. That is safe ONLY if it has been reduced to a small,
known-good subset first:

* only the tags in ``ALLOWED_TAGS`` (paragraphs, headings, lists, links,
  emphasis, quotes) and no ``style`` / ``on*`` / ``class`` attributes;
* links only to ``http``, ``https``, ``mailto``, ``tel`` or a relative URL
  -- ``javascript:``, ``data:``, ``vbscript:`` and obfuscated variants
  (control characters, entities) are rejected;
* ``script`` / ``style`` / ``iframe`` / ``object`` / ``embed`` / ``svg``
  are dropped WITH their contents, not just unwrapped.

No third-party package is used (the project deliberately keeps its
dependency list minimal); this is the stdlib ``html.parser`` implementation
the task allows. ``sanitize_html`` is applied on admin save AND again in the
public serializer, so legacy/directly-written rows cannot bypass it.
"""
from __future__ import annotations

import html
import re
from html.parser import HTMLParser

#: Inline text markup an owner may use in an info page.
ALLOWED_TAGS = frozenset(
    {
        "p", "br", "hr", "strong", "b", "em", "i", "u", "s",
        "h2", "h3", "h4", "ul", "ol", "li", "blockquote", "a",
    }
)

#: Void elements: emitted once, never pushed on the open-tag stack.
VOID_TAGS = frozenset({"br", "hr"})

#: Dropped TOGETHER WITH their contents.
DROP_WITH_CONTENT = frozenset(
    {"script", "style", "iframe", "object", "embed", "svg", "math", "noscript", "template"}
)

#: Tags/attributes accepted in the e-namad (trust seal) snippet.
EMBED_TAGS = frozenset(
    {"div", "span", "a", "img", "p", "br", "strong", "em", "small", "table", "tbody", "tr", "td"}
)
EMBED_ATTRS = {
    "a": {"href", "target", "rel", "title", "referrerpolicy"},
    "img": {"src", "alt", "title", "width", "height", "referrerpolicy", "loading"},
    "*": {"id", "class", "dir", "lang"},
}

SAFE_SCHEMES = frozenset({"http", "https", "mailto", "tel"})

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x20\x7f]+")
_SCHEME_RE = re.compile(r"^([a-zA-Z][a-zA-Z0-9+.-]*):")


def _compact(value: str) -> str:
    """Lower-cased URL with whitespace/control characters removed.

    Browsers ignore those characters when resolving a scheme, so
    ``java\\nscript:`` must be treated exactly like ``javascript:``.
    """
    return _CONTROL_CHARS_RE.sub("", value or "").lower()


def is_safe_url(value: str, *, allow_relative: bool = True) -> bool:
    """True when ``value`` is a link/image source we accept."""
    text = html.unescape(str(value or "")).strip()
    if not text:
        return False
    compact = _compact(text)
    if compact.startswith(("#", "/")):
        # Same-origin relative URL, fragment, /media/... or //host/path.
        return allow_relative
    match = _SCHEME_RE.match(compact)
    if not match:
        # A relative URL such as "page.html" or "images/x.png".
        return allow_relative
    return match.group(1) in SAFE_SCHEMES


def _clean_attrs(tag, attrs, allowed_frozenset):
    """Serialise the allowed attributes of one tag, in a stable order."""
    cleaned = []
    seen = set()
    for name, value in attrs:
        name = (name or "").lower()
        if name in seen:
            continue
        if name.startswith("on") or name == "style":
            continue
        if name not in allowed_frozenset:
            continue
        value = "" if value is None else str(value)
        if name in {"href", "src"}:
            if not is_safe_url(value):
                continue
            if name == "src" and tag == "img":
                # Image sources are also limited to http(s)/relative.
                pass
        if name == "target":
            if value not in {"_blank", "_self"}:
                continue
        if name == "class":
            # Class names can only reference the storefront's own stylesheet.
            value = " ".join(part for part in value.split() if part.isascii())
        seen.add(name)
        cleaned.append(f'{name}="{html.escape(value, quote=True)}"')
    if tag == "a" and dict(attrs).get("target") == "_blank":
        if "rel" not in seen:
            cleaned.append('rel="noopener noreferrer"')
    return (" " + " ".join(cleaned)) if cleaned else ""


class _Sanitizer(HTMLParser):
    def __init__(self, embed=False):
        super().__init__(convert_charrefs=False)
        self.embed = embed
        self.allowed = EMBED_TAGS if embed else ALLOWED_TAGS
        self.out: list[str] = []
        self.stack: list[str] = []
        self.skip_depth = 0

    # -- helpers ---------------------------------------------------------
    def _allowed_attrs(self, tag):
        if not self.embed:
            if tag == "a":
                return {"href", "title", "target"}
            return frozenset()
        base = EMBED_ATTRS.get(tag, EMBED_ATTRS["*"])
        return frozenset(base | EMBED_ATTRS["*"])

    def _void(self):
        if self.embed:
            return {"br", "hr", "img"}
        return VOID_TAGS

    def _emit_start(self, tag, attrs):
        attributes = _clean_attrs(tag, attrs, self._allowed_attrs(tag))
        self.out.append(f"<{tag}{attributes}>")

    def _close_all(self):
        while self.stack:
            self.out.append(f"</{self.stack.pop()}>")

    # -- HTMLParser API --------------------------------------------------
    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in DROP_WITH_CONTENT:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag not in self.allowed:
            return  # unwrap unknown tags, keep their text
        if tag == "a":
            href = dict(attrs).get("href")
            if href is not None and not is_safe_url(href):
                return  # drop the link, keep the text
        self._emit_start(tag, attrs)
        if tag not in self._void():
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        tag = tag.lower()
        if tag in DROP_WITH_CONTENT or self.skip_depth:
            return
        if tag not in self.allowed:
            return
        if tag == "a":
            href = dict(attrs).get("href")
            if href is not None and not is_safe_url(href):
                return
        self._emit_start(tag, attrs)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in DROP_WITH_CONTENT:
            if self.skip_depth:
                self.skip_depth -= 1
            return
        if self.skip_depth:
            return
        if tag not in self.allowed or tag in self._void():
            return
        if tag in self.stack:
            while self.stack:
                open_tag = self.stack.pop()
                self.out.append(f"</{open_tag}>")
                if open_tag == tag:
                    break

    def handle_data(self, data):
        if self.skip_depth:
            return
        self.out.append(html.escape(data, quote=False))

    def handle_entityref(self, name):
        if self.skip_depth:
            return
        self.out.append(html.escape(html.unescape(f"&{name};"), quote=False))

    def handle_charref(self, name):
        if self.skip_depth:
            return
        self.out.append(html.escape(html.unescape(f"&#{name};"), quote=False))

    def result(self):
        self._close_all()
        return "".join(self.out)


def sanitize_html(value: str) -> str:
    """Reduce an owner-edited info-page body to the safe inline subset."""
    if not value:
        return ""
    parser = _Sanitizer(embed=False)
    parser.feed(str(value))
    parser.close()
    return parser.result()


def sanitize_embed(value: str) -> str:
    """Sanitise the e-namad/trust-seal snippet (links + images allowed)."""
    if not value:
        return ""
    parser = _Sanitizer(embed=True)
    parser.feed(str(value))
    parser.close()
    return parser.result()
