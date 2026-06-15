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


class VerifyRouter:
    """Router that scripts the WORKHORSE (generation) and FAST (verification) calls apart.

    The second-pass self-check uses Capability.FAST; generation uses WORKHORSE. This
    fake returns ``gen_text`` for the WORKHORSE call and either ``verify_text`` (or
    raises ``verify_exc``) for the FAST call, so tests can drive each pass independently.
    """

    def __init__(
        self,
        *,
        gen_text: str,
        verify_text: str = "{}",
        verify_exc: Exception | None = None,
    ) -> None:
        self._gen_text = gen_text
        self._verify_text = verify_text
        self._verify_exc = verify_exc
        self.calls: list[str] = []

    def complete(
        self, capability: object, messages: Sequence[dict[str, str]], **_: object
    ) -> LLMResult:
        self.calls.append(str(getattr(capability, "value", capability)))
        if str(getattr(capability, "value", capability)) == "fast":
            if self._verify_exc is not None:
                raise self._verify_exc
            text = self._verify_text
        else:
            text = self._gen_text
        return LLMResult(
            text=text,
            provider=Provider.AZURE,
            model="gpt-4o-mini",
            tier=1,
            prompt_tokens=10,
            completion_tokens=5,
            latency_ms=12,
        )


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


def test_generate_practice_online_malformed_choices_returns_cta(monkeypatch) -> None:
    """Structurally valid JSON but `choices` is a string (not a list) → fail closed.

    Azure JSON mode is advisory; a string would otherwise iterate into single-char
    "choices" and pass the count check. Guard rejects it, so no card is rendered.
    """
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
        {"prompt": f"Q{i}", "choices": "abcd", "answer_index": 1, "explanation": "e"}
        for i in range(5)
    ]
    fake = FakeRouter(complete_text=json.dumps({"questions": questions}))
    online = Settings(_env_file=None, offline_llm=False, groq_api_key="gsk_x")  # type: ignore[call-arg]
    reply = assessor.generate_practice(
        module_id="cb-c01-m01", module_title="Functions", router=fake, settings=online
    )
    assert reply.practice is None
    assert reply.actions is not None and reply.actions.actions[0].kind == "go_to_module"


# ---------------------------------------------------------------------------
# Answer-key second-pass self-check (online only)
# ---------------------------------------------------------------------------


def _gen_payload() -> str:
    """Five shape-valid MCQs whose key is choices[1] (== "b{i}")."""
    import json

    return json.dumps(
        {
            "questions": [
                {
                    "prompt": f"Q{i}",
                    "choices": [f"a{i}", f"b{i}", f"c{i}", f"d{i}"],
                    "answer_index": 1,
                    "explanation": "e",
                }
                for i in range(5)
            ]
        }
    )


def _online_settings():
    from app.config import Settings

    return Settings(_env_file=None, offline_llm=False, groq_api_key="gsk_x")  # type: ignore[call-arg]


def _content_patch(monkeypatch) -> None:
    from app.agent import assessor
    from app.catalog.content import ModuleContent

    monkeypatch.setattr(
        assessor,
        "get_module_content",
        lambda mid: ModuleContent(module_id=mid, title="Functions", body="Body."),
    )


def test_offline_does_not_run_second_pass_self_check(monkeypatch) -> None:
    """Offline mode produces the deterministic round and never calls the verifier."""
    from app.agent import assessor

    _content_patch(monkeypatch)

    def _boom(*_a: object, **_k: object) -> None:
        raise AssertionError("offline path must not run the online verifier")

    monkeypatch.setattr(assessor, "_verify_questions_online", _boom)
    reply = assessor.generate_practice(module_id="cb-c01-m01", module_title="Functions")
    assert reply.practice is not None and len(reply.practice.questions) == 5


def test_second_pass_disagreeing_with_a_key_drops_that_question(monkeypatch) -> None:
    """When the verifier disagrees on even one key, the confirmed set is < 5 → fall back.

    Dropping below the required count returns the original parsed set (better to show
    shape-valid questions than block practice), so the card still renders all five.
    """
    import json

    from app.agent import assessor

    _content_patch(monkeypatch)
    # Verifier confirms 4 keys but flags Q0 as the wrong key (correct_index != keyed 1).
    verdicts = [
        {"n": 0, "correct_index": 2, "key_correct": False, "grounded": True},
        *[{"n": i, "correct_index": 1, "key_correct": True, "grounded": True} for i in range(1, 5)],
    ]
    router = VerifyRouter(
        gen_text=_gen_payload(), verify_text=json.dumps({"verdicts": verdicts})
    )
    reply = assessor.generate_practice(
        module_id="cb-c01-m01", module_title="Functions", router=router, settings=_online_settings()
    )
    # Both passes ran: WORKHORSE generation then FAST verification.
    assert router.calls == ["workhorse", "fast"]
    assert reply.practice is not None and len(reply.practice.questions) == 5


def test_second_pass_failure_degrades_to_original_questions(monkeypatch) -> None:
    """A failing or unparseable verifier keeps the original questions, never crashes."""
    from app.agent import assessor
    from app.agent.llm import AllProvidersDown

    _content_patch(monkeypatch)
    router = VerifyRouter(gen_text=_gen_payload(), verify_exc=AllProvidersDown("down"))
    reply = assessor.generate_practice(
        module_id="cb-c01-m01", module_title="Functions", router=router, settings=_online_settings()
    )
    assert router.calls == ["workhorse", "fast"]
    assert reply.practice is not None and len(reply.practice.questions) == 5
    assert reply.practice.questions[0].correct == "b0"


def test_second_pass_all_confirmed_keeps_full_set(monkeypatch) -> None:
    """When every key is confirmed and grounded, all five verified questions survive."""
    import json

    from app.agent import assessor

    _content_patch(monkeypatch)
    verdicts = [
        {"n": i, "correct_index": 1, "key_correct": True, "grounded": True} for i in range(5)
    ]
    router = VerifyRouter(
        gen_text=_gen_payload(), verify_text=json.dumps({"verdicts": verdicts})
    )
    reply = assessor.generate_practice(
        module_id="cb-c01-m01", module_title="Functions", router=router, settings=_online_settings()
    )
    assert reply.practice is not None and len(reply.practice.questions) == 5
    assert reply.practice.questions[0].correct == "b0"


# ---------------------------------------------------------------------------
# Task 4: grade, verdict, review, CTA replies, dispatch
# ---------------------------------------------------------------------------


def _questions() -> list[dict[str, object]]:
    return [
        {"id": f"p{i}", "prompt": f"Q{i}", "choices": ["w", "x", "y", "z"], "correct": "w"}
        for i in range(1, 6)
    ]


@pytest.mark.parametrize(
    "n_correct,verdict",
    [(5, "ready"), (4, "ready"), (3, "not_yet"), (2, "not_yet"), (1, "study"), (0, "study")],
)
def test_grade_practice_verdict_mapping(n_correct: int, verdict: str) -> None:
    from app.agent.assessor import grade_practice

    qs = _questions()
    selections = {q["id"]: (["w"] if i < n_correct else ["x"]) for i, q in enumerate(qs)}
    grade = grade_practice(qs, selections)
    assert grade.correct == n_correct
    assert grade.total == 5
    assert grade.verdict == verdict


def test_grade_practice_multiselect_is_wrong() -> None:
    from app.agent.assessor import grade_practice

    qs = _questions()
    # Picking the correct plus an extra is not a clean single-correct answer.
    selections = {qs[0]["id"]: ["w", "x"]}
    grade = grade_practice(qs, selections)
    assert grade.correct == 0
    assert qs[0]["prompt"] in grade.missed


def test_review_practice_ready_offers_take_evaluation() -> None:
    from app.agent.assessor import PracticeGrade, review_practice

    grade = PracticeGrade(correct=5, total=5, verdict="ready", missed=())
    reply = review_practice(
        module_id="cb-c01-m01", module_title="Functions", material="Body.", grade=grade
    )
    kinds = [a.kind for a in reply.actions.actions]
    assert "take_evaluation" in kinds
    assert "5/5" in _drain(reply)


def test_review_practice_study_offers_go_to_module() -> None:
    from app.agent.assessor import PracticeGrade, review_practice

    grade = PracticeGrade(correct=1, total=5, verdict="study", missed=("Q2", "Q3"))
    reply = review_practice(
        module_id="cb-c01-m01", module_title="Functions", material="Body.", grade=grade
    )
    kinds = [a.kind for a in reply.actions.actions]
    assert "go_to_module" in kinds
    assert "take_evaluation" not in kinds


def test_review_practice_online_streams_and_tags_tier() -> None:
    from app.agent.assessor import PracticeGrade, review_practice
    from app.config import Settings

    grade = PracticeGrade(correct=2, total=5, verdict="not_yet", missed=("Q3", "Q4", "Q5"))
    fake = FakeRouter(tokens=["You ", "are ", "close."])
    online = Settings(_env_file=None, offline_llm=False, groq_api_key="gsk_x")  # type: ignore[call-arg]
    reply = review_practice(
        module_id="cb-c01-m01",
        module_title="Functions",
        material="Body.",
        grade=grade,
        router=fake,
        settings=online,
    )
    kinds = [a.kind for a in reply.actions.actions]
    assert "go_to_module" in kinds and "take_evaluation" not in kinds
    assert _drain(reply) == "You are close."
    # The online path tags the model + tier (observability parity with sibling agents).
    assert reply.telemetry.tier == 1
    assert reply.telemetry.model == "gpt-4o-mini"


def test_answer_assessor_practise_with_module(monkeypatch) -> None:
    from app.agent import assessor
    from app.catalog.content import ModuleContent

    monkeypatch.setattr(
        assessor,
        "get_module_content",
        lambda mid: ModuleContent(module_id=mid, title="Functions", body="Body."),
    )
    modules = [{"module_id": "cb-c01-m01", "title": "Functions", "completed": False}]
    reply = assessor.answer_assessor("quiz me", Route.PRACTISE_MODULE, modules=modules)
    assert reply.practice is not None and reply.practice.module_id == "cb-c01-m01"


def test_answer_assessor_take_evaluation_cta() -> None:
    from app.agent import assessor

    modules = [{"module_id": "cb-c01-m01", "title": "Functions", "completed": False}]
    reply = assessor.answer_assessor("I'm ready for the test", Route.TAKE_EVALUATION, modules=modules)
    assert reply.practice is None
    assert reply.actions is not None and reply.actions.actions[0].kind == "take_evaluation"
    assert reply.actions.actions[0].module_id == "cb-c01-m01"


def test_answer_assessor_go_to_module_cta() -> None:
    from app.agent import assessor

    modules = [{"module_id": "cb-c01-m01", "title": "Functions", "completed": False}]
    reply = assessor.answer_assessor("take me to the module", Route.GO_TO_MODULE, modules=modules)
    assert reply.actions is not None and reply.actions.actions[0].kind == "go_to_module"


def test_answer_assessor_no_plan_is_graceful_no_card() -> None:
    from app.agent import assessor

    reply = assessor.answer_assessor("quiz me", Route.PRACTISE_MODULE, modules=[])
    assert reply.practice is None and reply.actions is None
    assert "pick a course" in _drain(reply).lower()


def test_answer_assessor_all_complete_is_graceful_no_card() -> None:
    from app.agent import assessor

    modules = [{"module_id": "m1", "title": "One", "completed": True}]
    reply = assessor.answer_assessor("quiz me", Route.PRACTISE_MODULE, modules=modules)
    assert reply.practice is None and reply.actions is None
    assert "completed every module" in _drain(reply).lower()


# ---------------------------------------------------------------------------
# Task 5: Router — recognise the three intents
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,route",
    [
        ("quiz me on this module", Route.PRACTISE_MODULE),
        ("let me practise this module", Route.PRACTISE_MODULE),
        ("give me some practice questions", Route.PRACTISE_MODULE),
        ("I'm ready for the test", Route.TAKE_EVALUATION),
        ("take the evaluation", Route.TAKE_EVALUATION),
        ("take me to the module", Route.GO_TO_MODULE),
        ("open the module so I can study", Route.GO_TO_MODULE),
    ],
)
def test_classify_routes_assessor_intents(text: str, route: Route) -> None:
    from app.agent.router_agent import classify

    assert classify(text).route is route


def test_classify_does_not_hijack_progress_or_upcoming() -> None:
    from app.agent.router_agent import classify

    assert classify("how many modules have I completed").route is Route.PROGRESS
    assert classify("what is my next module").route is Route.UPCOMING
