"""The Azure assessor agent: practise the module the learner is currently in.

Pure functions returning :class:`AgentReply`, dispatched from the orchestrator for
the ``PRACTISE_MODULE`` / ``TAKE_EVALUATION`` / ``GO_TO_MODULE`` routes. Practice is
formative only: questions are generated (Azure, grounded in the module's markdown),
the answer key never reaches the client, and nothing is written to the Assessment
table. The offline path produces a deterministic round so the flow is testable
without a live model (mirroring every other agent).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass

from app.agent.answer import (
    _NO_LEAK,
    _NO_OVERRIDE,
    AgentReply,
    _answer_telemetry,
    _offline_stream,
)
from app.agent.contracts import (
    Action,
    ActionEvent,
    GroundingSource,
    PracticeEvent,
    PracticeQuestion,
    Route,
    TraceStep,
)
from app.agent.llm import Capability, ModelRouter
from app.catalog.content import get_module_content
from app.config import Settings, get_settings

PRACTICE_QUESTION_COUNT = 5
READY_MIN_CORRECT = 4  # >= 4/5 (80%) → ready for the evaluation
STUDY_MAX_CORRECT = 1  # <= 1/5 → needs to study; 2-3 → not yet


def resolve_current_module(modules: list[dict[str, object]] | None) -> dict[str, object] | None:
    """The module the learner is currently in: the first one not yet completed.

    Returns None when there is no plan (empty list) or every module is complete —
    the deterministic hard gate the assessor routes are filtered on.
    """
    return next((m for m in (modules or []) if not m.get("completed")), None)


def _intro(module_title: str) -> str:
    return (
        f'Here is a quick {PRACTICE_QUESTION_COUNT}-question practice on "{module_title}". '
        "Answer them and I will review how you did and tell you whether you are ready for the "
        "evaluation."
    )


def _practice_unavailable(module_id: str, module_title: str, *, reason: str) -> AgentReply:
    """No content / generation failed: apologise and point to the module to study."""
    msg = (
        "I could not put together a clean practice set for this module right now. Open the "
        "module to study it, and try practising again in a bit."
    )
    return AgentReply(
        telemetry=_answer_telemetry(
            summary="Practice unavailable",
            reasoning=reason,
            route=Route.PRACTISE_MODULE,
            sources=[],
            model=None,
            tier=None,
        ),
        tokens=_offline_stream(msg),
        actions=ActionEvent(
            actions=[Action(kind="go_to_module", label="Go to the module", module_id=module_id)]
        ),
    )


def _offline_questions(module_title: str) -> list[PracticeQuestion]:
    """A deterministic round so the offline / test path exercises the full flow."""
    out: list[PracticeQuestion] = []
    for i in range(1, PRACTICE_QUESTION_COUNT + 1):
        correct = f"Accurate statement {i} about {module_title}"
        out.append(
            PracticeQuestion(
                id=f"p{i}",
                prompt=f"Practice question {i} on {module_title}: which statement is most accurate?",
                choices=[correct, f"Distractor {i}A", f"Distractor {i}B", f"Distractor {i}C"],
                correct=correct,
                explanation=f"See the module material on {module_title}.",
            )
        )
    return out


def _parse_questions(raw: str) -> list[PracticeQuestion] | None:
    """Validate the model's JSON into 5 well-formed MCQs, or None if unusable.

    Temperature is 0, so a malformed reply will not change on retry; we fall straight
    to the graceful 'practice unavailable' path rather than re-calling.
    """
    try:
        data = json.loads(raw)
        items = data.get("questions") if isinstance(data, dict) else None
        if not isinstance(items, list) or len(items) < PRACTICE_QUESTION_COUNT:
            return None
        out: list[PracticeQuestion] = []
        for i, item in enumerate(items[:PRACTICE_QUESTION_COUNT], start=1):
            # Azure JSON mode is advisory: a string ("a,b,c,d") would iterate into
            # single-char "choices" and pass the count check, so guard the shape first.
            if not isinstance(item, dict) or not isinstance(item.get("choices"), list):
                return None
            prompt = str(item["prompt"]).strip()
            choices = [str(c).strip() for c in item["choices"]]
            idx = int(item["answer_index"])
            if not prompt or len(choices) != 4 or len(set(choices)) != 4 or not (0 <= idx < 4):
                return None
            out.append(
                PracticeQuestion(
                    id=f"p{i}",
                    prompt=prompt,
                    choices=choices,
                    correct=choices[idx],
                    explanation=str(item.get("explanation", "")).strip(),
                )
            )
        return out
    except (json.JSONDecodeError, KeyError, ValueError, TypeError):
        return None


def _generate_questions_online(
    module_title: str, body: str, router: ModelRouter
) -> tuple[list[PracticeQuestion] | None, str | None]:
    system = (
        "You are Athenaeum's practice question writer. Using ONLY the module material below, "
        f"write exactly {PRACTICE_QUESTION_COUNT} multiple-choice questions that check "
        "understanding of its core ideas. Each question has exactly 4 distinct answer choices "
        "with exactly one correct. Do not use em dashes; use commas or periods. Reply ONLY with "
        'JSON: {"questions":[{"prompt":str,"choices":[4 strings],"answer_index":0-3,'
        '"explanation":str}]}.'
        + _NO_LEAK
        + _NO_OVERRIDE
        + f"\n\nMODULE: {module_title}\n{body[:4000]}"
    )
    result = router.complete(
        Capability.WORKHORSE,
        [
            {"role": "system", "content": system},
            {"role": "user", "content": f"Write {PRACTICE_QUESTION_COUNT} practice questions on {module_title}."},
        ],
        json_mode=True,
        max_tokens=1400,
    )
    return _parse_questions(result.text), result.model


def generate_practice(
    *,
    module_id: str,
    module_title: str,
    router: ModelRouter | None = None,
    settings: Settings | None = None,
) -> AgentReply:
    """Generate a 5-MCQ practice round grounded in the current module's content."""
    settings = settings or get_settings()
    content = get_module_content(module_id)
    if content is None:
        return _practice_unavailable(module_id, module_title, reason="no module content")

    if settings.llm_offline:
        questions: list[PracticeQuestion] | None = _offline_questions(module_title)
        model: str | None = "offline"
    else:
        questions, model = _generate_questions_online(
            module_title, content.body, router or ModelRouter(settings)
        )
        if questions is None:
            return _practice_unavailable(module_id, module_title, reason="generation produced no valid questions")

    source = GroundingSource(
        ref=module_id, title=module_title, snippet=content.body[:200], kind="course"
    )
    steps = [
        TraceStep(
            label="Practice generation",
            passed=True,
            detail=f"{PRACTICE_QUESTION_COUNT} MCQs grounded in module material [{module_id}]",
            model=model,
        )
    ]
    return AgentReply(
        telemetry=_answer_telemetry(
            summary="Generated a practice round for your current module",
            reasoning=f"{PRACTICE_QUESTION_COUNT} grounded MCQs for {module_id}",
            route=Route.PRACTISE_MODULE,
            sources=[source],
            model=model,
            tier=None,
            steps=steps,
        ),
        tokens=_offline_stream(_intro(module_title)),
        sources=[source],
        practice=PracticeEvent(module_id=module_id, title=module_title, questions=questions),
    )
