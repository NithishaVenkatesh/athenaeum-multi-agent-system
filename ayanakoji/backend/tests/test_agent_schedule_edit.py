"""Natural-language schedule-edit parsing + its effect on the plan (offline)."""

from __future__ import annotations

from datetime import date

from app.agent.schedule_edit import parse_adjustment
from app.agent.study_plan import build_study_plan, weekly_study_slots
from app.workiq.repository import get_repository

TODAY = date(2026, 6, 13)


def test_start_after_a_date_starts_the_next_day() -> None:
    adj = parse_adjustment("can you move things so I start post June 30 instead", today=TODAY)
    assert adj is not None
    assert adj.start_date == date(2026, 7, 1)
    assert adj.exclude_days == frozenset()


def test_start_from_a_date_is_that_date() -> None:
    adj = parse_adjustment("I can only begin from July 1", today=TODAY)
    assert adj is not None and adj.start_date == date(2026, 7, 1)


def test_relative_start_in_n_weeks() -> None:
    adj = parse_adjustment("start in 2 weeks", today=TODAY)
    assert adj is not None and adj.start_date == date(2026, 6, 27)


def test_skip_a_day() -> None:
    adj = parse_adjustment("don't use the 1 hour on Monday", today=TODAY)
    assert adj is not None and adj.exclude_days == frozenset({"mon"})


def test_combined_edit() -> None:
    adj = parse_adjustment("start after June 30 and avoid fridays", today=TODAY)
    assert adj is not None
    assert adj.start_date == date(2026, 7, 1)
    assert adj.exclude_days == frozenset({"fri"})


def test_no_edit_returns_none() -> None:
    assert parse_adjustment("how do azure functions work", today=TODAY) is None


def test_exclude_day_removes_its_slots_from_the_plan() -> None:
    vega = get_repository().get_persona("EMP-001")
    assert vega is not None
    # Vega studies tue/wed/thu; excluding tue must drop those slots.
    full = weekly_study_slots(vega)
    minus_tue = weekly_study_slots(vega, frozenset({"tue"}))
    assert any(s.day == "tue" for s in full)
    assert not any(s.day == "tue" for s in minus_tue)


def test_start_date_shifts_all_module_deadlines() -> None:
    vega = get_repository().get_persona("EMP-001")
    assert vega is not None
    early = build_study_plan(
        catalog_id="cb-c01", title="x", cert="AZ-204", persona=vega, start_date=date(2026, 6, 15)
    )
    late = build_study_plan(
        catalog_id="cb-c01", title="x", cert="AZ-204", persona=vega, start_date=date(2026, 7, 1)
    )
    assert early is not None and late is not None
    assert late.modules[0].complete_before > early.modules[0].complete_before


def test_parse_pace_requires_a_steering_cue() -> None:
    from app.agent.contracts import Pace
    from app.agent.schedule_edit import parse_pace

    assert parse_pace("can we revert back to the slower pace instead") is Pace.SLOWER
    assert parse_pace("make it faster") is Pace.FASTER
    assert parse_pace("set it to a normal pace") is Pace.NORMAL
    # A topic mention is not a pace edit (no false positive).
    assert parse_pace("I want an intensive course on security") is None
    assert parse_pace("how do Azure Functions work") is None


def test_remove_week_parses_skip_weeks_and_drops_that_week() -> None:
    adj = parse_adjustment(
        "remove the schedules from week 2 as I am occupied, move to later slots", today=TODAY
    )
    assert adj is not None
    assert adj.skip_weeks == frozenset({2})

    vega = get_repository().get_persona("EMP-001")
    assert vega is not None
    plan = build_study_plan(
        catalog_id="cb-c01",
        title="x",
        cert="AZ-204",
        persona=vega,
        start_date=date(2026, 6, 15),
        skip_weeks=frozenset({2}),
    )
    assert plan is not None
    weeks_used = {b.week for m in plan.modules for b in m.scheduled}
    assert 2 not in weeks_used
