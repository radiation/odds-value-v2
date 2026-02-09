from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


def nfl_week1_bucket_start_et(season_year: int) -> datetime:
    """Start of Week 1 bucket in ET: Tuesday 00:00 ET after Labor Day."""

    labor_day = date(season_year, 9, 1)
    while labor_day.weekday() != 0:  # Monday
        labor_day += timedelta(days=1)
    tuesday = labor_day + timedelta(days=1)
    return datetime(tuesday.year, tuesday.month, tuesday.day, tzinfo=ET)


def in_nfl_regular_season_window(dt: datetime, season_year: int) -> bool:
    """Return True if `dt` falls in the NFL regular season window.

    Uses Tue→Mon ET buckets; excludes preseason and playoffs.
    """

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)

    dt_et = dt.astimezone(ET)

    season_weeks = 18 if season_year >= 2021 else 17
    start_window = nfl_week1_bucket_start_et(season_year)
    end_window = start_window + timedelta(weeks=season_weeks)
    return start_window <= dt_et <= end_window


def nfl_regular_season_week(dt: datetime, season_year: int) -> int:
    """Return the 1-based NFL regular season week for `dt`.

    Week buckets are Tue 00:00 ET → next Tue 00:00 ET (i.e., Tue→Mon games).
    Raises ValueError if `dt` is outside the regular season window.
    """

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)

    dt_et = dt.astimezone(ET)
    start_window = nfl_week1_bucket_start_et(season_year)

    if dt_et < start_window:
        raise ValueError("dt is before NFL regular season window")

    season_weeks = 18 if season_year >= 2021 else 17
    end_window = start_window + timedelta(weeks=season_weeks)
    if dt_et > end_window:
        raise ValueError("dt is after NFL regular season window")

    delta = dt_et - start_window
    week_index = int(delta.total_seconds() // (7 * 24 * 60 * 60))
    return week_index + 1
