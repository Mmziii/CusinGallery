"""Pure-Python Gregorian <-> Jalali (Shamsi) date conversion.

Ported from the well-known Jalaali calendar algorithm (K. Borkowski /
jalaali-js), which is exact for the years 1206..2256 Jalali (1827..2878
Gregorian) -- far beyond the lifetime of any shop data.

Deliberately dependency-free: the project forbids new Python packages and
the admin only needs a display filter (B2), never Jalali input parsing.
"""
from __future__ import annotations

import datetime as _dt

__all__ = [
    "JALALI_MONTH_NAMES",
    "JALALI_WEEKDAY_NAMES",
    "fa_digits",
    "JalaliDate",
    "gregorian_to_jalali",
    "jalali_to_gregorian",
    "to_jalali",
    "format_jalali",
    "format_jalali_datetime",
]

JALALI_MONTH_NAMES = (
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
)

# datetime.weekday(): Monday == 0 ... Sunday == 6
JALALI_WEEKDAY_NAMES = (
    "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه",
)

_JALALI_BREAKS = (
    -61, 9, 38, 199, 426, 686, 756, 818, 1111, 1181, 1210,
    1635, 2060, 2097, 2192, 2262, 2324, 2394, 2456, 3178,
)


class JalaliDate(_dt.date):
    """A ``datetime.date`` subclass carrying its Jalali components.

    ``jalali_year`` / ``jalali_month`` / ``jalali_day`` are plain ints so the
    object stays cheap and comparable exactly like the Gregorian date it
    extends (all ordering behaviour is inherited and unchanged).
    """

    __slots__ = ("jalali_year", "jalali_month", "jalali_day")

    def __new__(cls, year, month, day):  # noqa: ANN001 - mirrors date.__new__
        g = jalali_to_gregorian(year, month, day)
        obj = super().__new__(cls, g.year, g.month, g.day)
        obj.jalali_year = year
        obj.jalali_month = month
        obj.jalali_day = day
        return obj

    def iso_jalali(self) -> str:
        """Return ``JYYY-JMM-JDD`` (ASCII digits, zero-padded)."""
        return f"{self.jalali_year:04d}-{self.jalali_month:02d}-{self.jalali_day:02d}"


def _div(a: int, b: int) -> int:
    """Truncating integer division -- matches the JS ``~~(a / b)`` semantics
    the original algorithm relies on (Python ``//`` floors, which differs for
    negative operands such as ``gm - 8``)."""
    q = abs(a) // abs(b)
    return -q if (a < 0) != (b < 0) else q


def _mod(a: int, b: int) -> int:
    """Remainder matching JS ``%`` (sign follows the dividend)."""
    return a - _div(a, b) * b


def _jal_cal(jy: int) -> tuple[int, int, int]:
    """Return ``(leap_days_after_epoch, gregorian_year_of_jy_start, march_day)``.

    Direct port of ``jalCal()`` from jalaali-js.
    """
    bl = len(_JALALI_BREAKS)
    gy = jy + 621
    leap_j = -14
    jp = _JALALI_BREAKS[0]

    if jy < jp or jy >= _JALALI_BREAKS[bl - 1]:
        raise ValueError(f"Invalid Jalali year {jy!r}")

    jump = 0
    for i in range(1, bl):
        jm = _JALALI_BREAKS[i]
        jump = jm - jp
        if jy < jm:
            break
        leap_j = leap_j + _div(jump, 33) * 8 + _div(_mod(jump, 33), 4)
        jp = jm

    n = jy - jp
    leap_j = leap_j + _div(n, 33) * 8 + _div(_mod(n, 33) + 3, 4)
    if _mod(jump, 33) == 4 and jump - n == 4:
        leap_j += 1

    leap_g = _div(gy, 4) - _div((_div(gy, 100) + 1) * 3, 4) - 150
    march = 20 + leap_j - leap_g

    if jump - n < 6:
        n = n - jump + _div(jump + 4, 33) * 33
    leap = _mod(_mod(n + 1, 33) - 1, 4)
    if leap == -1:
        leap = 4
    return leap, gy, march


def _g2d(gy: int, gm: int, gd: int) -> int:
    """Gregorian date -> Julian Day Number (jalaali-js ``g2d``)."""
    d = (
        _div((gy + _div(gm - 8, 6) + 100100) * 1461, 4)
        + _div(153 * _mod(gm + 9, 12) + 2, 5)
        + gd
        - 34840408
    )
    d = d - _div(_div(gy + 100100 + _div(gm - 8, 6), 100) * 3, 4) + 752
    return d


def _d2g(jdn: int) -> _dt.date:
    """Julian Day Number -> Gregorian date (jalaali-js ``d2g``)."""
    j = 4 * jdn + 139361631
    j = j + _div(_div(4 * jdn + 183187720, 146097) * 3, 4) * 4 - 3908
    i = _div(_mod(j, 1461), 4) * 5 + 308
    gd = _div(_mod(i, 153), 5) + 1
    gm = _mod(_div(i, 153), 12) + 1
    gy = _div(j, 1461) - 100100 + _div(8 - gm, 6)
    return _dt.date(gy, gm, gd)


def gregorian_to_jalali(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    """Convert a Gregorian ``(year, month, day)`` to Jalali ``(jy, jm, jd)``."""
    jdn = _g2d(gy, gm, gd)
    gy_date = _d2g(jdn)
    jy = gy_date.year - 621
    r_leap, _gy_start, march = _jal_cal(jy)
    jdn1f = _g2d(gy_date.year, 3, march)

    k = jdn - jdn1f
    if k >= 0:
        if k <= 185:
            jm = 1 + _div(k, 31)
            jd = _mod(k, 31) + 1
            return jy, jm, jd
        k -= 186
    else:
        jy -= 1
        k += 179
        # NOTE: jalaali-js checks r.leap of the ORIGINAL jy here, not of the
        # decremented one -- keep the semantics identical.
        if r_leap == 1:
            k += 1

    jm = 7 + _div(k, 30)
    jd = _mod(k, 30) + 1
    return jy, jm, jd


def jalali_to_gregorian(jy: int, jm: int, jd: int) -> _dt.date:
    """Convert a Jalali ``(year, month, day)`` to a Gregorian ``datetime.date``."""
    if not 1 <= jm <= 12:
        raise ValueError(f"Invalid Jalali month {jm!r}")
    if not 1 <= jd <= 31:
        raise ValueError(f"Invalid Jalali day {jd!r}")
    _leap, gy, march = _jal_cal(jy)
    days_in_month = 31 if jm <= 6 else (30 if jm <= 11 else (30 if _leap == 0 else 29))
    if jd > days_in_month:
        raise ValueError(f"Invalid Jalali date {jy}/{jm}/{jd}")
    jdn = _g2d(gy, 3, march) + (jm - 1) * 31 - _div(jm, 7) * (jm - 7) + jd - 1
    return _d2g(jdn)


def to_jalali(value) -> JalaliDate | None:
    """Convert a ``date``/``datetime`` (or ``None``) to :class:`JalaliDate`.

    Accepts aware datetimes as-is; timezone conversion is the caller's
    business (the admin uses ``django.utils.timezone`` helpers before this).
    """
    if value is None:
        return None
    if isinstance(value, JalaliDate):
        return value
    if isinstance(value, (_dt.datetime, _dt.date)):
        jy, jm, jd = gregorian_to_jalali(value.year, value.month, value.day)
        return JalaliDate(jy, jm, jd)
    raise TypeError(f"Cannot convert {type(value).__name__} to Jalali")


def fa_digits(text: str) -> str:
    """ASCII digits -> Persian digits (۰-۹)."""
    return str(text).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


# Backwards-compatible private alias used inside this module.
_fa_digits = fa_digits


def format_jalali(
    value,
    *,
    persian_digits: bool = True,
    with_weekday: bool = False,
) -> str:
    """Format a date/datetime as ``JYYY/JMM/JDD`` (Persian digits by default)."""
    jd = to_jalali(value)
    if jd is None:
        return "—"
    text = f"{jd.jalali_year:04d}/{jd.jalali_month:02d}/{jd.jalali_day:02d}"
    if with_weekday:
        text = f"{JALALI_WEEKDAY_NAMES[jd.weekday()]} {text}"
    return _fa_digits(text) if persian_digits else text


def format_jalali_datetime(value, *, persian_digits: bool = True) -> str:
    """Format a datetime as ``JYYY/JMM/JDD HH:MM``; non-datetimes pass through."""
    jd = to_jalali(value)
    if jd is None:
        return "—"
    text = format_jalali(jd, persian_digits=persian_digits)
    if isinstance(value, _dt.datetime):
        time_text = f"{value.hour:02d}:{value.minute:02d}"
        if persian_digits:
            time_text = _fa_digits(time_text)
        text = f"{text} {time_text}"
    return text
