"""
Shared abstract base models.

These contain no business logic of their own -- they exist so every app
added from Phase 2 onward (products, orders, categories, ...) can inherit
common, consistently-named fields instead of redefining them, and so that
"is this timestamped / orderable / active" behaves identically everywhere
in the codebase.

Abstract models generate no database table and no migration by themselves;
migrations appear once a concrete model in another app inherits from one
of these.
"""
from django.db import models

from .theme import (
    BASE_FONT_SIZE_CHOICES,
    BUTTON_RADIUS_CHOICES,
    CARD_SHADOW_CHOICES,
    DEFAULT_BASE_FONT_SIZE,
    DEFAULT_BUTTON_RADIUS,
    DEFAULT_CARD_SHADOW,
    DEFAULT_PRESET,
    THEME_PRESET_CHOICES,
    validate_hex_color,
)


class TimeStampedModel(models.Model):
    """Adds created_at / updated_at, auto-managed on save."""

    created_at = models.DateTimeField("تاریخ ایجاد", auto_now_add=True)
    updated_at = models.DateTimeField("تاریخ ویرایش", auto_now=True)

    class Meta:
        abstract = True


class ActivableModel(models.Model):
    """Adds an is_active flag, for soft enable/disable instead of deletion."""

    is_active = models.BooleanField(
        "فعال", default=True, help_text="به‌جای حذف، برای غیرفعال‌کردن موقت استفاده می‌شود."
    )

    class Meta:
        abstract = True


class OrderableModel(models.Model):
    """Adds an integer ordering field for admin-controlled display order."""

    ordering = models.PositiveIntegerField(
        "ترتیب نمایش", default=0, help_text="عدد کوچک‌تر زودتر نمایش داده می‌شود."
    )

    class Meta:
        abstract = True
        ordering = ["ordering"]


#: Icon ids the storefront's Icon component really knows (see
#: frontend/src/components/Icon.jsx). The trust-strip icon dropdown offers
#: exactly these, so an owner can never save an icon that renders blank.
TRUST_ICON_CHOICES = (
    ("shield-check", "سپر تأیید (اصالت کالا)"),
    ("box", "جعبه (بسته‌بندی)"),
    ("truck", "کامیون (ارسال)"),
    ("lock", "قفل (پرداخت امن)"),
    ("bolt-fast", "صاعقه (ارسال سریع)"),
    ("clock", "ساعت (زمان‌بندی)"),
    ("store", "فروشگاه (دریافت حضوری)"),
    ("star", "ستاره (کیفیت)"),
    ("heart", "قلب (رضایت)"),
    ("check", "تیک (تضمین)"),
    ("phone", "تلفن (پشتیبانی)"),
    ("chat", "گفتگو (پشتیبانی پیام)"),
    ("send", "ارسال پیام"),
    ("home", "خانه"),
    ("bag", "کیف خرید"),
    ("info", "اطلاعات"),
)

#: The fixed info/trust pages and the URL each one is served at. Slugs are
#: part of the public route table (frontend/src/App.jsx + apps/core/spa.py),
#: so the owner edits their content, never the address.
INFO_PAGE_SLUGS = (
    ("about", "دربارهٔ ما"),
    ("contact", "تماس با ما"),
    ("shipping-returns", "ارسال و مرجوعی"),
    ("terms", "قوانین و مقررات"),
    ("privacy", "حریم خصوصی"),
)


class SiteSettings(TimeStampedModel):
    """
    Store-wide content/appearance settings -- a SINGLETON: there is exactly
    one row (pk forced to 1), edited in admin under «محتوا و ظاهر سایت».

    It started as the contact/branding singleton (Part 1) and is extended
    rather than duplicated: the footer, contact page, pickup info, invoices
    and the floating contact button already read these phone/address/social
    fields, so the owner has ONE place for every storefront text instead of
    two values that can disagree.

    Kept out of .env on purpose: these are business content the owner
    changes from the admin UI, not deployment configuration.
    """

    # --- هویت برند -----------------------------------------------------
    # «نام فروشگاه» used to be hardcoded in the invoice/print templates.
    # It lives here so the owner can change what their own documents say
    # without a deploy; empty falls back to the fixed brand name.
    shop_name = models.CharField(
        "نام فروشگاه (فاکتور)", max_length=120, blank=True, default="",
        help_text="بالای فاکتور مشتری و برگهٔ چاپ سفارش می‌آید. "
                  "اگر خالی بماند، نام ثابت برند استفاده می‌شود.",
    )
    site_name = models.CharField(
        "نام سایت", max_length=120, blank=True, default="کازین گالری",
        help_text="در هدر، فوتر، عنوان صفحات و پیام‌های فروشگاه نمایش داده می‌شود.",
    )
    tagline = models.CharField(
        "شعار سایت", max_length=200, blank=True,
        default="کازین گالری، خانهٔ ظروف دوست‌داشتنی",
        help_text="زیر نام سایت در هدر و در توضیحات پیش‌فرض صفحهٔ اصلی.",
    )
    logo_light = models.ImageField(
        "لوگوی هدر روشن", upload_to="branding/", blank=True, null=True,
        help_text="برای هدر با پس‌زمینهٔ روشن. خالی = لوگوی پیش‌فرض برند.",
    )
    logo_dark = models.ImageField(
        "لوگوی هدر تیره", upload_to="branding/", blank=True, null=True,
        help_text="برای هدر با پس‌زمینهٔ تیره (وقتی رنگ هدر در بخش ظاهر سایت "
        "تیره انتخاب شود). خالی = لوگوی پیش‌فرض برند.",
    )
    favicon = models.ImageField(
        "فاوآیکون", upload_to="branding/", blank=True, null=True,
        help_text="آیکون نوار مرورگر. PNG مربعی ۳۲×۳۲ یا SVG. خالی = فاوآیکون پیش‌فرض.",
    )

    # --- صفحهٔ اصلی ----------------------------------------------------
    home_heading = models.CharField(
        "عنوان اصلی صفحهٔ خانه", max_length=200, blank=True,
        default="کازین گالری؛ فروشگاه لوازم خانه و آشپزخانه",
        help_text="عنوان پنهان (برای موتورهای جستجو) بالای صفحهٔ اصلی.",
    )
    hero_title = models.CharField(
        "عنوان بنر پیش‌فرض", max_length=200, blank=True,
        default="کازین گالری، خانهٔ ظروف دوست‌داشتنی",
        help_text="فقط وقتی هیچ بنر فعالی در بخش «بنرها» وجود نداشته باشد نمایش "
        "داده می‌شود؛ در غیر این صورت متن هر بنر از خودش می‌آید.",
    )
    hero_subtitle = models.CharField(
        "زیرعنوان بنر پیش‌فرض", max_length=300, blank=True,
        default="ظروف آشپزخانه، بلور و کریستال و لوازم خانگی؛ "
        "انتخابی مطمئن برای خانه‌ای زیباتر.",
    )
    hero_button_text = models.CharField(
        "متن دکمهٔ بنر پیش‌فرض", max_length=80, blank=True, default="مشاهدهٔ فروشگاه",
    )
    hero_button_link = models.CharField(
        "نشانی دکمهٔ بنر پیش‌فرض", max_length=200, blank=True, default="/shop/",
        help_text="یک مسیر داخلی مثل /shop/ یا نشانی کامل https://…",
    )
    section_categories_title = models.CharField(
        "عنوان بخش دسته‌بندی‌ها", max_length=120, blank=True, default="دسته‌بندی‌ها",
    )
    section_deals_title = models.CharField(
        "عنوان بخش پیشنهاد امروز", max_length=120, blank=True, default="پیشنهاد امروز",
    )
    section_featured_title = models.CharField(
        "عنوان بخش محصولات منتخب", max_length=120, blank=True, default="محصولات منتخب",
    )
    section_new_title = models.CharField(
        "عنوان بخش جدیدترین محصولات", max_length=120, blank=True, default="جدیدترین محصولات",
    )
    section_best_title = models.CharField(
        "عنوان بخش پرفروش‌ترین‌ها", max_length=120, blank=True, default="پرفروش‌ترین‌ها",
    )
    section_reviews_title = models.CharField(
        "عنوان بخش نظرات خریداران", max_length=120, blank=True, default="از زبان خریداران",
    )
    story_title = models.CharField(
        "عنوان داستان برند", max_length=200, blank=True,
        default="کازین گالری؛ خانهٔ ظروف دوست‌داشتنی",
    )
    story_text = models.TextField(
        "متن داستان برند", blank=True,
        default="ما در کازین گالری باور داریم آشپزخانه قلب هر خانه است؛ به همین "
        "دلیل هر ظرف، قابلمه و بلوری را خودمان پیش از عرضه بررسی می‌کنیم و با "
        "بسته‌بندی ضدضربه و پشتیبانی پاسخگو به دست شما می‌رسانیم. انتخابی مطمئن، "
        "برای خانه‌ای زیباتر.",
    )

    # --- تماس و فوتر ---------------------------------------------------
    footer_about = models.TextField(
        "متن دربارهٔ فروشگاه در فوتر", blank=True,
        default="فروشگاه آنلاین ظروف آشپزخانه، پخت‌وپز، بلور و کریستال و لوازم "
        "خانگی. خریدی مطمئن برای خانه‌ای زیباتر.",
    )
    phone = models.CharField("تلفن پشتیبانی", max_length=40, blank=True, default="")
    extra_phones = models.TextField(
        "تلفن‌های دیگر", blank=True, default="",
        help_text="هر شماره در یک خط. در فوتر و صفحهٔ تماس با ما نمایش داده می‌شود.",
    )
    email = models.EmailField(
        "ایمیل", max_length=120, blank=True, default="support@cusin.ir",
    )
    whatsapp = models.CharField(
        "واتس‌اپ", max_length=40, blank=True, default="",
        help_text="شمارهٔ کامل با کد کشور، مثال: +989120000000",
    )
    telegram = models.CharField(
        "تلگرام", max_length=80, blank=True, default="",
        help_text="نام کاربری یا لینک، مثال: cusin_gallery یا https://t.me/cusin_gallery",
    )
    instagram = models.CharField(
        "اینستاگرام", max_length=80, blank=True, default="",
        help_text="نام کاربری یا لینک صفحهٔ اینستاگرام",
    )
    eitaa = models.CharField(
        "ایتا", max_length=120, blank=True, default="",
        help_text="نام کانال/صفحه یا لینک کامل ایتا، مثال: cusin_gallery",
    )
    bale = models.CharField(
        "بله", max_length=120, blank=True, default="",
        help_text="نام کانال/صفحه یا لینک کامل بله، مثال: cusin_gallery",
    )
    address = models.TextField("نشانی فروشگاه", blank=True, default="")
    working_hours = models.CharField("ساعات پاسخگویی", max_length=120, blank=True, default="")
    footer_quick_links_title = models.CharField(
        "عنوان ستون دسترسی سریع", max_length=120, blank=True, default="دسترسی سریع",
    )
    footer_help_links_title = models.CharField(
        "عنوان ستون راهنما و قوانین", max_length=120, blank=True, default="راهنما و قوانین",
    )
    footer_trust_title = models.CharField(
        "عنوان ستون نمادها", max_length=120, blank=True, default="نمادها و مجوزها",
    )
    copyright_text = models.CharField(
        "متن کپی‌رایت", max_length=200, blank=True, default="",
        help_text="مثال: © ۱۴۰۵ کازین گالری. خالی = «© سال جاری نام سایت» به‌صورت خودکار.",
    )
    enamad_html = models.TextField(
        "کد نماد اعتماد (e-namad)", blank=True, default="",
        help_text="اسنیپت embed را از پنل enamad.ir کپی و اینجا ذخیره کنید. برای "
        "امنیت، فقط تگ‌های مجاز (a، img، div و متن) نگه داشته می‌شوند و اسکریپت "
        "حذف می‌شود. خالی = نمایش جای خالی علامت‌گذاری‌شده.",
    )

    # --- دریافت حضوری --------------------------------------------------
    pickup_address = models.TextField(
        "نشانی دریافت حضوری", blank=True, default="",
        help_text="اگر مشتری «دریافت حضوری» را انتخاب کند، این نشانی در مرحلهٔ "
        "تکمیل خرید و در فاکتور به او نشان داده می‌شود.",
    )
    pickup_hours = models.CharField("ساعات دریافت حضوری", max_length=120, blank=True, default="")

    # --- ارسال و تحویل --------------------------------------------------
    shipping_standard_enabled = models.BooleanField(
        "ارسال عادی فعال باشد", default=True,
        help_text="امکان انتخاب ارسال عادی برای مشتریان در سراسر ایران.",
    )
    shipping_standard_cost = models.PositiveIntegerField(
        "هزینهٔ ارسال عادی (تومان)", default=50000, blank=True,
        help_text="هزینه به تومان برای سفارش‌هایی که به سقف ارسال رایگان نرسیده‌اند.",
    )
    shipping_standard_min_days = models.PositiveIntegerField(
        "حداقل روز تحویل عادی", default=3, blank=True,
        help_text="حداقل تعداد روز تقویمی برای تحویل سفارش عادی.",
    )
    shipping_standard_max_days = models.PositiveIntegerField(
        "حداکثر روز تحویل عادی", default=5, blank=True,
        help_text="حداکثر تعداد روز تقویمی برای تحویل سفارش عادی.",
    )
    shipping_standard_description = models.CharField(
        "توضیحات ارسال عادی", max_length=255, blank=True, default="",
        help_text="توضیح اختیاری که در مرحلهٔ انتخاب روش تحویل نمایش داده می‌شود.",
    )
    shipping_free_threshold = models.PositiveIntegerField(
        "سقف ارسال رایگان (تومان)", null=True, blank=True, default=1000000,
        help_text="مبلغ سبد خرید به تومان که بالاتر از آن ارسال عادی رایگان می‌شود. خالی = بدون ارسال رایگان.",
    )

    shipping_express_enabled = models.BooleanField(
        "ارسال اکسپرس فعال باشد", default=True,
        help_text="امکان انتخاب ارسال سریع/اکسپرس برای شهرهای مجاز.",
    )
    shipping_express_cost = models.PositiveIntegerField(
        "هزینهٔ ارسال اکسپرس (تومان)", default=90000, blank=True,
        help_text="هزینهٔ ثابت به تومان برای ارسال اکسپرس.",
    )
    shipping_express_min_days = models.PositiveIntegerField(
        "حداقل روز تحویل اکسپرس", default=1, blank=True,
        help_text="حداقل تعداد روز برای ارسال اکسپرس.",
    )
    shipping_express_max_days = models.PositiveIntegerField(
        "حداکثر روز تحویل اکسپرس", default=1, blank=True,
        help_text="حداکثر تعداد روز برای ارسال اکسپرس.",
    )
    shipping_express_description = models.CharField(
        "توضیحات ارسال اکسپرس", max_length=255, blank=True, default="",
        help_text="توضیح اختیاری برای ارسال اکسپرس در مرحلهٔ تحویل.",
    )
    shipping_express_cities = models.TextField(
        "شهرهای مجاز ارسال اکسپرس", blank=True, default="تهران",
        help_text="نام شهرهای مجاز برای ارسال اکسپرس (هر شهر در یک خط یا با ویرگول جدا شود). پیش‌فرض: تهران.",
    )

    shipping_pickup_enabled = models.BooleanField(
        "دریافت حضوری فعال باشد", default=True,
        help_text="امکان انتخاب تحویل حضوری سفارش در محل فروشگاه.",
    )
    shipping_pickup_description = models.CharField(
        "توضیحات دریافت حضوری", max_length=255, blank=True, default="",
        help_text="توضیح کوتاه دریافت حضوری برای نمایش در مرحلهٔ تحویل.",
    )

    # --- دکمه‌های شناور تماس --------------------------------------------
    floating_enabled = models.BooleanField(
        "نمایش دکمه‌های شناور", default=True,
        help_text="با برداشتن این تیک، همهٔ دکمه‌های شناور تماس پنهان می‌شوند.",
    )
    floating_whatsapp = models.BooleanField(
        "نمایش واتس‌اپ", default=True,
        help_text="فقط وقتی شمارهٔ واتس‌اپ در بخش فوتر پر شده باشد.",
    )
    floating_telegram = models.BooleanField(
        "نمایش تلگرام", default=True,
        help_text="فقط وقتی تلگرام در بخش فوتر پر شده باشد.",
    )
    floating_phone = models.BooleanField(
        "نمایش تماس تلفنی", default=True,
        help_text="فقط وقتی تلفن پشتیبانی پر شده باشد.",
    )
    floating_instagram = models.BooleanField(
        "نمایش اینستاگرام", default=False,
        help_text="فقط وقتی اینستاگرام در بخش فوتر پر شده باشد.",
    )

    # --- ظاهر سایت (تم) ------------------------------------------------
    # A preset is a complete palette; each color below is an OPTIONAL
    # override (blank = inherit the preset). The admin form refuses a
    # palette whose text/background pairs fail WCAG AA (see theme.py).
    theme_preset = models.CharField(
        "تم آماده", max_length=30, choices=THEME_PRESET_CHOICES,
        default=DEFAULT_PRESET,
        help_text="پالت پایه. رنگ‌های سفارشی پایین، هر کدام که پر شوند، "
        "مقدار همان رنگ را در تم آماده بازنویسی می‌کنند.",
    )
    theme_primary = models.CharField(
        "رنگ اصلی", max_length=7, blank=True, default="",
        validators=[validate_hex_color],
        help_text="خالی = رنگ اصلی تم آماده (مثال: #637037).",
    )
    theme_accent = models.CharField(
        "رنگ تأکیدی (طلایی)", max_length=7, blank=True, default="",
        validators=[validate_hex_color],
        help_text="خالی = رنگ تأکیدی تم آماده (مثال: #CEB464).",
    )
    theme_background = models.CharField(
        "رنگ پس‌زمینه", max_length=7, blank=True, default="",
        validators=[validate_hex_color],
        help_text="خالی = پس‌زمینهٔ تم آماده (مثال: #FAF7F0).",
    )
    theme_text = models.CharField(
        "رنگ متن", max_length=7, blank=True, default="",
        validators=[validate_hex_color],
        help_text="خالی = رنگ متن تم آماده (مثال: #1E2412).",
    )
    theme_header_background = models.CharField(
        "پس‌زمینهٔ هدر", max_length=7, blank=True, default="",
        validators=[validate_hex_color],
        help_text="خالی = پس‌زمینهٔ هدر تم آماده (مثال: #FFFFFF).",
    )
    theme_header_text = models.CharField(
        "متن هدر", max_length=7, blank=True, default="",
        validators=[validate_hex_color],
        help_text="خالی = متن هدر تم آماده (مثال: #1E2412).",
    )
    theme_button_text = models.CharField(
        "متن دکمه", max_length=7, blank=True, default="",
        validators=[validate_hex_color],
        help_text="رنگ نوشتهٔ روی دکمه‌های اصلی (مثال: #FFFFFF).",
    )
    theme_button_radius = models.CharField(
        "گردی گوشهٔ دکمه‌ها", max_length=10, choices=BUTTON_RADIUS_CHOICES,
        default=DEFAULT_BUTTON_RADIUS,
    )
    theme_base_font_size = models.CharField(
        "اندازهٔ متن پایه", max_length=10, choices=BASE_FONT_SIZE_CHOICES,
        default=DEFAULT_BASE_FONT_SIZE,
    )
    theme_card_shadow = models.CharField(
        "سایهٔ کارت‌ها", max_length=10, choices=CARD_SHADOW_CHOICES,
        default=DEFAULT_CARD_SHADOW,
    )

    class Meta:
        verbose_name = "محتوا و ظاهر سایت"
        verbose_name_plural = "محتوا و ظاهر سایت"

    def save(self, *args, **kwargs):
        # Singleton enforcement at the model level: every save targets
        # the one and only row.
        self.pk = 1
        if self.created_at is None:
            # A brand-new instance saving onto the existing singleton row
            # makes Django's save() try an UPDATE first -- and the UPDATE
            # value list would carry created_at=None (auto_now_add only
            # fills on INSERT), violating NOT NULL. Carry the real
            # created_at over so the update is sane; when no row exists
            # yet, auto_now_add fills it on the INSERT path.
            existing_created_at = (
                type(self)
                .objects.filter(pk=1)
                .values_list("created_at", flat=True)
                .first()
            )
            if existing_created_at is not None:
                self.created_at = existing_created_at
        super().save(*args, **kwargs)

    # --- placeholder-aware accessors ---------------------------------
    # A seeded «+98 21 0000 0000» or «[نشانی واقعی فروشگاه …]» is NOT
    # content: it is an instruction to the owner. Everything that shows or
    # checks these fields goes through apps/core/placeholders.py so the
    # storefront can never render a bracketed sentence and the readiness
    # card can never call a sample value "complete".

    def display(self, field: str) -> str:
        """The value for DISPLAY: "" when the stored value is a placeholder."""
        from .placeholders import clean_value

        return clean_value(getattr(self, field, None))

    def is_set(self, field: str) -> bool:
        """True when the field holds real content."""
        return bool(self.display(field))

    def missing_items(self) -> list:
        """[{field, label, value, required, reason}] -- what is still to do."""
        from .placeholders import missing_site_items

        return missing_site_items(self)

    def clean(self):
        super().clean()
        from django.core.exceptions import ValidationError

        errors = {}
        if self.shipping_standard_min_days is not None and self.shipping_standard_max_days is not None:
            if self.shipping_standard_min_days > self.shipping_standard_max_days:
                errors["shipping_standard_min_days"] = "حداقل روز تحویل عادی نمی‌تواند بیشتر از حداکثر روز تحویل باشد."

        if self.shipping_express_min_days is not None and self.shipping_express_max_days is not None:
            if self.shipping_express_min_days > self.shipping_express_max_days:
                errors["shipping_express_min_days"] = "حداقل روز تحویل اکسپرس نمی‌تواند بیشتر از حداکثر روز تحویل باشد."

        if (
            not self.shipping_standard_enabled
            and not self.shipping_express_enabled
            and not getattr(self, "shipping_pickup_enabled", True)
        ):
            errors["shipping_standard_enabled"] = "حداقل یکی از روش‌های ارسال باید فعال باشد."

        if self.shipping_express_enabled and not (self.shipping_express_cities or "").strip():
            errors["shipping_express_cities"] = "لطفاً حداقل یک شهر مجاز برای ارسال اکسپرس مشخص کنید."

        if errors:
            raise ValidationError(errors)

    @classmethod
    def load(cls) -> "SiteSettings":
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def display_name(self) -> str:
        """The shop name for printed documents.

        The owner's own value when they set one, otherwise the fixed brand
        name -- a document must never print an empty letterhead, and a
        PLACEHOLDER shop name (the seeded bracketed instruction) is worse
        than no name at all, so it falls back too.
        """
        from apps.core.placeholders import is_placeholder

        from .seo import SITE_NAME

        for candidate in (self.shop_name, self.site_name):
            name = (candidate or "").strip()
            if name and not is_placeholder(name):
                return name
        return SITE_NAME

    def __str__(self):
        return "محتوا و ظاهر سایت"


class TrustStripItem(TimeStampedModel):
    """One item of the home page's trust strip.

    A separate, orderable model (rather than five hard-coded pairs of
    fields) because the owner asked to reorder the five items and hide an
    individual one without deleting its text: ``is_active=False`` keeps
    the wording for later while the storefront omits it.
    """

    site = models.ForeignKey(
        SiteSettings, on_delete=models.CASCADE, related_name="trust_items",
        verbose_name="تنظیمات سایت", blank=True, null=True,
    )
    label = models.CharField("متن", max_length=200)
    icon = models.CharField(
        "آیکون", max_length=40, choices=TRUST_ICON_CHOICES, default="shield-check",
        help_text="از میان آیکون‌های موجود فروشگاه انتخاب کنید.",
    )
    ordering = models.PositiveIntegerField(
        "ترتیب نمایش", default=0, help_text="عدد کوچک‌تر زودتر نمایش داده می‌شود.",
    )
    is_active = models.BooleanField(
        "نمایش داده شود", default=True,
        help_text="برای پنهان‌کردن موقت یک مورد، تیک را بردارید (متن حفظ می‌شود).",
    )

    class Meta:
        verbose_name = "مورد نوار اعتماد"
        verbose_name_plural = "موارد نوار اعتماد"
        ordering = ["ordering", "pk"]

    def __str__(self):
        return self.label


class InfoPage(TimeStampedModel):
    """One of the five owner-editable info/trust pages.

    ``slug`` is a closed choice list: the URL of each page is part of the
    public route table (backend/apps/core/spa.py and frontend/src/App.jsx),
    so the owner edits the content and title, never the address. The body
    is rich HTML, sanitised on save (apps/core/sanitize.py) and again when
    served, so a pasted ``<script>``/``on*`` attribute can never reach the
    storefront.
    """

    slug = models.SlugField(
        "صفحه", max_length=40, choices=INFO_PAGE_SLUGS, unique=True,
        help_text="هر صفحه یک نشانی ثابت دارد؛ فقط محتوای آن قابل ویرایش است.",
    )
    title = models.CharField("عنوان صفحه", max_length=150)
    body = models.TextField(
        "متن صفحه", blank=True, default="",
        help_text="متن اصلی صفحه. با دکمه‌های بالای کادر می‌توانید متن را "
        "پررنگ/مورب/عنوان‌دار/فهرست یا پیوند کنید.",
    )
    seo_title = models.CharField(
        "عنوان سئو", max_length=150, blank=True, default="",
        help_text="عنوان تب مرورگر و نتیجهٔ جستجو. خالی = عنوان صفحه.",
    )
    seo_description = models.CharField(
        "توضیحات سئو", max_length=300, blank=True, default="",
        help_text="توضیح کوتاه زیر عنوان در نتایج جستجو (حدود ۱۵۰ نویسه).",
    )
    is_published = models.BooleanField(
        "منتشر شده", default=True,
        help_text="اگر تیک برداشته شود، این صفحه در فروشگاه نمایش داده نمی‌شود و "
        "نشانی آن پاسخ ۴۰۴ می‌دهد.",
    )
    ordering = models.PositiveIntegerField(
        "ترتیب نمایش", default=0, help_text="برای مرتب‌سازی فهرست صفحات.",
    )

    class Meta:
        verbose_name = "صفحهٔ اطلاعاتی"
        verbose_name_plural = "صفحات اطلاعاتی"
        ordering = ["ordering", "pk"]

    def __str__(self):
        return self.title

    @property
    def path(self) -> str:
        return f"/{self.slug}/"

