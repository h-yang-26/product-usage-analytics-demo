"""Deterministic generator of fictional events for an invented B2B web app.

Users are pseudonymous codes (``U0001`` ...). Session ids are numbered per
user (``S001`` ...), so the same session_id appears for many users; a session
is only identified by the ``(user_id, session_id)`` pair.

After the clean events are generated, a small fixed set of contract
violations is injected on purpose so the dashboard's data-quality panel has
something to report. See ``DEFECT_PLAN``.
"""

from __future__ import annotations

import csv
import random
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .schema import EVENT_TYPES, MODULES, REQUIRED_FIELDS, TIMESTAMP_FORMAT

DEFAULT_SEED = 20260901
DEFAULT_USERS = 180
DEFAULT_START = date(2026, 9, 1)
DEFAULT_DAYS = 28

MODULE_WEIGHTS = {"catalog": 0.40, "orders": 0.30, "support": 0.15, "reports": 0.15}

# Next action probabilities given the previous action; None ends the session.
TRANSITIONS = {
    "page_view": {"search": 0.45, "detail_view": 0.25, "page_view": 0.15, None: 0.15},
    "search": {"detail_view": 0.50, "search": 0.20, "page_view": 0.10, None: 0.20},
    "detail_view": {"page_view": 0.25, "detail_view": 0.15, "export": 0.15, None: 0.45},
    "export": {"page_view": 0.35, None: 0.65},
}
# Most sessions open with a page view; some arrive on a deep link.
FIRST_ACTION = {"page_view": 0.82, "search": 0.10, "detail_view": 0.08}
MAX_EVENTS_PER_SESSION = 14

# Rows appended or copied to exercise each validation rule.
DEFECT_PLAN = {
    "identical_duplicate_rows": 10,
    "conflicting_duplicate_ids": 4,
    "missing_event_id": 2,
    "missing_user_id": 3,
    "missing_session_id": 2,
    "invalid_timestamp": 3,
    "invalid_module": 2,
    "invalid_event_type": 1,
}


def _weighted(rng: random.Random, weights: dict):
    keys = list(weights)
    return rng.choices(keys, weights=[weights[k] for k in keys], k=1)[0]


def _fmt(ts: datetime) -> str:
    return ts.strftime(TIMESTAMP_FORMAT)


def _clean_events(rng: random.Random, n_users: int, start: date, days: int) -> list[dict]:
    events = []
    for u in range(1, n_users + 1):
        user_id = f"U{u:04d}"
        activity = rng.uniform(0.10, 0.60)
        # Some invented users join partway through the period.
        first_day = 0 if rng.random() < 0.7 else rng.randrange(days)
        home_module = _weighted(rng, MODULE_WEIGHTS)
        session_no = 0
        for d in range(first_day, days):
            day = start + timedelta(days=d)
            weekday_factor = 0.35 if day.weekday() >= 5 else 1.0
            if rng.random() >= activity * weekday_factor:
                continue
            for _ in range(1 if rng.random() < 0.8 else 2):
                session_no += 1
                session_id = f"S{session_no:03d}"
                ts = datetime(day.year, day.month, day.day, tzinfo=timezone.utc) + timedelta(
                    hours=rng.randrange(7, 20), minutes=rng.randrange(60), seconds=rng.randrange(60)
                )
                module = home_module if rng.random() < 0.6 else _weighted(rng, MODULE_WEIGHTS)
                action = _weighted(rng, FIRST_ACTION)
                for _ in range(MAX_EVENTS_PER_SESSION):
                    events.append(
                        {
                            "timestamp_utc": ts,
                            "user_id": user_id,
                            "session_id": session_id,
                            "module": module,
                            "event_type": action,
                        }
                    )
                    action = _weighted(rng, TRANSITIONS[action])
                    if action is None:
                        break
                    if action == "page_view" and rng.random() < 0.35:
                        module = _weighted(rng, MODULE_WEIGHTS)
                    ts = ts + timedelta(seconds=rng.randrange(4, 240))

    events.sort(key=lambda e: (e["timestamp_utc"], e["user_id"], e["session_id"]))
    rows = []
    for i, e in enumerate(events, start=1):
        rows.append({"event_id": f"E{i:06d}", **e, "timestamp_utc": _fmt(e["timestamp_utc"])})
    return rows


def _inject_defects(rng: random.Random, rows: list[dict], start: date) -> list[dict]:
    clean = list(rows)
    out = list(rows)
    next_id = len(rows) + 1

    def new_id() -> str:
        nonlocal next_id
        value = f"E{next_id:06d}"
        next_id += 1
        return value

    # Distinct source events so a re-sent copy never shares an id with a conflict.
    n_identical = DEFECT_PLAN["identical_duplicate_rows"]
    sources = rng.sample(clean, n_identical + DEFECT_PLAN["conflicting_duplicate_ids"])
    # Re-sent copies of existing events (identical payload).
    for row in sources[:n_identical]:
        out.append(dict(row))
    # Same event_id, different payload: the original and the copy are quarantined.
    for row in sources[n_identical:]:
        other = [t for t in EVENT_TYPES if t != row["event_type"]]
        out.append({**row, "event_type": rng.choice(other)})

    def bad_row(**changes) -> dict:
        base = dict(rng.choice(clean))
        base["event_id"] = new_id()
        base.update(changes)
        return base

    for _ in range(DEFECT_PLAN["missing_event_id"]):
        out.append(bad_row(event_id=""))
    for _ in range(DEFECT_PLAN["missing_user_id"]):
        out.append(bad_row(user_id=""))
    for _ in range(DEFECT_PLAN["missing_session_id"]):
        out.append(bad_row(session_id=""))
    day = start.isoformat()
    for text in (f"{day} 10:00:00", f"{day}T10:00:00-05:00", "2026-09-31T10:00:00Z"):
        out.append(bad_row(timestamp_utc=text))
    for _ in range(DEFECT_PLAN["invalid_module"]):
        out.append(bad_row(module="billing"))
    for _ in range(DEFECT_PLAN["invalid_event_type"]):
        out.append(bad_row(event_type="click"))

    assert len(out) - len(clean) == sum(DEFECT_PLAN.values())
    out.sort(key=lambda r: (r["timestamp_utc"], r["event_id"], r["event_type"]))
    return out


def generate_events(
    seed: int = DEFAULT_SEED,
    n_users: int = DEFAULT_USERS,
    start: date = DEFAULT_START,
    days: int = DEFAULT_DAYS,
    inject_defects: bool = True,
) -> list[dict]:
    if n_users < 1 or days < 1:
        raise ValueError("n_users and days must be positive")
    rng = random.Random(seed)
    rows = _clean_events(rng, n_users, start, days)
    if inject_defects:
        rows = _inject_defects(rng, rows, start)
    return rows


def write_events_csv(rows: list[dict], path: str | Path) -> Path:
    """Replace ``path`` with the rows; LF line endings for byte-identical reruns."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(REQUIRED_FIELDS), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return path


assert set(MODULE_WEIGHTS) == set(MODULES)
