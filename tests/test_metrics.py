"""Metric tests against the hand-traced fixture (see conftest.py)."""

from datetime import date

import pytest

from usage_analytics import metrics as m
from usage_analytics.schema import MODULES

JAN5, JAN6, JAN7 = date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7)
ALL = list(MODULES)


def _scope(tiny, start, end, modules=ALL):
    return m.filter_events(tiny.valid, start, end, modules)


def _dau(events, start, end):
    frame = m.daily_active_users(events, start, end)
    return dict(zip(frame["date_utc"].dt.date, frame["active_users"]))


def _volume(events, start, end):
    frame = m.daily_event_volume(events, start, end)
    return dict(zip(frame["date_utc"].dt.date, frame["events"]))


def _funnel(events):
    frame = m.session_funnel(events)
    return list(frame["sessions"]), [m.format_rate(v) for v in frame["conversion_from_entry"]]


def test_full_range_all_modules(tiny):
    events = _scope(tiny, JAN5, JAN7)
    assert len(events) == 17
    assert _volume(events, JAN5, JAN7) == {JAN5: 13, JAN6: 2, JAN7: 2}
    # 01-05: U1 U2 U3 U4; 01-06: U1 U5; 01-07: U5.
    assert _dau(events, JAN5, JAN7) == {JAN5: 4, JAN6: 2, JAN7: 1}
    assert m.scope_summary(events) == {"events": 17, "distinct_users": 5, "sessions": 7}


def test_dau_is_not_sum_of_module_distinct_users(tiny):
    # On 01-05: catalog {U1,U3}=2, orders {U2}=1, support {U4,U3}=2 -> sum 5, distinct 4.
    per_module = sum(
        _dau(_scope(tiny, JAN5, JAN5, [mod]), JAN5, JAN5)[JAN5] for mod in ALL
    )
    assert per_module == 5
    assert _dau(_scope(tiny, JAN5, JAN5), JAN5, JAN5)[JAN5] == 4


def test_module_usage_counts_events(tiny):
    usage = m.module_usage(_scope(tiny, JAN5, JAN7), ALL)
    assert dict(zip(usage["module"], usage["events"])) == {
        "catalog": 7,
        "orders": 6,
        "support": 3,
        "reports": 1,
    }
    assert usage["share_of_events"].tolist() == pytest.approx([7 / 17, 6 / 17, 3 / 17, 1 / 17])


def test_funnel_full_range(tiny):
    # Entry: U1/S1 U2/S1 U3/S2 U4/S3 U3/S7 U1/S4 U5/S6 = 7.
    # Search after page_view: U1/S1, U3/S2, U5/S6 = 3 (U2 out of order, U4 equal time).
    # Detail after that search: U1/S1, U5/S6 = 2.
    assert _funnel(_scope(tiny, JAN5, JAN7)) == ([7, 3, 2], ["100.0%", "42.9%", "28.6%"])


def test_date_filter_truncates_session(tiny):
    # End date 01-06 excludes 01-07 00:00:00 onward, cutting U5/S6 after its page_view.
    events = _scope(tiny, JAN5, JAN6)
    assert len(events) == 15
    assert _funnel(events) == ([7, 2, 1], ["100.0%", "28.6%", "14.3%"])


def test_end_boundary_is_exclusive_midnight(tiny):
    events = _scope(tiny, JAN6, JAN6)
    assert sorted(events["event_id"]) == ["E13", "E19"]


def test_session_without_first_step_in_scope_is_not_entry(tiny):
    events = _scope(tiny, JAN7, JAN7)
    assert len(events) == 2
    assert _funnel(events) == ([0, 0, 0], ["N/A", "N/A", "N/A"])


def test_module_filter_applies_before_funnel(tiny):
    events = _scope(tiny, JAN5, JAN7, ["orders"])
    assert len(events) == 6
    assert _dau(events, JAN5, JAN7) == {JAN5: 1, JAN6: 1, JAN7: 1}
    # U2/S1 entry only (out of order); U5/S6 completes.
    assert _funnel(events) == ([2, 1, 1], ["100.0%", "50.0%", "50.0%"])


def test_empty_module_selection(tiny):
    events = _scope(tiny, JAN5, JAN7, [])
    assert len(events) == 0
    assert _dau(events, JAN5, JAN7) == {JAN5: 0, JAN6: 0, JAN7: 0}
    assert _volume(events, JAN5, JAN7) == {JAN5: 0, JAN6: 0, JAN7: 0}
    assert m.module_usage(events, []).empty
    assert _funnel(events) == ([0, 0, 0], ["N/A", "N/A", "N/A"])
    assert m.scope_summary(events) == {"events": 0, "distinct_users": 0, "sessions": 0}


def test_selected_module_without_events_shows_zero_and_na_share(tiny):
    usage = m.module_usage(_scope(tiny, JAN7, JAN7, ["catalog"]), ["catalog"])
    assert usage.to_dict("records") == [{"module": "catalog", "events": 0, "share_of_events": None}]


def test_reversed_date_range_is_an_error(tiny):
    with pytest.raises(ValueError):
        _scope(tiny, JAN7, JAN5)


def test_repeated_steps_do_not_multiply_sessions():
    import pandas as pd

    ts = pd.to_datetime(
        ["2026-01-05T09:00:00Z", "2026-01-05T09:00:10Z", "2026-01-05T09:00:20Z", "2026-01-05T09:00:30Z"],
        utc=True,
    )
    events = pd.DataFrame(
        {
            "timestamp_utc": ts,
            "user_id": ["U9"] * 4,
            "session_id": ["S9"] * 4,
            "module": ["catalog"] * 4,
            "event_type": ["page_view", "search", "page_view", "search"],
        }
    )
    assert list(m.session_funnel(events)["sessions"]) == [1, 1, 0]


def test_greedy_match_uses_a_later_step_when_needed():
    import pandas as pd

    # search before page_view does not count, but a later search does.
    ts = pd.to_datetime(
        ["2026-01-05T09:00:00Z", "2026-01-05T09:00:10Z", "2026-01-05T09:00:20Z", "2026-01-05T09:00:30Z"],
        utc=True,
    )
    events = pd.DataFrame(
        {
            "timestamp_utc": ts,
            "user_id": ["U9"] * 4,
            "session_id": ["S9"] * 4,
            "module": ["catalog"] * 4,
            "event_type": ["search", "page_view", "search", "detail_view"],
        }
    )
    assert list(m.session_funnel(events)["sessions"]) == [1, 1, 1]
