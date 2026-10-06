"""
Demo catalog seed (Phase B - Store management).

`python manage.py seed_demo` populates the store with a small, honest
demo catalog -- categories, brands, products with real generated image
files, a coupon, banners and daily deals -- so the storefront can be
previewed end to end without inventing "real" business data.

Idempotent: every row is get_or_create'd on its natural key (slug /
SKU / code), so re-running never duplicates anything. The generated
images are plain Pillow graphics (no text), saved through the normal
ProductImage.save() path, so thumbnails are produced exactly like a
real upload.
"""
import io

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.banners.models import Banner, DailyDeal
from apps.categories.models import Category
from apps.discounts.models import Coupon
from apps.products.models import (
    Brand,
    Product,
    ProductAttribute,
    ProductAttributeValue,
    ProductImage,
    ProductVariant,
)


def make_image_bytes(color_a, color_b, size=(800, 600)):
    """A simple two-tone demo graphic -- a real image file, no text
    (the sandbox has no Persian font, and tofu boxes would be fake)."""
    from PIL import Image, ImageDraw

    width, height = size
    img = Image.new("RGB", (width, height), color_a)
    draw = ImageDraw.Draw(img)
    # A few soft shapes so each demo photo is distinct.
    draw.ellipse(
        [width * 0.15, height * 0.2, width * 0.85, height * 0.9],
        fill=color_b,
    )
    draw.ellipse(
        [width * 0.3, height * 0.35, width * 0.7, height * 0.75],
        fill=color_a,
    )
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=88)
    return buffer.getvalue()


CATEGORIES = [
    # (name, slug, parent_slug, description)
    ("ظروف پخت‌وپز", "cookware", None, "قابلمه، تابه و ظروف پخت"),
    ("ظروف سرو و پذیرایی", "serving", None, "ظروف سرو، دیس و کاسه"),
    ("لیوان و ماگ", "cups-mugs", None, "ماگ، لیوان و فنجان"),
    ("کریستال و دکوری", "crystal-decor", None, "ظروف کریستال و دکوراتیو"),
    ("ست‌های آشپزخانه", "kitchen-sets", "cookware", "ست‌های کامل آشپزخانه"),
]

# Part R2: a few brands double as the home page featured tiles
# (is_featured + display_order), e.g. Unique per the owner's example.
BRANDS = [
    ("کازین", "kuzin"),
    ("کریستال پارس", "crystal-pars"),
    ("زرین هوم", "zarrin-home"),
    ("یونیک", "unique"),
]
FEATURED_BRANDS = ["یونیک", "کریستال پارس", "زرین هوم"]

PRODUCTS = [
    # dict: name, slug, sku, category, brand, price, compare_at_price,
    # stock, featured, new, best_seller, colors((r,g,b),(r,g,b))
    dict(name="تابه گریل چدنی ۲۸ سانتی‌متری", slug="grill-pan-28", sku="PAN-001",
         category="cookware", brand="زرین هوم", price=850000, compare_at_price=980000,
         stock=12, featured=True, new=False, best_seller=True,
         colors=((40, 40, 45), (120, 120, 125))),
    dict(name="قابلمه استیل ۱۸/۱۰ سایز ۲۰", slug="steel-pot-20", sku="POT-020",
         category="cookware", brand="زرین هوم", price=1250000, compare_at_price=None,
         stock=8, featured=False, new=True, best_seller=False,
         colors=((70, 90, 110), (190, 205, 220))),
    dict(name="ماگ سرامیکی دسته‌دار ۳۰۰ میلی‌لیتر", slug="ceramic-mug-300", sku="MUG-300",
         category="cups-mugs", brand="کازین", price=180000, compare_at_price=220000,
         stock=40, featured=True, new=False, best_seller=True,
         colors=((150, 60, 40), (235, 190, 160))),
    dict(name="فنجان اسپرسو دوجداره", slug="espresso-cup-double", sku="MUG-ESP-02",
         category="cups-mugs", brand="کازین", price=240000, compare_at_price=None,
         stock=3, featured=False, new=False, best_seller=False,
         colors=((90, 60, 45), (220, 200, 180))),
    dict(name="دیس سرو کریستال پایه‌دار", slug="crystal-serving-plate", sku="CRY-010",
         category="serving", brand="کریستال پارس", price=1650000, compare_at_price=1900000,
         stock=5, featured=True, new=False, best_seller=False,
         colors=((120, 140, 160), (240, 245, 250))),
    dict(name="کاسه سالاد کریستال", slug="crystal-salad-bowl", sku="CRY-011",
         category="serving", brand="کریستال پارس", price=980000, compare_at_price=None,
         stock=9, featured=False, new=True, best_seller=False,
         colors=((100, 130, 140), (230, 240, 245))),
    dict(name="گلدان دکوری کریستال", slug="crystal-vase", sku="CRY-020",
         category="crystal-decor", brand="کریستال پارس", price=2200000, compare_at_price=None,
         stock=4, featured=True, new=True, best_seller=False,
         colors=((90, 110, 130), (235, 240, 248))),
    dict(name="ست قابلمه ۶ پارچه گرانیتی", slug="granite-pot-set-6", sku="SET-006",
         category="kitchen-sets", brand="زرین هوم", price=4800000, compare_at_price=5600000,
         stock=6, featured=True, new=False, best_seller=True,
         colors=((50, 50, 55), (140, 130, 120))),
    dict(name="ست ماگ ۴ عددی رنگی", slug="mug-set-4", sku="SET-MUG-04",
         category="kitchen-sets", brand="کازین", price=690000, compare_at_price=None,
         stock=15, featured=False, new=True, best_seller=False,
         colors=((170, 90, 60), (245, 220, 200))),
]


class Command(BaseCommand):
    help = (
        "Seed a small demo catalog (categories, brands, products with images, "
        "one coupon, banners and a daily deal) so the storefront can be "
        "previewed. Safe to re-run: existing rows are reused, never duplicated."
    )

    def handle(self, *args, **options):
        now = timezone.now()

        categories = {}
        for name, slug, parent_slug, description in CATEGORIES:
            parent = categories.get(parent_slug)
            category, _ = Category.objects.get_or_create(
                slug=slug,
                defaults={
                    "name": name,
                    "parent": parent,
                    "description": description,
                    "is_active": True,
                    "ordering": len(categories),
                },
            )
            categories[slug] = category
        self.stdout.write(f"Categories: {Category.objects.count()}")

        brands = {}
        for i, (name, slug) in enumerate(BRANDS):
            brand, _ = Brand.objects.get_or_create(
                slug=slug, defaults={"name": name, "is_active": True}
            )
            # Part R2 featured tiles: keep the seed idempotent by syncing the
            # flags on every run.
            featured = name in FEATURED_BRANDS
            if brand.is_featured != featured or (featured and brand.display_order != FEATURED_BRANDS.index(name)):
                brand.is_featured = featured
                brand.display_order = FEATURED_BRANDS.index(name) if featured else 0
                brand.save(update_fields=["is_featured", "display_order", "updated_at"])
            brands[name] = brand
        self.stdout.write(f"Brands: {Brand.objects.count()}")

        color_attribute, _ = ProductAttribute.objects.get_or_create(
            slug="color", defaults={"name": "رنگ"}
        )

        created_products = 0
        for data in PRODUCTS:
            product, created = Product.objects.get_or_create(
                sku=data["sku"],
                defaults={
                    "name": data["name"],
                    "slug": data["slug"],
                    "category": categories[data["category"]],
                    "brand": brands[data["brand"]],
                    "price": data["price"],
                    "compare_at_price": data["compare_at_price"],
                    "stock_quantity": data["stock"],
                    "low_stock_threshold": 5,
                    "is_active": True,
                    "is_featured": data["featured"],
                    "is_new": data["new"],
                    "is_best_seller": data["best_seller"],
                    "short_description": f"{data['name']} — محصول نمایشی برای پیش‌نمایش فروشگاه.",
                },
            )
            if created:
                created_products += 1
                color_a, color_b = data["colors"]
                image = ProductImage(product=product, alt_text=data["name"], is_primary=True)
                image.image.save(
                    f"demo-{data['sku'].lower()}.jpg",
                    ContentFile(make_image_bytes(color_a, color_b)),
                    save=False,
                )
                image.save()  # thumbnail generated by the normal save() path

                # One demo product shows the variant system: two colors.
                if data["sku"] == "MUG-300":
                    for color_name, hexish in [("کرم", (235, 190, 160)), ("آجری", (150, 60, 40))]:
                        value, _ = ProductAttributeValue.objects.get_or_create(
                            attribute=color_attribute, value=color_name
                        )
                        variant, _ = ProductVariant.objects.get_or_create(
                            product=product,
                            sku=f"{data['sku']}-{color_name}",
                            defaults={
                                "price": product.price,
                                "stock_quantity": product.stock_quantity // 2,
                                "is_active": True,
                            },
                        )
                        variant.attribute_values.add(value)
        self.stdout.write(
            f"Products: {Product.objects.count()} ({created_products} newly created)"
        )

        coupon, created = Coupon.objects.get_or_create(
            code="WELCOME10",
            defaults={
                "discount_type": Coupon.DiscountType.PERCENTAGE,
                "percentage_value": 10,
                "maximum_discount_amount": 200000,
                "usage_limit": 1000,
                "per_user_usage_limit": 1,
                "is_active": True,
            },
        )
        self.stdout.write(f"Coupon WELCOME10: {'created' if created else 'already exists'}")

        banner_title = "جشنوارهٔ پاییزی کازین گالری"
        created = not Banner.objects.filter(title=banner_title).exists()
        if created:
            banner = Banner(
                title=banner_title,
                subtitle="تا ۲۰٪ تخفیف روی ست‌های آشپزخانه",
                cta_text="مشاهدهٔ محصولات",
                cta_url="/shop/",
                is_active=True,
                ordering=0,
            )
            # image is NOT NULL, so it must be set before the first save
            banner.image.save(
                "demo-banner.jpg",
                ContentFile(make_image_bytes((30, 58, 95), (200, 140, 60), size=(1600, 500))),
                save=False,
            )
            banner.save()
        self.stdout.write(f"Banner: {'created' if created else 'already exists'}")

        deal_product = Product.objects.get(sku="CRY-010")
        deal, created = DailyDeal.objects.get_or_create(
            product=deal_product,
            starts_at__lte=now,
            ends_at__gte=now,
            defaults={
                "sale_price": int(deal_product.price * 0.85),
                "starts_at": now,
                "ends_at": now + timezone.timedelta(days=1),
                "is_active": True,
            },
        )
        self.stdout.write(f"Daily deal: {'created' if created else 'already exists'}")

        self.stdout.write(self.style.SUCCESS("Demo catalog is ready."))
