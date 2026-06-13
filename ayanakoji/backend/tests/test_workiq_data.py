"""Data-integrity contract for the committed synthetic Work IQ data source.

These tests are the guardrail the synthesizer's output must always pass: they
re-derive the aggregates from the calendar (Response Fidelity), enforce the
synthetic-data rules (fabricated IDs, no PII, sane ranges), and pin the org
shape (a senior + junior per vertical + one manager).
"""

from __future__ import annotations

import re

import pytest
from app.workiq.models import WorkIQDocument
from app.workiq.repository import DATA_PATH, WorkIQRepository

EMP_RE = re.compile(r"^EMP-\d{3}$")
LEARNER_RE = re.compile(r"^L-\d{4}$")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri"]
MEETING_THRESHOLD = 20.0


@pytest.fixture(scope="module")
def document() -> WorkIQDocument:
    """The real committed data source, validated through the models."""
    return WorkIQDocument.model_validate_json(DATA_PATH.read_text(encoding="utf-8"))


def _to_minutes(hhmm: str) -> int:
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)


def test_data_file_validates_against_models(document: WorkIQDocument) -> None:
    # model_validate_json above already enforces the schema; assert it loaded.
    assert document.service.schema_version
    assert document.personas


def test_org_shape_is_senior_junior_per_vertical_plus_manager(
    document: WorkIQDocument,
) -> None:
    assert len(document.verticals) == 5
    personas = document.personas
    assert len(personas) == 11

    managers = [p for p in personas if p.is_manager]
    assert len(managers) == 1
    assert managers[0].seniority == "manager"

    for vertical in document.verticals:
        members = [p for p in personas if p.vertical == vertical.id]
        seniorities = sorted(p.seniority for p in members)
        assert seniorities == ["junior", "senior"], f"{vertical.id}: {seniorities}"


def test_manager_reports_cover_every_individual_contributor(
    document: WorkIQDocument,
) -> None:
    manager = next(p for p in document.personas if p.is_manager)
    ics = {p.employee_id for p in document.personas if not p.is_manager}
    assert set(manager.reports) == ics
    assert manager.manager_employee_id is None
    for ic in (p for p in document.personas if not p.is_manager):
        assert ic.manager_employee_id == manager.employee_id


def test_identifiers_are_fabricated_and_consistent(document: WorkIQDocument) -> None:
    seen_emp: set[str] = set()
    for persona in document.personas:
        assert EMP_RE.match(persona.employee_id)
        assert LEARNER_RE.match(persona.learner_id)
        assert persona.employee_id not in seen_emp
        seen_emp.add(persona.employee_id)
        # Cross-surface ID consistency.
        assert persona.work_signals.employee_id == persona.employee_id
        assert persona.learning.learner_id == persona.learner_id


def test_no_pii_email_addresses_anywhere(document: WorkIQDocument) -> None:
    blob = document.model_dump_json()
    assert not EMAIL_RE.search(blob), "synthetic data must contain no email addresses"


def test_disclaimer_declares_synthetic(document: WorkIQDocument) -> None:
    disclaimer = document.service.disclaimer.lower()
    assert "synthetic" in disclaimer
    assert "demo" in disclaimer


def test_learner_values_are_in_sane_ranges(document: WorkIQDocument) -> None:
    for persona in document.personas:
        learning = persona.learning
        assert 0 <= learning.practice_score_avg <= 100
        assert 5 <= learning.hours_studied <= 40


def test_every_schedule_covers_monday_to_friday(document: WorkIQDocument) -> None:
    for persona in document.personas:
        days = [d.day for d in persona.schedule.days]
        assert days == WEEKDAYS, f"{persona.employee_id}: {days}"


def test_calendar_blocks_never_overlap(document: WorkIQDocument) -> None:
    for persona in document.personas:
        for day in persona.schedule.days:
            blocks = sorted(day.blocks, key=lambda b: _to_minutes(b.start))
            for prev, cur in zip(blocks, blocks[1:], strict=False):
                assert _to_minutes(cur.start) >= _to_minutes(prev.end), (
                    f"{persona.employee_id} {day.day}: {prev.title} overlaps {cur.title}"
                )


def test_block_duration_matches_start_and_end(document: WorkIQDocument) -> None:
    for persona in document.personas:
        for day in persona.schedule.days:
            for block in day.blocks:
                expected = (_to_minutes(block.end) - _to_minutes(block.start)) / 60.0
                assert block.duration_hours == pytest.approx(expected)


def test_work_signals_are_derived_from_the_calendar(document: WorkIQDocument) -> None:
    """The aggregate surface must equal a fresh recomputation from the blocks."""
    for persona in document.personas:
        meeting = focus = 0.0
        for day in persona.schedule.days:
            for block in day.blocks:
                if block.meter == "meeting":
                    meeting += block.duration_hours
                elif block.meter == "focus":
                    focus += block.duration_hours
        assert persona.work_signals.meeting_hours_per_week == pytest.approx(round(meeting, 2))
        assert persona.work_signals.focus_hours_per_week == pytest.approx(round(focus, 2))


def test_distribution_exercises_the_capacity_and_slot_rules(
    document: WorkIQDocument,
) -> None:
    signals = [p.work_signals for p in document.personas]
    # Both preferred slots represented.
    assert {s.preferred_learning_slot for s in signals} == {"Morning", "Afternoon"}
    # At least a few personas trip the >20 meeting-hour capacity rule.
    heavy = [s for s in signals if s.meeting_hours_per_week > MEETING_THRESHOLD]
    assert len(heavy) >= 3
    # Focus-rich personas exist (capacity headroom).
    assert any(s.focus_hours_per_week > 20 for s in signals)
    # All three readiness verdicts are present (edge cases covered).
    verdicts = {p.learning.readiness_status for p in document.personas}
    assert verdicts == {"GO", "CONDITIONAL", "NOT_YET"}


def test_repository_loads_the_committed_file(document: WorkIQDocument) -> None:
    repo = WorkIQRepository.from_path(DATA_PATH)
    assert len(repo.list_personas()) == len(document.personas)
