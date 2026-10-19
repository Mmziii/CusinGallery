"""
Seed the owner-editable content with the CURRENT hard-coded storefront
texts, so deploying this feature changes nothing a customer can see:

* the singleton SiteSettings row keeps the exact footer/brand/home wording
  that used to live in frontend/src/components/{Footer,Header,Home}.jsx;
* the five trust-strip items are the same five labels/icons, in the same
  order;
* the five info pages start as the exact copy of
  frontend/src/pages/info/*.jsx (body, SEO title and description).

The theme needs no rows: the default preset «زیتونی و طلایی» is the current
variables.css palette.
"""
from django.db import migrations

TRUST_ITEMS = (
    ("shield-check", "تضمین اصالت کالا و سلامت فیزیکی اجناس", 10),
    ("box", "بسته‌بندی ضدضربهٔ کالا", 20),
    ("truck", "ارسال به سراسر ایران", 30),
    ("lock", "پرداخت امن اینترنتی", 40),
    ("bolt-fast", "امکان تحویل اکسپرس", 50),
)

SITE_TEXTS = {
    "site_name": "کازین گالری",
    "tagline": "کازین گالری، خانهٔ ظروف دوست‌داشتنی",
    "home_heading": "کازین گالری؛ فروشگاه لوازم خانه و آشپزخانه",
    "hero_title": "کازین گالری، خانهٔ ظروف دوست‌داشتنی",
    "hero_subtitle": "ظروف آشپزخانه، بلور و کریستال و لوازم خانگی؛ "
    "انتخابی مطمئن برای خانه‌ای زیباتر.",
    "hero_button_text": "مشاهدهٔ فروشگاه",
    "hero_button_link": "/shop/",
    "section_categories_title": "دسته‌بندی‌ها",
    "section_deals_title": "پیشنهاد امروز",
    "section_featured_title": "محصولات منتخب",
    "section_new_title": "جدیدترین محصولات",
    "section_best_title": "پرفروش‌ترین‌ها",
    "section_reviews_title": "از زبان خریداران",
    "story_title": "کازین گالری؛ خانهٔ ظروف دوست‌داشتنی",
    "story_text": "ما در کازین گالری باور داریم آشپزخانه قلب هر خانه است؛ به همین "
    "دلیل هر ظرف، قابلمه و بلوری را خودمان پیش از عرضه بررسی می‌کنیم و با "
    "بسته‌بندی ضدضربه و پشتیبانی پاسخگو به دست شما می‌رسانیم. انتخابی مطمئن، "
    "برای خانه‌ای زیباتر.",
    "footer_about": "فروشگاه آنلاین ظروف آشپزخانه، پخت‌وپز، بلور و کریستال و "
    "لوازم خانگی. خریدی مطمئن برای خانه‌ای زیباتر.",
    "email": "support@cusin.ir",
    "footer_quick_links_title": "دسترسی سریع",
    "footer_help_links_title": "راهنما و قوانین",
    "footer_trust_title": "نمادها و مجوزها",
    "copyright_text": "",
    "floating_enabled": True,
    "floating_whatsapp": True,
    "floating_telegram": True,
    "floating_phone": True,
    "floating_instagram": False,
}

INFO_PAGES = (
    {
        "slug": "about",
        "title": "دربارهٔ کازین گالری",
        "seo_title": "دربارهٔ کازین گالری",
        "seo_description": "آشنایی با کازین گالری، فروشگاه تخصصی ظروف آشپزخانه، "
        "بلور و کریستال و لوازم خانه.",
        "body": (
            "<p>کازین گالری با هدف ارائهٔ ظروف آشپزخانه، لوازم پخت‌وپز، بلور و "
            "کریستال و لوازم خانگی باکیفیت راه‌اندازی شده است. ما تلاش می‌کنیم "
            "تجربهٔ خریدی مطمئن، شفاف و لذت‌بخش برای خانه‌های ایرانی فراهم کنیم.</p>"
            "<p>در این فروشگاه می‌توانید از میان برندهای معتبر داخلی و خارجی "
            "انتخاب کنید، مشخصات و قیمت هر کالا را با دقت بررسی نمایید و سفارش "
            "خود را با پرداخت امن اینترنتی و ارسال به سراسر ایران تکمیل کنید.</p>"
            "<h2>چرا کازین گالری؟</h2>"
            "<ul>"
            "<li>تضمین اصالت و سلامت فیزیکی کالا</li>"
            "<li>پشتیبانی پاسخگو پیش و پس از خرید</li>"
            "<li>ارسال سریع و بسته‌بندی ایمن ظروف شکستنی</li>"
            "</ul>"
        ),
        "ordering": 10,
    },
    {
        "slug": "contact",
        "title": "تماس با ما",
        "seo_title": "تماس با ما",
        "seo_description": "راه‌های ارتباطی با کازین گالری: تلفن، واتس‌اپ، تلگرام، "
        "اینستاگرام، نشانی و ساعات پاسخگویی.",
        "body": (
            "<p>ایمیل پشتیبانی: "
            '<a href="mailto:support@cusin.ir">support@cusin.ir</a></p>'
            "<p>برای پیگیری سفارش، از بخش <strong>حساب کاربری، بخش سفارش‌ها</strong> "
            "وضعیت و کد رهگیری مرسوله را مشاهده کنید؛ در صورت نیاز به پشتیبانی، "
            "شمارهٔ سفارش را همراه داشته باشید.</p>"
        ),
        "ordering": 20,
    },
    {
        "slug": "shipping-returns",
        "title": "رویهٔ ارسال و مرجوعی",
        "seo_title": "رویهٔ ارسال و مرجوعی",
        "seo_description": "شرایط ارسال، هزینه‌ها، بازهٔ تحویل و رویهٔ مرجوع کردن "
        "کالا در کازین گالری.",
        "body": (
            "<h2>ارسال</h2>"
            "<ul>"
            "<li>ارسال <strong>استاندارد</strong>: معمولاً ۳ تا ۵ روز کاری، با "
            "هزینهٔ ثابت (ارسال رایگان برای خریدهای بالای مبلغ تعیین‌شده).</li>"
            "<li>ارسال <strong>اکسپرس</strong>: معمولاً ۱ تا ۲ روز کاری با هزینهٔ "
            "جداگانه.</li>"
            "<li>ظروف شکستنی با بسته‌بندی محافظ ارسال می‌شوند؛ لطفاً هنگام تحویل، "
            "سلامت بسته را بررسی کنید.</li>"
            "</ul>"
            "<h2>مرجوعی</h2>"
            "<ul>"
            "<li>در صورت انصراف از خرید، تا ۷ روز پس از تحویل امکان درخواست "
            "مرجوعی وجود دارد؛ کالا باید استفاده‌نشده و در بسته‌بندی اولیه باشد.</li>"
            "<li>کالای آسیب‌دیده یا مغایر با سفارش را حداکثر تا ۴۸ ساعت پس از "
            "تحویل اطلاع دهید تا بدون هزینه تعویض یا بازپرداخت شود.</li>"
            "<li>بازپرداخت مبالغ پس از رسیدن کالا و تأیید کارشناس، از همان مسیر "
            "پرداخت انجام می‌شود و معمولاً چند روز کاری زمان می‌برد.</li>"
            "</ul>"
            "<p>برای شروع درخواست مرجوعی با پشتیبانی تماس بگیرید (صفحهٔ «تماس با "
            "ما»)؛ شمارهٔ سفارش را همراه داشته باشید.</p>"
        ),
        "ordering": 30,
    },
    {
        "slug": "terms",
        "title": "شرایط و قوانین استفاده",
        "seo_title": "شرایط و قوانین استفاده",
        "seo_description": "شرایط و قوانین خرید و استفاده از فروشگاه اینترنتی "
        "کازین گالری.",
        "body": (
            "<h2>۱. کلیات</h2>"
            "<p>استفاده از وب‌سایت کازین گالری و ثبت سفارش، به معنای پذیرش شرایط "
            "زیر است. این شرایط ممکن است به‌روزرسانی شود؛ نسخهٔ معتبر، همین صفحه "
            "در زمان خرید است.</p>"
            "<h2>۲. حساب کاربری</h2>"
            "<p>اطلاعات حساب (شمارهٔ موبایل/ایمیل و رمز عبور) محرمانه است و "
            "مسئولیت حفظ آن و فعالیت‌های انجام‌شده با حساب، بر عهدهٔ کاربر است.</p>"
            "<h2>۳. سفارش و پرداخت</h2>"
            "<p>قیمت‌ها به تومان و شامل مالیات بر ارزش افزوده (در صورت اعمال) است. "
            "سفارش پس از پرداخت موفق ثبت قطعی می‌شود؛ تا پیش از پرداخت، امکان لغو "
            "سفارش وجود دارد.</p>"
            "<h2>۴. مسئولیت</h2>"
            "<p>مسئولیت فروشگاه در قبال هر سفارش حداکثر معادل مبلغ همان سفارش است "
            "و این شرایط هیچ‌گاه حقوق قانونی غیرقابل‌اسقاط مصرف‌کننده را محدود "
            "نمی‌کند.</p>"
        ),
        "ordering": 40,
    },
    {
        "slug": "privacy",
        "title": "حریم خصوصی",
        "seo_title": "حریم خصوصی",
        "seo_description": "سیاست حفظ حریم خصوصی و داده‌های کاربران در کازین گالری.",
        "body": (
            "<h2>چه داده‌هایی جمع‌آوری می‌شود؟</h2>"
            "<ul>"
            "<li>اطلاعات حساب: شمارهٔ موبایل، ایمیل (اختیاری) و نام.</li>"
            "<li>اطلاعات سفارش: آدرس و شمارهٔ تماس گیرنده، اقلام و مبالغ خرید.</li>"
            "<li>اطلاعات پرداخت نزد درگاه پرداخت معتبر (زرین‌پال) می‌ماند؛ "
            "<strong>شمارهٔ کامل کارت یا رمز شما هرگز در سیستم ما ذخیره "
            "نمی‌شود</strong> (فقط شمارهٔ مرجع تراکنش و شمارهٔ ماسک‌شدهٔ کارت).</li>"
            "</ul>"
            "<h2>داده‌ها چگونه استفاده می‌شوند؟</h2>"
            "<ul>"
            "<li>پردازش و ارسال سفارش‌ها، پشتیبانی و اطلاع‌رسانی وضعیت سفارش "
            "(پیامک/ایمیل).</li>"
            "<li>انجام تکالیف قانونی (مالیاتی و صنفی).</li>"
            "</ul>"
            "<h2>حقوق شما</h2>"
            "<p>می‌توانید برای مشاهده، اصلاح یا حذف اطلاعات حساب خود با پشتیبانی "
            "تماس بگیرید. کوکی‌های این سایت فقط برای نگهداری نشست ورود (session) "
            "استفاده می‌شوند.</p>"
        ),
        "ordering": 50,
    },
)


def seed(apps, schema_editor):
    SiteSettings = apps.get_model("core", "SiteSettings")
    TrustStripItem = apps.get_model("core", "TrustStripItem")
    InfoPage = apps.get_model("core", "InfoPage")

    site, _created = SiteSettings.objects.get_or_create(pk=1)
    for field, value in SITE_TEXTS.items():
        setattr(site, field, value)
    site.save()

    for icon, label, ordering in TRUST_ITEMS:
        TrustStripItem.objects.get_or_create(
            site=site,
            label=label,
            defaults={"icon": icon, "ordering": ordering, "is_active": True},
        )

    for page in INFO_PAGES:
        InfoPage.objects.get_or_create(
            slug=page["slug"],
            defaults={
                "title": page["title"],
                "body": page["body"],
                "seo_title": page["seo_title"],
                "seo_description": page["seo_description"],
                "ordering": page["ordering"],
                "is_published": True,
            },
        )


def unseed(apps, schema_editor):
    TrustStripItem = apps.get_model("core", "TrustStripItem")
    InfoPage = apps.get_model("core", "InfoPage")

    TrustStripItem.objects.filter(label__in=[item[1] for item in TRUST_ITEMS]).delete()
    InfoPage.objects.filter(slug__in=[page["slug"] for page in INFO_PAGES]).delete()


class Migration(migrations.Migration):
    dependencies = [("core", "0005_infopage_alter_sitesettings_options_and_more")]

    operations = [migrations.RunPython(seed, unseed)]
