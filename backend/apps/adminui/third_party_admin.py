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


MODEL_NAMES = {
    StaticDevice: ("کد پشتیبان", "کدهای پشتیبان"),
    TOTPDevice: ("دستگاه کد یک‌بارمصرف", "دستگاه‌های کد یک‌بارمصرف"),
}

#: Field labels the plugin ships in English («Created at»، «Last used at»).
FIELD_LABELS = {
    "created_at": "تاریخ ایجاد",
    "last_used_at": "آخرین استفاده",
    "throttling_failure_timestamp": "زمان آخرین تلاش ناموفق",
    "throttling_failure_count": "شمار تلاش‌های ناموفق",
}


def relabel_otp_models() -> None:
    """Rename the models themselves («TOTP devices» -> Persian).

    The plugin's models declare no verbose_name, so Django falls back to
    the class names. Patching ``_meta`` is deliberate: it changes what the
    admin PRINTS only -- there is no migration, no field and no query
    involved, and a third-party model cannot be given a Persian
    ``verbose_name`` any other way without forking the package.
    """
    for model, (singular, plural) in MODEL_NAMES.items():
        model._meta.verbose_name = singular
        model._meta.verbose_name_plural = plural
        for field in model._meta.fields:
            label = FIELD_LABELS.get(field.name)
            if label:
                field.verbose_name = label


def register_persian_otp_admins():
    for model, admin_class in (
        (StaticDevice, PersianStaticDeviceAdmin),
        (TOTPDevice, PersianTOTPDeviceAdmin),
    ):
        if model in admin.site._registry:
            admin.site.unregister(model)
        admin.site.register(model, admin_class)
    relabel_otp_models()
