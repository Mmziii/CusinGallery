"""
Reviews admin registration.

Includes bulk approve/reject actions -- this is data moderation (setting
a status field on selected rows), not the review business logic
(notifications, verified-purchase detection) that belongs to later
phases.
"""
from django.contrib import admin

from .models import Review


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("product", "user", "rating", "status", "is_verified_purchase", "created_at")
    list_filter = ("status", "rating", "is_verified_purchase")
    search_fields = ("product__name", "user__username", "user__email", "title", "body")
    autocomplete_fields = ("product", "user")
    actions = ["approve_reviews", "reject_reviews"]

    @admin.action(description="Approve selected reviews")
    def approve_reviews(self, request, queryset):
        updated = queryset.update(status=Review.Status.APPROVED)
        self.message_user(request, f"{updated} review(s) approved.")

    @admin.action(description="Reject selected reviews")
    def reject_reviews(self, request, queryset):
        updated = queryset.update(status=Review.Status.REJECTED)
        self.message_user(request, f"{updated} review(s) rejected.")
