import pandas as pd
import pytest

from usage_analytics.validation import load_and_validate, load_events, validate_events


def _frame(rows):
    columns = ["event_id", "timestamp_utc", "user_id", "session_id", "module", "event_type"]
    df = pd.DataFrame(rows, columns=columns).astype(object)
    df.insert(0, "source_record", range(1, len(df) + 1))
    return df


def test_dispositions_cover_every_raw_row(tiny):
    assert tiny.summary() == {
        "raw_rows": 26,
        "valid_events": 17,
        "collapsed_duplicate_rows": 1,
        "quarantined_rows": 2,
        "rejected_rows": 6,
    }


def test_reasons_and_source_records(tiny):
    # The fixture has no blank lines, so record = CSV line - 1 (see conftest.py).
    got = {(int(r.source_record), r.reason) for r in tiny.excluded.itertuples()}
    assert got == {
        (16, "conflicting_duplicate_id"),
        (17, "conflicting_duplicate_id"),
        (18, "missing_user_id"),
        (19, "missing_timestamp_utc"),
        (20, "invalid_timestamp"),
        (21, "invalid_module"),
        (22, "missing_event_id"),
        (23, "invalid_timestamp"),
    }


def test_identical_duplicate_kept_once_and_conflict_removed(tiny):
    ids = list(tiny.valid["event_id"])
    assert ids.count("E13") == 1
    assert "E14" not in ids
    assert tiny.valid["event_id"].is_unique


def test_missing_user_is_not_a_user(tiny):
    assert "" not in set(tiny.valid["user_id"])
    assert set(tiny.valid["user_id"]) == {"U1", "U2", "U3", "U4", "U5"}


def test_valid_timestamps_are_utc(tiny):
    ts = tiny.valid["timestamp_utc"]
    assert str(ts.dt.tz) == "UTC"
    assert ts.min() == pd.Timestamp("2026-01-05T09:00:00Z")
    assert ts.max() == pd.Timestamp("2026-01-07T00:02:00Z")


@pytest.mark.parametrize(
    "text",
    ["2026-01-05 09:00:00", "2026-01-05T09:00:00+00:00", "2026-1-5T9:0:0Z", "2026-02-30T09:00:00Z"],
)
def test_timestamp_forms_outside_contract_are_rejected(text):
    result = validate_events(_frame([["A1", text, "U1", "S1", "catalog", "page_view"]]))
    assert len(result.valid) == 0
    assert list(result.excluded["reason"]) == ["invalid_timestamp"]


def test_whitespace_only_field_counts_as_missing():
    result = validate_events(_frame([["A1", "2026-01-05T09:00:00Z", "   ", "S1", "catalog", "search"]]))
    assert list(result.excluded["reason"]) == ["missing_user_id"]


def test_three_copies_with_one_conflict_quarantines_all():
    row = ["A1", "2026-01-05T09:00:00Z", "U1", "S1", "catalog", "search"]
    result = validate_events(_frame([row, row, row[:-1] + ["export"]]))
    assert result.summary()["quarantined_rows"] == 3
    assert result.collapsed_rows == 0
    assert len(result.valid) == 0


def test_unknown_event_type_rejected():
    result = validate_events(_frame([["A1", "2026-01-05T09:00:00Z", "U1", "S1", "catalog", "click"]]))
    assert list(result.excluded["reason"]) == ["invalid_event_type"]


def test_missing_column_is_an_error(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("event_id,timestamp_utc,user_id,module,event_type\n", encoding="utf-8")
    with pytest.raises(ValueError, match="session_id"):
        load_events(path)


HEADER = "event_id,timestamp_utc,user_id,session_id,module,event_type\n"


@pytest.mark.parametrize(
    "timestamp",
    [
        "\u0662\u0660\u0662\u0666-01-02T03:00:00Z",  # Arabic-Indic digits in the year
        "\uff12\uff10\uff12\uff16-01-02T03:00:00Z",  # fullwidth digits in the year
    ],
    ids=["arabic-indic", "fullwidth"],
)
def test_non_ascii_digit_timestamp_is_rejected(tmp_path, timestamp):
    path = tmp_path / "one_row.csv"
    path.write_text(HEADER + f"A1,{timestamp},U1,S1,catalog,page_view\n", encoding="utf-8")
    result = load_and_validate(path)
    assert len(result.valid) == 0
    assert list(result.excluded["reason"]) == ["invalid_timestamp"]
    # The rejected-event diagnostics keep the raw text exactly as read.
    assert list(result.excluded["timestamp_utc"]) == [timestamp]


def test_blank_lines_do_not_shift_source_record(tmp_path):
    path = tmp_path / "blank_lines.csv"
    path.write_text(
        HEADER
        + "A1,2026-01-05T09:00:00Z,U1,S1,catalog,page_view\n"  # line 2, record 1
        + "\n"  # line 3, empty: skipped
        + "   \n"  # line 4, whitespace only: skipped
        + "A2,2026-01-05T09:01:00Z,,S1,catalog,search\n",  # line 5, record 2
        encoding="utf-8",
    )
    result = load_and_validate(path)
    assert result.raw_rows == 2
    # Skipped lines are not records, so the field is a record number, not a line number.
    assert "source_line" not in result.excluded.columns
    assert list(result.excluded["source_record"]) == [2]
    assert list(result.excluded["reason"]) == ["missing_user_id"]


def test_rejected_diagnostics_preserve_untrimmed_source_values():
    row = [" bad ", " 2026-01-05T09:00:00Z ", "   ", " S ", " catalog ", " search "]
    raw = _frame([row])
    before = raw.copy(deep=True)
    result = validate_events(raw)
    assert list(result.excluded["reason"]) == ["missing_user_id"]
    assert result.excluded.iloc[0][list(before.columns[1:])].tolist() == row
    pd.testing.assert_frame_equal(raw, before)


def test_conflicting_diagnostics_preserve_each_original_payload():
    first = [" same ", "2026-01-05T09:00:00Z", " U ", " S ", "catalog", " search "]
    second = ["same", "2026-01-05T09:00:00Z", "U", "S", "catalog", "export"]
    raw = _frame([first, second])
    result = validate_events(raw)
    assert result.summary()["quarantined_rows"] == 2
    assert result.excluded[list(raw.columns[1:])].values.tolist() == [first, second]
