"""Calendar-grounded, module-level study-plan algorithm.

Pure functions over the course's modules and the learner's *real* weekly
calendar (master-plan §13). Nothing is hardcoded or guessed:

- **Capacity is read from the calendar**, not a multiplier. Study time = the
  learner's dedicated study blocks (``category=learning``) plus genuine free gaps
  within working hours, on their preferred study days. The one committed week is
  treated as the repeating weekly template.
- **Per-module time is computed from that module's content** (objectives +
  skills) and scaled by the learner's chosen pace. A modest safety headroom is
  applied internally and is **not** surfaced to the learner.
- **Modules are scheduled sequentially** into the repeating weekly slots; each
  gets the concrete sessions that cover it and a "complete before" date.

An LLM only narrates the result, every number here is computed and auditable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

from app.agent.contracts import (
    ModulePlan,
    Pace,
    ScheduledBlock,
    StudyPlan,
    StudySession,
)
from app.catalog.loader import default_catalog_path
from app.config import Settings, get_settings
from app.workiq.models import DaySchedule, Persona

# --- Module time estimate (computed from content; headroom is internal) ---
MODULE_BASE_MINUTES = 40
MINUTES_PER_OBJECTIVE = 18
MINUTES_PER_SKILL = 8
SAFETY_HEADROOM = 1.5  # internal buffer so estimates run generous, never surfaced
SESSION_GRANULARITY = 15  # round estimates to a tidy quarter-hour
PACE_FACTOR: dict[Pace, float] = {Pace.SLOWER: 1.35, Pace.NORMAL: 1.0, Pace.FASTER: 0.75}

# --- Calendar interpretation ---
_STUDY_CATEGORIES = {"learning"}  # dedicated study blocks already in the calendar
_WEEKDAY_ORDER = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_WEEKDAY_INDEX = {d: i for i, d in enumerate(_WEEKDAY_ORDER)}
_MIN_SLOT_MINUTES = 20  # ignore slivers too short to study in


@dataclass(frozen=True)
class ModuleInfo:
    """A course module with the fields the planner needs."""

    module_id: str
    title: str
    order: int
    objectives: tuple[str, ...]
    skills: int
    prereq_module_ids: tuple[str, ...]


@lru_cache(maxsize=16)
def course_modules(catalog_path: str, catalog_id: str) -> tuple[ModuleInfo, ...]:
    """Modules for a course, in prereq/teaching order (cached)."""
    data = json.loads(Path(catalog_path).read_text(encoding="utf-8"))
    for vertical in data["verticals"]:
        for course in vertical["courses"]:
            if course["id"] != catalog_id:
                continue
            mods = [
                ModuleInfo(
                    module_id=m["id"],
                    title=m["title"],
                    order=m.get("order", 0),
                    objectives=tuple(m.get("objectives", [])),
                    skills=len(m.get("grounded_skills", [])),
                    prereq_module_ids=tuple(m.get("prereq_module_ids", [])),
                )
                for m in course.get("modules", [])
            ]
            return tuple(sorted(mods, key=lambda m: m.order))
    return ()


# ── 1. Per-module time (content + pace; headroom internal) ─────────────────────


def estimate_module_minutes(module: ModuleInfo, pace: Pace) -> int:
    """Minutes for a module from its own content, scaled by pace.

    Varies per module (more objectives/skills ⇒ more time). The internal safety
    headroom keeps estimates generous; it is deliberately not exposed.
    """
    content = (
        MODULE_BASE_MINUTES
        + MINUTES_PER_OBJECTIVE * len(module.objectives)
        + MINUTES_PER_SKILL * module.skills
    )
    raw = content * SAFETY_HEADROOM * PACE_FACTOR[pace]
    rounded = round(raw / SESSION_GRANULARITY) * SESSION_GRANULARITY
    return max(SESSION_GRANULARITY, int(rounded))


# ── 2. Weekly study slots from the real calendar ───────────────────────────────


def _to_min(hhmm: str) -> int:
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)


def _to_hhmm(total: int) -> str:
    return f"{total // 60:02d}:{total % 60:02d}"


def _slot_of(start_minute: int) -> str:
    if start_minute < 12 * 60:
        return "Morning"
    if start_minute < 17 * 60:
        return "Afternoon"
    return "Evening"


@dataclass(frozen=True)
class WeeklySlot:
    """A recurring weekly study opportunity drawn from the calendar."""

    day: str
    start: int  # minutes since midnight
    end: int
    source: str

    @property
    def minutes(self) -> int:
        return self.end - self.start


def _day_study_slots(day: DaySchedule, work_start: int, work_end: int) -> list[WeeklySlot]:
    """Study openings in one day: dedicated study blocks + genuine free gaps."""
    slots: list[WeeklySlot] = []
    cursor = work_start
    for block in sorted(day.blocks, key=lambda b: _to_min(b.start)):
        bs, be = _to_min(block.start), _to_min(block.end)
        if bs > cursor:  # an unscheduled gap is free to study in
            slots.append(WeeklySlot(day.day, cursor, bs, "free time"))
        if block.category in _STUDY_CATEGORIES:  # an existing study block
            slots.append(WeeklySlot(day.day, bs, be, block.title))
        cursor = max(cursor, be)
    if cursor < work_end:
        slots.append(WeeklySlot(day.day, cursor, work_end, "free time"))
    return [s for s in slots if s.minutes >= _MIN_SLOT_MINUTES]


def weekly_study_slots(
    persona: Persona, exclude_days: frozenset[str] = frozenset()
) -> list[WeeklySlot]:
    """The learner's recurring weekly study slots, grounded in their calendar.

    Restricted to their preferred study days when those have any opening; the one
    committed week is the repeating template for every week of the plan.
    ``exclude_days`` (a natural-language edit) drops those weekdays entirely.
    """
    work_start = _to_min(persona.work_context.working_hours.start)
    work_end = _to_min(persona.work_context.working_hours.end)
    preferred = {str(d) for d in persona.learning_preferences.preferred_study_days}

    by_day: dict[str, list[WeeklySlot]] = {}
    for day in persona.schedule.days:
        if day.day in exclude_days:
            continue
        opened = _day_study_slots(day, work_start, work_end)
        if opened:
            by_day[day.day] = opened

    # Prefer the learner's chosen study days if any of them have openings.
    chosen_days = [d for d in by_day if d in preferred] or list(by_day)
    slots = [s for d in chosen_days for s in by_day[d]]
    return sorted(slots, key=lambda s: (_WEEKDAY_INDEX.get(s.day, 9), s.start))


# ── 3. Schedule modules sequentially into the repeating weekly slots ───────────


def _capacity_reason(slots: list[WeeklySlot], weekly_hours: float) -> str:
    if not slots:
        return "No free study time was found in your calendar."
    shown = ", ".join(
        f"{s.day.capitalize()} {_to_hhmm(s.start)}–{_to_hhmm(s.end)}" for s in slots[:4]
    )
    return (
        f"I found {weekly_hours:g} h of study time already in your week, {shown}"
        + ("…" if len(slots) > 4 else "")
        + ". I'll reuse this every week."
    )


def schedule_modules(
    estimates: list[tuple[ModuleInfo, int]],
    slots: list[WeeklySlot],
    start_date: date,
) -> list[ModulePlan]:
    """Fill the repeating weekly slots with modules in order; deadline per module."""
    if not slots:
        return []
    plans: list[ModulePlan] = []
    week = 1
    slot_idx = 0
    cursor = slots[0].start  # position within the current slot

    for seq, (module, minutes) in enumerate(estimates, start=1):
        remaining = minutes
        blocks: list[ScheduledBlock] = []
        last_week = week
        while remaining > 0:
            slot = slots[slot_idx]
            avail = slot.end - cursor
            if avail < _MIN_SLOT_MINUTES:  # slot exhausted → advance
                slot_idx += 1
                if slot_idx >= len(slots):  # next repeating week
                    slot_idx = 0
                    week += 1
                cursor = slots[slot_idx].start
                continue
            take = min(remaining, avail)
            blocks.append(
                ScheduledBlock(
                    week=week,
                    day=slot.day,
                    start=_to_hhmm(cursor),
                    end=_to_hhmm(cursor + take),
                    minutes=take,
                )
            )
            last_week = week
            cursor += take
            remaining -= take
        # Complete-before = end of the last week the module occupies.
        complete_before = start_date + timedelta(days=last_week * 7)
        plans.append(
            ModulePlan(
                module_id=module.module_id,
                title=module.title,
                sequence=seq,
                estimated_minutes=minutes,
                scheduled=blocks,
                complete_before=complete_before.isoformat(),
                objectives=list(module.objectives),
            )
        )
    return plans


# ── Build the full plan ────────────────────────────────────────────────────────


def build_study_plan(
    *,
    catalog_id: str,
    title: str,
    cert: str,
    persona: Persona,
    pace: Pace = Pace.NORMAL,
    start_date: date,
    exclude_days: frozenset[str] = frozenset(),
    settings: Settings | None = None,
) -> StudyPlan | None:
    """Assemble the calendar-grounded, module-level plan, or None if no modules."""
    settings = settings or get_settings()
    path = str(settings.athenaeum_catalog_path or default_catalog_path())
    modules = course_modules(path, catalog_id)
    if not modules:
        return None

    estimates = [(m, estimate_module_minutes(m, pace)) for m in modules]
    total_minutes = sum(mins for _, mins in estimates)

    slots = weekly_study_slots(persona, exclude_days)
    weekly_minutes = sum(s.minutes for s in slots)
    weekly_hours = round(weekly_minutes / 60, 1) if weekly_minutes else 0.0

    module_plans = schedule_modules(estimates, slots, start_date)
    weeks = max((b.week for m in module_plans for b in m.scheduled), default=0)

    sessions = [
        StudySession(
            day=s.day,
            slot=_slot_of(s.start),
            start=_to_hhmm(s.start),
            end=_to_hhmm(s.end),
            duration_minutes=s.minutes,
            source=s.source,
        )
        for s in slots
    ]

    return StudyPlan(
        catalog_id=catalog_id,
        title=title,
        cert=cert,
        pace=pace,
        weekly_study_hours=weekly_hours,
        total_hours=round(total_minutes / 60, 1),
        weeks=weeks,
        start_date=start_date.isoformat(),
        modules=module_plans,
        sessions=sessions,
        capacity_reason=_capacity_reason(slots, weekly_hours),
    )
