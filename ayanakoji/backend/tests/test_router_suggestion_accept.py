"""Conversational course-suggestion accept (finding R2)."""

from __future__ import annotations

import pytest
from app.agent.contracts import Route
from app.agent.router_agent import classify, is_acceptance


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
