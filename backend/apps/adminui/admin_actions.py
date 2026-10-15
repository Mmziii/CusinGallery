"""
Persian labels for Django's built-in admin actions (item 15).

Django's «delete_selected» is a SITE-wide action whose description is
``_("Delete selected %(verbose_name_plural)s")``. Django's Persian
translation of that sentence is broken: with ``verbose_name_plural``
``محصولات`` the product changelist offered

    «حذف  محصولات های انتخاب شده»

-- a double space where the placeholder was, and «های» glued onto a word
that is already plural («محصولات‌های»). It is not translatable correctly,
because Persian does not build a plural the way the English sentence
does, and the same verb phrase has to work for «سفارش‌ها» و «نظرات» و
«برندها» alike.

So the action is replaced with a single, plural-independent Persian
label that means the same thing for every model. The replacement
delegates to Django's own implementation -- confirmation page,
permissions, protected-relation handling and all -- so only the label
changes.
"""
from __future__ import annotations

from django.contrib import admin
from django.contrib.admin.actions import delete_selected as _django_delete_selected


def delete_selected_persian(modeladmin, request, queryset):
    """Same behaviour as Django's ``delete_selected``, Persian label."""
    return _django_delete_selected(modeladmin, request, queryset)


delete_selected_persian.allowed_permissions = ("delete",)
delete_selected_persian.short_description = "حذف موارد انتخاب‌شده"


def install_persian_admin_actions() -> None:
    """Replace the site-wide action, keeping its name.

    ``add_action`` overwrites an action registered under the same name, so
    the built-in English one is gone rather than duplicated.
    """
    admin.site.add_action(delete_selected_persian, "delete_selected")
