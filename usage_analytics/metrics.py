"""Usage metrics computed from validated events.

Scope rule: every displayed usage metric is computed from the same filtered
valid events returned by :func:`filter_events`. Validation counts are
file-wide and live in :mod:`usage_analytics.validation`.

Definitions (also in README.md):

* Date filter: UTC; includes ``start_date`` 00:00:00 and excludes 00:00:00 on
  the day after ``end_date``.
* Module filter: an explicit list; an empty list selects no events.
* Daily active users (DAU): distinct non-missing ``user_id`` per UTC day.
* Event volume: count of valid events per UTC day.
* Module usage: count of valid events per module; share uses the total
  filtered valid events as denominator.
* Session: the pair ``(user_id, session_id)``.
* Funnel entry: a session with at least one first-step event in scope.
* Stage k reached: a session has events for steps 1..k with strictly
  increasing timestamps. Each session counts at most once per stage.
* Conversion from entry: stage sessions / entry sessions; ``None`` (shown as
  ``N/A``) when there are no entry sessions.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date, timedelta

import pandas as pd

from .schema import FUNNEL_STEPS


def _day_bounds(start_date: date, end_date: date) -> tuple[pd.Timestamp, pd.Timestamp]:
    if start_date > end_date:
        raise ValueError(f"start_date {start_date} is after end_date {end_date}")
    start = pd.Timestamp(start_date, tz="UTC")
    end_exclusive = pd.Timestamp(end_date + timedelta(days=1), tz="UTC")
    return start, end_exclusive


def filter_events(
    valid: pd.DataFrame, start_date: date, end_date: date, modules: Iterable[str]
) -> pd.DataFrame:
    """Valid events in ``[start_date 00:00Z, end_date + 1 day 00:00Z)`` and ``modules``."""
    start, end_exclusive = _day_bounds(start_date, end_date)
    ts = valid["timestamp_utc"]
    mask = (ts >= start) & (ts < end_exclusive) & valid["module"].isin(list(modules))
    return valid[mask].reset_index(drop=True)


def _utc_days(start_date: date, end_date: date) -> pd.DatetimeIndex:
    _day_bounds(start_date, end_date)
    return pd.date_range(start_date, end_date, freq="D", name="date_utc")


def _event_days(events: pd.DataFrame) -> pd.Series:
    return events["timestamp_utc"].dt.tz_convert("UTC").dt.tz_localize(None).dt.normalize()


def daily_active_users(events: pd.DataFrame, start_date: date, end_date: date) -> pd.DataFrame:
    """One row per UTC day in the range; days without events in scope show 0."""
    users = events[events["user_id"] != ""]
    per_day = users.groupby(_event_days(users))["user_id"].nunique()
    per_day = per_day.reindex(_utc_days(start_date, end_date), fill_value=0)
    return per_day.rename("active_users").astype(int).reset_index()


def daily_event_volume(events: pd.DataFrame, start_date: date, end_date: date) -> pd.DataFrame:
    """One row per UTC day in the range with the count of valid events in scope."""
    per_day = events.groupby(_event_days(events)).size()
    per_day = per_day.reindex(_utc_days(start_date, end_date), fill_value=0)
    return per_day.rename("events").astype(int).reset_index()


def module_usage(events: pd.DataFrame, modules: Sequence[str]) -> pd.DataFrame:
    """Valid event count per selected module, plus share of all filtered events."""
    counts = events["module"].value_counts().reindex(list(modules), fill_value=0).astype(int)
    total = int(counts.sum())
    result = counts.rename("events").rename_axis("module").reset_index()
    result["share_of_events"] = [(n / total) if total else None for n in result["events"]]
    return result


def scope_summary(events: pd.DataFrame) -> dict:
    users = events.loc[events["user_id"] != "", "user_id"]
    return {
        "events": len(events),
        "distinct_users": int(users.nunique()),
        "sessions": int(events[["user_id", "session_id"]].drop_duplicates().shape[0]),
    }


def _stages_reached(session: pd.DataFrame, steps: Sequence[str]) -> int:
    """Number of leading funnel steps matched with strictly increasing timestamps.

    Greedy matching (earliest qualifying timestamp for each step) is enough:
    picking the earliest possible time never removes a later option.
    """
    last = None
    reached = 0
    for step in steps:
        times = session.loc[session["event_type"] == step, "timestamp_utc"]
        if last is not None:
            times = times[times > last]
        if times.empty:
            break
        last = times.min()
        reached += 1
    return reached


def session_funnel(events: pd.DataFrame, steps: Sequence[str] = FUNNEL_STEPS) -> pd.DataFrame:
    """Sessions reaching each ordered stage within the filtered events."""
    if len(steps) == 0:
        raise ValueError("funnel needs at least one step")
    reached = [
        _stages_reached(session, steps)
        for _, session in events.groupby(["user_id", "session_id"], sort=True)
    ]
    entry = sum(1 for r in reached if r >= 1)
    rows = []
    for k, step in enumerate(steps, start=1):
        sessions = sum(1 for r in reached if r >= k)
        rows.append(
            {
                "stage": k,
                "step": step,
                "sessions": sessions,
                "conversion_from_entry": (sessions / entry) if entry else None,
            }
        )
    return pd.DataFrame(rows)


def format_rate(value: float | None) -> str:
    """Percentage with one decimal, or ``N/A`` for an undefined rate."""
    if value is None or pd.isna(value):
        return "N/A"
    return f"{value:.1%}"
