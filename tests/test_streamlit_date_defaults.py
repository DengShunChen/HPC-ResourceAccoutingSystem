from datetime import date, timedelta

from streamlit_date_defaults import (
    DEFAULT_RECENT_WINDOW_DAYS,
    LONG_SPAN_THRESHOLD_DAYS,
    normalize_start_end_dates,
    sidebar_default_date_range,
)


def test_sidebar_default_short_span():
    lo, hi = date(2025, 1, 1), date(2025, 2, 1)
    ds, de = sidebar_default_date_range(lo, hi)
    assert ds == lo
    assert de == hi


def test_sidebar_default_long_span_caps_recent_window():
    lo = date(2020, 1, 1)
    hi = date(2025, 7, 1)
    assert (hi - lo).days > LONG_SPAN_THRESHOLD_DAYS
    ds, de = sidebar_default_date_range(lo, hi)
    assert de == hi
    assert (hi - ds).days == DEFAULT_RECENT_WINDOW_DAYS


def test_normalize_start_end_dates_swap():
    a, b = date(2025, 7, 10), date(2025, 7, 1)
    s, e = normalize_start_end_dates(a, b)
    assert s == b and e == a


def test_normalize_start_end_dates_noop():
    s, e = normalize_start_end_dates(date(2025, 1, 1), date(2025, 12, 31))
    assert s == date(2025, 1, 1) and e == date(2025, 12, 31)
