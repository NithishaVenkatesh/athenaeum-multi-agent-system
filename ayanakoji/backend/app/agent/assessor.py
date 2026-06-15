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
import logging
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
from app.agent.llm import Capability, LLMError, ModelRouter
from app.catalog.content import get_module_content
from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

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
                prompt=(
                    f"Practice question {i} on {module_title}: which statement is most accurate?"
                ),
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


def _verify_questions_online(
    module_title: str, body: str, questions: list[PracticeQuestion], router: ModelRouter
) -> list[PracticeQuestion]:
    """Second pass: re-derive each answer from the module and keep only confirmed keys.

    One batched, cheap (FAST capability) verification call re-grades the *keyed*
    answer of every question against the module material. We drop a question when the
    verifier disagrees with the key or flags it as not grounded in the module. The key
    is never sent: we send the choice *index* it claims is correct and ask the verifier
    for the index it believes is correct, so agreement is a real re-derivation, not an
    echo. Degrades gracefully: any failure or unparseable reply keeps the original set.
    """
    payload = [
        {
            "n": i,
            "prompt": q.prompt,
            "choices": list(q.choices),
            "keyed_index": q.choices.index(q.correct),
        }
        for i, q in enumerate(questions)
    ]
    system = (
        "You are Athenaeum's practice answer-key verifier. Using ONLY the module material "
        "below, decide for each question whether the answer at 'keyed_index' is the single "
        "correct, module-grounded answer. Independently work out the correct choice index "
        "yourself. Mark grounded=false if the question is not answerable from this module. "
        "Reply ONLY with JSON: "
        '{"verdicts":[{"n":int,"correct_index":0-3,"key_correct":bool,"grounded":bool}]}.'
        + _NO_LEAK
        + _NO_OVERRIDE
        + f"\n\nMODULE: {module_title}\n{body[:4000]}"
    )
    try:
        result = router.complete(
            Capability.FAST,
            [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps({"questions": payload})},
            ],
            json_mode=True,
            max_tokens=600,
        )
        data = json.loads(result.text)
        verdicts = data.get("verdicts") if isinstance(data, dict) else None
        if not isinstance(verdicts, list):
            raise ValueError("verifier returned no 'verdicts' list")
    except (json.JSONDecodeError, KeyError, ValueError, TypeError, LLMError) as exc:
        logger.warning("practice verification unavailable, keeping unverified questions: %s", exc)
        return questions

    confirmed: dict[int, bool] = {}
    for v in verdicts:
        if not isinstance(v, dict):
            continue
        try:
            n = int(v["n"])
            keyed_index = questions[n].choices.index(questions[n].correct)
            ok = bool(v.get("key_correct")) and bool(v.get("grounded", True))
            ok = ok and int(v.get("correct_index", keyed_index)) == keyed_index
        except (KeyError, ValueError, TypeError, IndexError):
            continue
        confirmed[n] = ok

    kept = [q for i, q in enumerate(questions) if confirmed.get(i, False)]
    if len(kept) < PRACTICE_QUESTION_COUNT:
        # Better to show shape-valid questions than block practice; mirror the graceful
        # "practice unavailable" stance rather than dropping below the required count.
        logger.warning(
            "practice verification confirmed only %d/%d keys; keeping the original set",
            len(kept),
            PRACTICE_QUESTION_COUNT,
        )
        return questions
    return kept


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
            {
                "role": "user",
                "content": (
                    f"Write {PRACTICE_QUESTION_COUNT} practice questions on {module_title}."
                ),
            },
        ],
        json_mode=True,
        max_tokens=1400,
    )
    questions = _parse_questions(result.text)
    if questions is not None:
        # Second pass: re-derive each key from the module and drop unconfirmed ones.
        questions = _verify_questions_online(module_title, body, questions, router)
    return questions, result.model


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
            return _practice_unavailable(
                module_id, module_title, reason="generation produced no valid questions"
            )

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


# ---------------------------------------------------------------------------
# Task 4: grading, verdict, review, CTA replies, dispatch
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PracticeGrade:
    """Deterministic grading of one practice round."""

    correct: int
    total: int
    verdict: str  # "ready" | "not_yet" | "study"
    missed: tuple[str, ...]  # prompts of the questions answered wrong (immutable)


def _verdict_for(correct: int) -> str:
    if correct >= READY_MIN_CORRECT:
        return "ready"
    if correct <= STUDY_MAX_CORRECT:
        return "study"
    return "not_yet"


def grade_practice(
    questions: list[dict[str, object]], selections: dict[str, list[str]]
) -> PracticeGrade:
    """Grade selections against the server-side key: a single exact correct pick wins."""
    correct = 0
    missed: list[str] = []
    for q in questions:
        qid = str(q.get("id"))
        picks = selections.get(qid) or []
        # A single exact match wins; blank, wrong, multi-select, or a non-list value
        # (defensive — the wire schema enforces a list, but this is a pure function) → missed.
        if isinstance(picks, list) and len(picks) == 1 and picks[0] == q.get("correct"):
            correct += 1
        else:
            missed.append(str(q.get("prompt", qid)))
    total = len(questions)
    return PracticeGrade(
        correct=correct, total=total, verdict=_verdict_for(correct), missed=tuple(missed)
    )


def _practice_actions(verdict: str, module_id: str) -> ActionEvent:
    again = Action(kind="practice_again", label="Practise again", module_id=module_id)
    if verdict == "ready":
        return ActionEvent(
            prompt="You are ready. Take the module evaluation whenever you want.",
            actions=[
                Action(kind="take_evaluation", label="Take the evaluation", module_id=module_id),
                again,
            ],
        )
    return ActionEvent(
        prompt="Spend a little more time on the module, then come back.",
        actions=[
            Action(kind="go_to_module", label="Go to the module", module_id=module_id),
            again,
        ],
    )


def _review_offline(module_title: str, grade: PracticeGrade) -> str:
    score = f"{grade.correct}/{grade.total}"
    missed = "; ".join(grade.missed[:3])
    # Only name specific gaps when there are any (avoids a dangling ": ." if missed is empty).
    gaps = f" Review these before the evaluation: {missed}." if missed else ""
    if grade.verdict == "ready":
        return (
            f"(offline mode) Nice work, you got {score} on this practice for {module_title}. You "
            "clearly understand the core ideas. When you are ready, take the module evaluation."
        )
    if grade.verdict == "not_yet":
        return (
            f"(offline mode) You got {score} on this practice for {module_title}. You are close."
            f"{gaps} Then practise again or open the module."
        )
    return (
        f"(offline mode) You got {score} on this practice for {module_title}. Let us build the "
        f"foundation first. Revisit the module.{gaps} Practise again when ready."
    )


def review_practice(
    *,
    module_id: str,
    module_title: str,
    material: str,
    grade: PracticeGrade,
    router: ModelRouter | None = None,
    settings: Settings | None = None,
) -> AgentReply:
    """Honest, motivating review of a practice round, with the verdict's CTA."""
    settings = settings or get_settings()
    source = GroundingSource(
        ref=module_id, title=module_title, snippet=material[:200], kind="course"
    )
    reasoning = f"Practice review for {module_id}: {grade.correct}/{grade.total} → {grade.verdict}"

    if settings.llm_offline:
        tokens: Iterator[str] = _offline_stream(_review_offline(module_title, grade))
        model: str | None = "offline"
        tier: int | None = None
        steps = [TraceStep(label="LLM review", passed=True, detail="offline mode", model="offline")]
    else:
        # Cap the named gaps at 3, matching the offline path (bounds the prompt + focuses study).
        missed = "; ".join(grade.missed[:3]) or "(none)"
        tone = (
            "They passed; congratulate them honestly and invite them to take the evaluation."
            if grade.verdict == "ready"
            else "They are not ready yet; be honest about the gaps but motivating, and steer them "
            "back to study the module before the evaluation."
        )
        system = (
            "You are Athenaeum's honest, encouraging course tutor reviewing a short practice the "
            f"learner just took for the module below. They scored {grade.correct}/{grade.total}. "
            f"{tone} Ground every point in the MODULE material; name the concepts they missed and "
            "what to revisit, in 3 to 4 sentences. Never invent content. Do not use em dashes; use "
            "commas or periods."
            + _NO_LEAK
            + _NO_OVERRIDE
            + f"\n\nMODULE [{module_id}] {module_title}:\n{material}\n\nMISSED QUESTIONS:\n{missed}"
        )
        active = router or ModelRouter(settings)
        stream_handle = active.stream(
            Capability.WORKHORSE,
            [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": (f"Review my practice; I scored {grade.correct}/{grade.total}."),
                },
            ],
            max_tokens=500,
        )
        tokens = stream_handle.tokens
        model = stream_handle.model
        tier = stream_handle.tier
        steps = [
            TraceStep(
                label="LLM review",
                passed=True,
                detail="WORKHORSE capability · max 500 tokens · grounded in module material",
                model=model,
            )
        ]

    return AgentReply(
        telemetry=_answer_telemetry(
            summary="Reviewed your practice and gave a verdict",
            reasoning=reasoning,
            route=Route.PRACTISE_MODULE,
            sources=[source],
            model=model,
            tier=tier,
            steps=steps,
        ),
        tokens=tokens,
        sources=[source],
        actions=_practice_actions(grade.verdict, module_id),
    )


def _cta_reply(module_id: str, module_title: str, route: Route) -> AgentReply:
    """A short deterministic reply that surfaces a single CTA button."""
    if route is Route.TAKE_EVALUATION:
        msg = (
            f'Great, you can take the evaluation for "{module_title}" whenever you are ready. Use '
            "the button below to start it."
        )
        action = Action(kind="take_evaluation", label="Take the evaluation", module_id=module_id)
        summary = "Pointed the learner to the evaluation"
    else:
        msg = (
            f'Sure, here is the module "{module_title}". Use the button below to open it and study.'
        )
        action = Action(kind="go_to_module", label="Go to the module", module_id=module_id)
        summary = "Pointed the learner to the module"
    return AgentReply(
        telemetry=_answer_telemetry(
            summary=summary,
            reasoning=f"CTA for {module_id}",
            route=route,
            sources=[],
            model=None,
            tier=None,
        ),
        tokens=_offline_stream(msg),
        actions=ActionEvent(actions=[action]),
    )


def _no_current_module(modules: list[dict[str, object]] | None) -> AgentReply:
    """Graceful reply (no card, no button) when the hard module gate is not met."""
    if not modules:
        msg = (
            "You do not have an active module yet. Pick a course and I will build your study plan, "
            "then you can practise the module you are on."
        )
        reasoning = "No plan modules: nothing to practise."
    else:
        msg = (
            "You have completed every module in this course. There is nothing left to practise "
            "here, consider the certification exam or ask me for your next course."
        )
        reasoning = "All modules complete."
    return AgentReply(
        telemetry=_answer_telemetry(
            summary="No current module to practise",
            reasoning=reasoning,
            route=Route.PRACTISE_MODULE,
            sources=[],
            model=None,
            tier=None,
        ),
        tokens=_offline_stream(msg),
    )


def answer_assessor(
    text: str,
    route: Route,
    *,
    modules: list[dict[str, object]] | None,
    router: ModelRouter | None = None,
    settings: Settings | None = None,
) -> AgentReply:
    """Dispatch the three assessor routes behind the hard current-module gate."""
    settings = settings or get_settings()
    current = resolve_current_module(modules)
    if current is None:
        return _no_current_module(modules)
    module_id = str(current["module_id"])
    module_title = str(current.get("title", "")) or module_id
    if route is Route.PRACTISE_MODULE:
        return generate_practice(
            module_id=module_id, module_title=module_title, router=router, settings=settings
        )
    return _cta_reply(module_id, module_title, route)
