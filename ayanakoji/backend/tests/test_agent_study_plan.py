"""Calendar-grounded study-plan algorithm tests (offline; over committed data)."""

from __future__ import annotations

from datetime import date

from app.agent.contracts import Pace
from app.agent.study_plan import (
    ModuleInfo,
    build_study_plan,
    course_modules,
    estimate_module_minutes,
    schedule_modules,
    weekly_study_slots,
)
from app.catalog.loader import default_catalog_path
from app.workiq.repository import get_repository

START = date(2026, 6, 15)


def _module(objectives: int, skills: int = 2, order: int = 1) -> ModuleInfo:
    return ModuleInfo(
        module_id=f"m{order}",
        title=f"Module {order}",
        order=order,
        objectives=tuple(f"obj{i}" for i in range(objectives)),
        skills=skills,
        prereq_module_ids=(),
    )


# ── Per-module estimate (computed from content + pace; no exposed factor) ───────


def test_estimate_varies_with_content() -> None:
    assert estimate_module_minutes(_module(5), Pace.NORMAL) > estimate_module_minutes(
        _module(1), Pace.NORMAL
    )


def test_pace_scales_estimate() -> None:
    m = _module(3)
    slower = estimate_module_minutes(m, Pace.SLOWER)
    normal = estimate_module_minutes(m, Pace.NORMAL)
    faster = estimate_module_minutes(m, Pace.FASTER)
    assert slower > normal > faster


def test_estimate_rounded_to_quarter_hour() -> None:
    assert estimate_module_minutes(_module(3), Pace.NORMAL) % 15 == 0


def test_study_plan_does_not_expose_overestimate_factor() -> None:
    vega = get_repository().get_persona("EMP-001")
    assert vega is not None
    plan = build_study_plan(
        catalog_id="cb-c01", title="x", cert="AZ-204", persona=vega, start_date=START
    )
    assert plan is not None
    assert not hasattr(plan, "overestimate_factor")
    assert not hasattr(plan, "timeline_multiplier")


# ── Capacity from the real calendar (not a multiplier) ─────────────────────────


def test_weekly_slots_grounded_in_calendar() -> None:
    vega = get_repository().get_persona("EMP-001")
    assert vega is not None
    slots = weekly_study_slots(vega)
    # Vega's calendar has dedicated "Cert study" (category=learning) blocks
    # tue/wed/thu 11:00–12:00 → exactly those three slots.
    assert {s.day for s in slots} == {"tue", "wed", "thu"}
    assert all(s.start == 11 * 60 and s.end == 12 * 60 for s in slots)


def test_capacity_reason_names_real_slots() -> None:
    vega = get_repository().get_persona("EMP-001")
    assert vega is not None
    plan = build_study_plan(
        catalog_id="cb-c01", title="x", cert="AZ-204", persona=vega, start_date=START
    )
    assert plan is not None
    assert plan.weekly_study_hours == 3.0  # grounded: 3×1h, not 0.6×5
    assert "Tue" in plan.capacity_reason and "11:00" in plan.capacity_reason


# ── Sequential module schedule + deadlines ─────────────────────────────────────


def test_schedule_is_sequential_with_deadlines() -> None:
    vega = get_repository().get_persona("EMP-001")
    assert vega is not None
    slots = weekly_study_slots(vega)
    estimates = [(_module(3, order=i), 120) for i in range(1, 4)]
    plans = schedule_modules(estimates, slots, START)
    assert [m.sequence for m in plans] == [1, 2, 3]
    # Deadlines are non-decreasing along the sequence.
    deadlines = [m.complete_before for m in plans]
    assert deadlines == sorted(deadlines)
    # Every module has at least one concrete session.
    assert all(m.scheduled for m in plans)


def test_pace_changes_weeks() -> None:
    vega = get_repository().get_persona("EMP-001")
    assert vega is not None
    faster = build_study_plan(
        catalog_id="cb-c01",
        title="x",
        cert="AZ-204",
        persona=vega,
        pace=Pace.FASTER,
        start_date=START,
    )
    slower = build_study_plan(
        catalog_id="cb-c01",
        title="x",
        cert="AZ-204",
        persona=vega,
        pace=Pace.SLOWER,
        start_date=START,
    )
    assert faster is not None and slower is not None
    assert slower.total_hours > faster.total_hours
    assert slower.weeks >= faster.weeks


def test_build_plan_modules_match_course() -> None:
    vega = get_repository().get_persona("EMP-001")
    assert vega is not None
    plan = build_study_plan(
        catalog_id="cb-c01", title="x", cert="AZ-204", persona=vega, start_date=START
    )
    assert plan is not None
    mods = course_modules(str(default_catalog_path()), "cb-c01")
    assert [m.module_id for m in plan.modules] == [m.module_id for m in mods]
    assert plan.pace is Pace.NORMAL


def test_build_plan_unknown_course_is_none() -> None:
    vega = get_repository().get_persona("EMP-001")
    assert vega is not None
    assert (
        build_study_plan(catalog_id="nope", title="x", cert="y", persona=vega, start_date=START)
        is None
    )
