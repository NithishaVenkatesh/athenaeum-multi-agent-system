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
    CHOSEN = "chosen"  # course linked, skill check not done
    ASSESSED = "assessed"  # skill check done (or fresher), pace not set
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
    skill_source: str | None = None,
    module_ids: frozenset[str] | None = None,
    passed_ids: frozenset[str] | None = None,
) -> CourseState:
    """Compute the course state from the persisted facts (pure).

    The skill-gap check sits between choosing a course and pacing it: a linked
    course with no ``skill_source`` is CHOSEN (ask fresher / skill check); once the
    check is done it is ASSESSED (ask pace); with a pace it is PACED (build the
    preview). Modules only exist after the learner approves the preview.

    Completion is measured against the *current* plan. When ``module_ids`` and
    ``passed_ids`` are supplied, completion is the count of passed modules that
    are still in the plan (``passed_ids & module_ids``) over the current plan
    size — never a raw running tally. This matters after a re-plan that *shrinks*
    the module set: a learner who passed 6 of the old 8 modules would, on a count
    basis, look complete against a new 5-module plan (6 >= 5) and skip straight to
    COMPLETED, even though the new modules may be untouched. Intersecting ids keeps
    that course IN_PROGRESS until the current modules are actually passed. Callers
    that pass only counts keep the legacy behaviour for backward compatibility.
    """
    if not catalog_id:
        return CourseState.NEW
    if module_ids is not None and passed_ids is not None:
        module_count = len(module_ids)
        completed_count = len(passed_ids & module_ids)
    if module_count == 0:
        if skill_source is None:
            return CourseState.CHOSEN
        if pace is None:
            return CourseState.ASSESSED
        return CourseState.PACED
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
        CourseState.CHOSEN: "course set, no skill check → ask fresher / skill check",
        CourseState.ASSESSED: "skill check done → ask pace",
        CourseState.PACED: "pace set → build the plan preview",
        CourseState.PLANNED: "plan exists → rebuild preview / open Modules",
        CourseState.IN_PROGRESS: "in progress → rebuild keeps completed modules",
        CourseState.COMPLETED: "course completed → recommend what's next",
    }[state]
    return f"state={state.value}: {gate}"
