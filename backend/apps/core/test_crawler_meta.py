"""
Part S4 item 3: crawler-visible meta for product and category pages.

WhatsApp/Telegram/Twitter/search crawlers do not run JavaScript, so the
SPA's runtime meta tags never reach them. The nginx configs proxy known
bot user agents to /seo/product/<slug>/ and /seo/shop/?category=<slug>;
these tests pin the behaviour of those two endpoints:

  * with an image: the largest existing WebP variant, as an ABSOLUTE URL;
  * without an image: the shared 1200x630 brand placeholder;
  * inactive or unknown products/categories: 404 (never a preview of an
    unpublished product);
  * Persian slugs, both raw and percent-encoded;
  * JSON-LD Product with price + availability, a Twitter card, a canonical
    URL and a link back to the real page;
  * a short Cache-Control so a price change is never cached for long.
"""
from pathlib import Path
from urllib.parse import quote

from django.test import SimpleTestCase, TestCase, override_settings

from apps.categories.models import Category
from apps.products.tests.helpers import make_category, make_image, make_product

FRONTEND = "https://example.test"


@override_settings(FRONTEND_URL=FRONTEND)
class ProductMetaTests(TestCase):
    def test_product_with_image_uses_the_largest_webp_variant_as_an_absolute_url(self):
        product = make_product(is_active=True, stock_quantity=4, short_description="قابلمهٔ استیل با درب شیشه‌ای")
        make_image(
            product,
            image="products/pan.jpg",
            is_primary=True,
            webp_400="products/pan-400.webp",
            webp_800="products/pan-800.webp",
            webp_1200="products/pan-1200.webp",
        )

        response = self.client.get(f"/seo/product/{product.slug}/")

        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn(
            f'<meta property="og:image" content="{FRONTEND}/media/products/pan-1200.webp">',
            body,
        )
        self.assertIn('<meta property="og:type" content="product">', body)
        self.assertIn(f'<meta property="og:url" content="{FRONTEND}/products/{product.slug}/">', body)
        self.assertIn('<meta name="twitter:card" content="summary_large_image">', body)
        self.assertIn('"@type": "Product"', body)
        self.assertIn(f'"sku": "{product.sku}"', body)
        self.assertIn('"priceCurrency": "IRT"', body)
        self.assertIn('"availability": "https://schema.org/InStock"', body)
        # A human landing here is sent to the real page.
        self.assertIn(f'href="{FRONTEND}/products/{product.slug}/"', body)
        # Short cache: prices/availability move.
        self.assertEqual(response["Cache-Control"], "public, max-age=300")

    def test_product_without_image_falls_back_to_the_brand_placeholder(self):
        product = make_product(is_active=True)

        response = self.client.get(f"/seo/product/{product.slug}/")

        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn(
            f'<meta property="og:image" content="{FRONTEND}/brand/og-placeholder.png">',
            body,
        )
        # The placeholder has a known size, so crawlers get it.
        self.assertIn('<meta property="og:image:width" content="1200">', body)
        self.assertIn('"availability": "https://schema.org/OutOfStock"', body)

    def test_falls_back_to_the_original_upload_when_no_webp_variant_exists(self):
        product = make_product(is_active=True, stock_quantity=3)
        make_image(product, image="products/plain.jpg", is_primary=True)

        body = self.client.get(f"/seo/product/{product.slug}/").content.decode()

        self.assertIn(f'content="{FRONTEND}/media/products/plain.jpg"', body)

    def test_inactive_product_is_404_and_never_rendered(self):
        product = make_product(is_active=False)

        response = self.client.get(f"/seo/product/{product.slug}/")

        self.assertEqual(response.status_code, 404)

    def test_unknown_slug_is_404(self):
        self.assertEqual(self.client.get("/seo/product/does-not-exist/").status_code, 404)

    def test_persian_slug_works_raw_and_percent_encoded(self):
        product = make_product(
            name="قابلمه استیل",
            slug="قابلمه-استیل-۲۸",
            is_active=True,
        )

        raw = self.client.get(f"/seo/product/{product.slug}/")
        encoded = self.client.get(f"/seo/product/{quote(product.slug)}/")

        self.assertEqual(raw.status_code, 200)
        self.assertEqual(encoded.status_code, 200)
        self.assertIn(f"<h1>{product.name}</h1>", raw.content.decode())
        # The canonical/og:url carry the percent-encoded (IRI-safe) slug.
        self.assertIn(quote(product.slug), raw.content.decode())

    def test_html_is_escaped_so_a_product_name_cannot_break_the_document(self):
        product = make_product(name='قابلمه <script>alert("x")</script>', is_active=True)

        body = self.client.get(f"/seo/product/{product.slug}/").content.decode()

        self.assertNotIn("<script>alert", body)
        self.assertIn("&lt;script&gt;", body)


@override_settings(FRONTEND_URL=FRONTEND)
class ShopCategoryMetaTests(TestCase):
    def test_shop_without_category_renders_a_generic_document(self):
        response = self.client.get("/seo/shop/")

        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn(f'<meta property="og:url" content="{FRONTEND}/shop/">', body)
        self.assertIn(
            f'{FRONTEND}/brand/og-placeholder.png', body,
        )

    def test_category_filter_uses_the_category_name_and_image(self):
        category = make_category(name="قابلمه و ماهیتابه")
        # Category.image is a plain ImageField (no webp variants).
        category.image = "categories/pots.jpg"
        category.save(update_fields=["image"])

        response = self.client.get("/seo/shop/", {"category": category.slug})

        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("<h1>قابلمه و ماهیتابه</h1>", body)
        self.assertIn(f'content="{FRONTEND}/media/categories/pots.jpg"', body)
        self.assertIn("category=", body)

    def test_category_without_image_uses_the_placeholder(self):
        category = make_category(name="بلور و کریستال")

        body = self.client.get("/seo/shop/", {"category": category.slug}).content.decode()

        self.assertIn(f'content="{FRONTEND}/brand/og-placeholder.png"', body)

    def test_inactive_category_is_404(self):
        category = Category.objects.create(name="غیرفعال", slug="inactive-cat", is_active=False)

        response = self.client.get("/seo/shop/", {"category": category.slug})

        self.assertEqual(response.status_code, 404)
        self.assertNotIn("غیرفعال", response.content.decode())

    def test_unknown_category_is_404(self):
        self.assertEqual(self.client.get("/seo/shop/", {"category": "nope"}).status_code, 404)

    def test_persian_category_slug(self):
        category = make_category(name="ظروف آشپزخانه", slug="ظروف-آشپزخانه")

        response = self.client.get("/seo/shop/", {"category": category.slug})

        self.assertEqual(response.status_code, 200)
        self.assertIn("ظروف آشپزخانه", response.content.decode())


class NginxBotRoutingWiringTests(SimpleTestCase):
    """
    The endpoint tests above can only pass if nginx actually sends bots
    here. This does NOT validate nginx syntax (that needs `nginx -t`, which
    is not available in this environment); it only guards that both edge
    configs keep the bot map and the two /seo/ proxy targets, so a future
    edit cannot silently drop server-rendered previews.
    """

    CONFIGS = (
        Path(__file__).resolve().parents[3] / "nginx" / "conf.d" / "cusin.conf",
        Path(__file__).resolve().parents[3] / "nginx" / "prod.d" / "cusin.conf",
    )

    def test_both_configs_route_bots_to_the_seo_endpoints(self):
        for config in self.CONFIGS:
            text = config.read_text(encoding="utf-8")
            with self.subTest(config=config.name):
                self.assertIn("map $http_user_agent $cusin_is_bot", text)
                self.assertIn("whatsapp", text)
                self.assertIn("telegram", text)
                self.assertIn("eitaa", text)
                self.assertIn("/seo/product/$cusin_product_slug/", text)
                self.assertIn("/seo/shop/", text)
                # The payment callback and API routing must stay untouched.
                self.assertIn("location /payment/callback/", text)
                self.assertIn("location /api/", text)
