"""Conversational course-suggestion accept (finding R2)."""

from __future__ import annotations

import pytest
from app.agent.contracts import Route
from app.agent.router_agent import classify, is_acceptance, is_suggestion_response


@pytest.mark.parametrize(
    "text",
    ["yes", "yes, start that one", "sure, let's begin", "start that one", "sign me up", "go ahead"],
)
def test_is_acceptance_true(text: str) -> None:
    assert is_acceptance(text)


@pytest.mark.parametrize(
    "text", ["what's next?", "tell me about functions", "no thanks", "maybe later", "not now"]
)
def test_is_acceptance_false(text: str) -> None:
    assert not is_acceptance(text)


def test_accept_after_suggestion_routes_to_setup() -> None:
    assert classify("yes, start that one", pending="suggestion").route is Route.STUDY_PLAN


def test_bare_yes_without_pending_is_not_setup() -> None:
    # A 'yes' with no outstanding offer must not be read as a plan request.
    assert classify("yes", pending=None).route is not Route.STUDY_PLAN


@pytest.mark.parametrize(
    "text", ["the second one", "number 2", "the first", "the latter", "3rd", "last one"]
)
def test_ordinal_is_a_suggestion_response(text: str) -> None:
    assert is_suggestion_response(text)


def test_ordinal_after_suggestion_routes_to_setup() -> None:
    assert classify("the second one", pending="suggestion").route is Route.STUDY_PLAN


def test_resolve_choice_handles_ordinal_and_name() -> None:
    from app.courses.models import Course
    from app.courses.router import _resolve_suggestion_choice

    course = Course(persona_id="EMP-001", chat_name="x")
    course.messages = [
        {"role": "user", "content": "recommend a course"},
        {
            "role": "assistant",
            "content": "Pick one:",
            "meta": {"suggestion": {"options": [{"catalog_id": "cb-c02"}, {"catalog_id": "as-c01"}]}},
        },
    ]
    assert _resolve_suggestion_choice(course, "the second one") == "as-c01"
    assert _resolve_suggestion_choice(course, "number 1") == "cb-c02"
    assert _resolve_suggestion_choice(course, "let's do as-c01") == "as-c01"
    # Ambiguous bare 'yes' over two options does not pick one.
    assert _resolve_suggestion_choice(course, "yes") is None
    # Already linked → nothing to accept.
    course.catalog_id = "cb-c01"
    assert _resolve_suggestion_choice(course, "the second one") is None
