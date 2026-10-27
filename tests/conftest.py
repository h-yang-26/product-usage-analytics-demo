"""Shared fixture loading.

Hand trace of tests/fixtures/tiny_events.csv (26 data rows, CSV lines 2-27).
Expected values in the tests are derived from this table, not from the
metric code. The file has no blank lines, so each row's ``source_record``
is its CSV line minus 1 (line 2 = record 1).

    line id   day    user sess module  type         disposition / role
    2    E01  01-05  U1   S1   catalog page_view    valid; U1/S1 full ordered funnel
    3    E02  01-05  U1   S1   catalog search       valid
    4    E03  01-05  U1   S1   catalog detail_view  valid
    5    E04  01-05  U2   S1   orders  detail_view  valid; U2/S1 actions out of order
    6    E05  01-05  U2   S1   orders  search       valid  (S1 reused by another user)
    7    E06  01-05  U2   S1   orders  page_view    valid  -> U2/S1 reaches stage 1 only
    8    E07  01-05  U3   S2   catalog page_view    valid; U3/S2 repeated actions
    9    E08  01-05  U3   S2   catalog page_view    valid
    10   E09  01-05  U3   S2   catalog search       valid
    11   E10  01-05  U3   S2   catalog search       valid  -> U3/S2 reaches stage 2
    12   E11  01-05  U4   S3   support page_view    valid; equal timestamps
    13   E12  01-05  U4   S3   support search       valid  -> same second, stage 1 only
    14   E23  01-05  U3   S7   support page_view    valid; U3 in two modules on 01-05
    15   E13  01-06  U1   S4   reports page_view    valid (kept copy)
    16   E13  01-06  U1   S4   reports page_view    collapsed identical duplicate
    17   E14  01-06  U1   S4   reports search       quarantined (conflict)
    18   E14  01-06  U1   S4   reports export       quarantined (conflict)
    19   E15  01-06  --   S5   catalog page_view    rejected missing_user_id
    20   E16  ----   U2   S5   catalog page_view    rejected missing_timestamp_utc
    21   E17  bad    U2   S5   catalog search       rejected invalid_timestamp
    22   E18  01-06  U2   S5   billing page_view    rejected invalid_module
    23   ---  01-06  U2   S5   catalog detail_view  rejected missing_event_id
    24   E22  -05:00 U2   S5   catalog search       rejected invalid_timestamp (not UTC "Z")
    25   E19  01-06  U5   S6   orders  page_view    valid; 23:59 on 01-06
    26   E20  01-07  U5   S6   orders  search       valid; session crosses midnight
    27   E21  01-07  U5   S6   orders  detail_view  valid

Totals: 17 valid, 1 collapsed, 2 quarantined, 6 rejected = 26 raw rows.
"""

from pathlib import Path

import pytest

from usage_analytics.validation import load_and_validate

FIXTURE = Path(__file__).parent / "fixtures" / "tiny_events.csv"


@pytest.fixture(scope="session")
def tiny():
    return load_and_validate(FIXTURE)
