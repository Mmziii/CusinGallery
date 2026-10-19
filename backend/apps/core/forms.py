"""Admin forms for the owner-editable site content and theme.

Two responsibilities live here, both are safety rails rather than UI:

* every rich-text/embed field is sanitised BEFORE it is stored, so no
  ``<script>``/``on*``/``javascript:`` value can ever reach the storefront;
* the theme form refuses palettes that fail the WCAG AA contrast guard,
  with a Persian message naming the exact pair (text/background, button,
  header). The check reads the EFFECTIVE colors, i.e. blank overrides are
  filled from the selected preset first.
"""
from __future__ import annotations

from django import forms
from django.core.exceptions import ValidationError

from .models import InfoPage, SiteSettings
from .sanitize import sanitize_embed, sanitize_html
from .theme import COLOR_FIELDS, contrast_issues, is_hex_color, normalize_hex


class SiteSettingsAdminForm(forms.ModelForm):
    class Meta:
        model = SiteSettings
        fields = "__all__"

    def clean_enamad_html(self):
        # Trust-seal embed: links/images allowed, scripts and event handlers
        # are stripped. Rendered with dangerouslySetInnerHTML on the site.
        return sanitize_embed(self.cleaned_data.get("enamad_html") or "")

    def clean(self):
        cleaned = super().clean()

        # Normalise #abc -> #aabbcc so stored values are consistent.
        for field in COLOR_FIELDS:
            if field not in cleaned:
                continue
            raw = (cleaned.get(field) or "").strip()
            if not raw:
                cleaned[field] = ""
                continue
            if not is_hex_color(raw):
                self.add_error(
                    field,
                    "رنگ را به شکل کد شش‌رقمی وارد کنید؛ مثال: #637037.",
                )
                continue
            cleaned[field] = normalize_hex(raw)

        # WCAG contrast guard. Runs only when the form really carries the
        # theme fields (it always does on the site settings page; the guard
        # is skipped for any future form that reuses this class without
        # them instead of crashing on an unknown field).
        if not any(field in self.fields for field in COLOR_FIELDS):
            return cleaned
        if self.errors:
            # Don't pile contrast errors on top of a malformed color: the
            # owner first needs to fix the value they typed.
            return cleaned
        issues = contrast_issues(cleaned)
        field_for_issue = {
            "text_on_background": "theme_text",
            "button_text_on_primary": "theme_button_text",
            "header_text_on_header_background": "theme_header_text",
        }
        for issue in issues:
            field = field_for_issue.get(issue["key"])
            self.add_error(field if field in self.fields else None, issue["message"])
        return cleaned


class InfoPageAdminForm(forms.ModelForm):
    class Meta:
        model = InfoPage
        fields = "__all__"
        widgets = {
            "body": forms.Textarea(
                attrs={
                    "rows": 18,
                    "class": "vLargeTextField cusin-rich-text",
                    "data-cusin-rich-text": "1",
                    "dir": "rtl",
                }
            ),
            "seo_description": forms.Textarea(attrs={"rows": 3}),
        }

    def clean_body(self):
        return sanitize_html(self.cleaned_data.get("body") or "")

    def clean(self):
        cleaned = super().clean()
        # An empty SEO title is allowed (the storefront falls back to the
        # page title); an empty body is allowed too (the owner may be
        # drafting), but publishing an empty page is almost always a slip.
        if cleaned.get("is_published") and not (cleaned.get("body") or "").strip():
            raise ValidationError(
                "صفحهٔ منتشرشده نمی‌تواند متن خالی داشته باشد؛ متن را وارد کنید یا "
                "تیک «منتشر شده» را بردارید."
            )
        return cleaned
