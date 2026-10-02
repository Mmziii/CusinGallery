"""
Bulk product import (Phase B - Store management).

One engine, two front-ends: the `import_products` management command
and the admin "import from file" view both call import_products_from_rows(),
so their behavior can never drift apart.

Semantics, kept deliberately simple and safe for a non-developer owner:

* Format: CSV (UTF-8, a BOM is fine) or Excel (.xlsx, first sheet).
* The first row is the header; it must match TEMPLATE_COLUMNS exactly
  (order does not matter; extra/missing columns are reported, not
  guessed at).
* Rows are matched to the catalog by SKU: a SKU that already exists is
  UPDATED, anything else is created. That makes the same file usable
  both for first-time loading and for price/stock updates later.
* All-or-nothing: every row is validated first; if ANY row has an
  error, NOTHING is written and all errors are reported with their
  spreadsheet row numbers. If every row is valid, the whole import
  runs in one transaction.
* Persian/Arabic digits entered in Excel (e.g. ۱۲۰۰۰۰) are normalized
  to ASCII before numeric parsing.

Images are intentionally NOT part of the file format: uploads belong in
the admin product form where validation and thumbnailing already live.
"""
import csv
import io

from django.db import transaction

from apps.categories.models import Category

from .models import Brand, Product

TEMPLATE_COLUMNS = [
    "name", "slug", "sku", "category_slug", "brand_name", "price",
    "compare_at_price", "discount_percentage", "stock_quantity",
    "low_stock_threshold", "short_description", "description",
    "is_active", "is_featured",
]

REQUIRED_COLUMNS = ["name", "slug", "sku", "category_slug", "price"]

_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_TRUE = {"true", "1", "yes", "بله", "فعال"}
_FALSE = {"false", "0", "no", "خیر", "غیرفعال", ""}


class ImportResult:
    def __init__(self):
        self.created = 0
        self.updated = 0
        self.errors = []

    @property
    def ok(self):
        return not self.errors


def _normalize(value):
    if value is None:
        return ""
    return str(value).translate(_PERSIAN_DIGITS).strip()


def _to_int(raw, *, minimum=0):
    text = _normalize(raw)
    if text == "":
        return None
    try:
        number = int(text.replace(",", ""))
    except ValueError:
        raise ValueError(f"«{raw}» یک عدد صحیح نیست")
    if number < minimum:
        raise ValueError(f"«{raw}» باید بزرگ‌تر یا مساوی {minimum} باشد")
    return number


def _to_bool(raw, default):
    text = _normalize(raw).lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False if text else default
    raise ValueError(f"«{raw}» مقدار معتبری برای درست/نادرست نیست")


def template_csv():
    """
    The downloadable sample/template: header + one realistic example
    row. Generated from the same constant the importer validates
    against, so template and importer can never drift apart.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(TEMPLATE_COLUMNS)
    writer.writerow([
        "ماگ سرامیکی دسته‌دار", "mug-ceramic", "MUG-001", "cookware",
        "کوزین", 180000, 220000, 10, 40, 5, "ماگ سرامیکی ۳۰۰ میلی‌لیتری",
        "بدنه سرامیک با لعاب براق، قابل شست‌وشو در ماشین ظرفشویی.",
        "true", "false",
    ])
    return buffer.getvalue()


def read_rows(upload):
    """
    Turn an uploaded file (or filesystem path string) into a list of
    dicts keyed by header name. Raises ValueError with an owner-readable
    message when the file itself is unusable.
    """
    name = getattr(upload, "name", "") or str(upload)
    lower = name.lower()

    if lower.endswith(".csv"):
        if hasattr(upload, "read"):
            raw = upload.read()
        else:
            with open(upload, "rb") as handle:
                raw = handle.read()
        text = raw.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        if reader.fieldnames is None:
            raise ValueError("فایل CSV خالی است.")
        rows = list(reader)
        return [dict(row) for row in rows], [h.strip() for h in reader.fieldnames]

    if lower.endswith(".xlsx"):
        try:
            from openpyxl import load_workbook
        except ImportError as exc:  # pragma: no cover - openpyxl is pinned
            raise ValueError("برای واردکردن اکسل، کتابخانهٔ openpyxl لازم است.") from exc
        workbook = load_workbook(upload, read_only=True, data_only=True)
        sheet = workbook.worksheets[0]
        grid = [[cell for cell in row] for row in sheet.iter_rows(values_only=True)]
        workbook.close()
        if not grid or all(c is None for c in grid[0]):
            raise ValueError("فایل اکسل خالی است.")
        header = ["" if c is None else str(c).strip() for c in grid[0]]
        rows = []
        for raw_row in grid[1:]:
            if all(c is None or str(c).strip() == "" for c in raw_row):
                continue  # ignore fully blank trailing rows Excel likes to add
            rows.append({header[i]: raw_row[i] for i in range(len(header))})
        return rows, header

    raise ValueError("نوع فایل پشتیبانی نمی‌شود. فایل .csv یا .xlsx بارگذاری کنید.")


def _validate_row(number, row, categories, brands):
    """Validate one row; return (errors, cleaned) where cleaned is None
    on failure. ``number`` is the spreadsheet row number (header = 1)."""
    errors = []

    def need(column, parser=None, *, required=True, default=None, minimum=0):
        raw = row.get(column)
        text = _normalize(raw)
        if text == "":
            if required:
                errors.append(f"ردیف {number}: ستون «{column}» الزامی است.")
            return default
        if parser is None:
            return text
        try:
            return parser(raw, minimum=minimum) if parser is _to_int else parser(raw)
        except ValueError as exc:
            errors.append(f"ردیف {number}: ستون «{column}» -- {exc}.")
            return default

    name = need("name")
    slug = need("slug")
    sku = need("sku")
    category_slug = need("category_slug")
    price = need("price", _to_int, minimum=1)
    compare_at_price = need("compare_at_price", _to_int, required=False, minimum=1)
    discount_percentage = need("discount_percentage", _to_int, required=False, default=0, minimum=0) or 0
    stock_quantity = need("stock_quantity", _to_int, required=False, default=0) or 0
    low_stock_threshold = need("low_stock_threshold", _to_int, required=False, default=5) or 0
    short_description = _normalize(row.get("short_description"))
    description = _normalize(row.get("description"))

    try:
        is_active = _to_bool(row.get("is_active"), default=True)
    except ValueError as exc:
        errors.append(f"Row {number}: 'is_active' -- {exc}.")
        is_active = True
    try:
        is_featured = _to_bool(row.get("is_featured"), default=False)
    except ValueError as exc:
        errors.append(f"Row {number}: 'is_featured' -- {exc}.")
        is_featured = False

    brand_name = _normalize(row.get("brand_name"))
    category = None
    if category_slug:
        category = categories.get(category_slug)
        if category is None:
            errors.append(
                f"ردیف {number}: دسته‌بندی «{category_slug}» وجود ندارد. "
                f"ابتدا آن را در بخش دسته‌بندی‌ها بسازید (یا category_slug را اصلاح کنید)."
            )
    brand = None
    if brand_name:
        brand = brands.get(brand_name)
        if brand is None:
            errors.append(
                f"ردیف {number}: برند «{brand_name}» وجود ندارد. "
                f"ابتدا آن را در بخش برندها بسازید (یا brand_name را اصلاح کنید)."
            )

    if discount_percentage > 100:
        errors.append(f"ردیف {number}: «discount_percentage» باید بین ۰ تا ۱۰۰ باشد.")
    if compare_at_price is not None and price is not None and compare_at_price < price:
        errors.append(
            f"ردیف {number}: «compare_at_price» نمی‌تواند کمتر از «price» باشد."
        )

    if errors:
        return errors, None
    return [], {
        "name": name, "slug": slug, "sku": sku, "category": category,
        "brand": brand, "price": price, "compare_at_price": compare_at_price,
        "discount_percentage": discount_percentage, "stock_quantity": stock_quantity,
        "low_stock_threshold": low_stock_threshold, "short_description": short_description,
        "description": description, "is_active": is_active, "is_featured": is_featured,
    }


def import_products_from_rows(rows, header, *, dry_run=False):
    """
    Validate ``rows`` (list of dicts keyed by column name) against
    ``header`` and import them all-or-nothing. Returns an ImportResult;
    when result.errors is non-empty NOTHING has been written.
    """
    result = ImportResult()

    header_set = [h for h in header if h]
    missing = [c for c in TEMPLATE_COLUMNS if c not in header_set]
    unknown = [h for h in header_set if h not in TEMPLATE_COLUMNS]
    if missing or unknown:
        if missing:
            result.errors.append(
                "ستون(های) الزامی در سرتیت فایل موجود نیست: " + ", ".join(missing) + "."
            )
        if unknown:
            result.errors.append(
                "ستون(های) ناشناخته در سرتیت فایل وجود دارد: " + ", ".join(unknown) +
                ". از قالب نمونهٔ قابل‌دانلود استفاده کنید."
            )
        return result

    if not rows:
        result.errors.append("فایل هیچ ردیف داده‌ای ندارد.")
        return result

    categories = {c.slug: c for c in Category.objects.all()}
    brands = {b.name: b for b in Brand.objects.all()}

    cleaned_rows = []
    seen_skus = {}
    seen_slugs = {}
    existing_by_sku = {p.sku: p for p in Product.objects.filter(sku__in=[
        _normalize(r.get("sku")) for r in rows
    ])}
    for index, row in enumerate(rows):
        number = index + 2  # header is spreadsheet row 1
        errors, cleaned = _validate_row(number, row, categories, brands)
        result.errors.extend(errors)
        if cleaned is not None:
            sku = cleaned["sku"]
            if sku in seen_skus:
                result.errors.append(
                    f"ردیف {number}: کد کالای «{sku}» بیش از یک بار در فایل آمده است "
                    f"(اولین بار در ردیف {seen_skus[sku]})."
                )
                continue
            # Slug collisions: a NEW row may not take a slug that a
            # DIFFERENT product already owns (would crash the unique
            # index mid-import). An update row may keep its own slug.
            slug = cleaned["slug"]
            owner = existing_by_sku.get(sku)
            slug_owner = Product.objects.filter(slug=slug).first()
            if slug_owner is not None and slug_owner.sku != sku and (owner is None or owner.pk != slug_owner.pk):
                result.errors.append(
                    f"ردیف {number}: شناسهٔ «{slug}» از آنِ محصول دیگری است."
                )
                continue
            if slug in seen_slugs and seen_slugs[slug] != number:
                result.errors.append(
                    f"ردیف {number}: شناسهٔ «{slug}» بیش از یک بار در فایل آمده است."
                )
                continue
            seen_skus[sku] = number
            seen_slugs[slug] = number
            cleaned_rows.append(cleaned)

    if result.errors or dry_run:
        if not result.errors:
            result.created = sum(
                1 for c in cleaned_rows if not Product.objects.filter(sku=c["sku"]).exists()
            )
            result.updated = len(cleaned_rows) - result.created
        return result

    with transaction.atomic():
        for cleaned in cleaned_rows:
            sku = cleaned.pop("sku")
            product, created = Product.objects.get_or_create(sku=sku, defaults=cleaned)
            if created:
                result.created += 1
            else:
                for key, value in cleaned.items():
                    setattr(product, key, value)
                product.save()
                result.updated += 1
    return result
