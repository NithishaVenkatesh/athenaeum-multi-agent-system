"""Assessor agent: contracts, generation, grading, verdict, routing, dispatch."""

from __future__ import annotations

from collections.abc import Iterator, Sequence

import pytest
from app.agent.contracts import ActionEvent, PracticeEvent, PracticeQuestion, Route
from app.agent.llm import LLMResult, Provider, StreamHandle


class FakeRouter:
    """Stand-in ModelRouter: scripted ``complete`` JSON and ``stream`` tokens."""

    def __init__(self, *, complete_text: str = "{}", tokens: list[str] | None = None) -> None:
        self._complete_text = complete_text
        self._tokens = tokens or ["ok"]

    def complete(
        self, capability: object, messages: Sequence[dict[str, str]], **_: object
    ) -> LLMResult:
        return LLMResult(
            text=self._complete_text,
            provider=Provider.AZURE,
            model="gpt-4o-mini",
            tier=1,
            prompt_tokens=10,
            completion_tokens=5,
            latency_ms=12,
        )

    def stream(
        self, capability: object, messages: Sequence[dict[str, str]], **_: object
    ) -> StreamHandle:
        def _gen() -> Iterator[str]:
            yield from self._tokens

        return StreamHandle(tokens=_gen(), provider=Provider.AZURE, model="gpt-4o-mini", tier=1)


def test_route_enum_has_assessor_intents() -> None:
    assert Route.PRACTISE_MODULE.value == "practise_module"
    assert Route.TAKE_EVALUATION.value == "take_evaluation"
    assert Route.GO_TO_MODULE.value == "go_to_module"


def test_practice_event_hides_answer_key_from_the_wire() -> None:
    event = PracticeEvent(
        module_id="cb-c01-m01",
        title="Functions",
        questions=[
            PracticeQuestion(
                id="p1",
                prompt="What is X?",
                choices=["a", "b", "c", "d"],
                correct="a",
                explanation="because a",
            )
        ],
    )
    dumped = event.model_dump(mode="json")
    q = dumped["questions"][0]
    assert "correct" not in q and "explanation" not in q
    assert q["choices"] == ["a", "b", "c", "d"]
    # The key is still readable on the live object for server-side grading.
    assert event.questions[0].correct == "a"


def test_action_event_serializes_actions() -> None:
    from app.agent.contracts import Action

    ev = ActionEvent(
        prompt="ready",
        actions=[Action(kind="take_evaluation", label="Take it", module_id="cb-c01-m01")],
    )
    dumped = ev.model_dump(mode="json")
    assert dumped["type"] == "action"
    assert dumped["actions"][0]["kind"] == "take_evaluation"
