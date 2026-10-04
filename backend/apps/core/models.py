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


class SiteSettings(TimeStampedModel):
    """
    Store-wide contact/branding settings (Part 1) -- a SINGLETON: there
    is exactly one row (pk forced to 1), edited in admin under
    «تنظیمات فروشگاه» and read by the footer, contact page, pickup
    info, invoices and the floating contact button.

    Kept out of .env on purpose: these are business content the owner
    changes from the admin UI, not deployment configuration.
    """

    phone = models.CharField("تلفن پشتیبانی", max_length=40, blank=True, default="")
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
    address = models.TextField("نشانی فروشگاه", blank=True, default="")
    working_hours = models.CharField("ساعات پاسخگویی", max_length=120, blank=True, default="")
    pickup_address = models.TextField(
        "نشانی دریافت حضوری", blank=True, default="",
        help_text="برای روش ارسال «حضوری» در checkout و فاکتور نمایش داده می‌شود.",
    )
    pickup_hours = models.CharField("ساعات دریافت حضوری", max_length=120, blank=True, default="")
    enamad_html = models.TextField(
        "کد نماد اعتماد (e-namad)", blank=True, default="",
        help_text="اسنیپت embed را از پنل enamad.ir کپی و اینجا ذخیره کنید؛ عیناً در "
        "فوتر رندر می‌شود. خالی = نمایش جای خالی علامت‌گذاری‌شده.",
    )

    class Meta:
        verbose_name = "تنظیمات فروشگاه"
        verbose_name_plural = "تنظیمات فروشگاه"

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

    @classmethod
    def load(cls) -> "SiteSettings":
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return "تنظیمات فروشگاه"
