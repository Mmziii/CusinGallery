"""
Accounts admin registration.

Registers User with a small extension of Django's built-in UserAdmin --
surfacing `phone` (Phase 2) and making it searchable (Phase 3) -- and
registers Address. Passwords are never exposed: DjangoUserAdmin already
renders the password field as a one-way hash display
(ReadOnlyPasswordHashField), inherited here unmodified.
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import Address, User


class UserAdmin(DjangoUserAdmin):
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("Contact", {"fields": ("phone",)}),
    )
    list_display = DjangoUserAdmin.list_display + ("phone",)
    search_fields = DjangoUserAdmin.search_fields + ("phone",)


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ("recipient_name", "user", "city", "province", "is_default", "created_at")
    list_filter = ("is_default", "province")
    search_fields = ("recipient_name", "phone", "city", "postal_code", "user__username", "user__email")
    autocomplete_fields = ("user",)


admin.site.register(User, UserAdmin)
