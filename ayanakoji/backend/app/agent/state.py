"""The conversation state machine — the pipeline is a state graph, not a line.

A course chat moves through explicit states, and the orchestrator's transitions
are *conditioned* on the state (master-plan §5): a plan request in ``CHOSEN``
asks for a pace; in ``PACED`` it builds; ``PLANNED``/``IN_PROGRESS`` drive the
Modules tab. Deriving the state here keeps that branching auditable and lets the
trace show *why* a turn went where it did.

    NEW ──choose course──▶ CHOSEN ──set pace──▶ PACED ──build plan──▶ PLANNED
                                                                         │ complete a module
                                                                         ▼
                                              COMPLETED ◀──last module── IN_PROGRESS
"""

from __future__ import annotations

from enum import StrEnum

from app.agent.contracts import Pace, Route


class CourseState(StrEnum):
    """Where a course chat is in its lifecycle (derived, never stored)."""

    NEW = "new"  # no course chosen yet
    CHOSEN = "chosen"  # course linked, pace not set
    PACED = "paced"  # pace set, plan not built
    PLANNED = "planned"  # plan modules exist, none completed
    IN_PROGRESS = "in_progress"  # some modules completed
    COMPLETED = "completed"  # every module completed


def derive_course_state(
    *,
    catalog_id: str | None,
    pace: Pace | None,
    module_count: int,
    completed_count: int,
) -> CourseState:
    """Compute the course state from the persisted facts (pure)."""
    if not catalog_id:
        return CourseState.NEW
    if module_count == 0:
        return CourseState.PACED if pace is not None else CourseState.CHOSEN
    if completed_count == 0:
        return CourseState.PLANNED
    if completed_count >= module_count:
        return CourseState.COMPLETED
    return CourseState.IN_PROGRESS


def transition_note(state: CourseState, route: Route) -> str:
    """A short, inspectable description of the state-conditioned transition."""
    if route is not Route.STUDY_PLAN:
        return f"state={state.value}"
    gate = {
        CourseState.NEW: "no course → choose one first",
        CourseState.CHOSEN: "course set, no pace → ask pace",
        CourseState.PACED: "pace set → build the plan",
        CourseState.PLANNED: "plan exists → rebuild / open Modules",
        CourseState.IN_PROGRESS: "in progress → rebuild keeps completed modules",
        CourseState.COMPLETED: "course completed → recommend what's next",
    }[state]
    return f"state={state.value}: {gate}"
