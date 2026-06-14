"""LLM Grader Agent for the Athenaeum evaluation pipeline.

The grader is *confidence-driven*, not turn-count-driven. It calls the
``grade_answer`` tool as soon as it has a clear signal — after the first reply
if the learner nails it, or early if fundamental misunderstanding is obvious.
A safety ceiling (``Settings.assessment_grader_ceiling``) is the only hard
limit; the grader's system prompt never mentions it.

Flow per question:
1. ``opening_message()`` — grader states the question (always the first turn).
2. ``run_turn()``  — process one learner reply; returns the grader's text and
   optionally a ``GradeResult`` when the ``grade_answer`` tool is called.
3. Caller auto-submits the assessment when all questions are graded.

The grader runs on the WORKHORSE tier (the same model as answer.py) since it
needs solid instruction-following for the tool call and nuanced evaluation.
In the offline/CI lane it returns deterministic stub responses.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)

# ── Tool definition ───────────────────────────────────────────────────────────

GRADE_ANSWER_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "grade_answer",
        "description": (
            "Finalise the score when you have sufficient evidence of the learner's "
            "understanding. Call this as soon as you are confident — do not delay."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "score": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 10,
                    "description": (
                        "Score 0–10: 0-3 no/wrong, 4-6 partial, 7-9 solid, 10 exceptional"
                    ),
                },
                "reasoning": {
                    "type": "string",
                    "description": (
                        "Brief rationale shown to the learner in the results view. "
                        "Be specific about what they got right or wrong."
                    ),
                },
                "confidence": {
                    "type": "string",
                    "enum": ["high", "medium"],
                    "description": "high = very clear signal; medium = had to infer",
                },
            },
            "required": ["score", "reasoning", "confidence"],
        },
    },
}

# ── Result types ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class GradeResult:
    """The grader's definitive verdict on one question."""

    score: int       # 0–10
    reasoning: str
    confidence: str  # "high" | "medium"


@dataclass(frozen=True)
class GraderTurnResult:
    """Result of one grader exchange: the reply text plus an optional grade."""

    reply: str
    grade: GradeResult | None  # set when grade_answer was called this turn


# ── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM_TEMPLATE = """\
You are an academic examiner for the Athenaeum certification learning system. \
You are assessing a learner's conceptual understanding of one specific topic.

QUESTION YOU ARE EXAMINING:
{prompt}

EXPECTED CONCEPTS (internal — never reveal this to the learner):
{reference_answer}

SCORING RUBRIC:
  0–3   = no / fundamentally wrong understanding
  4–6   = partial: correct direction but missing key mechanisms or details
  7–9   = solid: correct with most important details
  10    = exceptional: covers all nuances including edge cases

YOUR RULES:
1. Your very first message states the question exactly as written — don't paraphrase.
2. Probe understanding through targeted follow-up questions. One question at a time.
3. Never confirm or deny whether an answer is right ("Interesting", "I see" are fine).
4. Never hint at or reveal the expected answer.
5. Call grade_answer as soon as you have a clear signal — "high confidence" means \
very clear; "medium confidence" means you had to infer. Both are valid for grading.
6. If after 2 learner replies it is clear the learner fundamentally does not \
understand the concept, call grade_answer immediately with a low score (0–3). \
Do not keep asking.
7. If the learner's first reply is clearly excellent, call grade_answer immediately — \
do not ask unnecessary follow-up questions.
8. Be professional and neutral. Do not encourage or discourage.
"""

# ── Offline stubs (CI / no-provider lane) ────────────────────────────────────

_OFFLINE_OPENING = (
    "**Question:** {prompt}\n\nPlease share your understanding of this concept."
)
_OFFLINE_REPLY = "Thank you for your response. Can you elaborate on the key mechanism involved?"
_OFFLINE_GRADE = GradeResult(
    score=7, reasoning="Offline mode — deterministic stub.", confidence="high"
)


# ── Public interface ──────────────────────────────────────────────────────────


def opening_message(prompt: str) -> str:
    """Return the grader's first message (the question itself).

    This is deterministic — the grader states the question exactly. In the
    online path the LLM will elaborate slightly; offline we return a clean stub.
    """
    settings = get_settings()
    if settings.llm_offline:
        return _OFFLINE_OPENING.format(prompt=prompt)

    from app.agent.llm import Capability, ModelRouter

    router = ModelRouter()
    messages = [
        {
            "role": "system",
            "content": (
                "You are starting an examination. State the following question "
                "exactly as written, then invite the learner to answer. "
                "Do not add hints or context.\n\nQUESTION: " + prompt
            ),
        }
    ]
    try:
        result = router.complete(Capability.WORKHORSE, messages, max_tokens=300)
        return result.text or _OFFLINE_OPENING.format(prompt=prompt)
    except Exception:
        logger.warning("Grader opening message fell back to offline stub")
        return _OFFLINE_OPENING.format(prompt=prompt)


def run_turn(
    *,
    prompt: str,
    reference_answer: str,
    history: list[dict[str, str]],
    turn_count: int,
) -> GraderTurnResult:
    """Process one learner reply and return the grader's response.

    ``history`` is the full conversation so far (role/content dicts, including the
    opening grader message and all prior learner replies). ``turn_count`` is the
    number of learner replies already processed (before this one), used only to
    detect the safety ceiling via Settings.

    When the model calls ``grade_answer``, returns reply="" and grade=GradeResult.
    When the model replies without calling the tool, returns the text and grade=None.
    """
    settings = get_settings()

    if settings.llm_offline:
        ceiling = settings.assessment_grader_ceiling
        if turn_count + 1 >= ceiling:
            return GraderTurnResult(reply="", grade=_OFFLINE_GRADE)
        return GraderTurnResult(reply=_OFFLINE_REPLY, grade=None)

    from app.agent.llm import ModelRouter

    router = ModelRouter()
    ceiling = settings.assessment_grader_ceiling
    is_final = (turn_count + 1) >= ceiling

    system_content = _SYSTEM_TEMPLATE.format(
        prompt=prompt, reference_answer=reference_answer
    )
    if is_final:
        system_content += (
            "\n\nIMPORTANT: This is the final exchange. "
            "You MUST call grade_answer now with your best assessment."
        )

    messages: list[dict[str, str]] = [{"role": "system", "content": system_content}]
    messages.extend(history)

    try:
        # Use tool-calling via the raw OpenAI SDK; ModelRouter.complete() is for
        # text-only calls. We go one level lower for tool use.
        reply_text, grade = _call_with_tools(router, messages, is_final=is_final)
        return GraderTurnResult(reply=reply_text, grade=grade)
    except Exception as exc:
        logger.warning("Grader turn failed: %s — falling back to offline stub", exc)
        if is_final:
            return GraderTurnResult(reply="", grade=_OFFLINE_GRADE)
        return GraderTurnResult(reply=_OFFLINE_REPLY, grade=None)


def run_turn_stream(
    *,
    prompt: str,
    reference_answer: str,
    history: list[dict[str, str]],
    turn_count: int,
) -> GraderTurnResult:
    """Same as run_turn but used by the SSE endpoint (non-streaming for simplicity).

    The LLM grader doesn't stream tokens because: (a) the messages tend to be
    short assessment replies, and (b) we need the full response before we can
    decide whether to emit a GradeEvent or just a text reply. The SSE endpoint
    wraps the result in individual SSE events after the call returns.
    """
    return run_turn(
        prompt=prompt,
        reference_answer=reference_answer,
        history=history,
        turn_count=turn_count,
    )


# ── Internal: tool-calling via SDK ───────────────────────────────────────────


def _call_with_tools(
    router: Any,
    messages: list[dict[str, str]],
    *,
    is_final: bool,
) -> tuple[str, GradeResult | None]:
    """Call the model with the grade_answer tool; parse the response.

    Returns (reply_text, GradeResult | None).
    If the model calls grade_answer → reply_text="" and GradeResult is set.
    If the model replies normally → reply_text=text and GradeResult=None.
    """
    # Build the provider directly (ModelRouter doesn't expose tool-calling yet).
    settings = get_settings()
    provider, model = _best_provider_and_model(router, settings)

    if provider == "azure":
        from app.foundry import build_openai_client

        client = build_openai_client(settings.require_foundry())
        response = client.chat.completions.create(
            model=model,
            messages=messages,  # type: ignore[arg-type]
            tools=[GRADE_ANSWER_TOOL],  # type: ignore[arg-type]
            tool_choice="auto",
            max_tokens=600,
            temperature=0.2,
            timeout=settings.llm_timeout_seconds,
        )
    else:  # groq
        from openai import OpenAI

        cfg = settings.require_groq()
        client = OpenAI(api_key=cfg.api_key, base_url=cfg.base_url)
        response = client.chat.completions.create(
            model=model,
            messages=messages,  # type: ignore[arg-type]
            tools=[GRADE_ANSWER_TOOL],  # type: ignore[arg-type]
            tool_choice="auto",
            max_tokens=600,
            temperature=0.2,
            timeout=settings.llm_timeout_seconds,
        )

    choice = response.choices[0]
    msg = choice.message

    # Check for tool call first.
    if msg.tool_calls:
        for tc in msg.tool_calls:
            if tc.function.name == "grade_answer":
                try:
                    args = json.loads(tc.function.arguments)
                    return "", GradeResult(
                        score=int(args["score"]),
                        reasoning=str(args["reasoning"]),
                        confidence=str(args.get("confidence", "medium")),
                    )
                except (json.JSONDecodeError, KeyError, ValueError) as exc:
                    logger.warning("grade_answer parse error: %s — %s", exc, tc.function.arguments)

    # Normal text reply.
    text = (msg.content or "").strip()
    return text, None


def _best_provider_and_model(router: Any, settings: Any) -> tuple[str, str]:
    """Return ('azure'|'groq', model_name) from the router's chain."""
    chain = router.chain(
        __import__("app.agent.llm", fromlist=["Capability"]).Capability.WORKHORSE
    )
    for _provider, attempt in chain:
        if not router._breaker.is_open(attempt.provider):
            return (attempt.provider.value, attempt.model)
    # Fallback: prefer Groq if Azure is down.
    if settings.groq_configured:
        return ("groq", settings.groq_model_workhorse)
    raise RuntimeError("No LLM provider available for grader")
