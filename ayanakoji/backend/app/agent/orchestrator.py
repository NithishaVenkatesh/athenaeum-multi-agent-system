"""The agentic pipeline spine, plain-Python orchestrator over the nodes.

Flow (each arrow is an accept; a reject exits early with an explicit event):

    entry ─▶ injection gate ─reject▶ BlockedEvent → done
                  │accept
                  ▼
              router ─▶ {foundry_iq | work_iq | general}
                  │
                  ▼
              answer agent ─▶ stream tokens ─▶ [course suggestion] ─▶ done

It is a synchronous generator of :class:`PipelineEvent` so it drops straight into
the existing SSE response. Every phase emits PII-safe telemetry the user sees as
grounding. There are no silent failures: a blocked turn emits ``BlockedEvent``,
an all-providers-down turn emits ``ErrorEvent`` with a clear message, and a
mid-stream break emits ``ErrorEvent`` before ``DoneEvent``.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import date

from app.agent.answer import (
    AgentReply,
    answer_foundry,
    answer_general,
    answer_greeting,
    answer_recommend,
    answer_study_plan,
    answer_work,
)
from app.agent.contracts import (
    BlockedEvent,
    DoneEvent,
    ErrorEvent,
    Pace,
    PhaseEvent,
    PipelineEvent,
    PlanEvent,
    Route,
    RouteDecision,
    TakenCourse,
    TokenEvent,
)
from app.agent.gate import screen
from app.agent.grounding import CourseGrounding, get_grounding
from app.agent.llm import AllProvidersDown, ModelRouter
from app.agent.router_agent import route
from app.agent.state import CourseState, transition_note
from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

_BLOCKED_MESSAGE = (
    "That message looks like an attempt to override how I work, so I can't act on it. "
    "I'm here to help with Azure certifications and your enterprise learning, ask me about a "
    "topic or course and we'll dig in."
)
_SERVICES_DOWN_MESSAGE = (
    "Sorry, the AI services are unavailable right now. Please try again in a moment."
)
_STREAM_BROKE_MESSAGE = "The reply was interrupted before it finished. Please resend your message."


def _dispatch(
    text: str,
    decision: RouteDecision,
    *,
    persona_id: str,
    catalog_id: str | None,
    taken: list[TakenCourse],
    pace: Pace | None,
    start_date: date | None,
    exclude_days: frozenset[str],
    router: ModelRouter | None,
    grounding: CourseGrounding,
    settings: Settings,
) -> AgentReply:
    """Branch to the answer agent for the chosen route (opens the stream)."""
    if decision.route is Route.GREETING:
        return answer_greeting(text, persona_id=persona_id, taken=taken, settings=settings)
    if decision.route is Route.RECOMMEND:
        return answer_recommend(
            text, persona_id=persona_id, taken=taken, router=router, settings=settings
        )
    if decision.route is Route.STUDY_PLAN:
        return answer_study_plan(
            text,
            persona_id=persona_id,
            catalog_id=catalog_id,
            taken=taken,
            pace=pace,
            start_date=start_date,
            exclude_days=exclude_days,
            router=router,
            settings=settings,
        )
    if decision.route is Route.FOUNDRY_IQ:
        return answer_foundry(
            text, catalog_id=catalog_id, router=router, grounding=grounding, settings=settings
        )
    if decision.route is Route.WORK_IQ:
        return answer_work(text, persona_id=persona_id, router=router, settings=settings)
    return answer_general(text, decision, router=router, settings=settings)


def run_pipeline(
    text: str,
    *,
    persona_id: str,
    catalog_id: str | None = None,
    taken: list[TakenCourse] | None = None,
    pace: Pace | None = None,
    start_date: date | None = None,
    exclude_days: frozenset[str] = frozenset(),
    course_state: CourseState | None = None,
    router: ModelRouter | None = None,
    grounding: CourseGrounding | None = None,
    settings: Settings | None = None,
) -> Iterator[PipelineEvent]:
    """Run one turn through the pipeline, yielding events for the SSE stream."""
    settings = settings or get_settings()
    grounding = grounding or get_grounding()
    taken = taken or []
    # One router instance per turn so the provider clients are reused across nodes.
    if router is None and not settings.llm_offline:
        router = ModelRouter(settings)

    # ── Node 1: injection gate (reject → exit) ─────────────────────────────────
    verdict, gate_tel = screen(text, router=router, settings=settings)
    yield PhaseEvent(phase=gate_tel)
    if verdict.blocked:
        yield BlockedEvent(reason=_BLOCKED_MESSAGE)
        yield DoneEvent()
        return

    # ── Node 2: router (state-conditioned; the graph branches on course state) ──
    decision, route_tel = route(text, router=router, grounding=grounding, settings=settings)
    if course_state is not None:
        note = transition_note(course_state, decision.route)
        route_tel = route_tel.model_copy(
            update={"state": course_state.value, "reasoning": f"{route_tel.reasoning} ({note})"}
        )
    yield PhaseEvent(phase=route_tel)

    # ── Node 3: answer agent (open stream; all-providers-down → explicit error) ─
    try:
        reply = _dispatch(
            text,
            decision,
            persona_id=persona_id,
            catalog_id=catalog_id,
            taken=taken,
            pace=pace,
            start_date=start_date,
            exclude_days=exclude_days,
            router=router,
            grounding=grounding,
            settings=settings,
        )
    except AllProvidersDown:
        logger.warning("all providers down while answering route=%s", decision.route)
        yield ErrorEvent(message=_SERVICES_DOWN_MESSAGE)
        yield DoneEvent(route=decision.route)
        return

    yield PhaseEvent(phase=reply.telemetry)

    # ── Stream the answer tokens (mid-stream break → explicit error) ───────────
    try:
        for token in reply.tokens:
            yield TokenEvent(token=token)
    except Exception as exc:  # noqa: BLE001, surface, never swallow, a stream break
        logger.warning("answer stream broke: %s", exc)
        yield ErrorEvent(message=_STREAM_BROKE_MESSAGE)
        yield DoneEvent(route=decision.route)
        return

    # ── Pace HITL gate (ask before planning) ───────────────────────────────────
    if reply.pace_request is not None:
        yield reply.pace_request

    # ── Structured study plan (rendered as a schedule card) ────────────────────
    if reply.plan is not None:
        yield PlanEvent(plan=reply.plan)

    # ── The course-selection tool (1+ choosable courses) ───────────────────────
    if reply.suggestion is not None:
        yield reply.suggestion

    yield DoneEvent(route=decision.route, suggested=reply.suggestion is not None)
