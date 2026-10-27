# Sample data

**Synthetic demonstration; not actual company analytics.**

`synthetic_events.csv` is written by `python generate_sample_data.py` (seed `20260901`). Every user, session, and event is invented. User ids are pseudonymous codes (`U0001`); there are no names, email addresses, or device ids.

The generator deliberately adds 27 contract-violating rows (identical re-sent rows, conflicting duplicate ids, missing fields, malformed or non-UTC timestamps, unknown module/event values). Together with the 4 original rows that the conflicting copies collide with, 31 of the 5,766 rows are not valid events (10 collapsed, 8 quarantined, 13 rejected). This gives the dashboard's data-quality panel something to show. See `DEFECT_PLAN` in `usage_analytics/generator.py`.

Re-running the generator replaces the file; the same seed produces identical bytes.
