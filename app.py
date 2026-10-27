"""Streamlit dashboard for the synthetic product usage demo.

Run: streamlit run app.py
Set USAGE_EVENTS_CSV to read a different event file.
All calculations come from usage_analytics; this file only presents them.
"""

from __future__ import annotations

import os
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from usage_analytics import metrics as m
from usage_analytics.schema import FUNNEL_STEPS, MODULES, SYNTHETIC_LABEL
from usage_analytics.validation import load_and_validate

DEFAULT_CSV = Path(__file__).parent / "data" / "synthetic_events.csv"


@st.cache_data
def _load(path: str, mtime: float):
    return load_and_validate(path)


def _chart(data: pd.DataFrame, title: str) -> alt.Chart:
    return alt.Chart(data, title=alt.TitleParams(title, subtitle=SYNTHETIC_LABEL))


def _count_scale(values: pd.Series) -> alt.Scale:
    # An all-zero series would otherwise get a degenerate [0, 0] axis.
    top = int(values.max()) if len(values) else 0
    return alt.Scale(domain=[0, max(top, 1)], nice=True)


def _count_axis() -> alt.Axis:
    return alt.Axis(format="d", tickMinStep=1)


st.set_page_config(page_title="Synthetic Product Usage Analytics", layout="wide")
st.title("Product usage analytics (fictional B2B web app)")
st.warning(f"**{SYNTHETIC_LABEL}.** All users, sessions, and events are invented by a seeded generator.")

csv_path = Path(os.environ.get("USAGE_EVENTS_CSV", DEFAULT_CSV))
if not csv_path.exists():
    st.error(f"Event file not found: `{csv_path}`. Run `python generate_sample_data.py` first.")
    st.stop()

result = _load(str(csv_path), csv_path.stat().st_mtime)
valid = result.valid
if valid.empty:
    st.error("The event file contains no valid events; see the data-quality counts below.")
    first_day = last_day = pd.Timestamp.now(tz="UTC").date()
else:
    first_day = valid["timestamp_utc"].min().date()
    last_day = valid["timestamp_utc"].max().date()

# --- Filters --------------------------------------------------------------
with st.sidebar:
    st.header("Filters")
    picked = st.date_input(
        "UTC date range",
        value=(first_day, last_day),
        min_value=first_day,
        max_value=last_day,
    )
    # While a range is being picked Streamlit returns a single date.
    if isinstance(picked, tuple) and len(picked) == 0:
        start_date, end_date = first_day, last_day
    else:
        start_date, end_date = (picked[0], picked[-1]) if isinstance(picked, tuple) else (picked, picked)
    modules = st.multiselect("Modules", options=list(MODULES), default=list(MODULES))
    st.caption(
        f"Includes {start_date} 00:00:00 UTC up to, but not including, 00:00:00 UTC "
        "the day after the end date. An empty module list selects no events."
    )

events = m.filter_events(valid, start_date, end_date, modules)
scope = m.scope_summary(events)
funnel = m.session_funnel(events, FUNNEL_STEPS)

st.markdown(
    f"**Scope for all usage metrics below:** {start_date} to {end_date} (UTC), "
    f"modules: {', '.join(modules) if modules else 'none selected'}."
)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Valid events in scope", f"{scope['events']:,}")
c2.metric("Distinct users in scope", f"{scope['distinct_users']:,}")
c3.metric("Sessions in scope", f"{scope['sessions']:,}")
c4.metric("Funnel entry sessions", f"{int(funnel['sessions'].iloc[0]):,}")
if scope["events"] == 0:
    st.info("No valid events match this selection. Charts show zero counts and rates show N/A.")

# --- Daily activity -------------------------------------------------------
st.subheader("1. Daily activity")
dau = m.daily_active_users(events, start_date, end_date)
volume = m.daily_event_volume(events, start_date, end_date)
tab_dau, tab_volume = st.tabs(["Daily active users", "Event volume"])
with tab_dau:
    st.altair_chart(
        _chart(dau, "Daily active users (distinct users per UTC day)")
        .mark_line(point=True)
        .encode(
            x=alt.X("date_utc:T", title="UTC day", axis=alt.Axis(format="%b %d")),
            y=alt.Y(
                "active_users:Q",
                title="Distinct users",
                scale=_count_scale(dau["active_users"]),
                axis=_count_axis(),
            ),
            tooltip=[alt.Tooltip("date_utc:T", format="%Y-%m-%d"), "active_users:Q"],
        ),
        width="stretch",
    )
    st.caption(
        "Tells an administrator how many different people used the selected modules each day. "
        "A user counts once per day however many events or modules they used; per-module counts "
        "cannot be summed to get this number."
    )
with tab_volume:
    st.altair_chart(
        _chart(volume, "Event volume (valid events per UTC day)")
        .mark_bar()
        .encode(
            x=alt.X("date_utc:T", title="UTC day", axis=alt.Axis(format="%b %d")),
            y=alt.Y(
                "events:Q",
                title="Valid events",
                scale=_count_scale(volume["events"]),
                axis=_count_axis(),
            ),
            tooltip=[alt.Tooltip("date_utc:T", format="%Y-%m-%d"), "events:Q"],
        ),
        width="stretch",
    )
    st.caption(
        "Shows how much activity occurred each day. Volume rises with both more users and "
        "more actions per user, so read it next to daily active users."
    )

# --- Module usage ---------------------------------------------------------
st.subheader("2. Module usage (valid event count)")
usage = m.module_usage(events, modules)
if usage.empty:
    st.info("No modules selected.")
else:
    st.altair_chart(
        _chart(usage, "Module usage = valid events per module")
        .mark_bar()
        .encode(
            x=alt.X(
                "events:Q",
                title="Valid events",
                scale=_count_scale(usage["events"]),
                axis=_count_axis(),
            ),
            y=alt.Y("module:N", title="Module", sort="-x"),
            tooltip=["module:N", "events:Q", alt.Tooltip("share_of_events:Q", format=".1%")],
        ),
        width="stretch",
    )
    table = usage.assign(share_of_events=usage["share_of_events"].map(m.format_rate))
    st.dataframe(table, hide_index=True, width="stretch")
    st.caption(
        "Shows where activity concentrates. This counts events, not users: one heavy user can "
        "raise a module's count. Share denominator: all valid events in the current scope. "
        f"{SYNTHETIC_LABEL}."
    )

# --- Funnel ---------------------------------------------------------------
st.subheader("3. Ordered session funnel: " + " -> ".join(FUNNEL_STEPS))
st.altair_chart(
    _chart(funnel, "Sessions reaching each stage in order")
    .mark_bar()
    .encode(
        x=alt.X(
            "sessions:Q",
            title="Sessions",
            scale=_count_scale(funnel["sessions"]),
            axis=_count_axis(),
        ),
        y=alt.Y("step:N", title="Stage", sort=list(FUNNEL_STEPS)),
        tooltip=["stage:Q", "step:N", "sessions:Q"],
    ),
    width="stretch",
)
funnel_table = funnel.assign(
    conversion_from_entry=funnel["conversion_from_entry"].map(m.format_rate)
)
st.dataframe(funnel_table, hide_index=True, width="stretch")
st.caption(
    "Shows how often a session that opens a page goes on to search and then view a detail. "
    "A session is one (user_id, session_id) pair. Entry = sessions with a page_view in scope. "
    "A later stage needs every earlier step at strictly increasing timestamps; equal timestamps "
    "do not establish order and repeated actions do not count a session twice. "
    "Conversion denominator: entry sessions (N/A when zero). "
    "Filters are applied first, so a date or module filter can cut a session and remove steps "
    f"that happened outside the selection. {SYNTHETIC_LABEL}."
)

# --- Data quality ---------------------------------------------------------
st.subheader("4. Data quality (whole file, not affected by filters)")
summary = result.summary()
q = st.columns(5)
q[0].metric("Raw rows read", f"{summary['raw_rows']:,}")
q[1].metric("Valid events", f"{summary['valid_events']:,}")
q[2].metric("Collapsed duplicate rows", f"{summary['collapsed_duplicate_rows']:,}")
q[3].metric("Quarantined rows", f"{summary['quarantined_rows']:,}")
q[4].metric("Rejected rows", f"{summary['rejected_rows']:,}")
st.caption(
    "Every raw row has one outcome: valid, collapsed (extra identical copy of an event_id), "
    "quarantined (all rows of an event_id whose copies disagree), or rejected (a required field "
    "is missing or invalid). Excluded rows never enter the usage metrics above, so a row with a "
    "missing user_id is not counted as a user."
)
if not result.excluded.empty:
    st.dataframe(result.reason_counts(), hide_index=True, width="stretch")
    with st.expander("Excluded rows (source_record = data record number; blank lines skipped)"):
        st.dataframe(result.excluded, hide_index=True, width="stretch")

with st.expander("Metric definitions"):
    st.markdown(
        """
- **Date filter:** UTC; start date 00:00:00 inclusive, the midnight after the end date exclusive.
- **Daily active users:** distinct non-missing `user_id` per UTC day among valid events in scope.
- **Event volume:** count of valid events per UTC day in scope.
- **Module usage:** count of valid events per module in scope; share = module events / all events in scope.
- **Session:** a `(user_id, session_id)` pair.
- **Funnel entry:** a session with at least one `page_view` in scope.
- **Stage reached:** steps 1..k occur at strictly increasing timestamps within the session; counted once per session.
- **Conversion from entry:** stage sessions / entry sessions; N/A when there are no entry sessions.
"""
    )
st.caption(f"{SYNTHETIC_LABEL}. Source file: `{csv_path.name}`.")
