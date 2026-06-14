"""Natural-language schedule-edit parsing + its effect on the plan (offline)."""

from __future__ import annotations

from datetime import date, timedelta

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


def test_only_days_restricts_to_given_days() -> None:
    adj = parse_adjustment("please schedule me only on Tuesday and Thursday", today=TODAY)
    assert adj is not None
    # All days except tue and thu should be excluded
    assert "tue" not in adj.exclude_days
    assert "thu" not in adj.exclude_days
    assert "mon" in adj.exclude_days
    assert "wed" in adj.exclude_days
    assert "fri" in adj.exclude_days


def test_only_days_just_one_day() -> None:
    adj = parse_adjustment("just schedule on fridays please", today=TODAY)
    assert adj is not None
    assert "fri" not in adj.exclude_days
    assert "mon" in adj.exclude_days
    assert "tue" in adj.exclude_days


def test_exam_date_parsed_from_natural_language() -> None:
    adj = parse_adjustment("my exam is on July 10", today=TODAY)
    assert adj is not None
    assert adj.exam_date == date(2026, 7, 10)


def test_exam_date_month_day_order() -> None:
    adj = parse_adjustment("targeting August 15 for the cert exam", today=TODAY)
    assert adj is not None
    assert adj.exam_date == date(2026, 8, 15)


def test_exam_date_bumps_to_next_year_if_past() -> None:
    adj = parse_adjustment("exam date January 5", today=TODAY)
    assert adj is not None
    assert adj.exam_date is not None
    assert adj.exam_date.year == 2027  # Jan 5 2026 is in the past


def test_exam_date_combined_with_start_date() -> None:
    adj = parse_adjustment("start from July 1, my exam is August 20", today=TODAY)
    assert adj is not None
    assert adj.start_date == date(2026, 7, 1)
    assert adj.exam_date == date(2026, 8, 20)


def test_no_edit_text_returns_none() -> None:
    adj = parse_adjustment("what is Azure Functions?", today=TODAY)
    assert adj is None


def test_multi_week_skip_keeps_every_week() -> None:
    """R1: 'skip weeks 2 and 3' must keep BOTH weeks, not just the first."""
    adj = parse_adjustment("I'm busy, skip weeks 2 and 3", today=TODAY)
    assert adj is not None
    assert adj.skip_weeks == frozenset({2, 3})


def _skip(text: str) -> frozenset[int]:
    adj = parse_adjustment(text, today=TODAY)
    assert adj is not None
    return adj.skip_weeks


def test_week_list_and_range_skip() -> None:
    assert _skip("away weeks 2, 3 and 4") == frozenset({2, 3, 4})
    assert _skip("I'm occupied weeks 2-4") == frozenset({2, 3, 4})
    assert _skip("skip week 2 and week 5") == frozenset({2, 5})


def test_relative_start_next_week_does_not_crash() -> None:
    """Red-team: 'start next week' crashed _parse_start (group 2 None) -> empty turn."""
    for phrase in ["build my plan starting next week", "start next month", "a week from now"]:
        adj = parse_adjustment(phrase, today=TODAY)
        assert adj is not None and adj.start_date is not None, f"no start parsed for {phrase!r}"
    nxt = parse_adjustment("start next week", today=TODAY)
    assert nxt is not None and nxt.start_date == TODAY + timedelta(days=7)


def test_multi_day_exclude_keeps_every_day() -> None:
    """Red-team: 'skip mon tue wed thu fri' must exclude all five, not just monday."""
    adj = parse_adjustment("skip monday tuesday wednesday thursday and friday", today=TODAY)
    assert adj is not None
    assert adj.exclude_days == frozenset({"mon", "tue", "wed", "thu", "fri"})
    # A later unrelated weekday after a non-skip verb is not swept in.
    adj2 = parse_adjustment("skip monday, but study tuesday", today=TODAY)
    assert adj2 is not None and adj2.exclude_days == frozenset({"mon"})


def test_start_in_week_is_not_a_skip() -> None:
    """A plain 'start in week 2' (no busy cue) must not be read as a skip."""
    adj = parse_adjustment("let's start in week 2", today=TODAY)
    skip = adj.skip_weeks if adj is not None else frozenset()
    assert skip == frozenset()


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
