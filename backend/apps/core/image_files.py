"""
Upload-time image handling (Phase B - Store management).

One validator + one thumbnail helper shared by every ImageField in the
project (product images, brand logos, category images, banners):

* validate_image_file(): rejects oversized uploads and anything Pillow
  cannot open and verify as a real image in an allowed raster format.
  An attacker-rename of "shell.php" -> "photo.jpg" still fails here,
  because the check is on the decoded content, not the extension.
* make_thumbnail(): downscales to a bounded box and stores a JPEG next
  to the originals, used by admin list views (cheap pages) without
  re-encoding anything at render time.

SVG is deliberately NOT allowed: it is XML, Pillow does not decode it,
and it can carry scripts -- none of which belongs in a catalog upload.
"""
import io
import os

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils.text import get_valid_filename

# 5 MB covers large phone photos while keeping uploads sane.
MAX_IMAGE_UPLOAD_SIZE = 5 * 1024 * 1024

ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}

THUMBNAIL_MAX_SIZE = (400, 400)
THUMBNAIL_DIRECTORY = "products/thumbnails/"


def validate_image_file(value):
    """
    Field validator for ImageFields. ``value`` is an uploaded file /
    FieldFile. Raises ValidationError when the file is too large or is
    not a decodable image in an allowed format.
    """
    size = getattr(value, "size", None)
    if size is not None and size > MAX_IMAGE_UPLOAD_SIZE:
        raise ValidationError(
            f"Image is too large ({size // (1024 * 1024) + 1} MB). "
            f"Maximum allowed size is {MAX_IMAGE_UPLOAD_SIZE // (1024 * 1024)} MB."
        )

    from PIL import Image, UnidentifiedImageError

    try:
        value.seek(0)
        try:
            with Image.open(value) as img:
                img.verify()
                fmt = (img.format or "").upper()
        finally:
            value.seek(0)
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
        raise ValidationError(
            "The uploaded file is not a valid image. Upload a JPEG, PNG, WEBP or GIF file."
        )

    if fmt not in ALLOWED_IMAGE_FORMATS:
        raise ValidationError(
            f"Image format '{fmt}' is not supported. Upload a JPEG, PNG, WEBP or GIF file."
        )


def make_thumbnail(source_field, max_size=THUMBNAIL_MAX_SIZE):
    """
    Build a JPEG thumbnail for an ImageField's stored file and return a
    storage-relative path, or None when there is nothing to thumbnail.

    Returns None (never raises) when the underlying file is absent or
    unreadable: a ProductImage row can legitimately exist with only a
    stored name (test fixtures, seed data, files not yet copied), and a
    missing thumbnail is a cosmetic gap, not a reason to fail the save.
    """
    from PIL import Image, UnidentifiedImageError

    if not source_field:
        return None

    try:
        with Image.open(source_field.path) as img:
            img.thumbnail(max_size)
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=85)
    except (FileNotFoundError, OSError, UnidentifiedImageError):
        return None

    stem = os.path.splitext(os.path.basename(source_field.name))[0]
    relative = f"{THUMBNAIL_DIRECTORY}{get_valid_filename(stem)}_thumb.jpg"
    saved_name = default_storage.save(relative, ContentFile(buffer.getvalue()))
    return saved_name


RESPONSIVE_WIDTHS = (400, 800, 1200)
RESPONSIVE_DIRECTORY = "products/variants/"


def make_responsive_variants(source_field):
    """
    Part 3 image optimization: next to the validated ORIGINAL (which is
    never touched), store WebP re-encodes at 400/800/1200px widths so
    cards/galleries/banners can serve <picture>/srcset.

    Returns {width: storage-relative path} for every width that could be
    produced; an empty dict (never raises) when the source file is
    missing or undecodable -- responsive variants are a progressive
    enhancement and must not break uploads or imports.
    """
    from PIL import Image, UnidentifiedImageError

    if not source_field:
        return {}
    try:
        source_field.seek(0)
        with Image.open(source_field) as img:
            img.load()
            base = img.convert("RGB") if img.mode in ("RGBA", "P", "LA") else img
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
        return {}
    finally:
        try:
            source_field.seek(0)
        except (OSError, ValueError):
            pass

    try:
        name = os.path.splitext(os.path.basename(source_field.name))[0]
    except (AttributeError, ValueError):
        return {}

    produced = {}
    for width in RESPONSIVE_WIDTHS:
        try:
            ratio = width / float(base.width or width)
            size = (width, max(1, int(base.height * min(ratio, 1.0)))) if ratio < 1 else (base.width, base.height)
            resized = base.resize(size, Image.LANCZOS) if ratio < 1 else base
            buffer = io.BytesIO()
            resized.save(buffer, format="WEBP", quality=80, method=4)
            path = f"{RESPONSIVE_DIRECTORY}{get_valid_filename(name)}_{width}.webp"
            saved = default_storage.save(path, ContentFile(buffer.getvalue()))
            produced[width] = saved
        except (OSError, ValueError):
            continue  # one bad width must not kill the others
    return produced
