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


def media_url(path):
    """
    Part R1 fix: responsive-variant columns store STORAGE-RELATIVE paths
    (the value default_storage.save returns), but API clients need a
    servable URL. Serialize every webp_* column through this helper so
    <picture> srcsets actually resolve (previously the raw relative path
    reached the browser and 404'd, silently disabling the variants).
    """
    if not path:
        return None
    if path.startswith(("http://", "https://", "/")):
        return path
    return default_storage.url(path)


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


# ---------------------------------------------------------------------------
# Part S4 item 1: ONE placeholder markup for Django-rendered surfaces.
# ---------------------------------------------------------------------------
# Every storefront surface renders images through the shared SmartImage
# component (frontend/src/components/SmartImage.jsx), which falls back to
# the brand mark on the warm-grey field. The Django-rendered surfaces --
# the admin product list/inline thumbnails and the printable invoice --
# use the markup below instead, with the SAME field colour (#efece4), the
# SAME mark (/brand/mark.svg), the SAME olive (#637037 = --brand-green)
# and the SAME .35 opacity, so a missing or broken image looks identical
# everywhere. Everything is inline (no extra admin stylesheet to load) and
# the `onerror` swap means a file that exists in the database but is gone
# from storage degrades exactly like a missing one.
PLACEHOLDER_FIELD_COLOR = "#efece4"
PLACEHOLDER_MARK_COLOR = "#637037"
PLACEHOLDER_MARK_OPACITY = "0.35"
PLACEHOLDER_MARK_URL = "/brand/mark.svg"


def placeholder_html(width=40, height=40, css_class="", radius=6, hidden=False):
    """The shared 'no image' placeholder markup (warm-grey field + brand
    mark in olive at .35 opacity), sized to the image area it replaces."""
    return (
        f'<span class="cusin-img-ph {css_class}" role="img" aria-label="بدون تصویر" '
        f'style="width:{width}px;height:{height}px;border-radius:{radius}px;'
        f"background:{PLACEHOLDER_FIELD_COLOR};display:{'none' if hidden else 'inline-block'};"
        'text-align:center;line-height:0">'
        f'<span style="display:inline-block;width:46%;height:46%;vertical-align:middle;'
        f"background:{PLACEHOLDER_MARK_COLOR};opacity:{PLACEHOLDER_MARK_OPACITY};"
        f"-webkit-mask:url('{PLACEHOLDER_MARK_URL}') no-repeat center/contain;"
        f"mask:url('{PLACEHOLDER_MARK_URL}') no-repeat center/contain\"></span></span>"
    )


def image_or_placeholder_html(image, width=48, height=48, css_class="", radius=6):
    """
    An <img> for a stored image file WITH the shared placeholder behind it:
    a missing image renders the placeholder directly, and a broken file
    swaps itself for the placeholder on error (never a broken-image icon).
    """
    from django.utils.html import format_html
    from django.utils.safestring import mark_safe

    # Accepts a FieldFile (.url), a model instance whose ImageField is
    # .image (ProductImage, Category), or a plain URL/path string.
    url = getattr(image, "url", None)
    if not url:
        inner = getattr(image, "image", None)
        url = getattr(inner, "url", None)
    if not url and isinstance(image, str):
        url = image
    if not url:
        return mark_safe(placeholder_html(width, height, css_class, radius))
    return format_html(
        '<img src="{}" alt="" style="width:{}px;height:{}px;object-fit:cover;'
        'border-radius:{}px" onerror="this.style.display=\'none\';'
        'this.nextElementSibling.style.display=\'inline-block\';">{}',
        url,
        width,
        height,
        radius,
        mark_safe(placeholder_html(width, height, css_class, radius, hidden=True)),
    )
