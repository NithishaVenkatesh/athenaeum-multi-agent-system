"""Deterministic study-plan algorithm tests (offline; over the committed catalog/personas)."""

from __future__ import annotations

from app.agent.study_plan import (
    HEAVY_CAPACITY_FACTOR,
    MINUTES_PER_OBJECTIVE,
    MODULE_BASE_MINUTES,
    OVERESTIMATE_FACTOR,
    WEEKLY_HOURS_CAP,
    ModuleInfo,
    allocate_modules_to_weeks,
    build_study_plan,
    calculate_capacity,
    course_modules,
    estimate_module_minutes,
    select_sessions,
)
from app.catalog.loader import default_catalog_path
from app.workiq.repository import get_repository


def _module(n_objectives: int, order: int = 1) -> ModuleInfo:
    return ModuleInfo(
        module_id=f"m{order}",
        title=f"Module {order}",
        order=order,
        objectives=tuple(f"obj{i}" for i in range(n_objectives)),
        skills=0,
        prereq_module_ids=(),
    )


# ── Module estimate (×2 over-estimate) ─────────────────────────────────────────


def test_module_estimate_is_doubled() -> None:
    module = _module(3)
    base = MODULE_BASE_MINUTES + MINUTES_PER_OBJECTIVE * 3
    assert estimate_module_minutes(module) == int(round(base * OVERESTIMATE_FACTOR))
    # 2× factor is explicit and applied.
    assert OVERESTIMATE_FACTOR == 2.0
    assert estimate_module_minutes(module) == base * 2


def test_more_objectives_means_more_time() -> None:
    assert estimate_module_minutes(_module(5)) > estimate_module_minutes(_module(1))


# ── Capacity ───────────────────────────────────────────────────────────────────


def test_heavy_meeting_load_reduces_capacity_and_extends_timeline() -> None:
    cap = calculate_capacity(meeting_hours=24, base_weekly_hours=5)
    assert cap.meeting_heavy is True
    assert cap.weekly_hours == round(5 * HEAVY_CAPACITY_FACTOR, 1)  # 3.0
    assert cap.timeline_multiplier > 1.0
    assert "reduced" in cap.reason


def test_manageable_meeting_load_uses_full_capacity() -> None:
    cap = calculate_capacity(meeting_hours=8, base_weekly_hours=8)
    assert cap.meeting_heavy is False
    assert cap.weekly_hours == 8.0
    assert cap.timeline_multiplier == 1.0


def test_capacity_is_capped() -> None:
    cap = calculate_capacity(meeting_hours=2, base_weekly_hours=40)
    assert cap.weekly_hours == WEEKLY_HOURS_CAP


# ── Allocation ─────────────────────────────────────────────────────────────────


def test_allocation_packs_into_weeks_without_splitting_modules() -> None:
    estimates = [(_module(2, i), 120) for i in range(1, 5)]  # 4 modules × 120 min
    module_plans, weeks = allocate_modules_to_weeks(estimates, weekly_minutes=240)
    # 240/week → 2 modules per week → 2 weeks.
    assert len(weeks) == 2
    assert all(w.total_minutes == 240 for w in weeks)
    assert [m.week for m in module_plans] == [1, 1, 2, 2]


def test_oversized_module_gets_its_own_week() -> None:
    estimates = [(_module(2, 1), 300)]  # 300 min > 240 weekly
    _, weeks = allocate_modules_to_weeks(estimates, weekly_minutes=240)
    assert len(weeks) == 1
    assert weeks[0].total_minutes == 300


# ── Sessions ───────────────────────────────────────────────────────────────────


def test_sessions_land_in_focus_window_on_preferred_days() -> None:
    sessions = select_sessions(
        weekly_minutes=180,
        session_minutes=60,
        study_days=["tue", "wed", "thu"],
        focus_windows=[(9 * 60 + 45, 12 * 60)],  # 09:45–12:00
        study_window=(11 * 60, 12 * 60),  # 11:00–12:00
        preferred_slot="Morning",
    )
    assert [s.day for s in sessions] == ["tue", "wed", "thu"]
    assert all(s.slot == "Morning" for s in sessions)
    assert sessions[0].start == "11:00"  # focus ∩ study window
    assert sum(s.duration_minutes for s in sessions) == 180  # sessions cover the weekly load


def test_sessions_fall_back_to_default_days() -> None:
    sessions = select_sessions(
        weekly_minutes=120,
        session_minutes=60,
        study_days=[],
        focus_windows=[],
        study_window=(13 * 60, 14 * 60),
        preferred_slot="Afternoon",
    )
    assert sessions  # never empty
    assert sessions[0].slot == "Afternoon"


# ── Course modules + full plan ─────────────────────────────────────────────────


def test_course_modules_in_order() -> None:
    mods = course_modules(str(default_catalog_path()), "cb-c01")
    assert [m.module_id for m in mods] == ["cb-c01-m01", "cb-c01-m02", "cb-c01-m03", "cb-c01-m04"]


def test_build_plan_for_heavy_meeting_learner() -> None:
    vega = get_repository().get_persona("EMP-001")
    assert vega is not None and vega.work_signals.meeting_hours_per_week > 20
    plan = build_study_plan(
        catalog_id="cb-c01", title="Compute Foundations", cert="AZ-204", persona=vega
    )
    assert plan is not None
    assert plan.weekly_study_hours < vega.learning_preferences.preferred_study_hours_per_week
    assert plan.timeline_multiplier > 1.0
    assert plan.overestimate_factor == 2.0
    assert len(plan.modules) == 4
    assert plan.weeks == len(plan.schedule)
    # every module is scheduled in some week
    assert {m.module_id for m in plan.modules} == {
        mid for w in plan.schedule for mid in w.module_ids
    }
    # sessions are in her preferred morning slot
    assert all(s.slot == "Morning" for s in plan.sessions)


def test_build_plan_unknown_course_is_none() -> None:
    vega = get_repository().get_persona("EMP-001")
    assert vega is not None
    assert build_study_plan(catalog_id="nope", title="x", cert="y", persona=vega) is None
