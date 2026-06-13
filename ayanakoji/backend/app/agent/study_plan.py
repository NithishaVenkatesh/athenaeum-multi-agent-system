"""Deterministic study-plan algorithm — workload-aware schedule for one course.

Pure functions over the course's modules and the learner's Work IQ signals
(master-plan §13). An LLM only narrates the result; every number here is computed,
so the plan is auditable and reproducible (A-104).

Pipeline:
1. estimate each module's minutes from its objectives, then **over-estimate ×2**.
2. capacity: weekly study hours from the learner's stated capacity, reduced when
   meeting load is heavy (>20 h/week ⇒ ×0.6), capped at 15 h/week.
3. allocate modules into weeks, packed to the weekly capacity, in prereq order.
4. place recurring study sessions in the learner's focus windows on their
   preferred study days, inside their preferred Morning/Afternoon slot.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.agent.contracts import ModulePlan, StudyPlan, StudySession, WeekPlan
from app.catalog.loader import default_catalog_path
from app.config import Settings, get_settings
from app.workiq.models import Persona

# --- Tunable constants (the plan's safety posture) ---
OVERESTIMATE_FACTOR = 2.0  # over-estimate every module by 2× (user requirement)
MODULE_BASE_MINUTES = 45  # reading/setup floor per module
MINUTES_PER_OBJECTIVE = 20  # hands-on time per learning objective
HEAVY_MEETING_THRESHOLD = 20.0  # meeting h/week above which capacity is reduced
HEAVY_CAPACITY_FACTOR = 0.6  # ×0.6 weekly study hours when meeting-heavy (§13)
WEEKLY_HOURS_CAP = 15.0  # never plan more than this per week
WEEKLY_HOURS_FLOOR = 1.0  # always plan at least this per week
SESSION_MIN_MINUTES = 30
SESSION_MAX_MINUTES = 150
_DEFAULT_STUDY_DAYS = ("tue", "wed", "thu")


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


# ── 1. Module time estimate (over-estimated ×2) ────────────────────────────────


def estimate_module_minutes(module: ModuleInfo) -> int:
    """Base time from objectives, then over-estimated by ``OVERESTIMATE_FACTOR``."""
    base = MODULE_BASE_MINUTES + MINUTES_PER_OBJECTIVE * len(module.objectives)
    return int(round(base * OVERESTIMATE_FACTOR))


# ── 2. Capacity from work load ─────────────────────────────────────────────────


@dataclass(frozen=True)
class Capacity:
    weekly_hours: float
    timeline_multiplier: float
    meeting_heavy: bool
    reason: str


def calculate_capacity(*, meeting_hours: float, base_weekly_hours: float) -> Capacity:
    """Weekly study hours after adjusting for meeting load (§13)."""
    base = max(base_weekly_hours, WEEKLY_HOURS_FLOOR)
    heavy = meeting_hours > HEAVY_MEETING_THRESHOLD
    weekly = base * (HEAVY_CAPACITY_FACTOR if heavy else 1.0)
    weekly = max(min(weekly, WEEKLY_HOURS_CAP), WEEKLY_HOURS_FLOOR)
    weekly = round(weekly, 1)
    timeline_multiplier = round(base / weekly, 2) if weekly else 1.0
    if heavy:
        reason = (
            f"Meeting load is heavy ({meeting_hours:.0f} h/week), so the weekly study "
            f"target is reduced from {base:.0f} h to {weekly:.0f} h — the plan runs "
            f"~{timeline_multiplier:.1f}× longer to stay realistic."
        )
    else:
        reason = (
            f"Meeting load is manageable ({meeting_hours:.0f} h/week), so the full "
            f"{weekly:.0f} h/week study target is used."
        )
    return Capacity(weekly, timeline_multiplier, heavy, reason)


# ── 3. Allocate modules into weeks ─────────────────────────────────────────────


def allocate_modules_to_weeks(
    estimates: list[tuple[ModuleInfo, int]], weekly_minutes: float
) -> tuple[list[ModulePlan], list[WeekPlan]]:
    """Pack modules into weeks up to the weekly capacity, in order.

    A module that alone exceeds a week's capacity still occupies its own week
    (we never split a module across weeks). Returns the per-module plan and the
    week roll-up.
    """
    module_plans: list[ModulePlan] = []
    weeks: list[WeekPlan] = []
    week_no = 1
    cur_ids: list[str] = []
    cur_titles: list[str] = []
    cur_total = 0

    def flush() -> None:
        nonlocal cur_ids, cur_titles, cur_total, week_no
        if cur_ids:
            weeks.append(
                WeekPlan(
                    week=week_no,
                    module_ids=cur_ids,
                    module_titles=cur_titles,
                    total_minutes=cur_total,
                )
            )
            week_no += 1
            cur_ids, cur_titles, cur_total = [], [], 0

    for module, minutes in estimates:
        if cur_total and cur_total + minutes > weekly_minutes:
            flush()
        module_plans.append(
            ModulePlan(
                module_id=module.module_id,
                title=module.title,
                week=week_no,
                estimated_minutes=minutes,
                objectives=list(module.objectives),
            )
        )
        cur_ids.append(module.module_id)
        cur_titles.append(module.title)
        cur_total += minutes
    flush()
    return module_plans, weeks


# ── 4. Session slot selection ──────────────────────────────────────────────────


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


def _select_window(
    focus_windows: list[tuple[int, int]],
    study_window: tuple[int, int],
    preferred_slot: str,
) -> tuple[int, int]:
    """Best (start, end) for sessions: a focus window in the preferred slot,
    intersected with the learner's study window when they overlap."""
    candidates = focus_windows or [study_window]
    # Prefer a focus window whose slot matches; else the first one.
    chosen = next((w for w in candidates if _slot_of(w[0]) == preferred_slot), candidates[0])
    start = max(chosen[0], study_window[0])
    end = min(chosen[1], study_window[1])
    if start >= end:  # no overlap → fall back to the whole focus window
        start, end = chosen
    return start, end


def select_sessions(
    *,
    weekly_minutes: float,
    session_minutes: int,
    study_days: list[str],
    focus_windows: list[tuple[int, int]],
    study_window: tuple[int, int],
    preferred_slot: str,
) -> list[StudySession]:
    """Recurring weekly sessions placed in the focus window on preferred days."""
    days = study_days or list(_DEFAULT_STUDY_DAYS)
    target = max(weekly_minutes, 1)
    n = min(len(days), max(1, round(target / max(session_minutes, 1))))
    per_session = int(round(target / n))
    per_session = max(SESSION_MIN_MINUTES, min(per_session, SESSION_MAX_MINUTES))

    # The window anchors the START; the session runs its full needed length so the
    # weekly sessions actually sum to the planned capacity (not the window length).
    win_start, _win_end = _select_window(focus_windows, study_window, preferred_slot)
    duration = per_session
    slot = _slot_of(win_start)

    return [
        StudySession(
            day=day,
            slot=slot,
            start=_to_hhmm(win_start),
            end=_to_hhmm(win_start + duration),
            duration_minutes=duration,
        )
        for day in days[:n]
    ]


# ── Build the full plan ────────────────────────────────────────────────────────


def build_study_plan(
    *,
    catalog_id: str,
    title: str,
    cert: str,
    persona: Persona,
    settings: Settings | None = None,
) -> StudyPlan | None:
    """Assemble the workload-aware study plan for a course + learner, or None."""
    settings = settings or get_settings()
    path = str(settings.athenaeum_catalog_path or default_catalog_path())
    modules = course_modules(path, catalog_id)
    if not modules:
        return None

    estimates = [(m, estimate_module_minutes(m)) for m in modules]
    total_minutes = sum(mins for _, mins in estimates)
    total_hours = round(total_minutes / 60, 1)

    prefs = persona.learning_preferences
    capacity = calculate_capacity(
        meeting_hours=persona.work_signals.meeting_hours_per_week,
        base_weekly_hours=float(prefs.preferred_study_hours_per_week),
    )
    weekly_minutes = capacity.weekly_hours * 60

    module_plans, weeks = allocate_modules_to_weeks(estimates, weekly_minutes)

    focus_windows = [(_to_min(w.start), _to_min(w.end)) for w in persona.work_context.focus_windows]
    study_window = (_to_min(prefs.study_window.start), _to_min(prefs.study_window.end))
    sessions = select_sessions(
        weekly_minutes=weekly_minutes,
        session_minutes=prefs.preferred_session_minutes,
        study_days=list(prefs.preferred_study_days),
        focus_windows=focus_windows,
        study_window=study_window,
        preferred_slot=persona.work_signals.preferred_learning_slot,
    )

    return StudyPlan(
        catalog_id=catalog_id,
        title=title,
        cert=cert,
        weekly_study_hours=capacity.weekly_hours,
        timeline_multiplier=capacity.timeline_multiplier,
        total_hours=total_hours,
        weeks=len(weeks),
        overestimate_factor=OVERESTIMATE_FACTOR,
        modules=module_plans,
        schedule=weeks,
        sessions=sessions,
        capacity_reason=capacity.reason,
    )
