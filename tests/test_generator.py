import subprocess
import sys
from pathlib import Path

import pytest

from usage_analytics.generator import DEFECT_PLAN, generate_events, write_events_csv
from usage_analytics.validation import load_and_validate

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "data" / "synthetic_events.csv"


def test_same_seed_gives_identical_bytes(tmp_path):
    a = write_events_csv(generate_events(), tmp_path / "a.csv")
    b = write_events_csv(generate_events(), tmp_path / "b.csv")
    assert a.read_bytes() == b.read_bytes()


def test_different_seed_changes_output(tmp_path):
    a = write_events_csv(generate_events(seed=1), tmp_path / "a.csv")
    b = write_events_csv(generate_events(seed=2), tmp_path / "b.csv")
    assert a.read_bytes() != b.read_bytes()


def test_committed_sample_matches_generator(tmp_path):
    fresh = write_events_csv(generate_events(), tmp_path / "fresh.csv")
    assert SAMPLE.read_bytes() == fresh.read_bytes()


def test_sample_shape_and_injected_defects(tmp_path):
    result = load_and_validate(write_events_csv(generate_events(), tmp_path / "s.csv"))
    users = result.valid["user_id"]
    assert 100 <= users.nunique() <= 250
    # [0-9], not \d: \d also matches non-ASCII digits.
    assert users.str.fullmatch(r"U[0-9]{4}").all()
    assert result.valid["timestamp_utc"].dt.date.nunique() >= 14

    counts = {
        reason: int(n)
        for reason, n in result.excluded.groupby("reason").size().items()
    }
    # Each conflicting id quarantines the original row and its altered copy.
    assert counts.pop("conflicting_duplicate_id") == 2 * DEFECT_PLAN["conflicting_duplicate_ids"]
    expected_rejections = {
        k: v
        for k, v in DEFECT_PLAN.items()
        if k not in ("identical_duplicate_rows", "conflicting_duplicate_ids")
    }
    assert counts == expected_rejections
    assert result.collapsed_rows == DEFECT_PLAN["identical_duplicate_rows"]


def test_clean_generation_has_no_exclusions(tmp_path):
    result = load_and_validate(
        write_events_csv(generate_events(inject_defects=False), tmp_path / "c.csv")
    )
    assert result.excluded.empty
    assert result.collapsed_rows == 0


def _run_generator(*args):
    return subprocess.run(
        [sys.executable, str(ROOT / "generate_sample_data.py"), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    "seed", ["\u0664\u0662", "\uff14\uff12"], ids=["arabic-indic", "fullwidth"]
)
def test_seed_argument_rejects_non_ascii_digits(tmp_path, seed):
    # int() alone would read both as 42.
    out = tmp_path / "events.csv"
    completed = _run_generator("--seed", seed, "--output", str(out))
    assert completed.returncode == 2
    assert "seed" in completed.stderr
    assert not out.exists()


def test_seed_argument_accepts_ascii_integer(tmp_path):
    out = tmp_path / "events.csv"
    completed = _run_generator("--seed", "42", "--output", str(out))
    assert completed.returncode == 0, completed.stderr
    assert out.exists()
