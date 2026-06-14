"""The learner's wall-clock — resolving 'today' in the persona's own timezone.

Scheduling is anchored to dates ("start next week", "finish before my exam", a
module's complete-by date). Those must be computed in the *learner's* timezone,
not the server's: a learner in Asia/Kolkata asking at 01:00 their time is already
on "tomorrow" relative to a UTC server, so a server-local ``date.today()`` would
plan a day off (critique M4). Calendar block times (HH:MM) are already the
learner's local wall-clock, so only the date anchor needs this.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)


def today_in_timezone(tz_name: str | None) -> date:
    """The current calendar date in ``tz_name`` (an IANA zone like 'America/Chicago').

    Falls back to the UTC date when the zone is missing or unknown, so a bad or
    absent persona timezone degrades to a deterministic anchor instead of the
    arbitrary server-local date.
    """
    if tz_name:
        try:
            return datetime.now(ZoneInfo(tz_name)).date()
        except (ZoneInfoNotFoundError, ValueError) as exc:
            logger.warning("unknown persona timezone %r, falling back to UTC: %s", tz_name, exc)
    return datetime.now(UTC).date()
