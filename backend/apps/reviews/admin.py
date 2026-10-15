"""
Reviews admin registration.

Includes bulk approve/reject actions -- this is data moderation (setting
a status field on selected rows), not the review business logic
(notifications, verified-purchase detection) that belongs to later
phases.
"""
from django.contrib import admin

from apps.adminui.admin_dates import jalali_column
from apps.adminui.templatetags.adminui_extras import to_fa_digits as fa_digits

from .models import Review


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = (
        "product", "user", "rating", "status", "is_verified_purchase",
        jalali_column("created_at", "تاریخ ثبت", with_time=True),
    )
    list_filter = ("status", "rating", "is_verified_purchase")
    search_fields = ("product__name", "user__username", "user__email", "title", "body")
    autocomplete_fields = ("product", "user")
    actions = ["approve_reviews", "reject_reviews"]

    @admin.action(description="تأیید نظرات انتخاب‌شده")
    def approve_reviews(self, request, queryset):
        updated = queryset.update(status=Review.Status.APPROVED)
        self.message_user(request, f"{fa_digits(updated)} نظر تأیید شد.")

    @admin.action(description="رد نظرات انتخاب‌شده")
    def reject_reviews(self, request, queryset):
        updated = queryset.update(status=Review.Status.REJECTED)
        self.message_user(request, f"{fa_digits(updated)} نظر رد شد.")
