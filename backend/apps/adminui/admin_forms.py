"""Admin-only helpers shared by changelist forms."""

from django import forms


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
