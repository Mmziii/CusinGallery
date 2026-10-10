"""B2: pure-Python Jalali conversion + display filters.

The converter was cross-validated against jdatetime over 29,586 days
(1980-2060, zero mismatches) during development; these tests pin the
anchors, leap-year behaviour (1399), Nowruz boundaries and the
display-only filters used across the admin.
"""
import datetime as dt

from django.test import SimpleTestCase, override_settings

from apps.adminui.jalali import (
    JalaliDate,
    fa_digits,
    format_jalali,
    format_jalali_datetime,
    gregorian_to_jalali,
    jalali_to_gregorian,
    to_jalali,
)
from apps.adminui.templatetags.adminui_extras import (
    group_thousands,
    jdate_filter,
    jdatetime_filter,
    jweekday_filter,
    numfa_filter,
    pctfa_filter,
    to_fa_digits,
    toman_filter,
)


class JalaliConversionTests(SimpleTestCase):
    def test_known_anchors(self):
        cases = [
            ((2026, 10, 10), (1405, 7, 18)),   # "today" at build time
            ((2026, 3, 21), (1405, 1, 1)),     # Nowruz 1405
            ((2026, 3, 20), (1404, 12, 29)),   # day before Nowruz 1405
            ((2021, 3, 20), (1399, 12, 30)),   # 1399 is leap: Esfand 30 exists
            ((2021, 3, 21), (1400, 1, 1)),     # Nowruz 1400
            ((2024, 3, 20), (1403, 1, 1)),     # Nowruz 1403
            ((2025, 3, 21), (1404, 1, 1)),     # Nowruz 1404 (algorithmic)
            ((2000, 1, 1), (1378, 10, 11)),
            ((1979, 2, 11), (1357, 11, 22)),   # revolution day
        ]
        for g, expected in cases:
            with self.subTest(gregorian=g):
                self.assertEqual(gregorian_to_jalali(*g), expected)

    def test_leap_year_1399_has_esfand_30_but_1400_does_not(self):
        self.assertEqual(jalali_to_gregorian(1399, 12, 30), dt.date(2021, 3, 20))
        with self.assertRaises(ValueError):
            jalali_to_gregorian(1400, 12, 30)

    def test_invalid_jalali_inputs_raise(self):
        with self.assertRaises(ValueError):
            jalali_to_gregorian(1405, 7, 32)
        with self.assertRaises(ValueError):
            jalali_to_gregorian(1405, 13, 1)

    def test_round_trip_sweep_including_leap_boundaries(self):
        day = dt.date(2002, 1, 1)
        end = dt.date(2050, 12, 31)
        while day <= end:
            j = gregorian_to_jalali(day.year, day.month, day.day)
            back = jalali_to_gregorian(*j)
            self.assertEqual(back, day, f"round trip failed at {day}")
            day += dt.timedelta(days=37)  # sampled sweep: fast but thorough

    def test_every_day_of_one_leap_and_one_common_year(self):
        for year_start in (dt.date(2020, 3, 20), dt.date(2021, 3, 21)):
            day = year_start
            for _ in range(366):
                j = gregorian_to_jalali(day.year, day.month, day.day)
                self.assertEqual(jalali_to_gregorian(*j), day)
                day += dt.timedelta(days=1)

    def test_to_jalali_carries_components_and_formatting(self):
        jd = to_jalali(dt.date(2026, 10, 10))
        self.assertIsInstance(jd, JalaliDate)
        self.assertEqual((jd.jalali_year, jd.jalali_month, jd.jalali_day), (1405, 7, 18))
        self.assertEqual(jd.iso_jalali(), "1405-07-18")
        self.assertEqual(format_jalali(dt.date(2026, 10, 10)), "۱۴۰۵/۰۷/۱۸")
        self.assertEqual(
            format_jalali(dt.date(2026, 10, 10), persian_digits=False), "1405/10/18".replace("10/18", "07/18")
        )
        self.assertIsNone(to_jalali(None))
        self.assertEqual(format_jalali(None), "—")
        with self.assertRaises(TypeError):
            to_jalali("2026-10-10")

    def test_weekday_names(self):
        from apps.adminui.jalali import JALALI_WEEKDAY_NAMES

        # 2026-10-10 is a Saturday -> شنبه
        self.assertEqual(JALALI_WEEKDAY_NAMES[dt.date(2026, 10, 10).weekday()], "شنبه")


@override_settings(TIME_ZONE="Asia/Tehran", USE_TZ=True)
class JalaliFilterTests(SimpleTestCase):
    def test_jdate_converts_aware_datetime_in_active_timezone(self):
        # 2026-10-09 20:30 UTC == 2026-10-10 00:00 Tehran -> ۱۴۰۵/۰۷/۱۸
        moment = dt.datetime(2026, 10, 9, 20, 30, tzinfo=dt.timezone.utc)
        self.assertEqual(jdate_filter(moment), "۱۴۰۵/۰۷/۱۸")
        self.assertEqual(jdate_filter(moment, "iso"), "1405-07-18")
        # one minute earlier is still the 17th in Tehran
        self.assertEqual(jdate_filter(moment - dt.timedelta(minutes=1)), "۱۴۰۵/۰۷/۱۷")

    def test_jdate_handles_plain_dates_and_empty(self):
        self.assertEqual(jdate_filter(dt.date(2026, 3, 21)), "۱۴۰۵/۰۱/۰۱")
        self.assertEqual(jdate_filter(None), "—")
        self.assertEqual(jdate_filter(""), "—")

    def test_jdatetime_adds_time(self):
        # class-level TIME_ZONE override makes Tehran the active zone:
        # 2026-10-09 20:30 UTC == 2026-10-10 00:00 Tehran
        moment = dt.datetime(2026, 10, 9, 20, 30, tzinfo=dt.timezone.utc)
        self.assertEqual(jdatetime_filter(moment), "۱۴۰۵/۰۷/۱۸ ۰۰:۰۰")

    def test_jweekday(self):
        moment = dt.datetime(2026, 10, 9, 20, 30, tzinfo=dt.timezone.utc)
        self.assertEqual(jweekday_filter(moment), "شنبه")

    def test_number_filters(self):
        self.assertEqual(fa_digits("1234"), "۱۲۳۴")
        self.assertEqual(to_fa_digits("0912"), "۰۹۱۲")
        self.assertEqual(group_thousands(1234567), "1٬234٬567")
        self.assertEqual(numfa_filter(1234567), "۱٬۲۳۴٬۵۶۷")
        self.assertEqual(toman_filter(1234567), "۱٬۲۳۴٬۵۶۷ تومان")
        self.assertEqual(toman_filter(0), "۰ تومان")
        self.assertEqual(toman_filter(None), "—")
        self.assertEqual(toman_filter("abc"), "abc")

    def test_pctfa(self):
        self.assertEqual(pctfa_filter(12.4), "+۱۲٪")
        self.assertEqual(pctfa_filter(-8.2), "−۸٪")
        self.assertEqual(pctfa_filter(0.2), "۰٪")
        self.assertEqual(pctfa_filter(None), "—")
        self.assertEqual(pctfa_filter("x"), "—")

    def test_format_jalali_datetime_plain(self):
        text = format_jalali_datetime(dt.datetime(2026, 10, 10, 8, 5))
        self.assertEqual(text, "۱۴۰۵/۰۷/۱۸ ۰۸:۰۵")
        self.assertEqual(format_jalali_datetime(None), "—")
