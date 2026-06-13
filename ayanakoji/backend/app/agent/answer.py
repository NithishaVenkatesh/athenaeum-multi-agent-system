"""The three answer agents the router dispatches to.

- ``answer_general`` — no tools; a helpful reply plus a platform nudge whose
  strength scales with how off-topic the turn is.
- ``answer_foundry`` — tool scope: course grounding only. Grounded, cited answer
  over approved catalog content, followed by the 'pursue this course?' tool.
- ``answer_work`` — tool scope: the Work IQ persona read only. A work-aware reply
  grounded in the learner's own (synthetic) schedule signals.

Every agent returns an :class:`AgentReply`: telemetry (built once the winning
provider tier is known), a token iterator, the grounding sources, and an optional
course suggestion. Online answers stream via the model router; offline answers
stream a deterministic reply word-by-word (mirroring ``courses/service.py``).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

from app.agent.contracts import (
    CourseSuggestion,
    GroundingSource,
    PhaseName,
    PhaseStatus,
    PhaseTelemetry,
    Route,
    RouteDecision,
)
from app.agent.grounding import CourseGrounding, get_grounding
from app.agent.llm import Capability, ModelRouter, StreamHandle
from app.config import Settings, get_settings
from app.workiq.models import Persona
from app.workiq.repository import WorkIQRepository, get_repository


@dataclass
class AgentReply:
    """A streamed answer plus the telemetry + grounding the user is shown."""

    telemetry: PhaseTelemetry
    tokens: Iterator[str]
    sources: list[GroundingSource] = field(default_factory=list)
    suggestion: CourseSuggestion | None = None


def _offline_stream(text: str) -> Iterator[str]:
    """Stream a fixed reply word-by-word so the offline path looks live."""
    for word in text.split(" "):
        yield word + " "


def _answer_telemetry(
    *,
    summary: str,
    reasoning: str,
    route: Route,
    sources: list[GroundingSource],
    model: str | None,
    tier: int | None,
) -> PhaseTelemetry:
    return PhaseTelemetry(
        phase=PhaseName.ANSWER,
        status=PhaseStatus.PASSED,
        summary=summary,
        reasoning=reasoning,
        route=route,
        sources=sources,
        model=model,
        tier=tier,
    )


# ── General (no tools) ─────────────────────────────────────────────────────────

_NUDGE_LIGHT = (
    "End with a brief, warm invitation to explore the platform's Azure certification "
    "courses — one short sentence, not pushy."
)
_NUDGE_MEDIUM = (
    "Answer helpfully, then note in one sentence that this assistant is primarily for "
    "enterprise Azure certification learning."
)
_NUDGE_STRONG = (
    "Answer the question briefly and accurately, then clearly but politely say this "
    "assistant is primarily for Azure / enterprise-learning help and invite them back to it."
)


def _nudge_for(off_topic: float) -> str:
    if off_topic >= 0.7:
        return _NUDGE_STRONG
    if off_topic >= 0.3:
        return _NUDGE_MEDIUM
    return _NUDGE_LIGHT


def _general_offline(off_topic: float) -> str:
    base = (
        "(offline mode) I'm Athenaeum, your enterprise learning assistant. I can help most "
        "with Azure certifications and the courses in this platform."
    )
    if off_topic >= 0.7:
        return base + (
            " That topic is outside what I focus on, but I'm happy to point you toward an "
            "Azure learning path whenever you're ready."
        )
    if off_topic >= 0.3:
        return base + " Tell me a certification or topic you're aiming for and we'll start there."
    return base + " Ask me about any Azure topic or course to begin exploring."


def answer_general(
    text: str,
    decision: RouteDecision,
    *,
    router: ModelRouter | None = None,
    settings: Settings | None = None,
) -> AgentReply:
    """Helpful general reply with a platform nudge scaled to how off-topic the turn is."""
    settings = settings or get_settings()
    reasoning = f"General assistance; off-topic≈{decision.off_topic:.1f} → scaled nudge."
    if settings.llm_offline:
        reply = _general_offline(decision.off_topic)
        return AgentReply(
            telemetry=_answer_telemetry(
                summary="Answered generally with a platform nudge",
                reasoning=reasoning,
                route=Route.GENERAL,
                sources=[],
                model="offline",
                tier=None,
            ),
            tokens=_offline_stream(reply),
        )

    router = router or ModelRouter(settings)
    system = (
        "You are Athenaeum, an enterprise learning assistant focused on Azure certifications. "
        "Be helpful and concise. " + _nudge_for(decision.off_topic)
    )
    handle: StreamHandle = router.stream(
        Capability.WORKHORSE,
        [{"role": "system", "content": system}, {"role": "user", "content": text}],
        max_tokens=600,
    )
    return AgentReply(
        telemetry=_answer_telemetry(
            summary="Answered generally with a platform nudge",
            reasoning=reasoning,
            route=Route.GENERAL,
            sources=[],
            model=handle.model,
            tier=handle.tier,
        ),
        tokens=handle.tokens,
    )


# ── Foundry IQ (tool scope: course grounding only) ─────────────────────────────


def _sources_block(sources: list[GroundingSource]) -> str:
    return "\n".join(f"[{s.ref}] {s.title}: {s.snippet}" for s in sources)


def _foundry_offline(sources: list[GroundingSource]) -> str:
    if not sources:
        return (
            "(offline mode) I don't have approved course content covering that yet. Try asking "
            "about an Azure topic such as App Service, Functions, Cosmos DB, or identity."
        )
    lead = sources[0]
    refs = ", ".join(s.ref for s in sources)
    return (
        f"(offline mode) Here's what our approved content covers on this. {lead.title} "
        f"addresses it directly — {lead.snippet} You can dig deeper in the linked modules "
        f"[{refs}]. Want a study plan built around this?"
    )


def answer_foundry(
    text: str,
    *,
    catalog_id: str | None = None,
    router: ModelRouter | None = None,
    grounding: CourseGrounding | None = None,
    settings: Settings | None = None,
) -> AgentReply:
    """Grounded, cited answer over approved content + a 'pursue this course?' suggestion."""
    settings = settings or get_settings()
    grounding = grounding or get_grounding()
    sources = grounding.search(text, catalog_id=catalog_id)
    suggestion = grounding.suggest(text, catalog_id=catalog_id)
    reasoning = (
        f"Grounded on {len(sources)} approved module(s): {', '.join(s.ref for s in sources)}."
        if sources
        else "No approved content matched — answering with an explicit 'not covered'."
    )

    if settings.llm_offline:
        reply = _foundry_offline(sources)
        return AgentReply(
            telemetry=_answer_telemetry(
                summary="Answered from approved course content",
                reasoning=reasoning,
                route=Route.FOUNDRY_IQ,
                sources=sources,
                model="offline",
                tier=None,
            ),
            tokens=_offline_stream(reply),
            sources=sources,
            suggestion=suggestion,
        )

    router = router or ModelRouter(settings)
    system = (
        "You are Athenaeum's course tutor. Answer ONLY from the approved sources below; cite "
        "the module id in square brackets like [cb-c01-m02] for each claim. If the sources do "
        "not cover the question, say so plainly — never invent content.\n\nSOURCES:\n"
        + (_sources_block(sources) or "(none)")
    )
    handle = router.stream(
        Capability.WORKHORSE,
        [{"role": "system", "content": system}, {"role": "user", "content": text}],
        max_tokens=800,
    )
    return AgentReply(
        telemetry=_answer_telemetry(
            summary="Answered from approved course content",
            reasoning=reasoning,
            route=Route.FOUNDRY_IQ,
            sources=sources,
            model=handle.model,
            tier=handle.tier,
        ),
        tokens=handle.tokens,
        sources=sources,
        suggestion=suggestion,
    )


# ── Work IQ (tool scope: persona read only) ────────────────────────────────────


def _work_sources(persona: Persona) -> list[GroundingSource]:
    ws = persona.work_signals
    return [
        GroundingSource(
            ref="work_signals.meeting_hours_per_week",
            title="Meeting load",
            snippet=f"{ws.meeting_hours_per_week} h/week",
            kind="work",
        ),
        GroundingSource(
            ref="work_signals.focus_hours_per_week",
            title="Focus time",
            snippet=f"{ws.focus_hours_per_week} h/week",
            kind="work",
        ),
        GroundingSource(
            ref="work_signals.preferred_learning_slot",
            title="Preferred learning slot",
            snippet=ws.preferred_learning_slot,
            kind="work",
        ),
    ]


def _work_facts(persona: Persona) -> str:
    ws = persona.work_signals
    return (
        f"meeting_hours_per_week={ws.meeting_hours_per_week}; "
        f"focus_hours_per_week={ws.focus_hours_per_week}; "
        f"preferred_learning_slot={ws.preferred_learning_slot}; "
        f"collaboration_load={ws.collaboration_load}; "
        f"on_call={persona.work_context.on_call.is_on_call}"
    )


def _work_offline(persona: Persona) -> str:
    ws = persona.work_signals
    heavy = ws.meeting_hours_per_week > 20
    pace = "a lighter, protected" if heavy else "a steady"
    return (
        f"(offline mode) This week you have about {ws.meeting_hours_per_week} hours of meetings "
        f"and {ws.focus_hours_per_week} hours of focus time, and you prefer studying in the "
        f"{ws.preferred_learning_slot.lower()}. I'd suggest {pace} study plan that lands in "
        f"your {ws.preferred_learning_slot.lower()} focus windows."
    )


def answer_work(
    text: str,
    *,
    persona_id: str,
    router: ModelRouter | None = None,
    repo: WorkIQRepository | None = None,
    settings: Settings | None = None,
) -> AgentReply:
    """Work-aware reply grounded in the learner's own (synthetic) schedule signals."""
    settings = settings or get_settings()
    repo = repo or get_repository()
    persona = repo.get_persona(persona_id)

    if persona is None:
        reply = (
            "I couldn't find work-context signals for your profile, so I can't tailor this to "
            "your schedule yet. I can still help with course content and study planning."
        )
        return AgentReply(
            telemetry=_answer_telemetry(
                summary="No work context available",
                reasoning=f"No persona '{persona_id}' in the Work IQ source.",
                route=Route.WORK_IQ,
                sources=[],
                model="offline" if settings.llm_offline else None,
                tier=None,
            ),
            tokens=_offline_stream(reply),
        )

    sources = _work_sources(persona)
    reasoning = f"Grounded on Work IQ signals for {persona.codename}: {_work_facts(persona)}."

    if settings.llm_offline:
        return AgentReply(
            telemetry=_answer_telemetry(
                summary="Answered from your Work IQ signals",
                reasoning=reasoning,
                route=Route.WORK_IQ,
                sources=sources,
                model="offline",
                tier=None,
            ),
            tokens=_offline_stream(_work_offline(persona)),
            sources=sources,
        )

    router = router or ModelRouter(settings)
    system = (
        "You are Athenaeum's study coach. Use ONLY the learner's work signals below to tailor "
        "timing and load. Quote only these numbers; do not invent figures. If meeting load is "
        "above 20 h/week, recommend a lighter plan.\n\nWORK SIGNALS: " + _work_facts(persona)
    )
    handle = router.stream(
        Capability.WORKHORSE,
        [{"role": "system", "content": system}, {"role": "user", "content": text}],
        max_tokens=600,
    )
    return AgentReply(
        telemetry=_answer_telemetry(
            summary="Answered from your Work IQ signals",
            reasoning=reasoning,
            route=Route.WORK_IQ,
            sources=sources,
            model=handle.model,
            tier=handle.tier,
        ),
        tokens=handle.tokens,
        sources=sources,
    )
