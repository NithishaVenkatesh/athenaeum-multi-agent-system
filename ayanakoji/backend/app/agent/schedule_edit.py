"""Parse natural-language schedule adjustments into structured plan edits.

Lets a learner say "start after June 30" or "skip Mondays this week" and have
the deterministic planner honor it (no LLM, fully testable). Returns a structured
adjustment the courses layer persists on the course, so the edit sticks and every
re-plan respects it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from app.agent.contracts import Pace

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

# Longest-first so "monday" matches before its prefix "mon" (alternation is ordered).
_WEEKDAY_ALT = (
    r"monday|mon|tuesday|tues|tue|wednesday|weds|wed|thursday|thurs|thur|thu|"
    r"friday|fri|saturday|sat|sunday|sun"
)
# A negation near a weekday means: don't study that day.
_EXCLUDE = re.compile(
    r"\b(skip|avoid|no|not|don'?t|without|remove|free\s+up|busy\s+on|can'?t|cannot|drop)\b"
    rf"[^.]{{0,25}}?\b({_WEEKDAY_ALT})s?\b",
    re.IGNORECASE,
)
# A skip/avoid cue, then a *run* of weekdays ("skip mon tue wed thu fri") so a single
# cue before a list excludes EVERY day, not just the first (red-team: multi-day drop).
_EXCLUDE_CUE = re.compile(
    r"\b(skip|avoid|without|remove|free\s+up|busy\s+on|can'?t|cannot|drop|no|not|don'?t)\b",
    re.IGNORECASE,
)
_DAY_RUN = re.compile(
    rf"\b(?:{_WEEKDAY_ALT})s?(?:[\s,]+(?:and\s+|&\s+|or\s+)?(?:{_WEEKDAY_ALT})s?)*",
    re.IGNORECASE,
)
_DAY_TOKEN = re.compile(rf"\b({_WEEKDAY_ALT})s?\b", re.IGNORECASE)

# "no weekends" / "skip the weekend" / "free up weekdays" — a negation cue near the
# group word expands to its member days (weekend → sat,sun; weekday → mon–fri), so a
# clearly-stated group exclusion is not silently dropped for lack of a day name.
_WEEKEND = frozenset({"sat", "sun"})
_WEEKDAY_SET = frozenset({"mon", "tue", "wed", "thu", "fri"})
_EXCLUDE_GROUP = re.compile(
    r"\b(skip|avoid|no|not|don'?t|without|remove|free\s+up|busy\s+on|can'?t|cannot|drop)\b"
    r"[^.]{0,25}?\b(weekends?|weekdays?)\b",
    re.IGNORECASE,
)

# "only on tuesday and thursday" / "just on tue/thu" → restrict to those days.
_ONLY_DAYS = re.compile(
    r"\b(only|just|exclusively|restrict\s+to|limit\s+to|schedule\s+(?:me\s+)?(?:only\s+)?on)\b"
    r"[^.]{0,40}?\b(mon|monday|tue|tues|tuesday|wed|weds|wednesday|thu|thur|thurs|thursday|"
    r"fri|friday|sat|saturday|sun|sunday)s?\b",
    re.IGNORECASE,
)

# "my exam is on July 10" / "target date: June 30" / "targeting Aug 15 for the cert"
_EXAM_DATE = re.compile(
    r"\b(?:exam|cert(?:ification)?|test|assessment|target(?:ing|ed|s)?)\b[^.]{0,40}?"
    r"(?:on|by|before|date\s*:?\s*)?\s*"
    r"(?:(\d{1,2})(?:st|nd|rd|th)?\s+(\w+)|(\w+)\s+(\d{1,2})(?:st|nd|rd|th)?)",
    re.IGNORECASE,
)

_ALL_WEEKDAYS = frozenset(_WEEKDAYS.values())

# Sane horizons so a deterministic parse can never overflow the C-int that ``date``
# math uses, nor emit a plan the builder would choke on. A relative start beyond ~3
# years is nonsense for a cert plan; a skip-week beyond ~2 years of weekly modules
# is a week that doesn't exist. These are clamps, not new per-attack patterns.
_MAX_START_DAYS_AHEAD = 366 * 3  # ~3 years; mirrors the audit's believable window
_MAX_PLAN_WEEK = 104  # two years of weekly modules is already generous

# "I'm occupied / busy / away in week 2" → drop that plan week, repacking later.
_BUSY = (
    r"(skip|avoid|remove|free\s+up|busy|occupied|unavailable|can'?t|cannot|drop|off|away|out|no)"
)
_BUSY_CUE = re.compile(rf"\b{_BUSY}\b", re.IGNORECASE)
# A "week N" mention, possibly a list ("weeks 2 and 3", "weeks 2, 3 and 4") or a
# range ("weeks 2-4"); the numbers are extracted/expanded in _parse_skip_weeks so a
# multi-week skip keeps every week, not just the first (R1).
_WEEK_LIST = re.compile(
    r"\bweeks?\s+(\d+(?:\s*(?:,|and|&|\+|to|through|thru|-|–|—)\s*\d+)*)", re.IGNORECASE
)
_WEEK_RANGE = re.compile(r"(\d+)\s*(?:to|through|thru|-|–|—)\s*(\d+)")
# How far a busy/skip cue may sit from a week mention and still bind to it as a skip.
_BUSY_PROXIMITY = 30
_MAX_WEEK_SPAN = 52  # never expand an absurd range

# Speed adjectives, only honored as a pace change when clearly *about* the pace.
_PACE_SLOWER = (" slower", " slow it down", " ease up", " lighter", " more relaxed",
                " spread it out", " less intensive", " gentler", " take it slow")  # fmt: skip
_PACE_FASTER = (" faster", " speed it up", " more intensive", " intensive", " quicker",
                " pick up the pace", " accelerate", " ramp it up")  # fmt: skip
_PACE_NORMAL = (" normal pace", " balanced pace", " standard pace", " regular pace",
                " moderate pace", " back to normal")  # fmt: skip
# A cue that the message is steering the plan's pace (vs. describing a course topic).
_PACE_CUES = (" pace", " make it", " go ", " revert", " switch to", " change to",
              " set it to", " keep it", " dial it", " move to")  # fmt: skip


def _speed_directive(t: str, phrases: tuple[str, ...]) -> bool:
    """True if a speed phrase is a pace directive, NOT an adverbial '<faster> to <do X>'.

    'make it faster to query Cosmos DB' describes an action (faster *at* querying), not the
    plan's pace, so a speed word immediately followed by ' to ' is not a pace change. A real
    pace ask ('make it faster', 'go quicker please') has no trailing infinitive.
    """
    for p in phrases:
        i = t.find(p)
        while i != -1:
            if not t[i + len(p) :].startswith(" to "):
                return True
            i = t.find(p, i + 1)
    return False


def parse_pace(text: str) -> Pace | None:
    """A requested pace change (slower|normal|faster), or None if the text isn't one.

    Requires a steering cue (the word "pace" or a verb like "make it / revert") so a topic
    mention ("an intensive security course") is not read as a pace edit, and a speed word
    used adverbially ("make it faster to query Cosmos DB") is a content question, not a pace
    edit, so it is excluded too.
    """
    t = f" {text.lower()} "
    has_cue = any(cue in t for cue in _PACE_CUES)
    if any(p in t for p in _PACE_NORMAL):
        return Pace.NORMAL
    wants_slower = has_cue and _speed_directive(t, _PACE_SLOWER)
    wants_faster = has_cue and _speed_directive(t, _PACE_FASTER)
    # A self-contradiction ("faster but also slower") is not a confident edit — refuse
    # to silently guess one direction; let the planner keep its current pace.
    if wants_slower and wants_faster:
        return None
    if wants_slower:
        return Pace.SLOWER
    if wants_faster:
        return Pace.FASTER
    return None


@dataclass(frozen=True)
class ScheduleAdjustment:
    """A structured plan edit derived from natural language."""

    start_date: date | None
    exclude_days: frozenset[str]
    note: str
    skip_weeks: frozenset[int] = field(default_factory=frozenset)
    exam_date: date | None = None


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
            # Parse defensively: the digit run is unbounded, so a huge value would
            # overflow ``timedelta`` (C int) and turn this turn replyless. Convert,
            # then clamp to a sane horizon — beyond ~3y is nonsense, so drop it.
            try:
                n = int(rel.group(1))
            except ValueError:
                return None
            unit = rel.group(2).lower()
            offset_days = n * (7 if unit.startswith("week") else 1)
            if offset_days < 0 or offset_days > _MAX_START_DAYS_AHEAD:
                return None
            return today + timedelta(days=offset_days)
        # The "next week / next month / a week from now" alternation lands in group 3,
        # not group 2 (group 2 is None here) — reading group 2 crashed the offline parser
        # and produced an empty, replyless turn for "start next week" (red-team crash).
        phrase = (rel.group(3) or "").lower()
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
    days = {_WEEKDAYS[m.group(2).lower()] for m in _EXCLUDE.finditer(text)}
    # A single skip cue followed by a run of weekdays excludes them all, not just the
    # first ("skip mon tue wed thu fri" -> all five), without grabbing a later unrelated
    # weekday ("skip monday, study tuesday" keeps tuesday).
    for cue in _EXCLUDE_CUE.finditer(text):
        run = _DAY_RUN.search(text[cue.end() : cue.end() + 60])
        if run and run.start() <= 10:
            days.update(_WEEKDAYS[d.group(1).lower()] for d in _DAY_TOKEN.finditer(run.group(0)))
    # "no weekends" / "free up weekdays" expand to their member days.
    for g in _EXCLUDE_GROUP.finditer(text):
        days |= _WEEKEND if g.group(2).lower().startswith("weekend") else _WEEKDAY_SET
    return frozenset(days)


def _parse_only_days(text: str) -> frozenset[str]:
    """Infer exclude_days from "only on tue and thu" (complement of the allowed set).

    Returns the set of weekdays to *exclude* (all days NOT in the allowed set),
    or an empty frozenset when no "only on" restriction is found.
    """
    matches = list(_ONLY_DAYS.finditer(text))
    if not matches:
        return frozenset()
    allowed: set[str] = set()
    for m in matches:
        allowed.add(_WEEKDAYS[m.group(2).lower()])
    # Also scan for any additional weekdays after the first match (e.g. "only tue and thu and fri")
    day_re = re.compile(
        r"\b(mon|monday|tue|tues|tuesday|wed|weds|wednesday|thu|thur|thurs|thursday|"
        r"fri|friday|sat|saturday|sun|sunday)s?\b",
        re.IGNORECASE,
    )
    first_trigger = matches[0].start()
    for dm in day_re.finditer(text, first_trigger):
        allowed.add(_WEEKDAYS[dm.group(1).lower()])
    return _ALL_WEEKDAYS - allowed


def _parse_exam_date(text: str, today: date) -> date | None:
    """Extract an exam/certification target date from natural language."""
    m = _EXAM_DATE.search(text)
    if not m:
        return None
    # Group layout: (day, monthword) or (monthword, day)
    if m.group(1) and m.group(2) and m.group(2).lower() in _MONTHS:
        day, month = int(m.group(1)), _MONTHS[m.group(2).lower()]
    elif m.group(3) and m.group(4) and m.group(3).lower() in _MONTHS:
        month, day = _MONTHS[m.group(3).lower()], int(m.group(4))
    else:
        return None
    return _resolve_month_day(month, day, today)


def _expand_week_list(spec: str) -> set[int]:
    """Every week number in a list/range spec ('2 and 3' → {2,3}; '2-4' → {2,3,4}).

    Both the range expansion AND the raw-endpoint sweep are clamped to a sane plan
    horizon, so an absurd 'weeks 1 to 999999' (or a bare 'week 99999999999999999999')
    can never re-enter past the range guard and brick the builder.
    """
    weeks: set[int] = set()
    for lo, hi in _WEEK_RANGE.findall(spec):
        a, b = int(lo), int(hi)
        if a <= b <= a + _MAX_WEEK_SPAN:
            weeks.update(w for w in range(a, b + 1) if 1 <= w <= _MAX_PLAN_WEEK)
    weeks.update(n for n in (int(x) for x in re.findall(r"\d+", spec)) if 1 <= n <= _MAX_PLAN_WEEK)
    return weeks


def _parse_skip_weeks(text: str) -> frozenset[int]:
    """Plan-week numbers the learner says they're occupied in.

    Handles a single week ('busy in week 2'), a list ('skip weeks 2 and 3',
    'weeks 2, 3 and 4'), and a range ('away weeks 2-4'). A week mention only counts as
    a skip when a busy/skip cue sits near it, so 'start in week 2' is never dropped.
    """
    weeks: set[int] = set()
    for m in _WEEK_LIST.finditer(text):
        window = text[max(0, m.start() - _BUSY_PROXIMITY) : m.end() + _BUSY_PROXIMITY]
        if _BUSY_CUE.search(window):
            weeks |= _expand_week_list(m.group(1))
    return frozenset(w for w in weeks if 1 <= w <= _MAX_PLAN_WEEK)


def _reconcile_excludes(
    explicit: frozenset[str], only_complement: frozenset[str]
) -> frozenset[str]:
    """Merge explicit skips with the 'only X' complement, never emitting all 7.

    An impossible day-restriction (every weekday excluded) leaves the plan with no
    schedulable day, which bricks the builder. So:
      * skip wins over a conflicting 'only' (e.g. "only mondays but skip monday" merges
        to all 7) — fall back to the explicit skip alone;
      * if even the explicit skip is all 7 ("skip every day"), there is no valid
        restriction to apply — drop it entirely (treat as no day-restriction).
    """
    combined = explicit | only_complement
    if combined != _ALL_WEEKDAYS:
        return combined
    if explicit and explicit != _ALL_WEEKDAYS:
        return explicit  # skip wins over the self-contradictory 'only'
    return frozenset()  # genuinely impossible — emit no day-restriction


def _build_adjustment(text: str, today: date) -> ScheduleAdjustment | None:
    start = _parse_start(text, today)
    excludes = _parse_excludes(text)
    only_excludes = _parse_only_days(text)
    skip_weeks = _parse_skip_weeks(text)
    exam_date = _parse_exam_date(text, today)
    # Merge explicit excludes with the complement-of-only-days excludes, reconciling
    # any self-contradiction so we never emit an unschedulable all-7 exclude set.
    combined_excludes = _reconcile_excludes(excludes, only_excludes)
    if start is None and not combined_excludes and not skip_weeks and exam_date is None:
        return None
    parts: list[str] = []
    if start is not None:
        parts.append(f"start on {start.isoformat()}")
    if combined_excludes:
        parts.append("skip " + ", ".join(sorted(combined_excludes)))
    if skip_weeks:
        parts.append("skip week(s) " + ", ".join(str(w) for w in sorted(skip_weeks)))
    if exam_date is not None:
        parts.append(f"exam on {exam_date.isoformat()}")
    return ScheduleAdjustment(
        start_date=start,
        exclude_days=combined_excludes,
        note="; ".join(parts),
        skip_weeks=skip_weeks,
        exam_date=exam_date,
    )


def parse_adjustment(text: str, *, today: date) -> ScheduleAdjustment | None:
    """Return a structured adjustment, or None if the text has no schedule edit.

    Defense-in-depth: ``is_plan_intent`` calls this on EVERY inbound message, so an
    uncaught exception here becomes a replyless/500 live turn. A parse failure means
    "no schedule edit", never a crashed turn — so any unexpected error falls back to
    None as a last resort. The clamps above mean well-formed inputs never reach here.
    """
    try:
        return _build_adjustment(text, today)
    except Exception:  # noqa: BLE001 — a parse failure must degrade to "no edit", not crash
        return None
