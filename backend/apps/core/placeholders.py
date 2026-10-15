"""
One definition of "this value is a PLACEHOLDER, not real content".

The store shipped with sample content baked into the seed migration
(``+98 21 0000 0000``, ``[نشانی واقعی فروشگاه را از پنل مدیریت وارد کنید]``)
and with trust pages marked «نمونه (placeholder)». Those are not values:
they are an instruction to the owner. Treating them as set meant

* the dashboard readiness card said «تلفن و نشانی در «تنظیمات سایت» تکمیل
  شده» while the storefront was showing a fake phone number, and
* the bracketed sentences were rendered verbatim to customers.

Everything that asks "is this filled in?" -- the readiness card, the
public API, the storefront -- goes through this module, so the answer can
never diverge again.
"""
from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings

# --------------------------------------------------------------------------
# Value-level placeholders
# --------------------------------------------------------------------------

# «[نشانی واقعی فروشگاه را از پنل مدیریت وارد کنید]» -- any value that is
# bracketed from end to end is an instruction, not content.
BRACKETED_RE = re.compile(r"^\s*[\[\]][\s\S]*[\]\[]\s*$")

# A seed/sample phone number: «+98 21 0000 0000». Real numbers keep their
# subscriber digits, so the test is "a long run of zeros with nothing but
# a short country/city prefix in front of it".
_ZERO_RUN_RE = re.compile(r"0{4,}")
_PHONEISH_RE = re.compile(r"^[\d\s\-+()]+$")


# Words that mark a still-unedited legal/trust page.
PLACEHOLDER_MARKERS = (
    "(placeholder)",
    "placeholder",
    "[متن نمونه",
    "متن نمونه",
)


def is_placeholder_phone(value) -> bool:
    """True for «+98 21 0000 0000» and friends.

    A real number can legitimately contain a few zeros («912 000 567»),
    so this is not "contains 0000": the zeros must run to the end of the
    number with at most a short country/city prefix ahead of them.
    """
    text = "" if value is None else str(value)
    digits = re.sub(r"\D", "", text)
    if not digits:
        return False
    match = _ZERO_RUN_RE.search(digits)
    if not match:
        return False
    head = digits[: match.start()]
    return len(head) <= 4


def is_placeholder(value) -> bool:
    """True when the stored value is a placeholder rather than content."""
    if value is None:
        return True
    text = str(value).strip()
    if not text:
        return True
    if BRACKETED_RE.match(text):
        return True
    if is_placeholder_phone(text) and _PHONEISH_RE.match(text):
        return True
    # A leftover marker inside a longer text («… نمونه (placeholder) …»).
    return any(marker in text.casefold() for marker in PLACEHOLDER_MARKERS)


def clean_value(value) -> str:
    """The value for DISPLAY: "" when it is a placeholder.

    This is the "never render a bracketed placeholder on the storefront"
    rule, in one place: templates and serializers call this instead of
    touching the raw field.
    """
    if value is None:
        return ""
    text = str(value)
    return "" if is_placeholder(text) else text.strip()


def is_set(value) -> bool:
    """True when a field holds real content (the readiness question)."""
    return bool(clean_value(value))


# --------------------------------------------------------------------------
# SiteSettings: what is still missing, in Persian
# --------------------------------------------------------------------------

#: (field name, Persian label, required for launch?)
SITE_FIELDS = (
    ("phone", "تلفن پشتیبانی", True),
    ("address", "نشانی فروشگاه", True),
    ("working_hours", "ساعات پاسخگویی", False),
    ("pickup_address", "نشانی دریافت حضوری", False),
    ("pickup_hours", "ساعات دریافت حضوری", False),
    ("instagram", "اینستاگرام", False),
    ("telegram", "تلگرام", False),
    ("whatsapp", "واتس‌اپ", False),
)

#: Fields that hold a phone number (placeholder-zero test applies).
PHONE_FIELDS = frozenset({"phone", "whatsapp"})


def missing_site_items(site) -> list[dict]:
    """Every SiteSettings field that is empty OR still a placeholder.

    Returns ``[{field, label, value, required, reason}]`` -- the reason is
    already Persian, so the dashboard can list each one verbatim.
    """
    missing = []
    for field, label, required in SITE_FIELDS:
        raw = getattr(site, field, None) or ""
        text = str(raw).strip()
        if is_placeholder(raw):
            reason = (
                "مقدار نمونه (رها شده) است و باید با مقدار واقعی جایگزین شود."
                if text
                else "خالی است."
            )
            if text and is_placeholder_phone(text):
                reason = "شمارهٔ نمونه (۰۰۰۰) است و باید با شمارهٔ واقعی جایگزین شود."
            missing.append(
                {
                    "field": field,
                    "label": label,
                    "value": text,
                    "required": required,
                    "reason": reason,
                }
            )
    return missing


def missing_site_labels(site) -> list[str]:
    """Just the Persian labels -- handy for one-line messages."""
    return [item["label"] for item in missing_site_items(site)]


# --------------------------------------------------------------------------
# Legal / trust pages
# --------------------------------------------------------------------------

#: The static trust pages (routes live in the React app; mirrored here so
#: the backend's readiness card can point the owner at each one).
LEGAL_PAGES = (
    ("about", "دربارهٔ ما", "/about/", "AboutPage.jsx"),
    ("contact", "تماس با ما", "/contact/", "ContactPage.jsx"),
    ("shipping-returns", "ارسال و مرجوعی", "/shipping-returns/", "ShippingReturnsPage.jsx"),
    ("terms", "شرایط استفاده", "/terms/", "TermsPage.jsx"),
    ("privacy", "حریم خصوصی", "/privacy/", "PrivacyPage.jsx"),
)

#: Where the page sources live in a checkout. Absent in a backend-only
#: production image -- see ``placeholder_legal_pages`` for the fallback.
LEGAL_PAGES_DIR = Path(settings.BASE_DIR).parent / "frontend" / "src" / "pages" / "info"


def _strip_js_comments(source: str) -> str:
    """Drop /* … */ and // … comments.

    Necessary because every page's header comment explains how to turn
    the flag off -- reading comments would report all of them as done.
    """
    without_blocks = re.sub(r"/\*[\s\S]*?\*/", "", source)
    return "\n".join(
        re.sub(r"(^|\s)//.*$", "", line) for line in without_blocks.splitlines()
    )


def _page_is_placeholder(source: str) -> bool:
    """A page is still a placeholder when it renders the owner notice.

    InfoPageLayout defaults ``placeholder`` to true, so the notice shows
    unless the page explicitly passes ``placeholder={false}`` -- that is
    exactly the signal (it is the step the docs tell the owner to take
    once the real text is in). A still-bracketed sample sentence
    («[متن نمونه …]») also counts, for the page that turned the flag off
    but never rewrote the copy.
    """
    code = _strip_js_comments(source)
    if re.search(r"placeholder\s*=\s*\{\s*false\s*\}", code):
        return any(marker in code for marker in ("[متن نمونه", "متن نمونه"))
    return True


def placeholder_legal_pages() -> list[dict]:
    """The trust pages that are still marked as sample content.

    Source of truth is the page source itself when it is available (a dev
    checkout, CI, tests). A deployed backend image does not carry the
    frontend sources, so it falls back to ``LEGAL_PAGES_PLACEHOLDER``
    (env, default: all of them) -- a missing source must never be read as
    "everything is fine".
    """
    if LEGAL_PAGES_DIR.is_dir():
        found = []
        for slug, label, path, filename in LEGAL_PAGES:
            target = LEGAL_PAGES_DIR / filename
            try:
                source = target.read_text(encoding="utf-8")
            except OSError:
                continue
            if _page_is_placeholder(source):
                found.append(
                    {
                        "slug": slug,
                        "label": label,
                        "path": path,
                        "file": f"frontend/src/pages/info/{filename}",
                        "reason": "متن این صفحه هنوز نمونه (placeholder) است.",
                    }
                )
        return found

    marked = {
        slug.strip()
        for slug in getattr(settings, "LEGAL_PAGES_PLACEHOLDER", []) or []
        if slug.strip()
    } or {slug for slug, _label, _path, _file in LEGAL_PAGES}
    return [
        {
            "slug": slug,
            "label": label,
            "path": path,
            "file": f"frontend/src/pages/info/{filename}",
            "reason": "متن این صفحه هنوز نمونه (placeholder) است.",
        }
        for slug, label, path, filename in LEGAL_PAGES
        if slug in marked
    ]
