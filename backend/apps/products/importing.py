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
        "کازین", 180000, 220000, 10, 40, 5, "ماگ سرامیکی ۳۰۰ میلی‌لیتری",
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


# ---------------------------------------------------------------------------
# Part R4 item 6: spreadsheet PRICE/STOCK updates + export
# ---------------------------------------------------------------------------
# The owner exports the catalog in the exact import format, edits prices
# and stock in Excel, and re-uploads it. Two safe modes are layered on
# top of the same engine:
#   * update-only (minimal template: sku + any of price/sale_price/stock)
#     NEVER creates products and NEVER touches a field that is not in
#     the file;
#   * dry-run preview: shows old -> new per field before the owner
#     confirms, still all-or-nothing.
# Column mapping (stated here AND in the admin page + owner guide):
#   price     -> Product.price            (قیمت فروش -- what is charged)
#   sale_price-> Product.compare_at_price (قیمت خط‌خوردهٔ قبل از تخفیف)
#   stock     -> Product.stock_quantity

UPDATE_TEMPLATE_COLUMNS = ["sku", "price", "sale_price", "stock"]
UPDATE_UPDATABLE = ["price", "sale_price", "stock"]

_UPDATE_FIELD_MAP = {
    "price": ("price", "قیمت فروش"),
    "sale_price": ("compare_at_price", "قیمت قبل از تخفیف"),
    "stock": ("stock_quantity", "موجودی"),
}


class UpdateResult:
    def __init__(self):
        self.changes = []    # {row, sku, name, field, label, old, new}
        self.skipped = 0     # rows that matched but changed nothing
        self.updated = 0     # distinct products changed
        self.errors = []
        self.applied = False

    @property
    def ok(self):
        return not self.errors


def _update_template_csv():
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(UPDATE_TEMPLATE_COLUMNS)
    writer.writerow(["MUG-001", 190000, 230000, 30])
    writer.writerow(["PAN-002", "", "", 12])  # blank cells = no change
    return buffer.getvalue()


def _validate_update_row(number, row, existing_by_sku):
    errors = []
    sku = _normalize(row.get("sku"))
    if not sku:
        errors.append(f"ردیف {number}: ستون «sku» الزامی است.")
        return errors, None

    product = existing_by_sku.get(sku)
    if product is None:
        errors.append(
            f"ردیف {number}: کالایی با کد «{sku}» وجود ندارد. حالت فقط-به‌روزرسانی "
            "هرگز محصول جدید نمی‌سازد؛ اول محصول را در پنل بسازید یا از واردکردن "
            "کامل استفاده کنید."
        )
        return errors, None

    values = {}
    for column in UPDATE_UPDATABLE:
        raw = row.get(column)
        text = _normalize(raw)
        if text == "":
            continue  # blank cell = leave the field untouched
        try:
            minimum = 0 if column == "stock" else 1
            values[column] = _to_int(raw, minimum=minimum)
        except ValueError as exc:
            errors.append(f"ردیف {number}: ستون «{column}» -- {exc}.")

    if errors:
        return errors, None

    # Cross-field sanity on the FINAL price pair (new values override).
    final_price = values.get("price", product.price)
    final_compare = values.get("sale_price", product.compare_at_price)
    if final_compare is not None and final_price is not None and final_compare < final_price:
        errors.append(
            f"ردیف {number}: «sale_price» نمی‌تواند کمتر از «price» باشد "
            f"(price={final_price}, sale_price={final_compare})."
        )
        return errors, None
    return errors, {"sku": sku, "product": product, "values": values}


def update_products_from_rows(rows, header, *, dry_run=False):
    """Update-only import (Part R4 item 6). Never creates, never touches
    unlisted fields, all-or-nothing, Persian digits normalized. Returns
    an UpdateResult; with dry_run=True nothing is written and `changes`
    holds the old->new preview."""
    result = UpdateResult()

    header_set = [h.strip() for h in header if h and h.strip()]
    if "sku" not in header_set:
        result.errors.append("ستون «sku» در سرتیت فایل وجود ندارد.")
        return result
    unknown = [h for h in header_set if h not in UPDATE_TEMPLATE_COLUMNS]
    if unknown:
        result.errors.append(
            "ستون(های) ناشناخته برای به‌روزرسانی: " + ", ".join(unknown) +
            ". ستون‌های مجاز: " + ", ".join(UPDATE_TEMPLATE_COLUMNS) + "."
        )
        return result
    if not [h for h in header_set if h in UPDATE_UPDATABLE]:
        result.errors.append(
            "هیچ ستون قابل‌به‌روزرسانی (price / sale_price / stock) در فایل نیست."
        )
        return result
    if not rows:
        result.errors.append("فایل هیچ ردیف داده‌ای ندارد.")
        return result

    existing_by_sku = {
        p.sku: p for p in Product.objects.filter(
            sku__in=[_normalize(r.get("sku")) for r in rows]
        )
    }

    cleaned_rows = []
    seen_skus = {}
    for index, row in enumerate(rows):
        number = index + 2
        errors, cleaned = _validate_update_row(number, row, existing_by_sku)
        result.errors.extend(errors)
        if cleaned is None:
            continue
        sku = cleaned["sku"]
        if sku in seen_skus:
            result.errors.append(
                f"ردیف {number}: کد کالای «{sku}» بیش از یک بار در فایل آمده است."
            )
            continue
        seen_skus[sku] = number
        cleaned_rows.append(cleaned)

    if result.errors:
        return result

    for cleaned in cleaned_rows:
        product = cleaned["product"]
        row_changes = []
        for column, value in cleaned["values"].items():
            field, label = _UPDATE_FIELD_MAP[column]
            old = getattr(product, field)
            if old == value:
                continue
            row_changes.append({
                "row": seen_skus[cleaned["sku"]], "sku": cleaned["sku"],
                "name": product.name, "field": field, "label": label,
                "old": old, "new": value,
            })
        if row_changes:
            result.changes.extend(row_changes)
            result.updated += 1
        else:
            result.skipped += 1

    if dry_run:
        return result

    with transaction.atomic():
        for cleaned in cleaned_rows:
            product = cleaned["product"]
            changed = False
            for column, value in cleaned["values"].items():
                field, _label = _UPDATE_FIELD_MAP[column]
                if getattr(product, field) != value:
                    setattr(product, field, value)
                    changed = True
            if changed:
                product.save()
    result.applied = True
    return result


def export_products_rows(queryset=None):
    """All products as dicts in EXACTLY the import template format, so
    the owner can edit the export and re-upload it."""
    products = (queryset if queryset is not None else Product.objects.all())
    products = products.select_related("brand", "category").order_by("id")
    out = []
    for product in products:
        out.append({
            "name": product.name,
            "slug": product.slug,
            "sku": product.sku,
            "category_slug": product.category.slug if product.category_id else "",
            "brand_name": product.brand.name if product.brand_id else "",
            "price": product.price,
            "compare_at_price": product.compare_at_price if product.compare_at_price is not None else "",
            "discount_percentage": product.discount_percentage,
            "stock_quantity": product.stock_quantity,
            "low_stock_threshold": product.low_stock_threshold,
            "short_description": product.short_description,
            "description": product.description,
            "is_active": "true" if product.is_active else "false",
            "is_featured": "true" if product.is_featured else "false",
        })
    return out


def export_products_csv(queryset=None):
    """UTF-8 CSV text (the view adds the BOM for Excel)."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=TEMPLATE_COLUMNS)
    writer.writeheader()
    for row in export_products_rows(queryset):
        writer.writerow(row)
    return buffer.getvalue()


def export_products_xlsx(queryset=None):
    """Excel workbook bytes in the same template format."""
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "products"
    sheet.append(TEMPLATE_COLUMNS)
    for row in export_products_rows(queryset):
        sheet.append([row[column] for column in TEMPLATE_COLUMNS])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
