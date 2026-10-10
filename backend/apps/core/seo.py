"""
Crawler-visible metadata (Part S4 item 3).

WhatsApp, Telegram, Instagram, Eitaa and search crawlers do NOT execute
JavaScript, so the per-page meta tags the React SPA writes at runtime are
invisible to them (the SPA only ever hands them index.html's site-wide
defaults). The nginx configs therefore recognise known bot user agents
for product and category URLs and proxy those requests here instead of to
the SPA; a real shopper keeps getting the SPA, unchanged.

What this module serves is deliberately MINIMAL: a small, valid HTML
document with exactly the metadata a link preview / crawler needs
(title, description, canonical, Open Graph, Twitter card, and -- for
products -- JSON-LD Product with price and availability), plus a link to
the real page for anything that does render HTML. No CSS, no JS, no
navigation: nothing to keep in sync with the storefront.

Rules enforced here:
  * only ACTIVE products/categories exist for crawlers -- unknown or
    inactive slugs are a hard 404 (never a leaked preview of an
    unpublished product);
  * every URL is absolute, built from settings.FRONTEND_URL;
  * Persian (unicode) slugs are matched by Django after decoding, so both
    /products/قابلمه/ and the percent-encoded form work;
  * images prefer the largest existing WebP variant (1200 -> 800 -> 400)
    and fall back to the shared brand placeholder
    (frontend/public/brand/og-placeholder.png, served by the frontend
    container at the site root) so a preview is never empty;
  * answers are cacheable for a short window (SECONDS) via
    Cache-Control, and nginx adds the same header at the edge.
"""
from html import escape

from django.conf import settings
from django.core.files import File
from django.http import Http404, HttpResponse
from django.utils.encoding import iri_to_uri

from apps.core.image_files import media_url

#: The Persian brand name. Not a setting: it is the store's fixed name
#: (see apps/core/test_brand_name.py for the spelling guard).
SITE_NAME = "کازین گالری"

#: How long a crawler response may be cached (edge + intermediate) --
#: short, because price/availability can change at any moment.
CACHE_SECONDS = 300

#: Fallback share image, shipped by the frontend at the site root.
PLACEHOLDER_IMAGE = "/brand/og-placeholder.png"

#: Largest-first: the first existing variant at least 600 px wide wins
#: (400 is below that, so it is only used when nothing larger exists).
_IMAGE_VARIANT_ORDER = ("webp_1200", "webp_800", "webp_400")

DEFAULT_DESCRIPTION = (
    "فروشگاه آنلاین ظروف آشپزخانه، پخت‌وپز، بلور و کریستال و لوازم خانه. "
    "ارسال به سراسر ایران، پرداخت امن اینترنتی."
)


def absolute(path):
    """Absolute URL for a site-root-relative path (or None)."""
    if not path:
        return None
    if path.startswith(("http://", "https://")):
        return path
    base = settings.FRONTEND_URL.rstrip("/")
    return f"{base}/{path.lstrip('/')}"


def og_image_for(image):
    """
    Share image for an image-bearing object, preferring the largest
    existing WebP variant (1200 -> 800 -> 400) and falling back to the
    original upload. Returns an ABSOLUTE URL; None when there is no image
    at all (callers then use placeholder_image()).
    """
    if not image:
        return None
    # A bare ImageField value (Category.image, Brand.logo) is already the
    # file itself; ProductImage rows are the objects with webp variants.
    if isinstance(image, File):
        return absolute(image.url)
    for field in _IMAGE_VARIANT_ORDER:
        value = getattr(image, field, None)
        # webp_* columns hold storage-relative paths (see apps.core.image_files).
        if value:
            return absolute(media_url(value))
    original = getattr(image, "image", None)
    if original:
        return absolute(original.url)
    return None


def placeholder_image():
    """Absolute URL of the shared brand placeholder used when an item has
    no (usable) image."""
    return absolute(PLACEHOLDER_IMAGE)


def _primary_image(product):
    """The product's primary ProductImage (or its first), without extra
    queries for a single-object page."""
    images = list(product.images.all())
    if not images:
        return None
    return next((img for img in images if img.is_primary), None) or images[0]


def product_meta(request, slug):
    """GET /seo/product/<slug>/ -- crawler HTML for one ACTIVE product."""
    from apps.products.models import Product
    from apps.products.pricing import price_info_for_product

    product = (
        Product.objects.filter(slug=slug, is_active=True)
        .select_related("brand", "category")
        .prefetch_related("images")
        .first()
    )
    if product is None:
        raise Http404("محصول یافت نشد.")

    price_info = price_info_for_product(product)
    in_stock = price_info and product.stock_quantity > 0
    page_url = absolute(f"/products/{iri_to_uri(product.slug)}/")
    image = og_image_for(_primary_image(product))
    is_placeholder = not image
    image = image or placeholder_image()

    description = (
        product.short_description
        or (product.description or "").strip()[:300]
        or DEFAULT_DESCRIPTION
    )
    title = f"{product.name} | {SITE_NAME}"

    json_ld = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": product.name,
        "description": description,
        "image": [image],
        "sku": product.sku,
        "url": page_url,
        "offers": {
            "@type": "Offer",
            "url": page_url,
            "price": str(price_info.price if price_info else product.price),
            # Whole-Toman prices (see README: "prices are whole Toman").
            "priceCurrency": "IRT",
            "availability": "https://schema.org/InStock" if in_stock else "https://schema.org/OutOfStock",
        },
    }
    if product.brand:
        json_ld["brand"] = {"@type": "Brand", "name": product.brand.name}

    return _html_response(
        title=title,
        description=description,
        url=page_url,
        image=image,
        og_type="product",
        extra_head=_json_ld_script(json_ld),
        heading=product.name,
        price_text=f"{price_info.price:,} تومان" if price_info else None,
        image_is_placeholder=is_placeholder,
    )


def shop_meta(request):
    """
    GET /seo/shop/ -- crawler HTML for the shop page, with the category
    filter honoured when ?category=<slug> is present (the storefront has
    no standalone category pages: /shop/?category=... is the canonical
    form, so that is the URL the preview must point back to).
    """
    from apps.categories.models import Category

    category_slug = (request.GET.get("category") or "").strip()
    if not category_slug:
        return _html_response(
            title=f"فروشگاه | {SITE_NAME}",
            description=DEFAULT_DESCRIPTION,
            url=absolute("/shop/"),
            image=placeholder_image(),
            og_type="website",
            heading="فروشگاه",
            image_is_placeholder=True,
        )

    category = Category.objects.filter(slug=category_slug, is_active=True).first()
    if category is None:
        raise Http404("دسته‌بندی یافت نشد.")

    description = (category.description or "").strip()[:300] or (
        f"خرید آنلاین {category.name} از {SITE_NAME}؛ ارسال به سراسر ایران."
    )
    image = og_image_for(category.image)
    is_placeholder = not image
    image = image or placeholder_image()
    return _html_response(
        title=f"{category.name} | {SITE_NAME}",
        description=description,
        url=absolute(f"/shop/?category={iri_to_uri(category.slug)}"),
        image=image,
        og_type="website",
        heading=category.name,
        image_is_placeholder=is_placeholder,
    )


def _json_ld_script(payload):
    import json

    # Valid JSON *and* safe inside <script>: only "<" is escaped (to its
    # \u003c JSON form), so a product name containing "</script>" cannot
    # break out of the block while crawlers still read plain JSON.
    data = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")
    return f'<script type="application/ld+json">{data}</script>'


def _html_response(
    *,
    title,
    description,
    url,
    image,
    og_type,
    heading,
    price_text=None,
    extra_head="",
    image_is_placeholder=False,
):
    parts = [
        "<!doctype html>",
        '<html lang="fa" dir="rtl">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{escape(title)}</title>",
        f'<meta name="description" content="{escape(description)}">',
        f'<link rel="canonical" href="{escape(url)}">',
        f'<meta property="og:type" content="{escape(og_type)}">',
        f'<meta property="og:site_name" content="{escape(SITE_NAME)}">',
        f'<meta property="og:title" content="{escape(title)}">',
        f'<meta property="og:description" content="{escape(description)}">',
        f'<meta property="og:url" content="{escape(url)}">',
        f'<meta property="og:image" content="{escape(image)}">',
        '<meta name="twitter:card" content="summary_large_image">',
        f'<meta name="twitter:title" content="{escape(title)}">',
        f'<meta name="twitter:description" content="{escape(description)}">',
        f'<meta name="twitter:image" content="{escape(image)}">',
    ]
    if image_is_placeholder:
        # The shared placeholder is a known 1200x630 asset; real product
        # images are whatever the owner uploaded, so we never invent a
        # size for them.
        parts.append('<meta property="og:image:width" content="1200">')
        parts.append('<meta property="og:image:height" content="630">')
    if extra_head:
        parts.append(extra_head)
    parts += [
        "</head>",
        "<body>",
        f"<h1>{escape(heading)}</h1>",
        f"<p>{escape(description)}</p>",
    ]
    if price_text:
        parts.append(f"<p>{escape(price_text)}</p>")
    parts += [
        f'<p><a href="{escape(url)}">مشاهدهٔ صفحهٔ کامل</a></p>',
        "</body>",
        "</html>",
    ]
    response = HttpResponse("\n".join(parts), content_type="text/html; charset=utf-8")
    response["Cache-Control"] = f"public, max-age={CACHE_SECONDS}"
    return response
