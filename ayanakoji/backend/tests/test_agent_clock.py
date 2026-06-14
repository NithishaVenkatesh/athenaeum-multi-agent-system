"""The learner-timezone clock (critique M4)."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.agent.clock import today_in_timezone


def test_resolves_date_in_the_named_timezone() -> None:
    for tz in ("America/Chicago", "Asia/Kolkata", "Europe/London"):
        assert today_in_timezone(tz) == datetime.now(ZoneInfo(tz)).date()


def test_far_east_zone_is_never_behind_far_west_zone() -> None:
    """Demonstrates the date actually depends on timezone: UTC+14 is same-or-ahead
    of UTC-11 at every instant, which a server-local date could not guarantee."""
    east = today_in_timezone("Pacific/Kiritimati")  # UTC+14
    west = today_in_timezone("Pacific/Pago_Pago")  # UTC-11
    assert east >= west


def test_unknown_timezone_falls_back_to_utc_date() -> None:
    assert today_in_timezone("Not/AZone") == datetime.now(UTC).date()


def test_missing_timezone_falls_back_to_utc_date() -> None:
    assert today_in_timezone(None) == datetime.now(UTC).date()
    assert today_in_timezone("") == datetime.now(UTC).date()
