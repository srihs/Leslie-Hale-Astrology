"""
Timezone display correctness (apps/bookings/availability.py:tz_label).

The rule under test, straight from that function's own docstring: the
abbreviation shown for an appointment must be computed from *the
appointment's own instant*, not from "now" — Pacific/Auckland crosses
DST (NZST <-> NZDT) every year, so a booking made in one half of the year
for an appointment in the other half must still show the *appointment's*
abbreviation. This was a real bug caught during the build; freezing time
away from the appointment's own date is what would have caught it, and a
test that only ever freezes time to match the appointment's own season
would pass even with the bug back in place.
"""

from __future__ import annotations

from datetime import datetime
from datetime import timezone as dt_timezone
from zoneinfo import ZoneInfo

import pytest
from freezegun import freeze_time

from apps.bookings.availability import tz_label

AUCKLAND = ZoneInfo("Pacific/Auckland")

# 15 January 2026, 01:00 UTC = 14:00 NZDT (daylight saving is in effect
# in the New Zealand summer).
NZDT_INSTANT = datetime(2026, 1, 15, 1, 0, tzinfo=dt_timezone.utc)

# 15 July 2026, 01:00 UTC = 13:00 NZST (daylight saving is not in effect
# in the New Zealand winter).
NZST_INSTANT = datetime(2026, 7, 15, 1, 0, tzinfo=dt_timezone.utc)


@freeze_time("2026-07-20 00:00:00")  # "now" is deep in NZST — the opposite season
def test_label_for_a_summer_appointment_is_nzdt_even_when_booked_in_winter():
    assert tz_label(AUCKLAND, at=NZDT_INSTANT) == "NZDT"


@freeze_time("2026-01-20 00:00:00")  # "now" is deep in NZDT — the opposite season
def test_label_for_a_winter_appointment_is_nzst_even_when_booked_in_summer():
    assert tz_label(AUCKLAND, at=NZST_INSTANT) == "NZST"


@freeze_time("2026-07-15 01:00:00+00:00")
def test_label_defaults_to_now_when_no_instant_is_given():
    """`at` is optional (booking_panel_context always passes it once a slot
    is selected, but tz_label itself must still degrade sensibly before
    that) — confirms the fallback is really `timezone.now()`, not a fixed
    default."""
    assert tz_label(AUCKLAND) == "NZST"


@pytest.mark.parametrize(
    "instant, expected",
    [
        (NZDT_INSTANT, "NZDT"),
        (NZST_INSTANT, "NZST"),
    ],
)
def test_label_is_a_pure_function_of_the_instant_not_wall_clock_time(instant, expected):
    """No freeze_time at all here — proves the result is fully determined
    by `at` regardless of whatever moment the test happens to run."""
    assert tz_label(AUCKLAND, at=instant) == expected
