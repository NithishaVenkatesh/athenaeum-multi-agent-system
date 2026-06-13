"""Parse natural-language schedule adjustments into structured plan edits.

Lets a learner say "start after June 30" or "skip Mondays this week" and have
the deterministic planner honor it (no LLM, fully testable). Returns a structured
adjustment the courses layer persists on the course, so the edit sticks and every
re-plan respects it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10, "october": 10,
    "nov": 11, "november": 11, "dec": 12, "december": 12,
}  # fmt: skip

_WEEKDAYS = {
    "mon": "mon", "monday": "mon", "tue": "tue", "tues": "tue", "tuesday": "tue",
    "wed": "wed", "weds": "wed", "wednesday": "wed", "thu": "thu", "thur": "thu",
    "thurs": "thu", "thursday": "thu", "fri": "fri", "friday": "fri",
    "sat": "sat", "saturday": "sat", "sun": "sun", "sunday": "sun",
}  # fmt: skip

# "after/post/from/starting <date>" — the lead-in decides if we start the day after.
_START_LEAD = (
    r"(after|post|from|starting|start(?:ing)?\s+(?:on|from)?"
    r"|begin(?:ning)?(?:\s+on)?|not\s+until|once\s+it'?s)"
)
_MONTH_DAY = re.compile(
    rf"{_START_LEAD}\s+(\d{{1,2}})(?:st|nd|rd|th)?\s+(\w+)"  # "after 30 June"
    rf"|{_START_LEAD}\s+(\w+)\s+(\d{{1,2}})(?:st|nd|rd|th)?",  # "after June 30"
    re.IGNORECASE,
)
_REL = re.compile(
    r"\b(?:start|begin|in)\b[^.]{0,20}?\bin\s+(\d+)\s+(day|week)s?"
    r"|\b(next\s+week|next\s+month|a\s+week\s+from\s+now)\b",
    re.IGNORECASE,
)
_AFTER_WORDS = ("after", "post", "not until", "once")

# A negation near a weekday means: don't study that day.
_EXCLUDE = re.compile(
    r"\b(skip|avoid|no|not|don'?t|without|remove|free\s+up|busy\s+on|can'?t|cannot|drop)\b"
    r"[^.]{0,25}?\b(mon|monday|tue|tues|tuesday|wed|weds|wednesday|thu|thur|thurs|thursday|"
    r"fri|friday|sat|saturday|sun|sunday)s?\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ScheduleAdjustment:
    """A structured plan edit derived from natural language."""

    start_date: date | None
    exclude_days: frozenset[str]
    note: str


def _resolve_month_day(month: int, day: int, today: date) -> date | None:
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    year = today.year
    try:
        candidate = date(year, month, day)
    except ValueError:
        return None
    # A month/day already well past gets bumped to next year.
    if candidate < today - timedelta(days=1):
        candidate = date(year + 1, month, day)
    return candidate


def _parse_start(text: str, today: date) -> date | None:
    lowered = text.lower()
    rel = _REL.search(text)
    if rel:
        if rel.group(1):  # "in N days/weeks"
            n, unit = int(rel.group(1)), rel.group(2).lower()
            return today + timedelta(days=n * (7 if unit.startswith("week") else 1))
        phrase = rel.group(2).lower()
        if "month" in phrase:
            return today + timedelta(days=30)
        return today + timedelta(days=7)  # next week / a week from now

    m = _MONTH_DAY.search(text)
    if not m:
        return None
    # Two alternations: (day, monthword) or (monthword, day).
    if m.group(2) and m.group(3) and m.group(3).lower() in _MONTHS:
        day, month = int(m.group(2)), _MONTHS[m.group(3).lower()]
    elif m.group(5) and m.group(6) and m.group(5).lower() in _MONTHS:
        month, day = _MONTHS[m.group(5).lower()], int(m.group(6))
    else:
        return None
    resolved = _resolve_month_day(month, day, today)
    if resolved is None:
        return None
    # "after/post June 30" means start the day AFTER.
    if any(w in lowered for w in _AFTER_WORDS):
        resolved = resolved + timedelta(days=1)
    return resolved


def _parse_excludes(text: str) -> frozenset[str]:
    return frozenset(_WEEKDAYS[m.group(2).lower()] for m in _EXCLUDE.finditer(text))


def parse_adjustment(text: str, *, today: date) -> ScheduleAdjustment | None:
    """Return a structured adjustment, or None if the text has no schedule edit."""
    start = _parse_start(text, today)
    excludes = _parse_excludes(text)
    if start is None and not excludes:
        return None
    parts: list[str] = []
    if start is not None:
        parts.append(f"start on {start.isoformat()}")
    if excludes:
        parts.append("skip " + ", ".join(sorted(excludes)))
    return ScheduleAdjustment(start_date=start, exclude_days=excludes, note="; ".join(parts))
