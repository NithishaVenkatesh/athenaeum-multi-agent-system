"""Tests for the course state machine + grounding guards."""

from __future__ import annotations

from datetime import date

from app.agent.answer import _plan_offline_narration
from app.agent.contracts import GroundingSource, Pace, Route
from app.agent.guards import (
    allowed_plan_numbers,
    numbers_in,
    plan_narration_is_grounded,
    stream_grounded,
    ungrounded_numbers,
)
from app.agent.state import CourseState, derive_course_state, transition_note
from app.agent.study_plan import build_study_plan
from app.workiq.repository import get_repository

# ── State machine ──────────────────────────────────────────────────────────────


def test_state_progression() -> None:
    assert (
        derive_course_state(catalog_id=None, pace=None, module_count=0, completed_count=0)
        is CourseState.NEW
    )
    assert (
        derive_course_state(catalog_id="cb-c01", pace=None, module_count=0, completed_count=0)
        is CourseState.CHOSEN
    )
    assert (
        derive_course_state(
            catalog_id="cb-c01", pace=Pace.NORMAL, module_count=0, completed_count=0
        )
        is CourseState.PACED
    )
    assert (
        derive_course_state(
            catalog_id="cb-c01", pace=Pace.NORMAL, module_count=4, completed_count=0
        )
        is CourseState.PLANNED
    )
    assert (
        derive_course_state(
            catalog_id="cb-c01", pace=Pace.NORMAL, module_count=4, completed_count=2
        )
        is CourseState.IN_PROGRESS
    )
    assert (
        derive_course_state(
            catalog_id="cb-c01", pace=Pace.NORMAL, module_count=4, completed_count=4
        )
        is CourseState.COMPLETED
    )


def test_transition_note_explains_the_gate() -> None:
    note = transition_note(CourseState.CHOSEN, Route.STUDY_PLAN)
    assert "ask pace" in note
    assert "chosen" in note


# ── Grounding guards ───────────────────────────────────────────────────────────


def test_numbers_in_normalizes() -> None:
    assert numbers_in("3.0 hours over 5 weeks") == {"3", "5"}


def test_offline_plan_narration_is_grounded() -> None:
    vega = get_repository().get_persona("EMP-001")
    assert vega is not None
    plan = build_study_plan(
        catalog_id="cb-c01", title="x", cert="AZ-204", persona=vega, start_date=date(2026, 6, 15)
    )
    assert plan is not None
    narration = _plan_offline_narration(plan)
    # Every number in the deterministic narration traces to the plan.
    assert plan_narration_is_grounded(narration, plan)


def test_guard_catches_fabricated_number() -> None:
    vega = get_repository().get_persona("EMP-001")
    assert vega is not None
    plan = build_study_plan(
        catalog_id="cb-c01", title="x", cert="AZ-204", persona=vega, start_date=date(2026, 6, 15)
    )
    assert plan is not None
    bad = "This plan needs 999 hours."  # 999 is not anywhere in the plan
    assert not plan_narration_is_grounded(bad, plan)
    assert "999" in ungrounded_numbers(bad, allowed_plan_numbers(plan))


# ── Streaming grounding scrubber (M5 live streaming + H5 honesty) ────────────────


def _src(ref: str) -> GroundingSource:
    return GroundingSource(ref=ref, title="t", snippet="s")


def test_stream_grounded_keeps_a_valid_citation() -> None:
    out = "".join(
        stream_grounded(["App Service ", "scales ", "[cb-c01-m02]"], [_src("cb-c01-m02")])
    )
    assert out == "App Service scales [cb-c01-m02]"


def test_stream_grounded_drops_an_invented_citation() -> None:
    out = "".join(stream_grounded(["App Service ", "[zz-c99-m99]"], [_src("cb-c01-m02")]))
    assert "[zz-c99-m99]" not in out
    assert "App Service" in out


def test_stream_grounded_handles_a_citation_split_across_tokens() -> None:
    # The model emits the bracket across several tokens; it must still be recognized.
    out = "".join(
        stream_grounded(["see ", "[cb-", "c01", "-m02", "]", " here"], [_src("cb-c01-m02")])
    )
    assert out == "see [cb-c01-m02] here"


def test_stream_grounded_appends_disclaimer_for_uncited_substantial_answer() -> None:
    long_claim = "Azure Functions scale automatically based on event triggers and demand patterns."
    out = "".join(stream_grounded([long_claim], [_src("cb-c01-m02")]))
    assert long_claim in out
    assert "beyond the cited course material" in out


def test_stream_grounded_no_disclaimer_when_cited() -> None:
    long_claim = (
        "Azure Functions scale automatically based on event triggers [cb-c01-m02] and demand."
    )
    out = "".join(stream_grounded([long_claim], [_src("cb-c01-m02")]))
    assert "beyond the cited course material" not in out


def test_stream_grounded_no_disclaimer_without_sources() -> None:
    long_claim = "Here is a long general answer with plenty of substance but no approved sources."
    out = "".join(stream_grounded([long_claim], []))
    assert out == long_claim  # untouched, no disclaimer


def test_stream_grounded_passes_through_non_citation_brackets() -> None:
    out = "".join(stream_grounded(["step [1] then [note]"], [_src("cb-c01-m02")]))
    assert "[1]" in out and "[note]" in out
