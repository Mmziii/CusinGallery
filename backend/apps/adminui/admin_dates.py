"""
Jalali rendering helpers for admin columns (item 13).

The project is entirely Persian-facing: the owner reads dates as
``۱۴۰۵/۰۷/۲۶``, not ``18 اکتبر 2026``. Django's ``fa`` locale gets the
month name right but the calendar wrong, because Django has no Jalali
support -- ``DATE_FORMAT`` is ``j F Y`` and the ``Year`` it prints is the
Gregorian one.

Every date the admin shows should go through here (or the ``jdate`` /
``jdatetime`` template filters, which share the same conversion), so the
whole panel agrees on what day it is.

The helpers never touch input widgets or stored data -- this is display
only.
"""
from __future__ import annotations

import datetime as _dt

from django.utils import timezone

from . import jalali

EMPTY = "—"


def localize(value):
    """Aware datetime -> the active timezone (Asia/Tehran); dates pass."""
    if isinstance(value, _dt.datetime) and timezone.is_aware(value):
        return timezone.localtime(value)
    return value


def jalali_date(value, *, with_time: bool = False) -> str:
    """A date/datetime as ``۱۴۰۵/۰۷/۲۶`` (``+ ۱۲:۳۴`` when ``with_time``)."""
    if value in (None, ""):
        return EMPTY
    value = localize(value)
    if with_time or isinstance(value, _dt.datetime):
        return jalali.format_jalali_datetime(value)
    return jalali.format_jalali(value)


def jalali_range(start, end, *, separator: str = " تا ") -> str:
    """A date window, e.g. ``۱۴۰۵/۰۷/۲۶ تا ۱۴۰۵/۰۷/۲۸``.

    A window that starts and ends on the SAME day prints that one date --
    «۱۴۰۵/۰۷/۲۶ تا ۱۴۰۵/۰۷/۲۶» reads like a bug, and the order change page
    used to append a stray «روز» on top of it.
    """
    if start in (None, "") and end in (None, ""):
        return EMPTY
    if start in (None, ""):
        return jalali_date(end)
    if end in (None, ""):
        return jalali_date(start)
    if start == end:
        return jalali_date(start)
    return f"{jalali_date(start)}{separator}{jalali_date(end)}"


def jalali_column(field_name: str, label: str, *, with_time: bool = False):
    """A ``list_display`` entry rendering ``field_name`` in Jalali.

    Usable directly in ``list_display`` (Django calls a non-string entry
    with the row object). ``admin_order_field`` is kept so the column
    header still sorts by the underlying field, not by the formatted text.

    ``with_time`` prints ``HH:MM`` too -- for timestamps where the owner
    needs to know *when*, not just which day.
    """
    def column(obj):
        value = getattr(obj, field_name, None)
        if with_time:
            return jalali_date(value, with_time=True)
        return jalali_date(value)

    column.short_description = label
    column.admin_order_field = field_name
    column.__name__ = f"{field_name}_jalali"
    return column
