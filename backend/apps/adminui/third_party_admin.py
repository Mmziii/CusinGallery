"""Persian fieldset titles for the django-otp admins (follow-up 3, item 4).

django-otp ships its ModelAdmins with English fieldset titles ("Identity",
"Timestamps") and no translations. The project's Persian admin must not show
them, so these two admins are re-registered with a subclass that maps the
titles. Only the titles change: fields, permissions, inlines and querysets
are the plugin's own. Registration runs from AdminuiConfig.ready(), which
comes after django.contrib.admin's autodiscover, so the plugin admins already
exist and are replaced exactly once.
"""
from django.contrib import admin
from django_otp.plugins.otp_static.admin import StaticDeviceAdmin
from django_otp.plugins.otp_static.models import StaticDevice
from django_otp.plugins.otp_totp.admin import TOTPDeviceAdmin
from django_otp.plugins.otp_totp.models import TOTPDevice

FIELDSET_TITLES = {
    "Identity": "هویت",
    "Timestamps": "زمان‌ها",
    "Configuration": "پیکربندی",
    "State": "وضعیت",
    "Throttling": "محدودیت تلاش",
}


def translate_fieldsets(fieldsets):
    return [
        (FIELDSET_TITLES.get(title, title), options) for title, options in fieldsets
    ]


class PersianFieldsetTitlesMixin:
    def get_fieldsets(self, request, obj=None):
        return translate_fieldsets(super().get_fieldsets(request, obj))


class PersianStaticDeviceAdmin(PersianFieldsetTitlesMixin, StaticDeviceAdmin):
    # the class attribute is translated too, not only get_fieldsets()
    fieldsets = translate_fieldsets(StaticDeviceAdmin.fieldsets)


class PersianTOTPDeviceAdmin(PersianFieldsetTitlesMixin, TOTPDeviceAdmin):
    pass


def register_persian_otp_admins():
    for model, admin_class in (
        (StaticDevice, PersianStaticDeviceAdmin),
        (TOTPDevice, PersianTOTPDeviceAdmin),
    ):
        if model in admin.site._registry:
            admin.site.unregister(model)
        admin.site.register(model, admin_class)
