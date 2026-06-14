from __future__ import annotations

from app.agent.contracts import Pace
from app.agent.state import CourseState, derive_course_state


def test_chosen_until_skill_then_assessed_then_paced() -> None:
    assert (
        derive_course_state(
            catalog_id="de-c01", pace=None, skill_source=None, module_count=0, completed_count=0
        )
        == CourseState.CHOSEN
    )
    assert (
        derive_course_state(
            catalog_id="de-c01",
            pace=None,
            skill_source="fresher",
            module_count=0,
            completed_count=0,
        )
        == CourseState.ASSESSED
    )
    assert (
        derive_course_state(
            catalog_id="de-c01",
            pace=Pace.NORMAL,
            skill_source="assessment",
            module_count=0,
            completed_count=0,
        )
        == CourseState.PACED
    )


def test_modules_present_overrides_to_planned() -> None:
    assert (
        derive_course_state(
            catalog_id="de-c01",
            pace=Pace.NORMAL,
            skill_source="assessment",
            module_count=5,
            completed_count=0,
        )
        == CourseState.PLANNED
    )


def test_no_catalog_is_new() -> None:
    assert (
        derive_course_state(
            catalog_id=None, pace=None, skill_source=None, module_count=0, completed_count=0
        )
        == CourseState.NEW
    )
