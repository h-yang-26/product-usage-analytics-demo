"""Load and validate raw event rows against the event contract.

Every raw row receives exactly one disposition:

* ``valid``      - accepted event (one row per distinct event_id)
* ``collapsed``  - extra copy of an event_id whose rows are all identical
* ``quarantined``- any row of an event_id whose copies disagree
* ``rejected``   - a row that fails a required-field rule

Checks run in this order and a row gets the first failing reason only:

1. ``missing_event_id``
2. duplicate handling by event_id (collapse identical / quarantine conflicting)
3. ``missing_<field>`` for the remaining required fields, in column order
4. ``invalid_timestamp`` (not exactly ``YYYY-MM-DDTHH:MM:SSZ`` with ASCII
   digits, or not a real date)
5. ``invalid_module``
6. ``invalid_event_type``

Validation always covers the whole loaded file; dashboard filters do not
change these counts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .schema import EVENT_TYPES, MODULES, PAYLOAD_FIELDS, REQUIRED_FIELDS, TIMESTAMP_FORMAT

CONFLICT_REASON = "conflicting_duplicate_id"
# [0-9], not \d: \d and strptime both accept non-ASCII digits such as "٢٠٢٦".
TIMESTAMP_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")


@dataclass(frozen=True)
class ValidationResult:
    valid: pd.DataFrame
    """Accepted events; ``timestamp_utc`` is a timezone-aware UTC datetime."""
    excluded: pd.DataFrame
    """Raw rows that are quarantined or rejected, with ``disposition`` and ``reason``."""
    raw_rows: int
    collapsed_rows: int

    def summary(self) -> dict:
        quarantined = int((self.excluded["disposition"] == "quarantined").sum())
        rejected = int((self.excluded["disposition"] == "rejected").sum())
        return {
            "raw_rows": self.raw_rows,
            "valid_events": len(self.valid),
            "collapsed_duplicate_rows": self.collapsed_rows,
            "quarantined_rows": quarantined,
            "rejected_rows": rejected,
        }

    def reason_counts(self) -> pd.DataFrame:
        counts = (
            self.excluded.groupby(["disposition", "reason"]).size().rename("rows").reset_index()
        )
        return counts.sort_values(["disposition", "reason"], ignore_index=True)


def load_events(path: str | Path) -> pd.DataFrame:
    """Read the event CSV as text; blank cells stay empty strings, not NaN.

    Empty and whitespace-only lines are skipped by the reader and are not
    records, so ``source_record`` (1 = first data record after the header)
    can differ from the physical line number.
    """
    raw = pd.read_csv(path, dtype=str, keep_default_na=False)
    missing_columns = [c for c in REQUIRED_FIELDS if c not in raw.columns]
    if missing_columns:
        raise ValueError(f"{path}: missing required columns: {', '.join(missing_columns)}")
    raw = raw[list(REQUIRED_FIELDS)].astype(object)
    raw.insert(0, "source_record", range(1, len(raw) + 1))
    return raw


def _parse_timestamp(text: str) -> datetime | None:
    # strptime alone accepts unpadded fields such as "2026-9-1T8:0:0Z".
    if not TIMESTAMP_PATTERN.fullmatch(text):
        return None
    try:
        return datetime.strptime(text, TIMESTAMP_FORMAT).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _field_reason(row: pd.Series) -> str | None:
    for field in PAYLOAD_FIELDS:
        if row[field] == "":
            return f"missing_{field}"
    if _parse_timestamp(row["timestamp_utc"]) is None:
        return "invalid_timestamp"
    if row["module"] not in MODULES:
        return "invalid_module"
    if row["event_type"] not in EVENT_TYPES:
        return "invalid_event_type"
    return None


def validate_events(raw: pd.DataFrame) -> ValidationResult:
    """Apply the event contract to rows produced by :func:`load_events`."""
    rows = raw.copy()
    for field in REQUIRED_FIELDS:
        rows[field] = rows[field].map(lambda v: "" if v is None else str(v).strip())

    excluded_parts = []

    no_id = rows["event_id"] == ""
    excluded_parts.append(rows[no_id].assign(disposition="rejected", reason="missing_event_id"))
    with_id = rows[~no_id]

    # Distinct payloads per event_id: more than one means the copies conflict.
    distinct = with_id.drop_duplicates(subset=list(REQUIRED_FIELDS), keep="first")
    payloads_per_id = distinct["event_id"].value_counts()
    conflicting_ids = set(payloads_per_id[payloads_per_id > 1].index)

    conflicting = with_id["event_id"].isin(conflicting_ids)
    excluded_parts.append(
        with_id[conflicting].assign(disposition="quarantined", reason=CONFLICT_REASON)
    )
    candidates = distinct[~distinct["event_id"].isin(conflicting_ids)]
    collapsed_rows = int((~conflicting).sum()) - len(candidates)

    reasons = candidates.apply(_field_reason, axis=1) if len(candidates) else pd.Series(dtype=object)
    failed = reasons.notna()
    excluded_parts.append(candidates[failed].assign(disposition="rejected", reason=reasons[failed]))

    valid = candidates[~failed].copy()
    valid["timestamp_utc"] = pd.to_datetime(
        [_parse_timestamp(t) for t in valid["timestamp_utc"]], utc=True
    )
    valid = valid.sort_values(["timestamp_utc", "event_id"], ignore_index=True)

    excluded = pd.concat(excluded_parts, ignore_index=True)
    excluded = excluded.sort_values("source_record", ignore_index=True)
    # Compare and validate trimmed text, but retain the original text in review
    # diagnostics. Record identity, not a normalized business ID, joins it back.
    original = raw.set_index("source_record")
    for field in REQUIRED_FIELDS:
        excluded[field] = excluded["source_record"].map(original[field])

    return ValidationResult(
        valid=valid,
        excluded=excluded,
        raw_rows=len(rows),
        collapsed_rows=collapsed_rows,
    )


def load_and_validate(path: str | Path) -> ValidationResult:
    return validate_events(load_events(path))
