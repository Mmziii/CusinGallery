# Core admin: the owner-editable site content ("محتوا و ظاهر سایت") and the
# five info pages. This module is imported by Django's admin autodiscovery
# (core is an installed app), which also makes it the single reliable place
# to brand the admin site for the Persian-speaking shop owner (Phase B).
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseNotAllowed, HttpResponseRedirect
from django.urls import path, reverse
from django.utils.translation import gettext_lazy as _

from apps.adminui.admin_dates import jalali_column

from .forms import InfoPageAdminForm, SiteSettingsAdminForm
from .models import INFO_PAGE_SLUGS, InfoPage, SiteSettings, TrustStripItem
from .theme import COLOR_FIELDS, THEME_PRESETS, theme_defaults

admin.site.site_header = "مدیریت کازین گالری"
admin.site.site_title = "کازین گالری"
admin.site.index_title = "داشبورد مدیریت فروشگاه"


class TrustStripItemInline(admin.TabularInline):
    """The five home-page benefits: text + icon + order + hide."""

    model = TrustStripItem
    fk_name = "site"
    extra = 1
    max_num = 8
    fields = ("ordering", "label", "icon", "is_active")
    ordering = ("ordering", "pk")
    verbose_name = "مورد نوار اعتماد"
    verbose_name_plural = "نوار اعتماد صفحهٔ اصلی (ترتیب و نمایش)"


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    """Singleton admin: the changelist redirects straight to the one
    content row; a second row cannot be added."""

    form = SiteSettingsAdminForm
    inlines = [TrustStripItemInline]
    change_form_template = "admin/core/sitesettings/change_form.html"
    save_on_top = True

    fieldsets = (
        (
            _("برند و هویت"),
            {
                "fields": (
                    "site_name", "tagline", "shop_name",
                    "logo_light", "logo_dark", "favicon",
                ),
                "description": "نام و نشان فروشگاه که در هدر، فوتر و عنوان "
                "صفحات نمایش داده می‌شود.",
            },
        ),
        (
            _("صفحهٔ اصلی"),
            {
                "fields": (
                    "home_heading",
                    "hero_title", "hero_subtitle", "hero_button_text", "hero_button_link",
                    "section_categories_title", "section_deals_title",
                    "section_featured_title", "section_new_title",
                    "section_best_title", "section_reviews_title",
                    "story_title", "story_text",
                ),
                "description": "متن بنر پیش‌فرض فقط وقتی هیچ بنر فعالی در بخش "
                "«بنرها» وجود نداشته باشد دیده می‌شود.",
            },
        ),
        (
            _("فوتر و راه‌های ارتباطی"),
            {
                "fields": (
                    "footer_about",
                    "phone", "extra_phones", "email",
                    "whatsapp", "telegram", "instagram", "eitaa", "bale",
                    "address", "working_hours",
                    "footer_quick_links_title", "footer_help_links_title",
                    "footer_trust_title",
                    "copyright_text", "enamad_html",
                ),
            },
        ),
        (
            _("دکمه‌های شناور تماس"),
            {
                "fields": (
                    "floating_enabled", "floating_whatsapp", "floating_telegram",
                    "floating_phone", "floating_instagram",
                ),
                "description": "هر دکمه فقط وقتی نمایش داده می‌شود که شماره یا "
                "نشانی همان شبکه در بخش فوتر پر شده باشد.",
            },
        ),
        (
            _("ظاهر سایت (تم)"),
            {
                "fields": (
                    "theme_preset",
                    "theme_primary", "theme_accent", "theme_background",
                    "theme_text", "theme_header_background", "theme_header_text",
                    "theme_button_text",
                    "theme_button_radius", "theme_base_font_size", "theme_card_shadow",
                ),
                "description": "تم آماده را انتخاب کنید و در صورت نیاز رنگ‌ها را "
                "بازنویسی کنید. پیش‌نمایش پایین همین صفحه تغییرات را نشان می‌دهد. "
                "اگر کنتراست متن و پس‌زمینه کمتر از ۴٫۵ به ۱ باشد، ذخیره انجام "
                "نمی‌شود.",
            },
        ),
        (
            _("ارسال و تحویل"),
            {
                "fields": (
                    "shipping_standard_enabled",
                    "shipping_standard_cost",
                    "shipping_standard_min_days",
                    "shipping_standard_max_days",
                    "shipping_standard_description",
                    "shipping_free_threshold",
                    "shipping_express_enabled",
                    "shipping_express_cost",
                    "shipping_express_min_days",
                    "shipping_express_max_days",
                    "shipping_express_description",
                    "shipping_express_cities",
                    "shipping_pickup_enabled",
                    "shipping_pickup_description",
                ),
                "description": "هزینه‌ها، زمان‌بندی و شهرهای مجاز برای روش‌های ارسال سفارش.",
            },
        ),
        (
            _("دریافت حضوری"),
            {
                "fields": ("pickup_address", "pickup_hours"),
                "classes": ("collapse",),
                "description": "این نشانی فقط به مشتریانی نشان داده می‌شود که "
                "«دریافت حضوری» را انتخاب کرده‌اند.",
            },
        ),
    )

    @property
    def media(self):
        """The stock admin media (jQuery, core.js, …) PLUS the preview.

        Replacing ModelAdmin.media dropped `admin/js/vendor/jquery/jquery.js`
        and `admin/js/jquery.init.js`, which left `django.jQuery` undefined
        for the prepopulate script the change form always renders (and for
        every stock widget). `super().media + …` keeps the stock order.
        """
        from django import forms

        return super().media + forms.Media(js=("admin_theme/js/theme_preview.js",))

    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        # The row is the singleton every page reads: deleting it would wipe
        # the whole storefront content/theme. Trust-strip items are removed
        # inside the inline, never by deleting the settings row.
        return False

    def changelist_view(self, request, extra_context=None):
        from django.shortcuts import redirect

        obj = SiteSettings.load()
        return redirect(reverse("admin:core_sitesettings_change", args=(obj.pk,)))

    # ------------------------------------------------------------------
    # Context for the live preview / reset button.
    # ------------------------------------------------------------------
    def render_change_form(self, request, context, *args, **kwargs):
        context["cusin_theme_presets"] = THEME_PRESETS
        context["cusin_theme_default_preset"] = "olive_gold"
        context["cusin_theme_reset_url"] = reverse(
            "admin:core_sitesettings_reset_theme"
        )
        return super().render_change_form(request, context, *args, **kwargs)

    # ------------------------------------------------------------------
    # «بازگشت به تنظیمات پیش‌فرض» (POST only, admin permission + CSRF).
    # ------------------------------------------------------------------
    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "reset-theme/",
                self.admin_site.admin_view(self.reset_theme_view),
                name="core_sitesettings_reset_theme",
            ),
        ]
        return custom + urls

    def reset_theme_view(self, request):
        if not self.has_change_permission(request):
            raise PermissionDenied
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])

        obj = SiteSettings.load()
        defaults = theme_defaults()
        for field in COLOR_FIELDS:
            if hasattr(obj, field):
                setattr(obj, field, defaults.get(field, ""))
        for field in (
            "theme_preset",
            "theme_button_radius",
            "theme_base_font_size",
            "theme_card_shadow",
        ):
            if hasattr(obj, field):
                setattr(obj, field, defaults[field])
        obj.save()

        self.message_user(
            request,
            "ظاهر فروشگاه به تنظیمات پیش‌فرض «زیتونی و طلایی» بازگشت.",
            messages.SUCCESS,
        )
        return HttpResponseRedirect(
            reverse("admin:core_sitesettings_change", args=(obj.pk,))
        )


@admin.register(InfoPage)
class InfoPageAdmin(admin.ModelAdmin):
    """«صفحات اطلاعاتی»: the owner edits the five trust/legal pages."""

    form = InfoPageAdminForm
    list_display = (
        "title",
        "slug_label",
        "is_published",
        "ordering",
        jalali_column("updated_at", "آخرین به‌روزرسانی", with_time=True),
    )
    list_editable = ("is_published", "ordering")
    list_filter = ("is_published",)
    search_fields = ("title", "body", "seo_title", "seo_description")
    ordering = ("ordering", "pk")
    save_on_top = True
    fieldsets = (
        (
            _("محتوا"),
            {
                "fields": ("slug", "title", "body"),
                "description": "نشانی هر صفحه ثابت است؛ فقط محتوای آن ویرایش "
                "می‌شود. برای امنیت، اسکریپت و کدهای ناشناخته هنگام ذخیره حذف "
                "می‌شوند.",
            },
        ),
        (
            _("سئو (عنوان و توضیح در نتایج جستجو)"),
            {"fields": ("seo_title", "seo_description")},
        ),
        (
            _("انتشار"),
            {
                "fields": ("is_published", "ordering"),
                "description": "صفحهٔ منتشرنشده در فروشگاه دیده نمی‌شود و نشانی "
                "آن پاسخ ۴۰۴ می‌دهد.",
            },
        ),
    )

    @property
    def media(self):
        """Stock admin media (jQuery and friends) plus the toolbar.

        The base change form always renders `prepopulate_init.js`, which
        reads `django.jQuery`; overriding `media` without `super()` used to
        remove the jQuery bundle and threw «$ is not a function» on every
        info-page change form.
        """
        from django import forms

        return super().media + forms.Media(
            js=("admin_theme/js/rich_text.js",),
            css={"all": ("admin_theme/css/rich_text.css",)},
        )

    @admin.display(description="صفحه", ordering="slug")
    def slug_label(self, obj):
        labels = dict(INFO_PAGE_SLUGS)
        return labels.get(obj.slug, obj.slug)

    def has_add_permission(self, request):
        # The five fixed pages are seeded by the data migration; the admin
        # only adds one if a row was deliberately deleted.
        return InfoPage.objects.count() < len(INFO_PAGE_SLUGS)
