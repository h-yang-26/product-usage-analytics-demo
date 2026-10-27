"""Headless dashboard runs with Streamlit's AppTest (no browser)."""

import logging
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from usage_analytics.schema import SYNTHETIC_LABEL

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).parent / "fixtures" / "tiny_events.csv"


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("USAGE_EVENTS_CSV", str(FIXTURE))
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)
    at.run()
    assert not at.exception
    return at


def _metrics(at):
    return {mt.label: mt.value for mt in at.metric}


def test_default_view_uses_full_fixture(app):
    values = _metrics(app)
    assert values["Valid events in scope"] == "17"
    assert values["Distinct users in scope"] == "5"
    assert values["Funnel entry sessions"] == "7"
    assert values["Rejected rows"] == "6"
    assert values["Quarantined rows"] == "2"
    assert any(SYNTHETIC_LABEL in w.value for w in app.warning)


def test_empty_module_selection_renders(app):
    app.multiselect[0].set_value([]).run()
    assert not app.exception
    values = _metrics(app)
    assert values["Valid events in scope"] == "0"
    assert values["Funnel entry sessions"] == "0"
    # Validation scope is the whole file and does not follow the filters.
    assert values["Valid events"] == "17"
    # With no modules the module table is hidden, so the first table is the funnel.
    funnel = app.dataframe[0].value
    assert list(funnel["conversion_from_entry"]) == ["N/A", "N/A", "N/A"]


def test_date_filter_changes_scope(app):
    from datetime import date

    app.date_input[0].set_value((date(2026, 1, 7), date(2026, 1, 7))).run()
    assert not app.exception
    values = _metrics(app)
    assert values["Valid events in scope"] == "2"
    assert values["Funnel entry sessions"] == "0"


def test_sample_data_renders(monkeypatch):
    monkeypatch.delenv("USAGE_EVENTS_CSV", raising=False)
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.run()
    assert not at.exception
    assert _metrics(at)["Raw rows read"] == "5,766"


def test_no_streamlit_deprecation_warnings(monkeypatch):
    # Streamlit logs deprecations here (and only shows them in the browser
    # when client.showErrorDetails is "full"), so capture the logger directly.
    records = []
    handler = logging.Handler(level=logging.WARNING)
    handler.emit = records.append
    logger = logging.getLogger("streamlit.deprecation_util")
    logger.addHandler(handler)
    try:
        monkeypatch.setenv("USAGE_EVENTS_CSV", str(FIXTURE))
        at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)
        at.run()
        at.multiselect[0].set_value([]).run()
        assert not at.exception
    finally:
        logger.removeHandler(handler)
    assert [r.getMessage() for r in records] == []
