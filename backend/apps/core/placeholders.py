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

#: The five fixed info pages: slug, Persian label, public path. Their TEXT
#: lives in the InfoPage rows now (Task 1), so the readiness check reads the
#: database -- a deleted React file can no longer make a page look "done".
LEGAL_PAGES = (
    ("about", "دربارهٔ ما", "/about/"),
    ("contact", "تماس با ما", "/contact/"),
    ("shipping-returns", "ارسال و مرجوعی", "/shipping-returns/"),
    ("terms", "قوانین و مقررات", "/terms/"),
    ("privacy", "حریم خصوصی", "/privacy/"),
)


def _page_body_is_placeholder(body) -> bool:
    """Empty text, or text still carrying a «نمونه» marker."""
    text = (body or "").strip()
    if not text:
        return True
    lowered = text.lower()
    return any(marker.lower() in lowered for marker in PLACEHOLDER_MARKERS)


def placeholder_legal_pages() -> list[dict]:
    """The trust pages that are empty, unpublished or still sample copy.

    The pages are database rows since Task 1; reading them here (instead of
    the old React sources) means the admin card keeps telling the truth
    after the page files were replaced by the owner-editable model.
    """
    from django.db import DatabaseError

    from apps.core.models import InfoPage

    try:
        rows = {page.slug: page for page in InfoPage.objects.all()}
    except DatabaseError:  # pragma: no cover - pre-migrate deployment
        rows = {}

    found = []
    for slug, label, path in LEGAL_PAGES:
        page = rows.get(slug)
        if (
            page is None
            or not page.is_published
            or _page_body_is_placeholder(page.body)
        ):
            found.append(
                {
                    "slug": slug,
                    "label": label,
                    "path": path,
                    "reason": (
                        "متن این صفحه هنوز کامل یا منتشر نشده است؛ در "
                        "«صفحات اطلاعاتی» تکمیل و منتشر کنید."
                    ),
                }
            )
    return found
