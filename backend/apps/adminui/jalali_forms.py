"""Jalali-aware form fields and widgets for every Django admin date input."""
from __future__ import annotations

import datetime as dt
import re

from django import forms
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from .jalali import fa_digits, format_jalali, jalali_to_gregorian

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_DATE_RE = re.compile(r"^(\d{3,4})[/-](\d{1,2})[/-](\d{1,2})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?)?$")


def _parse_components(value):
    normalized = str(value).strip().translate(_DIGITS)
    match = _DATE_RE.fullmatch(normalized)
    if not match:
        raise ValueError("invalid date format")
    year, month, day = map(int, match.group(1, 2, 3))
    hour, minute, second = match.group(4, 5, 6)
    if 1300 <= year <= 1599:
        date_value = jalali_to_gregorian(year, month, day)
    elif year >= 1700:
        date_value = dt.date(year, month, day)
    else:
        raise ValueError("تاریخ نامعتبر است")
    return date_value, int(hour or 0), int(minute or 0), int(second or 0), bool(match.group(4))


class _JalaliWidgetMixin:
    class Media:
        js = ("admin_theme/js/jalali_datepicker.js",)
        css = {"all": ("admin_theme/css/jalali_datepicker.css",)}

    def format_value(self, value):
        if not value:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, dt.datetime) and timezone.is_aware(value):
            value = timezone.localtime(value)
        date_text = format_jalali(value, persian_digits=True)
        if isinstance(value, dt.datetime):
            date_text += " " + fa_digits(value.strftime("%H:%M"))
        return date_text

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context["widget"]["attrs"]["data-jalali-date"] = "true"
        context["widget"]["attrs"].setdefault("autocomplete", "off")
        return context


class JalaliDateInput(_JalaliWidgetMixin, forms.TextInput):
    input_type = "text"

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context["widget"]["attrs"]["data-jalali-with-time"] = "false"
        return context


class JalaliDateTimeInput(_JalaliWidgetMixin, forms.TextInput):
    input_type = "text"

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context["widget"]["attrs"]["data-jalali-with-time"] = "true"
        return context


class JalaliDateField(forms.DateField):
    widget = JalaliDateInput

    def to_python(self, value):
        if value in self.empty_values:
            return None
        try:
            date_value, _hour, _minute, _second, _has_time = _parse_components(value)
            return date_value
        except (ValueError, TypeError, OverflowError) as exc:
            message = "تاریخ نامعتبر است" if str(exc) == "تاریخ نامعتبر است" else self.error_messages["invalid"]
            raise ValidationError(message, code="invalid")


class JalaliDateTimeField(forms.DateTimeField):
    widget = JalaliDateTimeInput

    def to_python(self, value):
        if value in self.empty_values:
            return None
        try:
            date_value, hour, minute, second, _has_time = _parse_components(value)
            result = dt.datetime.combine(date_value, dt.time(hour, minute, second))
            if timezone.is_naive(result):
                result = timezone.make_aware(result, timezone.get_current_timezone())
            return result
        except (ValueError, TypeError, OverflowError) as exc:
            message = "تاریخ نامعتبر است" if str(exc) == "تاریخ نامعتبر است" else self.error_messages["invalid"]
            raise ValidationError(message, code="invalid")


def install_jalali_admin_fields():
    """Make Jalali fields the default for all editable admin date fields."""
    from django.contrib.admin.options import BaseModelAdmin, ModelAdmin

    if getattr(BaseModelAdmin.formfield_for_dbfield, "_jalali_wrapped", False):
        return

    def wrap_formfield(original):
        def formfield_for_dbfield(self, db_field, request, **kwargs):
            if isinstance(db_field, models.DateTimeField):
                kwargs.setdefault("form_class", JalaliDateTimeField)
                kwargs.setdefault("widget", JalaliDateTimeInput())
            elif isinstance(db_field, models.DateField):
                kwargs.setdefault("form_class", JalaliDateField)
                kwargs.setdefault("widget", JalaliDateInput())
            return original(self, db_field, request, **kwargs)

        formfield_for_dbfield._jalali_wrapped = True
        return formfield_for_dbfield

    BaseModelAdmin.formfield_for_dbfield = wrap_formfield(BaseModelAdmin.formfield_for_dbfield)
    ModelAdmin.formfield_for_dbfield = wrap_formfield(ModelAdmin.formfield_for_dbfield)
