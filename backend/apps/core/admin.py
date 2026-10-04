# Core exposes only abstract base models (see models.py), so there is
# nothing concrete to register with the admin site from this app itself.
#
# This module IS imported by Django's admin autodiscovery (core is an
# installed app), which makes it the single reliable place to brand the
# admin site for the Persian-speaking shop owner (Phase B).
from django.contrib import admin

admin.site.site_header = "مدیریت کازین گالری"
admin.site.site_title = "کازین گالری"
admin.site.index_title = "داشبورد مدیریت فروشگاه"


from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from .models import SiteSettings


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    """Singleton admin: the changelist redirects straight to the one
    settings row; a second row cannot be added."""

    fieldsets = (
        (_("تماس"), {"fields": ("phone", "whatsapp", "telegram", "instagram",
                                "address", "working_hours")}),
        (_("دریافت حضوری"), {"fields": ("pickup_address", "pickup_hours")}),
        (_("نمادها"), {"fields": ("enamad_html",)}),
    )

    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

    def changelist_view(self, request, extra_context=None):
        from django.shortcuts import redirect

        obj = SiteSettings.load()
        return redirect(reverse("admin:core_sitesettings_change", args=(obj.pk,)))
