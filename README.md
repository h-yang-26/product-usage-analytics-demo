# Product Usage Analytics Demo

**Synthetic demonstration; not actual company analytics.**

A small Streamlit dashboard for a fictional multi-module B2B web application. It shows how raw timestamped events become clearly defined usage metrics: daily active users, event volume, module usage, and an ordered session funnel, with data-quality diagnostics kept separate from the usage numbers.

All data is generated from invented assumptions with a fixed seed. No real telemetry, company, customer, or person is represented.

## Quick start (Windows, PowerShell or cmd, from the project root)

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python generate_sample_data.py
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m streamlit run app.py
```

Streamlit prints a local URL (default `http://localhost:8501`). On macOS/Linux use `.venv/bin/python` instead of `.venv\Scripts\python`.

Tested by the implementing agent on Windows 11 Home (10.0.26300) with Python 3.13.15, pandas 3.1.0, Streamlit 1.66.1, Altair 6.3.0, pytest 9.1.1 (numpy 2.5.4 installed as a pandas dependency). `requirements.txt` pins exactly these versions; other versions, Python releases, and operating systems have not been tested.

`USAGE_EVENTS_CSV=<path>` makes the dashboard read a different event file with the same columns.

## Project layout

| Path | Purpose |
| --- | --- |
| `usage_analytics/schema.py` | Event contract: columns, allowed values, timestamp format, funnel steps, synthetic label |
| `usage_analytics/generator.py` | Seeded fictional event generator and deliberate defect injection |
| `usage_analytics/validation.py` | Loading, duplicate handling, and required-field validation |
| `usage_analytics/metrics.py` | Filters and metric calculations (no UI code) |
| `generate_sample_data.py` | Writes `data/synthetic_events.csv` (replaces the file each run); `--seed N` takes an ASCII integer, `--output PATH` another file |
| `app.py` | Streamlit dashboard; presentation only |
| `tests/fixtures/tiny_events.csv` | 26-row hand-traced fixture; trace table in `tests/conftest.py` |
| `tests/` | Validation, metric, generator, and headless dashboard tests |

The `usage_analytics` package has no Streamlit dependency, so a different interface could reuse the same metric definitions.

## Event schema

| Field | Meaning | Rule |
| --- | --- | --- |
| `event_id` | Identifier of one event | Required; repeated ids are deduplicated (below) |
| `timestamp_utc` | When the event happened | Required; exactly `YYYY-MM-DDTHH:MM:SSZ` with ASCII digits, a real calendar time |
| `user_id` | Pseudonymous user code, e.g. `U0042` | Required |
| `session_id` | Session code, numbered per user, e.g. `S003` | Required; only meaningful together with `user_id` |
| `module` | Application area | One of `catalog`, `orders`, `support`, `reports` |
| `event_type` | Action | One of `page_view`, `search`, `detail_view`, `export` |

`event_id`, `user_id`, and `session_id` are treated as opaque non-blank text; no digit or format check is applied to them. Blank or whitespace-only cells count as missing. Timestamp digits must be ASCII `0-9`; other Unicode digits (for example `٢٠٢٦` or fullwidth `２０２６`) are rejected as `invalid_timestamp`. Offsets other than `Z` (for example `+00:00` or `-05:00`) are rejected rather than converted, to keep one unambiguous UTC form.

## Validation contract

Every raw row gets exactly one outcome, so `raw rows = valid + collapsed + quarantined + rejected`:

1. **Rejected `missing_event_id`:** a row with no id cannot be deduplicated.
2. **Collapsed:** extra copies of an `event_id` whose rows are all identical. One copy continues to validation.
3. **Quarantined `conflicting_duplicate_id`:** every row of an `event_id` whose copies differ in any field. None of them is used.
4. **Rejected** (first failing rule only): `missing_<field>`, then `invalid_timestamp`, `invalid_module`, `invalid_event_type`.

Validation scope is the **whole loaded file**; date and module filters do not change these counts. Excluded rows never enter usage metrics, so a row with a missing `user_id` is never counted as a user. A missing required column makes the file unreadable and raises an error.

Excluded rows keep their raw text and a `source_record` number: 1 is the first data record after the header. Empty and whitespace-only lines are skipped by the CSV reader and are not records, so `source_record` is not a physical line number when a file contains such lines.

## Metric dictionary

All usage metrics use the same scope: valid events after the date and module filters.

| Metric | Definition | Denominator |
| --- | --- | --- |
| Date filter | UTC; includes the start date at 00:00:00 and excludes 00:00:00 on the day after the end date | n/a |
| Module filter | Events whose module is in the selected list; an empty list selects no events | n/a |
| Daily active users (DAU) | Distinct non-missing `user_id` per UTC day. Days in range with no events show 0 | n/a (count). Not the sum of per-module distinct users |
| Distinct users in scope | Distinct `user_id` across the whole selected range | n/a (count) |
| Event volume | Valid events per UTC day | n/a (count) |
| Module usage | Valid event count per module (events, not users) | Share = module events / all valid events in scope; `N/A` if zero |
| Session | A `(user_id, session_id)` pair | n/a |
| Funnel entry | Session with at least one `page_view` in scope | n/a |
| Funnel stage k | Session has `page_view`, `search`, `detail_view` (first k steps) at strictly increasing timestamps; counted once per session | n/a (count) |
| Conversion from entry | Stage-k sessions / entry sessions | Entry sessions; `N/A` when zero |

Funnel details:

- Equal timestamps do not establish order: a `search` at the same second as the `page_view` does not count.
- Repeated actions do not count a session twice.
- Matching takes the earliest qualifying event for each step, which finds an increasing sequence whenever one exists.
- Filters apply first. Narrowing the dates or modules can cut a session and remove steps that happened outside the selection; a session whose `page_view` is outside the scope is not an entry.

## What each chart tells a product administrator

- **Daily active users:** how many different people used the selected modules each day; the weekday/weekend pattern is part of the invented generator.
- **Event volume:** how much activity occurred; compare it with DAU to distinguish more users from more actions per user.
- **Module usage:** where activity concentrates; a heavy user can inflate one module's event count.
- **Ordered funnel:** how often a session that opens a page goes on to search and then view a detail.

## Tests

`pytest -q` runs:

- metric tests against the hand-traced fixture (valid sequence, out-of-order actions, repeated actions, equal timestamps, a reused session id, identical and conflicting duplicates, missing fields, a session cut by the date filter, a module filter, an empty selection, and a zero-denominator funnel);
- validation tests for timestamp formats (including non-ASCII digits), whitespace, triple duplicates, a missing column, and record numbering around blank lines;
- generator tests for byte-identical reruns, the committed sample matching the generator, user count, injected defect counts, and rejection of a non-ASCII `--seed`;
- headless dashboard runs with Streamlit `AppTest` (default view, empty module selection, date filter, sample data, and no Streamlit deprecation warnings logged).

Expected fixture values are derived by hand from the trace table in `tests/conftest.py`, not from the metric functions.

## Limitations

- The data is synthetic and small (about 5,700 events, 175 active invented users, 28 days). Patterns reflect generator assumptions only.
- No causal inference, attribution, forecasting, or statistical significance.
- No live collection, authentication, database, or production scheduling.
- Session ids are taken as given; there is no inactivity-timeout sessionization.
- Funnel steps are fixed in code (`FUNNEL_STEPS`); the dashboard does not let users edit them.

## Attribution and licenses

Uses [pandas](https://pandas.pydata.org/) (BSD-3-Clause), [Streamlit](https://streamlit.io/) (Apache-2.0), [Altair](https://altair-viz.github.io/) (BSD-3-Clause), and [pytest](https://pytest.org/) (MIT). No external data or design assets are included. No license has been chosen for this repository; no general reuse license is granted.
