"""
Bulk product image import (matched by SKU).

One engine, two front-ends -- the admin page («ورود گروهی تصاویر (فایل زیپ)»)
and the `import_product_images` management command -- so their behaviour
can never drift apart.

Naming rules (the file name IS the instruction):

    SKU.jpg          main image of that product
    SKU-1.jpg        image #1
    SKU_2.jpg        image #2
    SKU (2).jpg      image #2
    SKU/1.jpg        image #1 (one folder per product)
    SKU/2.jpg        image #2

* A name is matched against the catalog by SKU: case-insensitive, Persian
  and Arabic digits normalized, surrounding spaces trimmed. The WHOLE name
  is tried first (so a SKU that itself ends in a number, e.g. SOOLE-001,
  wins) and only then a numeric suffix is peeled off.
* Images of one product are ordered by that suffix (no suffix = 1) and the
  first one becomes the product's primary image.
* Directories, hidden files, `__MACOSX`, `.DS_Store`, `Thumbs.db`, nested
  archives and non-image files are ignored and REPORTED as ignored.

Safety, because a ZIP is attacker-controlled input:

* Path traversal (`../`), absolute paths, Windows drive letters and symlink
  members are rejected before anything is read; members are extracted to
  generated names inside a private temp directory, so a hostile name can
  never choose where a file lands.
* ZIP bombs: bounded number of members, bounded total uncompressed size,
  bounded compression ratio, bounded size per file (the shared 5 MB image
  limit) -- and the extraction reads in chunks with its own hard cap, so a
  member that LIES about its size is stopped too.
* The upload is streamed to a temp file (never held in memory) and every
  temp file is removed by the caller.
* Writing is all-or-nothing: one transaction per request. If anything
  fails, the rows roll back AND every file this import wrote to storage
  (original, thumbnail, WebP variants) is deleted again.

Images are validated by the project's shared validator
(apps.core.image_files.validate_image_file) and go through the normal
ProductImage.save() path, so thumbnails and responsive WebP variants are
produced exactly like a manual admin upload.
"""
import base64
import hashlib
import io
import os
import re
import stat
import zipfile
from dataclasses import dataclass, field

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction

from apps.core.image_files import MAX_IMAGE_UPLOAD_SIZE, validate_image_file

from .importing import _PERSIAN_DIGITS
from .models import Product, ProductImage

# ---------------------------------------------------------------- constants

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

# Files nobody wants to import -- macOS/Windows bookkeeping and editors'
# leftovers. Compared case-insensitively against the base name.
IGNORED_BASENAMES = {
    ".ds_store", "thumbs.db", "desktop.ini", ".localized", "icon\r",
}

# A ZIP inside a ZIP is never what the owner meant; importing archives is
# also how "zip bomb in two steps" starts.
NESTED_ARCHIVE_EXTENSIONS = {
    ".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar", ".jar", ".iso",
}

MODES = ("add", "replace")

# Trailing numeric suffix: "-2", "_2", " 2"? No -- a bare trailing number
# would eat real SKUs such as SOOLE-001. Only "-N", "_N" and "(N)" count,
# and only when what remains is an existing SKU.
_SUFFIX_PATTERNS = (
    re.compile(r"^(?P<base>.+?)[\s_-]*\(\s*(?P<number>\d+)\s*\)$"),
    re.compile(r"^(?P<base>.+?)[\s]*[-_][\s]*(?P<number>\d+)$"),
)


@dataclass(frozen=True)
class ImageImportLimits:
    """Every knob is env-configurable with a safe default (see settings)."""

    max_files: int
    max_total_uncompressed: int
    max_compressed_size: int
    max_ratio: int
    max_file_size: int
    # Preview thumbnails are inlined as data URIs; both caps keep the admin
    # page small no matter how large the ZIP is.
    thumbs_per_product: int = 4
    max_thumb_total: int = 400

    @classmethod
    def from_settings(cls):
        return cls(
            max_files=int(getattr(settings, "PRODUCT_IMAGE_IMPORT_MAX_FILES", 2000)),
            max_total_uncompressed=int(
                getattr(settings, "PRODUCT_IMAGE_IMPORT_MAX_TOTAL_UNCOMPRESSED", 500 * 1024 * 1024)
            ),
            max_compressed_size=int(
                getattr(settings, "PRODUCT_IMAGE_IMPORT_MAX_ZIP_SIZE", 200 * 1024 * 1024)
            ),
            max_ratio=int(getattr(settings, "PRODUCT_IMAGE_IMPORT_MAX_RATIO", 120)),
            max_file_size=int(getattr(settings, "PRODUCT_IMAGE_IMPORT_MAX_FILE_SIZE", MAX_IMAGE_UPLOAD_SIZE)),
        )


# ------------------------------------------------------------ Small helpers

_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def fa_digits(value):
    """1234 -> ۱۲۳۴ for owner-facing Persian sentences.

    Data a machine must read back (the CSV report's numeric columns, API
    payloads) stays ASCII on purpose.
    """
    return str(value).translate(_FA_DIGITS)


def _fa_mb(byte_count):
    return fa_digits(byte_count // (1024 * 1024))


# ------------------------------------------------------------ SKU matching


def sku_key(value):
    """Comparable form of a SKU or of a file name: Persian/Arabic digits
    folded to ASCII, case folded, surrounding spaces trimmed."""
    text = "" if value is None else str(value)
    return text.translate(_PERSIAN_DIGITS).strip().casefold()


def _clean_parts(member):
    """Zip member name -> path components, with the two hostile shapes
    normalised away: backslashes become separators and a trailing slash
    (a directory entry) is dropped."""
    name = str(member or "").replace("\\", "/")
    return [part for part in name.split("/") if part not in ("", ".")]


def member_problem(member):
    """
    Why this member name may not be touched at all, or "" when it is fine.

    These are the classic zip-slip / absolute-path attacks. Members are
    never extracted by their own name (the extractor writes generated file
    names), so this is defence in depth -- but a hostile ZIP must be
    REPORTED as hostile, not silently cleaned up.
    """
    raw = str(member or "")
    if not raw.strip():
        return "نام خالی در فایل زیپ"
    normalised = raw.replace("\\", "/")
    if normalised.startswith("/") or re.match(r"^[A-Za-z]:", normalised):
        return "مسیر مطلق (absolute path) در فایل زیپ"
    parts = normalised.split("/")
    if any(part == ".." for part in parts):
        return "مسیر خروج از پوشه (..) در فایل زیپ"
    if "\x00" in raw:
        return "نام فایل دارای کاراکتر غیرمجاز است"
    return ""


def ignored_reason(member):
    """Why this member is not even a candidate (junk / directory / archive),
    or "" when it should be considered."""
    parts = _clean_parts(member)
    if not parts:
        return "پوشه است"
    if str(member).endswith(("/", "\\")) and len(parts) >= 1:
        return "پوشه است"
    lowered = [part.casefold() for part in parts]
    if any(part == "__macosx" for part in lowered):
        return "پوشهٔ سیستمی مک (__MACOSX)"
    base = lowered[-1]
    if base in IGNORED_BASENAMES:
        return "فایل سیستمی (_.DS_Store/Thumbs.db)"
    if any(part.startswith(".") for part in lowered):
        return "فایل مخفی"
    if os.path.splitext(base)[1] in NESTED_ARCHIVE_EXTENSIONS:
        return "فایل فشردهٔ تودرتو"
    if os.path.splitext(base)[1] not in IMAGE_EXTENSIONS:
        return "فایل تصویری نیست"
    return ""


def split_sku_and_suffix(name, sku_index):
    """
    Try to read a file name as (sku, image number).

    Order matters and is the documented behaviour: the WHOLE name is looked
    up first, so `SOOLE-001.jpg` matches the SKU `SOOLE-001` instead of
    being read as `SOOLE` image #1. Only when that fails is a trailing
    `-N`, `_N` or `(N)` peeled off -- and only if what remains is a SKU
    that really exists.
    """
    stem = sku_key(os.path.splitext(os.path.basename(str(name or "")))[0])
    if not stem:
        return None, None
    if stem in sku_index:
        return sku_index[stem], 1
    for pattern in _SUFFIX_PATTERNS:
        match = pattern.match(stem)
        if not match:
            continue
        base = match.group("base").strip()
        if base in sku_index:
            return sku_index[base], int(match.group("number"))
    return None, None


def match_member(member, sku_index):
    """
    (product, number) for a member, or (None, None).

    A file name wins over its folder; the folder form (`SKU/1.jpg`,
    `SKU/main.jpg`) is tried second, using the file name as the number when
    it is numeric and 1 otherwise.
    """
    parts = _clean_parts(member)
    base = parts[-1] if parts else ""
    product, number = split_sku_and_suffix(base, sku_index)
    if product is not None:
        return product, number
    # `SKU/1.jpg` -- the folder names the product, the file names the slot.
    for folder in reversed(parts[:-1]):
        folder_key = sku_key(folder)
        if folder_key in sku_index:
            stem = sku_key(os.path.splitext(base)[0])
            return sku_index[folder_key], int(stem) if stem.isdigit() else 1
    return None, None


# ------------------------------------------------------------------ sources


class ZipImageSource:
    """
    A ZIP file on disk, opened safely.

    Nothing is read at construction time; `members()` yields lightweight
    descriptors and `open()` streams one member with hard caps.
    """

    def __init__(self, path, limits=None):
        self.path = path
        self.limits = limits or ImageImportLimits.from_settings()

    def _zip(self):
        try:
            return zipfile.ZipFile(self.path)
        except (zipfile.BadZipFile, OSError) as exc:
            raise ValueError(f"فایل زیپ خوانده نشد: {exc}") from exc

    def check_size(self):
        size = os.path.getsize(self.path)
        if size > self.limits.max_compressed_size:
            raise ValueError(
                "حجم فایل زیپ بیش از حد مجاز است "
                f"({_fa_mb(size)} مگابایت؛ حداکثر "
                f"{_fa_mb(self.limits.max_compressed_size)} مگابایت)."
            )

    def members(self):
        """[{name, size, compressed, is_dir, is_symlink}] plus the limit
        checks that need the whole member list (count, total size, ratio)."""
        with self._zip() as archive:
            infos = archive.infolist()
            if len(infos) > self.limits.max_files:
                raise ValueError(
                    f"تعداد فایل‌های داخل زیپ بیش از حد مجاز است "
                    f"({fa_digits(len(infos))} فایل؛ حداکثر {fa_digits(self.limits.max_files)})."
                )
            total = sum(info.file_size for info in infos)
            if total > self.limits.max_total_uncompressed:
                raise ValueError(
                    "حجم باز‌شدهٔ زیپ بیش از حد مجاز است "
                    f"({_fa_mb(total)} مگابایت؛ حداکثر "
                    f"{_fa_mb(self.limits.max_total_uncompressed)} مگابایت)."
                )
            compressed = sum(max(info.compress_size, 1) for info in infos)
            if total / max(compressed, 1) > self.limits.max_ratio:
                raise ValueError(
                    "نسبت فشردگی زیپ غیرعادی است (احتمال «زیپ‌بمب»)؛ "
                    "فایل را با نرم‌افزار معتبر دیگری بسازید."
                )
            listed = []
            for info in infos:
                mode = info.external_attr >> 16
                listed.append(
                    {
                        "name": info.filename,
                        "size": info.file_size,
                        "compressed": max(info.compress_size, 1),
                        "is_dir": info.is_dir(),
                        "is_symlink": stat.S_ISLNK(mode),
                    }
                )
            return listed

    def open(self, name):
        """A fresh read handle for one member (caller closes it)."""
        archive = self._zip()
        try:
            return archive.open(name, "r"), archive
        except KeyError:
            archive.close()
            raise

    def extract_member(self, name, target_path):
        """
        Stream ONE member to `target_path`, in chunks, with a hard cap.

        Returns (path, size, sha256). A member whose real content exceeds
        its declared size, or the per-file limit, is refused -- and any
        partial file is removed.
        """
        digest = hashlib.sha256()
        written = 0
        source, archive = self.open(name)
        try:
            with open(target_path, "wb") as handle:
                while True:
                    chunk = source.read(64 * 1024)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > self.limits.max_file_size:
                        raise ValueError("too-large")
                    handle.write(chunk)
                    digest.update(chunk)
        except ValueError:
            os.remove(target_path)
            raise
        except Exception:
            if os.path.exists(target_path):
                os.remove(target_path)
            raise
        finally:
            source.close()
            archive.close()
        return target_path, written, digest.hexdigest()


class FolderImageSource:
    """A directory on the server (the management command's second input).

    Folder-per-product works exactly like in a ZIP (`SKU/1.jpg`) and the
    same limits apply, so a huge folder cannot exhaust the server either.
    """

    def __init__(self, root, limits=None):
        self.root = root
        self.limits = limits or ImageImportLimits.from_settings()

    def check_size(self):
        if not os.path.isdir(self.root):
            raise ValueError(f"پوشه پیدا نشد: {self.root}")

    def members(self):
        listed = []
        total = 0
        for directory, _dirs, files in os.walk(self.root):
            for name in files:
                path = os.path.join(directory, name)
                try:
                    size = os.path.getsize(path)
                except OSError:
                    continue
                # The relative path keeps the folder-per-product rule working
                # and keeps file names unique in the report.
                relative = os.path.relpath(path, self.root).replace(os.sep, "/")
                total += size
                listed.append(
                    {
                        "name": relative,
                        "size": size,
                        "compressed": max(size, 1),
                        "is_dir": False,
                        "is_symlink": os.path.islink(path),
                    }
                )
        if len(listed) > self.limits.max_files:
            raise ValueError(
                f"تعداد فایل‌های پوشه بیش از حد مجاز است "
                f"({fa_digits(len(listed))} فایل؛ حداکثر {fa_digits(self.limits.max_files)})."
            )
        if total > self.limits.max_total_uncompressed:
            raise ValueError(
                "حجم کل پوشه بیش از حد مجاز است "
                f"({_fa_mb(total)} مگابایت؛ حداکثر "
                f"{_fa_mb(self.limits.max_total_uncompressed)} مگابایت)."
            )
        return listed

    def extract_member(self, name, target_path):
        source_path = os.path.join(self.root, *name.split("/"))
        digest = hashlib.sha256()
        written = 0
        with open(source_path, "rb") as source, open(target_path, "wb") as handle:
            while True:
                chunk = source.read(64 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > self.limits.max_file_size:
                    raise ValueError("too-large")
                handle.write(chunk)
                digest.update(chunk)
        return target_path, written, digest.hexdigest()


# --------------------------------------------------------------------- plan


@dataclass
class FileOutcome:
    """What happens (or happened) to one member of the upload."""

    member: str
    status: str  # add | skip | duplicate | unmatched | invalid | ignored | unsafe
    reason: str = ""
    sku: str = ""
    product_id: int | None = None
    suffix: int | None = None
    extracted: str | None = None
    sha256: str = ""
    size: int = 0
    thumb: str = ""

    @property
    def writes(self):
        return self.status == "add"


@dataclass
class ProductPlan:
    """The images one product will receive, already in final order."""

    product: Product
    files: list = field(default_factory=list)
    effect: str = "add"  # add | replace | skip
    existing_count: int = 0
    keeps_primary: bool = False

    @property
    def new_count(self):
        return len([item for item in self.files if item.writes])


@dataclass
class ImageImportPlan:
    ok: bool = True
    errors: list = field(default_factory=list)
    files: list = field(default_factory=list)
    groups: list = field(default_factory=list)
    catalog_without_images: int = 0
    limits: object = None
    mode: str = "add"
    skip_existing: bool = False
    labels: dict = field(default_factory=dict)

    # --- derived views used by the admin page and the CLI ----------------
    @property
    def added(self):
        return [item for item in self.files if item.status == "add"]

    @property
    def skipped(self):
        return [item for item in self.files if item.status == "skip"]

    @property
    def duplicates(self):
        return [item for item in self.files if item.status == "duplicate"]

    @property
    def unmatched(self):
        return [item for item in self.files if item.status == "unmatched"]

    @property
    def invalid(self):
        return [item for item in self.files if item.status == "invalid"]

    @property
    def ignored(self):
        return [item for item in self.files if item.status == "ignored"]

    @property
    def unsafe(self):
        return [item for item in self.files if item.status == "unsafe"]

    @property
    def writing_groups(self):
        return [group for group in self.groups if group.new_count]

    @property
    def products_still_without_image(self):
        return [group for group in self.groups if not group.new_count]

    def counts(self):
        return {
            "add": len(self.added),
            "skip": len(self.skipped),
            "duplicate": len(self.duplicates),
            "unmatched": len(self.unmatched),
            "invalid": len(self.invalid),
            "ignored": len(self.ignored),
            "unsafe": len(self.unsafe),
            "products": len(self.writing_groups),
            "images": len(self.added),
        }

    def report_rows(self):
        """Flat rows for the downloadable CSV report."""
        rows = []
        for item in self.files:
            rows.append(
                {
                    "file": item.member,
                    "status": item.status,
                    "sku": item.sku,
                    "product": self.labels.get(item.product_id, ""),
                    "reason": item.reason,
                    "size": item.size,
                }
            )
        return rows




def report_csv(rows):
    """The result report as a UTF-8 CSV with Persian headers."""
    import csv as csv_mod

    STATUS_LABELS = {
        "add": "افزوده می‌شود",
        "skip": "رد شد (محصول تصویر دارد)",
        "duplicate": "تکراری",
        "unmatched": "کد کالا پیدا نشد",
        "invalid": "تصویر نامعتبر",
        "ignored": "نادیده گرفته شد",
        "unsafe": "رد شد (فایل ناامن)",
        "applied": "ذخیره شد",
    }
    buffer = io.StringIO()
    writer = csv_mod.writer(buffer)
    writer.writerow(["فایل", "وضعیت", "کد کالا", "محصول", "دلیل", "حجم (بایت)"])
    for row in rows:
        writer.writerow(
            [
                row.get("file", ""),
                STATUS_LABELS.get(row.get("status"), row.get("status", "")),
                row.get("sku", ""),
                row.get("product", ""),
                row.get("reason", ""),
                row.get("size", ""),
            ]
        )
    return buffer.getvalue()


# ------------------------------------------------------------------ engine


def _thumb_data_uri(path, size=(72, 72)):
    """Small inline preview for the dry-run page (bounded: 72px JPEG)."""
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(path) as img:
            img.thumbnail(size)
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=70)
    except (OSError, UnidentifiedImageError, ValueError):
        return ""
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def _validate_extracted(path):
    """(ok, reason) using the project's shared validator, with Persian
    wording for the owner."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    with open(path, "rb") as handle:
        payload = handle.read()
    if len(payload) > MAX_IMAGE_UPLOAD_SIZE:
        return False, f"حجم فایل بیش از {_fa_mb(MAX_IMAGE_UPLOAD_SIZE)} مگابایت است"
    upload = SimpleUploadedFile("check", payload, content_type="application/octet-stream")
    try:
        validate_image_file(upload)
    except Exception:  # ValidationError from the shared validator
        return False, "تصویر معتبر نیست (فقط JPEG، PNG، WEBP یا GIF)"
    return True, ""


def _existing_hashes(product):
    """sha256 of the images a product already has (content dedupe).

    Files that cannot be read (missing on disk, non-filesystem storage)
    are simply not comparable -- they are skipped, never guessed.
    """
    digests = set()
    for image in product.images.all():
        try:
            path = image.image.path
        except (NotImplementedError, ValueError):
            continue
        try:
            with open(path, "rb") as handle:
                digest = hashlib.sha256()
                for chunk in iter(lambda: handle.read(64 * 1024), b""):
                    digest.update(chunk)
            digests.add(digest.hexdigest())
        except OSError:
            continue
    return digests


def build_plan(source, *, mode="add", skip_existing=False, extract_dir, thumbs=False, limits=None,
               products=None):
    """
    Read the source, validate everything, and describe what WOULD happen.

    Nothing is written to the database and nothing is added to product
    storage here: every image is extracted to `extract_dir` (the caller
    removes it) and validated; the plan is what the preview shows and what
    apply_plan() executes unchanged.
    """
    limits = limits or ImageImportLimits.from_settings()
    if mode not in MODES:
        raise ValueError(f"حالت نامعتبر: {mode}")

    plan = ImageImportPlan(limits=limits, mode=mode, skip_existing=skip_existing)

    try:
        source.check_size()
        members = source.members()
    except ValueError as exc:
        plan.ok = False
        plan.errors = [str(exc)]
        return plan

    catalog = list(products if products is not None else Product.objects.all().only("id", "sku", "name"))
    sku_index = {}
    for product in catalog:
        key = sku_key(product.sku)
        # Product.sku is unique; a catalog with two identical keys can only
        # come from a data repair job, in which case the first one wins.
        sku_index.setdefault(key, product)
    plan.labels = {product.pk: f"{product.name} ({product.sku})" for product in catalog}

    groups = {}
    thumb_budget = limits.max_thumb_total
    index = 0

    for member in members:
        index += 1
        name = member["name"]
        outcome = FileOutcome(member=name, status="ignored")

        problem = member_problem(name)
        if problem:
            outcome.status = "unsafe"
            outcome.reason = problem
            plan.files.append(outcome)
            continue

        if member.get("is_symlink"):
            outcome.status = "unsafe"
            outcome.reason = "پیوند نمادین (symlink) در فایل زیپ"
            plan.files.append(outcome)
            continue

        reason = ignored_reason(name)
        if reason or member.get("is_dir"):
            outcome.reason = reason or "پوشه است"
            plan.files.append(outcome)
            continue

        if member["size"] > limits.max_file_size:
            outcome.status = "invalid"
            outcome.reason = f"حجم فایل بیش از {_fa_mb(limits.max_file_size)} مگابایت است"
            outcome.size = member["size"]
            plan.files.append(outcome)
            continue

        if member["size"] / member["compressed"] > limits.max_ratio:
            outcome.status = "invalid"
            outcome.reason = "نسبت فشردگی غیرعادی (احتمال «زیپ‌بمب»)"
            outcome.size = member["size"]
            plan.files.append(outcome)
            continue

        product, number = match_member(name, sku_index)
        if product is None:
            outcome.status = "unmatched"
            outcome.reason = "کد کالا (SKU) در فروشگاه پیدا نشد"
            plan.files.append(outcome)
            continue

        outcome.sku = product.sku
        outcome.product_id = product.pk
        outcome.suffix = number

        group = groups.get(product.pk)
        if group is None:
            existing = product.images.count()
            group = ProductPlan(
                product=product,
                existing_count=existing,
                effect=("skip" if (skip_existing and existing) else mode),
            )
            groups[product.pk] = group
        if group.effect == "skip":
            outcome.status = "skip"
            outcome.reason = "این محصول از قبل تصویر دارد"
            plan.files.append(outcome)
            continue

        # Extract + validate. The extractor generates the target name, so a
        # hostile member name can never influence where the file goes.
        target = os.path.join(extract_dir, f"member-{index:05d}{os.path.splitext(name)[1].lower()}")
        try:
            path, size, digest = source.extract_member(name, target)
        except ValueError as exc:
            if str(exc) == "too-large":
                outcome.status = "invalid"
                outcome.reason = f"حجم فایل بیش از {_fa_mb(limits.max_file_size)} مگابایت است"
            else:
                outcome.status = "invalid"
                outcome.reason = f"خواندن فایل ممکن نشد: {exc}"
            plan.files.append(outcome)
            continue
        except Exception:  # a broken member must not break the others
            outcome.status = "invalid"
            outcome.reason = "خواندن فایل ممکن نشد (فایل زیپ آسیب‌دیده است)"
            plan.files.append(outcome)
            continue

        outcome.extracted = path
        outcome.size = size
        outcome.sha256 = digest

        ok, why = _validate_extracted(path)
        if not ok:
            outcome.status = "invalid"
            outcome.reason = why
            plan.files.append(outcome)
            continue

        outcome.status = "add"
        group.files.append(outcome)
        plan.files.append(outcome)

    # Ordering, primary image and duplicate detection -----------------------
    plans = []
    for product_id, group in groups.items():
        if group.effect == "replace":
            # Old images are removed, so their content cannot collide.
            existing = set()
        else:
            existing = _existing_hashes(group.product)
        seen = set()
        kept = []
        for item in sorted(group.files, key=lambda entry: (entry.suffix or 1, entry.member)):
            if item.sha256 in existing or item.sha256 in seen:
                item.status = "duplicate"
                item.reason = (
                    "این تصویر از قبل برای این محصول ثبت شده است"
                    if item.sha256 in existing
                    else "این تصویر در همین فایل زیپ تکراری است"
                )
                continue
            seen.add(item.sha256)
            kept.append(item)
        group.files = kept

        if group.effect != "skip":
            group.keeps_primary = (
                group.effect == "add"
                and group.product.images.filter(is_primary=True).exists()
            )
            if thumbs:
                for item in kept[: limits.thumbs_per_product]:
                    if thumb_budget <= 0:
                        break
                    item.thumb = _thumb_data_uri(item.extracted)
                    thumb_budget -= 1
        plans.append(group)

    plan.groups = sorted(plans, key=lambda group: group.product.sku)
    plan.catalog_without_images = (
        Product.objects.filter(images__isnull=True).distinct().count()
    )

    # A ZIP that tries to write outside its own tree (.., /etc, C:\) or that
    # smuggles symlinks is refused as a whole: nothing is previewed and
    # nothing is written. Suspicious INPUT is different from a broken FILE
    # -- the latter is reported and simply skipped.
    if plan.unsafe:
        plan.ok = False
        plan.errors.append(
            "فایل زیپ رد شد: "
            + fa_digits(len(plan.unsafe))
            + " مسیر ناامن در آن پیدا شد (فرار از پوشه، مسیر مطلق یا symlink)."
        )
    return plan


def apply_plan(plan):
    """
    Execute a plan: one transaction, all-or-nothing.

    Every created row's files (original, thumbnail, WebP variants) are
    recorded as they are written; if anything raises, the transaction rolls
    back and those files are deleted from storage, so a failed import
    leaves neither rows nor orphaned bytes behind.
    """
    if not plan.ok:
        raise ValueError("پلن نامعتبر است و اجرا نمی‌شود")

    created = 0
    replaced = 0
    products_touched = 0
    written_paths = []
    old_paths = []

    def remember(image):
        for candidate in (image.image, image.thumbnail):
            name = getattr(candidate, "name", "")
            if name:
                written_paths.append(name)
        for name in (image.webp_400, image.webp_800, image.webp_1200):
            if name:
                written_paths.append(name)

    try:
        with transaction.atomic():
            for group in plan.groups:
                if group.effect == "skip" or not group.files:
                    continue
                product = Product.objects.select_for_update().get(pk=group.product.pk)
                if group.effect == "replace":
                    for old in product.images.all():
                        for candidate in (old.image, old.thumbnail):
                            name = getattr(candidate, "name", "")
                            if name:
                                old_paths.append(name)
                        for name in (old.webp_400, old.webp_800, old.webp_1200):
                            if name:
                                old_paths.append(name)
                    deleted, _ = product.images.all().delete()
                    replaced += deleted

                ordering = 0
                if group.effect == "add":
                    last = (
                        product.images.order_by("-ordering")
                        .values_list("ordering", flat=True)
                        .first()
                    )
                    if last is not None:
                        ordering = last + 1
                has_primary = group.keeps_primary or (
                    group.effect == "add" and product.images.filter(is_primary=True).exists()
                )

                for item in group.files:
                    if not item.writes:
                        continue
                    with open(item.extracted, "rb") as handle:
                        payload = handle.read()
                    image = ProductImage(
                        product=product,
                        alt_text=product.name,
                        ordering=ordering,
                        is_primary=not has_primary,
                    )
                    # The stored name keeps the SKU visible on disk, and the
                    # storage layer still resolves any collision itself.
                    image.image.save(
                        f"{product.sku.lower()[:40]}-{ordering}{os.path.splitext(item.member)[1].lower()}",
                        ContentFile(payload),
                        save=False,
                    )
                    # Record the bytes as soon as they hit storage: if the
                    # ROW save (or anything after it) explodes, the rollback
                    # must still delete this file.
                    written_paths.append(image.image.name)
                    image.save()
                    remember(image)
                    has_primary = True
                    ordering += 1
                    created += 1
                    item.status = "applied"
                products_touched += 1
    except Exception:
        # The rows are gone (rollback); the bytes must be too.
        for name in written_paths:
            try:
                default_storage.delete(name)
            except Exception:  # pragma: no cover - storage hiccup
                pass
        raise
    else:
        # Replace mode deletes the OLD files only after the commit, so a
        # rollback can never lose pictures the shop was still showing.
        def drop_old(paths=tuple(old_paths)):
            for name in paths:
                try:
                    default_storage.delete(name)
                except Exception:  # pragma: no cover - storage hiccup
                    pass

        if old_paths:
            transaction.on_commit(drop_old)

    return {
        "created": created,
        "replaced": replaced,
        "products": products_touched,
    }
