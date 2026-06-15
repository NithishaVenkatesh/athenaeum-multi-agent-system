"""Router detection of the in-chat feedback intent + the pinned follow-up context.

The router gains a FEEDBACK route so a learner can type 'give me feedback on my
failed test' and have the turn resolved to grounded feedback (the same answer the
'Get Feedback' button produces), instead of the off-topic refusal a bare question
used to hit. Once feedback is given, a pin keeps generic follow-ups grounded on the
same test until the learner clearly changes topic.
"""

from __future__ import annotations

import pytest
from app.agent.contracts import Route
from app.agent.router_agent import classify, is_feedback_intent


@pytest.mark.parametrize(
    "text",
    [
        "give me feedback on my failed test",
        "can you give me feedback on this quiz?",
        "why did I fail my quiz?",
        "what did I get wrong on the test",
        "where did I go wrong?",
        "go over my answers with me",
        "walk me through my mistakes",
        "review my results",
        "how did I do on my oral exam?",
    ],
)
def test_feedback_intent_detected(text: str) -> None:
    assert is_feedback_intent(text)
    assert classify(text).route is Route.FEEDBACK


@pytest.mark.parametrize(
    "text",
    [
        "I'm ready to take the test",
        "start the evaluation",
        "quiz me on this module",
        "make me a study plan",
        "what's my next module?",
        "how many courses have I completed?",
        "recommend a course",
        "tell me about star schemas",
    ],
)
def test_non_feedback_intents_unaffected(text: str) -> None:
    """Feedback detection must not steal the existing high-signal intents."""
    assert not is_feedback_intent(text)
    assert classify(text).route is not Route.FEEDBACK


def test_pin_keeps_generic_followup_in_feedback() -> None:
    """With the pin active, an otherwise-general question stays in FEEDBACK."""
    # No pin: a bare 'why was that wrong' is off-topic → general.
    assert classify("why was answer B wrong?").route is Route.FEEDBACK  # explicit feedback phrasing
    # A truly generic follow-up the catalog can't ground.
    assert (
        classify("can you explain that part again?", feedback_active=False).route is Route.GENERAL
    )
    assert (
        classify("can you explain that part again?", feedback_active=True).route is Route.FEEDBACK
    )


def test_pin_breaks_on_a_competing_intent() -> None:
    """A clear navigation/plan intent ends the feedback context even while pinned."""
    assert (
        classify("I'm ready to take the test", feedback_active=True).route is Route.TAKE_EVALUATION
    )
    assert classify("make me a study plan", feedback_active=True).route is Route.STUDY_PLAN
    assert classify("what's my next module?", feedback_active=True).route is Route.UPCOMING


def test_pin_does_not_swallow_off_domain() -> None:
    """An off-platform question is still general, pin or not."""
    assert classify("what's the weather today?", feedback_active=True).route is Route.GENERAL
