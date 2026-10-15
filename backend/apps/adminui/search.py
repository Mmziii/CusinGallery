"""
Tolerant Persian/Arabic search for the admin (item 12).

The owner types what their keyboard gives them, which is not always what
is stored: Arabic yeh «ي» / alef-maksura «ى» where Persian yeh «ی» belongs,
Arabic kaf «ك» for Persian kaf «ک», Persian «۵» or Arabic «٥» digits where
the record has ASCII «5» (or the other way round), and nim-fasele that
someone typed and someone else did not. Postgres/SQLite compare codepoints,
so all of those returned «هیچ موردی یافت نشد» for a product that is
plainly there.

`apps/products/search.py` already normalizes for the STOREFRONT. This is
the admin side of the same problem, and it has to work "both ways":

* the QUERY is normalized (typing «علي» finds «علی»), and
* the STORED VALUE is matched tolerantly (typing «علی» finds «علي»).

Implementation note -- why a regex instead of normalizing the column
-------------------------------------------------------------------
Normalizing the stored value in SQL would mean ~30 chained REPLACE() calls
per search field (8 letters, 20 digits, 3 invisible characters), on every
row, per query. Instead each character of the normalized query becomes a
CHARACTER CLASS of the codepoints that normalize to it, with the invisible
characters allowed to appear anywhere between them. One `iregex` per field,
bounded cost, and it matches both directions at once.

The regex path is only used when the query actually contains something
ambiguous; a plain ASCII/Latin search keeps using Django's fast icontains.
"""
from __future__ import annotations

import re

from django.db.models import Q

from apps.products.search import normalize_text


def _ignorable() -> str:
    """Characters that carry no meaning in a search and may sit anywhere
    between the real ones: zero-width non-joiner (nim-fasele), zero-width
    joiner, tatweel, bidi/zero-width noise, and the Arabic diacritics.

    Built one codepoint at a time -- never as an ``a-z`` range -- so that
    ``re.escape`` cannot turn a hyphen into a literal and silently drop
    the range.
    """
    chars = [
        chr(0x200C),  # zero-width non-joiner (nim-fasele)
        chr(0x200D),  # zero-width joiner
        chr(0x0640),  # tatweel
        chr(0x200B),  # zero-width space
        chr(0x200E),  # LRM
        chr(0x200F),  # RLM
        chr(0x2060),  # word joiner
        chr(0x00A0),  # non-breaking space
        *[chr(c) for c in range(0x2066, 0x206A)],  # bidi isolates
        *[chr(c) for c in range(0x064B, 0x0660)],  # Arabic diacritics
        chr(0x0670),  # superscript alef
    ]
    return "".join(dict.fromkeys(chars))


_IGNORABLE = _ignorable()

# Every codepoint that normalizes down to a single character, grouped by
# that character -- built once from the SAME tables the storefront uses, so
# the two can never drift apart.
def _build_classes() -> dict[str, str]:
    groups: dict[str, set[str]] = {}
    for codepoint in list(range(0x0600, 0x0700)) + list(range(0x0030, 0x003A)):
        char = chr(codepoint)
        normalized = normalize_text(char)
        if len(normalized) == 1:
            groups.setdefault(normalized, set()).add(char)
    return {key: "".join(sorted(values)) for key, values in groups.items()}


_VARIANTS = _build_classes()

# A regex-safe "anything ignorable" fragment, inserted between characters.
_ANY_IGNORABLE = f"[{re.escape(_IGNORABLE)}]*"


def tolerant_pattern(query: str) -> str:
    """A case-insensitive regex matching ``query`` tolerantly, or "" when
    the query has nothing ambiguous in it (so the caller can keep using a
    plain ``icontains``)."""
    normalized = normalize_text(query)
    if not normalized:
        return ""

    parts = []
    interesting = False
    for char in normalized:
        if char.isspace():
            parts.append(f"[\\s{re.escape(_IGNORABLE)}]+")
            continue
        variants = _VARIANTS.get(char)
        if variants and len(variants) > 1:
            interesting = True
            parts.append(f"[{re.escape(variants)}]")
        elif variants:
            parts.append(re.escape(variants))
        else:
            parts.append(re.escape(char))
    if not interesting:
        return ""
    return _ANY_IGNORABLE.join(parts)


def _regex_lookups(search_fields) -> list[str]:
    """``search_fields`` -> ``iregex`` lookups, honouring the same prefixes
    Django's ``construct_search`` does (^ = iexact, = = iexact, @ = search)."""
    lookups = []
    for field in search_fields or ():
        if field.startswith("^") or field.startswith("="):
            lookups.append(f"{field[1:]}__iexact")
        elif field.startswith("@"):
            lookups.append(f"{field[1:]}__search")
        else:
            lookups.append(f"{field}__iregex")
    return lookups


def tolerant_q(search_fields, query: str) -> Q | None:
    """A Q matching ``query`` against ``search_fields`` tolerantly.

    Returns None when the query needs no tolerance (or is empty), so the
    caller can fall back to Django's default search untouched.
    """
    if not query or not search_fields:
        return None
    pattern = tolerant_pattern(query)
    if not pattern:
        return None
    clause = Q()
    for lookup in _regex_lookups(search_fields):
        clause |= Q(**{lookup: pattern})
    return clause


class NormalizedSearchMixin:
    """ModelAdmin mixin: Persian/Arabic-tolerant ``search_fields``.

    Widens Django's ``get_search_results`` with the tolerant clause. Any
    database that cannot run the regex (or any unexpected error) falls
    straight back to Django's own behaviour -- search must never break the
    changelist.
    """

    def get_search_results(self, request, queryset, search_term):
        from django.db.utils import DatabaseError

        plain, use_distinct = super().get_search_results(
            request, queryset, search_term
        )
        clause = tolerant_q(list(self.get_search_fields(request) or ()), search_term)
        if clause is None:
            return plain, use_distinct
        try:
            # Same base filters (get_queryset scoping, annotations and all),
            # different WHERE: Django's own clause OR the tolerant one. Both
            # sides select from the same table, so the OR cannot introduce
            # duplicates Django does not already know about.
            return plain | queryset.filter(clause), use_distinct
        except (DatabaseError, re.error, ValueError, AttributeError, TypeError):
            # A backend without REGEXP, or a pattern it rejects: degrade to
            # Django's plain search rather than 500 on the changelist.
            return plain, use_distinct
