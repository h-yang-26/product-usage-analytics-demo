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


# Same palette as the portfolio site and .streamlit/config.toml.
PALETTES = {
    "light": {"blue": "#1C5785", "teal": "#146C67", "amber": "#8A5A0C", "text": "#1A1D21", "muted": "#4F5660",
              "track": "#E5EAEF", "band": "#EEF1F4"},
    "dark": {"blue": "#8CC0EA", "teal": "#6FCDC2", "amber": "#E6B15C", "text": "#E9E7E2", "muted": "#A9AEB5",
             "track": "#2B3137", "band": "#1E232A"},
}
STEP_NAMES = {"page_view": "Opened a page", "search": "Then searched", "detail_view": "Then viewed a detail"}


def _palette() -> dict:
    # st.context.theme.type is "light" or "dark" once the browser has reported it.
    try:
        kind = st.context.theme.type
    except AttributeError:
        kind = None
    return PALETTES["dark" if kind == "dark" else "light"]


def _title(title: str) -> alt.TitleParams:
    # The subtitle keeps the synthetic label on screenshots of a single chart.
    return alt.TitleParams(title, subtitle=SYNTHETIC_LABEL, subtitleColor=_palette()["muted"], anchor="start")


def _chart(data: pd.DataFrame, title: str) -> alt.Chart:
    return alt.Chart(data, title=_title(title))


def _weekend_bands(start, end) -> pd.DataFrame:
    """Saturday and Sunday spans, centred on each daily point."""
    days = pd.date_range(start, end, freq="D")
    weekend = days[days.day_of_week >= 5]
    half = pd.Timedelta(hours=12)
    return pd.DataFrame({"start": weekend - half, "end": weekend + half})


def _humanize(code: str) -> str:
    text = code.replace("_", " ").capitalize()
    return text[:-3] + " ID" if text.endswith(" id") else text


def _labelled_bars(data: pd.DataFrame, value: str, name: str, colour: str, total_axis_title: str,
                   order: list | None = None, track: float | None = None) -> alt.LayerChart:
    """Horizontal bars with a value label after each bar, room reserved for the labels."""
    top = max(float(data[value].max()) if len(data) else 0.0, track or 0.0, 1.0)
    scale = alt.Scale(domain=[0, top * 1.45], nice=False)  # room for labels on phones
    x = alt.X(f"{value}:Q", title=total_axis_title, scale=scale, axis=_count_axis())
    y = alt.Y(f"{name}:N", title=None, sort=order, axis=alt.Axis(labelFontSize=13, labelLimit=220))
    layers = []
    if track is not None:
        layers.append(alt.Chart(data.assign(_track=track)).mark_bar(color=_palette()["track"], cornerRadiusEnd=3)
                      .encode(x=alt.X("_track:Q", scale=scale), y=y))
    bars = alt.Chart(data).mark_bar(color=colour, cornerRadiusEnd=3).encode(x=x, y=y, tooltip=[f"{name}:N", f"{value}:Q"])
    labels = bars.mark_text(align="left", dx=6, fontSize=13, fontWeight="bold", color=_palette()["text"]).encode(text="label:N")
    return alt.layer(*layers, bars, labels).properties(height=_bars_height(len(data)))


def _bars_height(rows: int) -> int:
    return max(52 * rows, 80)


def _element_height(rows: int) -> int:
    # Streamlit sizes the element separately from the chart; add title and axis space.
    return _bars_height(rows) + 110


def _count_scale(values: pd.Series) -> alt.Scale:
    # An all-zero series would otherwise get a degenerate [0, 0] axis.
    top = int(values.max()) if len(values) else 0
    return alt.Scale(domain=[0, max(top, 1)], nice=True)


def _count_axis() -> alt.Axis:
    return alt.Axis(format="d", tickMinStep=1)


st.set_page_config(page_title="Synthetic Product Usage Analytics", layout="wide")
st.title("Product usage analytics")
st.caption("A fictional multi-module B2B web application.")
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
P = _palette()
bands = alt.Chart(_weekend_bands(start_date, end_date)).mark_rect(color=P["band"]).encode(x="start:T", x2="end:T")
tab_dau, tab_volume = st.tabs(["Daily active users", "Event volume"])
with tab_dau:
    dau_line = (
        alt.Chart(dau)
        .mark_line(point=True, color=P["blue"], strokeWidth=2.5)
        .encode(
            x=alt.X("date_utc:T", title="UTC day", axis=alt.Axis(format="%b %d")),
            y=alt.Y(
                "active_users:Q",
                title="Distinct users",
                scale=_count_scale(dau["active_users"]),
                axis=_count_axis(),
            ),
            tooltip=[alt.Tooltip("date_utc:T", format="%Y-%m-%d"), "active_users:Q"],
        )
    )
    st.altair_chart(
        alt.layer(bands, dau_line).properties(title=_title("Daily active users (distinct users per UTC day)")),
        width="stretch",
    )
    st.caption(
        "Shaded columns are weekends. Tells an administrator how many different people used the selected modules each day. "
        "A user counts once per day however many events or modules they used; per-module counts "
        "cannot be summed to get this number."
    )
with tab_volume:
    volume_bars = (
        alt.Chart(volume)
        .mark_bar(color=P["blue"])
        .encode(
            x=alt.X("date_utc:T", title="UTC day", axis=alt.Axis(format="%b %d")),
            y=alt.Y(
                "events:Q",
                title="Valid events",
                scale=_count_scale(volume["events"]),
                axis=_count_axis(),
            ),
            tooltip=[alt.Tooltip("date_utc:T", format="%Y-%m-%d"), "events:Q"],
        )
    )
    st.altair_chart(
        alt.layer(bands, volume_bars).properties(title=_title("Event volume (valid events per UTC day)")),
        width="stretch",
    )
    st.caption(
        "Shaded columns are weekends. Shows how much activity occurred each day. Volume rises with both more users and "
        "more actions per user, so read it next to daily active users."
    )

# --- Module usage ---------------------------------------------------------
st.subheader("2. Module usage (valid event count)")
usage = m.module_usage(events, modules)
if usage.empty:
    st.info("No modules selected.")
else:
    ranked = usage.sort_values("events", ascending=False, kind="stable").reset_index(drop=True)
    shown = ranked.assign(
        name=ranked["module"].str.capitalize(),
        label=[f"{n:,} · {m.format_rate(r)}" for n, r in zip(ranked["events"], ranked["share_of_events"])],
    )
    st.altair_chart(
        _labelled_bars(shown, "events", "name", P["blue"], "Valid events", order=list(shown["name"]))
        .properties(title=_title("Events per module and share of total")),
        width="stretch",
        height=_element_height(len(shown)),
    )
    with st.expander("Module usage table"):
        table = ranked.assign(share_of_events=ranked["share_of_events"].map(m.format_rate))
        st.dataframe(table, hide_index=True, width="stretch")
    st.caption(
        "Shows where activity concentrates. This counts events, not users: one heavy user can "
        "raise a module's count. Share denominator: all valid events in the current scope. "
        f"{SYNTHETIC_LABEL}."
    )

# --- Funnel ---------------------------------------------------------------
st.subheader("3. Ordered session funnel")
entry_sessions = int(funnel["sessions"].iloc[0])
steps_shown = funnel.assign(
    name=[f"{k}. {STEP_NAMES.get(step, step)}" for k, step in zip(funnel["stage"], funnel["step"])],
    # Entry is 100% by definition, so its label shows the session count instead.
    label=[f"{n:,} sessions" if k == 1 else f"{n:,} · {m.format_rate(r)}"
           for k, n, r in zip(funnel["stage"], funnel["sessions"], funnel["conversion_from_entry"])],
)
st.altair_chart(
    _labelled_bars(steps_shown, "sessions", "name", P["blue"], "Sessions", order=list(steps_shown["name"]),
                   track=float(entry_sessions))
    .properties(title=_title("Sessions reaching each step, in order")),
    width="stretch",
    height=_element_height(len(steps_shown)),
)
with st.expander("Funnel table"):
    funnel_table = funnel.assign(
        conversion_from_entry=funnel["conversion_from_entry"].map(m.format_rate)
    )
    st.dataframe(funnel_table, hide_index=True, width="stretch")
st.caption(
    "Steps: " + " → ".join(f"`{s}`" for s in FUNNEL_STEPS) + ". "
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
    reasons = result.reason_counts().sort_values(["rows", "reason"], ascending=[False, True], kind="stable")
    reasons_shown = reasons.assign(
        name=[_humanize(r) for r in reasons["reason"]],
        label=[f"{n:,}" for n in reasons["rows"]],
    )
    st.altair_chart(
        _labelled_bars(reasons_shown, "rows", "name", P["amber"], "Rows", order=list(reasons_shown["name"]))
        .properties(title=_title("Excluded rows by reason (whole file)")),
        width="stretch",
        height=_element_height(len(reasons_shown)),
    )
    st.caption("Conflicting duplicate IDs are quarantined; every other reason is a rejection.")
    with st.expander("Reason table"):
        st.dataframe(reasons, hide_index=True, width="stretch")
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
