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
    # Round-trip from the wire string back to the enum member (router dispatch path).
    assert Route("practise_module") is Route.PRACTISE_MODULE
    assert Route("take_evaluation") is Route.TAKE_EVALUATION
    assert Route("go_to_module") is Route.GO_TO_MODULE


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


def test_course_persists_practice_active(session) -> None:
    from app.courses.repository import CourseRepository

    repo = CourseRepository(session)
    course = repo.create(persona_id="EMP-001", chat_name="Functions")
    course.practice_active = {"module_id": "cb-c01-m01", "title": "X", "questions": []}
    repo.save(course)

    reloaded = repo.get(course.id)
    assert reloaded is not None
    assert reloaded.practice_active["module_id"] == "cb-c01-m01"


def test_resolve_current_module_returns_first_incomplete() -> None:
    from app.agent.assessor import resolve_current_module

    modules = [
        {"module_id": "m1", "title": "One", "completed": True},
        {"module_id": "m2", "title": "Two", "completed": False},
        {"module_id": "m3", "title": "Three", "completed": False},
    ]
    current = resolve_current_module(modules)
    assert current is not None and current["module_id"] == "m2"


def test_resolve_current_module_none_when_empty_or_all_done() -> None:
    from app.agent.assessor import resolve_current_module

    assert resolve_current_module([]) is None
    assert resolve_current_module([{"module_id": "m1", "completed": True}]) is None


def _drain(reply) -> str:
    return "".join(reply.tokens)


def test_generate_practice_offline_makes_five_keyed_mcqs(monkeypatch) -> None:
    from app.agent import assessor
    from app.catalog.content import ModuleContent

    monkeypatch.setattr(
        assessor,
        "get_module_content",
        lambda mid: ModuleContent(module_id=mid, title="Functions", body="Body about functions."),
    )
    reply = assessor.generate_practice(module_id="cb-c01-m01", module_title="Functions")
    assert reply.practice is not None
    assert len(reply.practice.questions) == 5
    for q in reply.practice.questions:
        assert q.kind == "mcq"
        assert len(q.choices) == 4
        assert q.correct in q.choices
    assert "practice" in _drain(reply).lower()


def test_generate_practice_no_content_returns_go_to_module_cta(monkeypatch) -> None:
    from app.agent import assessor

    monkeypatch.setattr(assessor, "get_module_content", lambda mid: None)
    reply = assessor.generate_practice(module_id="cb-c01-m01", module_title="Functions")
    assert reply.practice is None
    assert reply.actions is not None
    assert reply.actions.actions[0].kind == "go_to_module"


def test_generate_practice_online_parses_model_json(monkeypatch) -> None:
    import json

    from app.agent import assessor
    from app.catalog.content import ModuleContent
    from app.config import Settings

    monkeypatch.setattr(
        assessor,
        "get_module_content",
        lambda mid: ModuleContent(module_id=mid, title="Functions", body="Body."),
    )
    questions = [
        {
            "prompt": f"Q{i}",
            "choices": [f"a{i}", f"b{i}", f"c{i}", f"d{i}"],
            "answer_index": 1,
            "explanation": "e",
        }
        for i in range(5)
    ]
    fake = FakeRouter(complete_text=json.dumps({"questions": questions}))
    online = Settings(_env_file=None, offline_llm=False, groq_api_key="gsk_x")  # type: ignore[call-arg]
    reply = assessor.generate_practice(
        module_id="cb-c01-m01", module_title="Functions", router=fake, settings=online
    )
    assert reply.practice is not None and len(reply.practice.questions) == 5
    assert reply.practice.questions[0].correct == "b0"


def test_generate_practice_online_bad_json_returns_cta(monkeypatch) -> None:
    from app.agent import assessor
    from app.catalog.content import ModuleContent
    from app.config import Settings

    monkeypatch.setattr(
        assessor,
        "get_module_content",
        lambda mid: ModuleContent(module_id=mid, title="Functions", body="Body."),
    )
    fake = FakeRouter(complete_text="not json")
    online = Settings(_env_file=None, offline_llm=False, groq_api_key="gsk_x")  # type: ignore[call-arg]
    reply = assessor.generate_practice(
        module_id="cb-c01-m01", module_title="Functions", router=fake, settings=online
    )
    assert reply.practice is None
    assert reply.actions is not None and reply.actions.actions[0].kind == "go_to_module"
