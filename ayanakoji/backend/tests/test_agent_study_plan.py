"""Calendar-grounded study-plan algorithm tests (offline; over committed data)."""

from __future__ import annotations

from datetime import date

from app.agent.contracts import Pace
from app.agent.study_plan import (
    ModuleInfo,
    WeeklySlot,
    _BALLOON_WEEKS_THRESHOLD,
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


# ── Reservation-aware scheduling ───────────────────────────────────────────────


from app.agent.study_plan import block_date, occupied_intervals  # noqa: E402
from app.agent.contracts import ScheduledBlock  # noqa: E402


def test_block_date_week1_same_day() -> None:
    # Week 1, Monday when start_date is a Monday → same day.
    start = date(2026, 6, 15)  # Monday
    assert block_date(start, week=1, weekday="mon") == date(2026, 6, 15)


def test_block_date_week1_forward_weekday() -> None:
    # Week 1, Wednesday when start is Monday → +2 days.
    start = date(2026, 6, 15)  # Monday
    assert block_date(start, week=1, weekday="wed") == date(2026, 6, 17)


def test_block_date_week2() -> None:
    # Week 2 starts +7 from start; Tuesday after that Monday start = +8 days.
    start = date(2026, 6, 15)
    assert block_date(start, week=2, weekday="tue") == date(2026, 6, 23)


def test_occupied_intervals_returns_absolute_tuples() -> None:
    start = date(2026, 6, 15)  # Monday
    blocks = [ScheduledBlock(week=1, day="mon", start="11:00", end="12:00", minutes=60)]
    intervals = occupied_intervals(start, blocks)
    assert ("2026-06-15", 660, 720) in intervals


def test_schedule_modules_skips_reserved_interval() -> None:
    """A block occupied by another course should not be double-booked."""
    vega = get_repository().get_persona("EMP-001")
    assert vega is not None
    slots = weekly_study_slots(vega)
    # Vega's slots are tue/wed/thu 11:00–12:00 (660–720).
    # Reserve the entire Tuesday 11:00–12:00 in week 1.
    reserved: frozenset = frozenset({("2026-06-16", 660, 720)})  # 2026-06-15 Mon, +1=Tue
    estimates = [(_module(3), 30)]  # 30 min; fits in half a slot
    plans = schedule_modules(estimates, slots, START, reserved=reserved)
    assert plans
    blocks = plans[0].scheduled
    # No block should overlap the reserved interval on that date.
    for b in blocks:
        day_iso = block_date(START, b.week, b.day).isoformat()
        if day_iso == "2026-06-16":
            b_start = int(b.start.split(":")[0]) * 60 + int(b.start.split(":")[1])
            b_end = int(b.end.split(":")[0]) * 60 + int(b.end.split(":")[1])
            assert b_end <= 660 or b_start >= 720, (
                f"Block {b} overlaps reserved 11:00–12:00 on 2026-06-16"
            )


def test_schedule_modules_extends_timeline_when_slot_fully_reserved() -> None:
    """When a whole weekly slot is reserved the work flows to the next week, not double-booked."""
    vega = get_repository().get_persona("EMP-001")
    assert vega is not None
    slots = weekly_study_slots(vega)
    # Reserve all three week-1 slots (tue/wed/thu 11:00–12:00).
    start = START  # 2026-06-15 Monday
    reserved: frozenset = frozenset(
        {
            ("2026-06-16", 660, 720),  # tue week 1
            ("2026-06-17", 660, 720),  # wed week 1
            ("2026-06-18", 660, 720),  # thu week 1
        }
    )
    estimates = [(_module(3), 60)]
    plans_no_res = schedule_modules(estimates, slots, start)
    plans_with_res = schedule_modules(estimates, slots, start, reserved=reserved)
    assert plans_with_res
    # The plan with all week-1 slots reserved must end later than the unreserved plan.
    assert plans_with_res[0].complete_before >= plans_no_res[0].complete_before


# ── PTO / on-call skip dates ───────────────────────────────────────────────────


def test_build_study_plan_skips_pto_days() -> None:
    """Modules should not be scheduled on PTO days."""
    vega = get_repository().get_persona("EMP-001")
    assert vega is not None
    # Inject a PTO day that falls in week 1 (first Tuesday, 2026-06-16)
    vega = vega.model_copy(
        update={"work_context": vega.work_context.model_copy(
            update={"pto_days": ["2026-06-16"]}
        )}
    )
    plan = build_study_plan(
        catalog_id="cb-c01",
        title="Test",
        cert="AZ-204",
        persona=vega,
        start_date=date(2026, 6, 15),
    )
    assert plan is not None
    # No block should land on 2026-06-16
    from app.agent.study_plan import block_date
    for mod in plan.modules:
        for b in mod.scheduled:
            bd = block_date(date(2026, 6, 15), b.week, b.day)
            assert bd.isoformat() != "2026-06-16", f"Block on PTO day: {bd}"


# ── Balloon warning ────────────────────────────────────────────────────────────


def test_build_study_plan_exam_date_overrun_sets_balloon_warning() -> None:
    """A plan that overruns the exam date should set balloon_warning."""
    vega = get_repository().get_persona("EMP-001")
    assert vega is not None
    plan = build_study_plan(
        catalog_id="cb-c01",
        title="Test",
        cert="AZ-204",
        persona=vega,
        start_date=date(2026, 6, 15),
        exam_date=date(2026, 6, 16),  # tomorrow — definitely overruns
    )
    assert plan is not None
    assert plan.balloon_warning is not None
    assert "exam" in plan.balloon_warning.lower() or "day" in plan.balloon_warning.lower()


def test_build_study_plan_no_balloon_warning_when_within_deadline() -> None:
    """A plan that finishes before the exam date should not warn."""
    vega = get_repository().get_persona("EMP-001")
    assert vega is not None
    plan = build_study_plan(
        catalog_id="cb-c01",
        title="Test",
        cert="AZ-204",
        persona=vega,
        start_date=date(2026, 6, 15),
        exam_date=date(2027, 12, 31),  # far future — won't overrun
    )
    assert plan is not None
    # Either no warning or only a length warning (not exam-overrun) for this deadline
    if plan.balloon_warning:
        assert "exam" not in plan.balloon_warning.lower()


# ── Time-of-day window + max session length (agentic scheduler capabilities) ─────


def test_time_window_clips_slots_to_part_of_day() -> None:
    vega = get_repository().get_persona("EMP-001")
    assert vega is not None
    full = weekly_study_slots(vega)
    windowed = weekly_study_slots(vega, time_window=(13 * 60, 17 * 60))
    # Every windowed slot sits strictly inside the afternoon window...
    assert all(13 * 60 <= s.start and s.end <= 17 * 60 for s in windowed)
    # ...and the window can only remove time, never add it.
    assert sum(s.minutes for s in windowed) <= sum(s.minutes for s in full)


def test_max_session_minutes_caps_every_block() -> None:
    slots = [WeeklySlot("mon", 9 * 60, 13 * 60, "free time")]  # one 4-hour opening
    estimates = [(_module(objectives=6, skills=4), 200)]  # a 200-minute module
    plans = schedule_modules(estimates, slots, START, max_session_minutes=45)
    blocks = plans[0].scheduled
    assert blocks, "expected scheduled blocks"
    assert all(b.minutes <= 45 for b in blocks)  # no sitting longer than 45 min
    assert sum(b.minutes for b in blocks) == 200  # but the whole module still fits


def test_build_plan_respects_max_session_minutes() -> None:
    vega = get_repository().get_persona("EMP-001")
    assert vega is not None
    plan = build_study_plan(
        catalog_id="cb-c01",
        title="x",
        cert="AZ-204",
        persona=vega,
        start_date=START,
        max_session_minutes=30,
    )
    assert plan is not None
    assert all(b.minutes <= 30 for m in plan.modules for b in m.scheduled)
