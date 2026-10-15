"""Admin-only helpers shared by changelist forms and image-owning admins."""

from django import forms
from django.contrib import admin


class NumericChangelistAdminMixin:
    """Keep numeric ``list_editable`` controls legible in RTL admin pages.

    Django's changelist formset factory creates another ModelForm from the
    class returned by ``get_changelist_form``. Apply the widget attributes to
    that final form as well so they reach the rendered inline-edit controls.
    """

    @staticmethod
    def _mark_numeric_widgets(form):
        for field in form.base_fields.values():
            if isinstance(field.widget, forms.NumberInput):
                field.widget.attrs.update({"dir": "ltr", "inputmode": "numeric"})
        return form

    def get_changelist_form(self, request, **kwargs):
        form = super().get_changelist_form(request, **kwargs)
        return self._mark_numeric_widgets(form)

    def get_changelist_formset(self, request, **kwargs):
        formset = super().get_changelist_formset(request, **kwargs)
        self._mark_numeric_widgets(formset.form)
        return formset


class AutoWebpVariantsMixin:
    """Presents the generated ``webp_400/800/1200`` columns read-only.

    Those three fields are a CACHE: ``save()`` re-encodes the uploaded
    image and fills them in, and nothing else should ever write them.
    Left in the form they showed up as «Webp 400» / «Webp 800» / «Webp
    1200» -- English, unexplained, and inviting the owner to type a path
    the next save overwrites.

    Subclasses declare:
      * ``image_field``  -- the upload field the variants come from;
      * ``image_help``   -- the recommended size, shown as that field's
        help text (without it the owner uploads a 4000-pixel photo);
      * ``fieldsets``    -- including the three ``*_readonly`` methods.
    """

    image_field = "image"
    image_help = ""

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj, change=change, **kwargs)
        if self.image_help and self.image_field in form.base_fields:
            form.base_fields[self.image_field].help_text = self.image_help
        return form

    @staticmethod
    def _variant(value):
        return value or "—"

    @admin.display(description="نسخهٔ WebP پهنای ۴۰۰ پیکسل")
    def webp_400_readonly(self, obj):
        return self._variant(obj.webp_400)

    @admin.display(description="نسخهٔ WebP پهنای ۸۰۰ پیکسل")
    def webp_800_readonly(self, obj):
        return self._variant(obj.webp_800)

    @admin.display(description="نسخهٔ WebP پهنای ۱۲۰۰ پیکسل")
    def webp_1200_readonly(self, obj):
        return self._variant(obj.webp_1200)
