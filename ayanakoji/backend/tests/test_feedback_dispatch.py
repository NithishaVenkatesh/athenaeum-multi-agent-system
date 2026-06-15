"""The FEEDBACK route dispatch inside the pipeline (offline lane).

Given a resolved FeedbackResolution, a typed feedback ask streams grounded feedback,
a cross-course ask streams a polite redirect, and a no-failed-test ask says so. The
pin keeps a generic follow-up in FEEDBACK.
"""

from __future__ import annotations

from app.agent.contracts import FeedbackResolution, PipelineEvent, Route
from app.agent.orchestrator import run_pipeline


def _text(events: list[PipelineEvent]) -> str:
    return "".join(e.token for e in events if e.type == "token")


def _answer() -> FeedbackResolution:
    return FeedbackResolution(
        kind="answer",
        module_id="cb-c01-m01",
        module_title="Storage Basics",
        type="choices",
        material="Azure Blob storage stores unstructured data in containers.",
        performance="Questions you missed:\n- What is a blob? You chose: nothing. Correct: A.",
        score=2.0,
        passed=False,
        this_course_title="Cloud & Backend",
    )


def test_feedback_answer_streams_grounded_text() -> None:
    events = list(
        run_pipeline(
            "why did I fail my quiz?", persona_id="p", feedback=_answer(), feedback_active=False
        )
    )
    assert events[-1].route is Route.FEEDBACK
    text = _text(events)
    assert "cb-c01-m01" in text  # cites the module it grounded on
    assert "feedback" in text.lower()


def test_feedback_redirect_points_to_other_chat() -> None:
    resolution = FeedbackResolution(
        kind="redirect", other_course_title="Data Engineering", this_course_title="Cloud & Backend"
    )
    events = list(
        run_pipeline("feedback on my data engineering test", persona_id="p", feedback=resolution)
    )
    assert events[-1].route is Route.FEEDBACK
    text = _text(events)
    assert "Data Engineering" in text  # names the other course
    assert "token" in [e.type for e in events]


def test_feedback_none_when_no_failed_tests() -> None:
    resolution = FeedbackResolution(kind="none", this_course_title="Cloud & Backend")
    events = list(run_pipeline("give me feedback on my test", persona_id="p", feedback=resolution))
    assert events[-1].route is Route.FEEDBACK
    text = _text(events).lower()
    assert "not failed" in text or "no" in text  # explains there is nothing to review


def test_pin_keeps_generic_followup_in_feedback() -> None:
    # A generic follow-up that names nothing, while pinned, still dispatches FEEDBACK.
    events = list(
        run_pipeline(
            "can you explain that part again?",
            persona_id="p",
            feedback=_answer(),
            feedback_active=True,
        )
    )
    assert events[-1].route is Route.FEEDBACK
    assert "token" in [e.type for e in events]
