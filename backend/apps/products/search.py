"""
Persian/Arabic search normalization (Part R5, item 7).

ONE shared normalizer is used for BOTH indexing (Product.search_text,
filled on save / rename / backfill) and querying (the products list
endpoint, which also powers the header's live suggestions), so the two
sides can never drift apart.

Rules:
  * Arabic yeh ي and alef-maksura ى -> Persian yeh ی; Arabic kaf ك ->
    Persian kaf ک;
  * alef variants آ أ إ ٱ -> plain ا; ta-marbuta ة -> ه;
  * ZWNJ/ZWJ, tatweel and Arabic diacritics removed entirely;
  * Persian (۰-۹) and Arabic-Indic (٠-٩) digits mapped to ASCII;
  * whitespace collapsed; Latin case-folded.

Searching is token-based and order-independent: every query token must
occur in the product's normalized search_text. Results are ranked by
relevance (exact SKU > normalized name starts-with > name contains >
other field hits). Deliberately NO PostgreSQL-only features (trigrams
etc.) so the suite stays SQLite-compatible.
"""
from django.db.models import Case, IntegerField, Value, When

# Single-codepoint replacements.
_CHAR_MAP = {
    "\u064A": "\u06CC",  # Arabic yeh -> Persian yeh
    "\u0649": "\u06CC",  # alef maksura -> Persian yeh
    "\u0643": "\u06A9",  # Arabic kaf -> Persian kaf
    "\u0622": "\u0627",  # alef with madda -> alef
    "\u0623": "\u0627",  # alef with hamza above -> alef
    "\u0625": "\u0627",  # alef with hamza below -> alef
    "\u0671": "\u0627",  # alef wasla -> alef
    "\u0629": "\u0647",  # ta marbuta -> he
}

# Characters dropped entirely.
_DROP = {
    "\u200C",  # zero-width non-joiner (nim-fasele)
    "\u200D",  # zero-width joiner
    "\u0640",  # tatweel
}
# Arabic diacritics block + superscript alef.
_DIACRITICS = [chr(c) for c in range(0x064B, 0x0660)] + ["\u0670"]

_PERSIAN_DIGITS = {chr(0x06F0 + i): str(i) for i in range(10)}
_ARABIC_DIGITS = {chr(0x0660 + i): str(i) for i in range(10)}

_TRANSLATE = {ord(k): v for k, v in {
    **_CHAR_MAP, **_PERSIAN_DIGITS, **_ARABIC_DIGITS,
}.items()}
_DROP_TRANSLATE = {ord(c): None for c in list(_DROP) + _DIACRITICS}


def normalize_text(value):
    """Returns the search-normalized form of any string ('' for None)."""
    if not value:
        return ""
    text = str(value).translate(_TRANSLATE).translate(_DROP_TRANSLATE)
    text = text.casefold()
    return " ".join(text.split())


def build_product_search_fields(product):
    """Computes (search_text, search_name) for a product instance from its
    name, sku, brand name, category name and short description."""
    parts = [
        product.name,
        product.sku,
        product.brand.name if getattr(product, "brand_id", None) else "",
        product.category.name if getattr(product, "category_id", None) else "",
        product.short_description,
    ]
    search_text = " ".join(normalize_text(part) for part in parts if part)
    return " ".join(search_text.split()), normalize_text(product.name)


def refresh_search_fields(products):
    """Recomputes search_text/search_name for the given products queryset
    in batches (used by Brand/Category rename propagation + backfill)."""
    batch = []
    for product in products.select_related("brand", "category").iterator(chunk_size=500):
        product.search_text, product.search_name = build_product_search_fields(product)
        batch.append(product)
        if len(batch) >= 500:
            _bulk_update(batch)
            batch = []
    if batch:
        _bulk_update(batch)


def _bulk_update(batch):
    from .models import Product

    Product.objects.bulk_update(batch, ["search_text", "search_name"], batch_size=500)


def product_search(queryset, query):
    """Token AND-match on search_text plus relevance ordering. Returns the
    filtered+ordered queryset (never raises)."""
    tokens = normalize_text(query).split()
    if not tokens:
        return queryset.none()
    qs = queryset
    for token in tokens:
        qs = qs.filter(search_text__icontains=token)
    raw = query.strip()
    full = " ".join(tokens)
    qs = qs.annotate(
        _search_rank=Case(
            When(sku__iexact=raw, then=Value(0)),
            When(search_name__startswith=full, then=Value(1)),
            When(search_name__icontains=full, then=Value(2)),
            default=Value(3),
            output_field=IntegerField(),
        )
    )
    return qs.order_by("_search_rank", "-created_at")
