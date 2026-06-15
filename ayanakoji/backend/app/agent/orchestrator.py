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
    _cross_user_decline_reply,
    answer_feedback,
    answer_feedback_none,
    answer_feedback_redirect,
    answer_foundry,
    answer_general,
    answer_greeting,
    answer_progress,
    answer_recommend,
    answer_study_plan,
    answer_upcoming,
    answer_work,
    cross_chat_redirect,
)
from app.agent.assessor import answer_assessor
from app.agent.contracts import (
    BlockedEvent,
    DoneEvent,
    ErrorEvent,
    FeedbackResolution,
    Pace,
    PhaseEvent,
    PipelineEvent,
    PlanEvent,
    ProgressSnapshot,
    Route,
    RouteDecision,
    TakenCourse,
    TokenEvent,
)
from app.agent.gate import screen
from app.agent.grounding import CourseGrounding, get_grounding
from app.agent.llm import AllProvidersDown, ModelRouter
from app.agent.output_guard import safe_output_stream
from app.agent.router_agent import mentions_other_person, route
from app.agent.state import CourseState, transition_note
from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

# Em dashes are banned in user-facing copy (a standing product rule). The model
# prompts ask for none, but we enforce it on the stream so one can never slip out.
_DASHES = frozenset("—–―")  # em dash, en dash, horizontal bar


def _dash_sub(dash: str, left: str, right: str) -> str:
    """What an em/en dash becomes, given the char on each side.

    A numeric range (digit-dash-digit) keeps a hyphen so "throughput 400—1000 RU/s" or
    ports "8000—8010" are NOT split into two discrete values; an en dash always becomes a
    hyphen (its only legitimate use here is a range); everything else is prose punctuation
    and becomes ", " per the no-em-dash rule."""
    if left.isdigit() and right.isdigit():
        return "-"
    if dash == "–":  # en dash
        return "-"
    return ", "


def _no_em_dashes(tokens: Iterator[str]) -> Iterator[str]:
    """Strip em/en dashes from a token stream, enforcing the no-em-dash rule.

    A dash and its right-hand neighbour can land in different stream tokens, so a single
    dash is carried across the token boundary until the next char arrives and the
    numeric-range guard can see both sides."""
    carry_dash = ""  # a deferred dash awaiting its right-hand context
    prev_char = ""  # left context for a deferred dash (the last non-dash char emitted)
    for token in tokens:
        out: list[str] = []
        for ch in token:
            if carry_dash:
                out.append(_dash_sub(carry_dash, prev_char, ch))
                carry_dash = ""
            if ch in _DASHES:
                carry_dash = ch  # defer: we don't yet know the char to its right
                continue
            out.append(ch)
            prev_char = ch
        if out:
            yield "".join(out)
    if carry_dash:  # stream ended on a dash — no right neighbour, treat as prose
        yield _dash_sub(carry_dash, prev_char, "")


_BLOCKED_MESSAGE = (
    "That message looks like an attempt to override how I work, so I can't act on it. "
    "I'm here to help with Azure certifications and your enterprise learning, ask me about a "
    "topic or course and we'll dig in."
)
_SERVICES_DOWN_MESSAGE = (
    "Sorry, the AI services are unavailable right now. Please try again in a moment."
)
_STREAM_BROKE_MESSAGE = "The reply was interrupted before it finished. Please resend your message."

# Routes that act on a specific course, where naming an already-registered course
# should steer the learner to its existing chat instead of duplicating it.
_COURSE_INTENT_ROUTES = frozenset({Route.RECOMMEND, Route.FOUNDRY_IQ, Route.STUDY_PLAN})

# Routes that act on the learner's OWN data/work — they must never do so for someone else.
# work_iq / progress already decline inside their nodes; gating here closes the bypass
# routes ("build a study plan for my colleague", "quiz my teammate") in one place.
_OWN_DATA_ROUTES = frozenset(
    {
        Route.WORK_IQ,
        Route.PROGRESS,
        Route.UPCOMING,
        Route.STUDY_PLAN,
        Route.PRACTISE_MODULE,
        Route.TAKE_EVALUATION,
        Route.GO_TO_MODULE,
    }
)


def _dispatch(
    text: str,
    decision: RouteDecision,
    *,
    persona_id: str,
    catalog_id: str | None,
    taken: list[TakenCourse],
    registered: dict[str, tuple[str, str]],
    reserved: frozenset[tuple[str, int, int]],
    pace: Pace | None,
    skill_source: str | None,
    skill_scores: dict[str, float] | None,
    start_date: date | None,
    exclude_days: frozenset[str],
    skip_weeks: frozenset[int],
    exam_date: date | None,
    plan_constraints: dict[str, object] | None,
    modules: list[dict[str, object]],
    progress: ProgressSnapshot | None,
    feedback: FeedbackResolution | None,
    router: ModelRouter | None,
    grounding: CourseGrounding,
    settings: Settings,
) -> AgentReply:
    """Branch to the answer agent for the chosen route (opens the stream)."""
    if decision.route is Route.GREETING:
        return answer_greeting(
            text, persona_id=persona_id, taken=taken, catalog_id=catalog_id, settings=settings
        )
    if decision.route is Route.RECOMMEND:
        return answer_recommend(
            text,
            persona_id=persona_id,
            taken=taken,
            catalog_id=catalog_id,
            registered=registered,
            router=router,
            settings=settings,
        )
    if decision.route is Route.UPCOMING:
        return answer_upcoming(modules, settings=settings)
    if decision.route is Route.PROGRESS:
        return answer_progress(modules, snapshot=progress, text=text, settings=settings)
    if decision.route is Route.STUDY_PLAN:
        return answer_study_plan(
            text,
            persona_id=persona_id,
            catalog_id=catalog_id,
            taken=taken,
            pace=pace,
            skill_source=skill_source,
            skill_scores=skill_scores,
            start_date=start_date,
            exclude_days=exclude_days,
            skip_weeks=skip_weeks,
            reserved=reserved,
            exam_date=exam_date,
            plan_constraints=plan_constraints,
            router=router,
            settings=settings,
        )
    if decision.route is Route.FOUNDRY_IQ:
        return answer_foundry(
            text, catalog_id=catalog_id, router=router, grounding=grounding, settings=settings
        )
    if decision.route is Route.WORK_IQ:
        return answer_work(text, persona_id=persona_id, router=router, settings=settings)
    if decision.route in (Route.PRACTISE_MODULE, Route.TAKE_EVALUATION, Route.GO_TO_MODULE):
        return answer_assessor(
            text, decision.route, modules=modules, router=router, settings=settings
        )
    if decision.route is Route.FEEDBACK:
        # The courses layer resolved the target (DB-bound); we just render it. A
        # missing/none resolution means there is nothing to review.
        if feedback is None or feedback.kind == "none":
            return answer_feedback_none(
                this_course_title=feedback.this_course_title if feedback else ""
            )
        if feedback.kind == "redirect":
            return answer_feedback_redirect(
                this_course_title=feedback.this_course_title,
                other_course_title=feedback.other_course_title or "another course",
            )
        return answer_feedback(
            module_id=feedback.module_id or "",
            module_title=feedback.module_title or "",
            course_title=feedback.this_course_title,
            material=feedback.material,
            kind=feedback.type or "choices",
            score=feedback.score,
            passed=feedback.passed,
            performance=feedback.performance,
            router=router,
            settings=settings,
        )
    return answer_general(text, decision, router=router, settings=settings)


def run_pipeline(
    text: str,
    *,
    persona_id: str,
    catalog_id: str | None = None,
    taken: list[TakenCourse] | None = None,
    registered: dict[str, tuple[str, str]] | None = None,
    reserved: frozenset[tuple[str, int, int]] = frozenset(),
    pace: Pace | None = None,
    skill_source: str | None = None,
    skill_scores: dict[str, float] | None = None,
    start_date: date | None = None,
    exclude_days: frozenset[str] = frozenset(),
    skip_weeks: frozenset[int] = frozenset(),
    exam_date: date | None = None,
    plan_constraints: dict[str, object] | None = None,
    modules: list[dict[str, object]] | None = None,
    progress: ProgressSnapshot | None = None,
    feedback: FeedbackResolution | None = None,
    feedback_active: bool = False,
    course_state: CourseState | None = None,
    history: list[dict[str, str]] | None = None,
    pending: str | None = None,
    router: ModelRouter | None = None,
    grounding: CourseGrounding | None = None,
    settings: Settings | None = None,
) -> Iterator[PipelineEvent]:
    """Run one turn through the pipeline, yielding events for the SSE stream.

    ``history`` (recent turns) and ``pending`` (the action the last assistant turn
    proposed) let the router resolve follow-ups like a bare "yes" in context.
    """
    settings = settings or get_settings()
    grounding = grounding or get_grounding()
    taken = taken or []
    registered = registered or {}
    # One router instance per turn so the provider clients are reused across nodes.
    if router is None and not settings.llm_offline:
        router = ModelRouter(settings)

    # ── Node 1: injection gate (reject → exit) ─────────────────────────────────
    verdict, gate_tel = screen(text, router=router, history=history, settings=settings)
    yield PhaseEvent(phase=gate_tel)
    if verdict.blocked:
        yield BlockedEvent(reason=_BLOCKED_MESSAGE)
        yield DoneEvent()
        return

    # ── Node 2: router (state-conditioned; the graph branches on course state) ──
    decision, route_tel = route(
        text,
        router=router,
        grounding=grounding,
        history=history,
        pending=pending,
        feedback_active=feedback_active,
        settings=settings,
    )
    if course_state is not None:
        note = transition_note(course_state, decision.route)
        route_tel = route_tel.model_copy(
            update={"state": course_state.value, "reasoning": f"{route_tel.reasoning} ({note})"}
        )
    yield PhaseEvent(phase=route_tel)

    # ── Node 3: answer agent (open stream; all-providers-down → explicit error) ─
    # Route-independent guard: an explicitly-named course already registered in
    # another chat steers the learner there instead of duplicating it (no model).
    reply: AgentReply | None = None
    if decision.route in _COURSE_INTENT_ROUTES:
        reply = cross_chat_redirect(
            text, registered=registered, catalog_id=catalog_id, settings=settings
        )
    # Route-independent cross-person guard: an own-data route asked about someone else
    # (the LLM router's third_party signal, or the deterministic marker floor) is declined
    # before dispatch, so "build a study plan for my colleague" / "quiz my teammate" can't
    # act on another person's behalf via a route that doesn't self-check.
    if (
        reply is None
        and decision.route in _OWN_DATA_ROUTES
        and (decision.third_party or mentions_other_person(text))
    ):
        reply = _cross_user_decline_reply(decision.route, settings=settings)
    if reply is None:
        try:
            reply = _dispatch(
                text,
                decision,
                persona_id=persona_id,
                catalog_id=catalog_id,
                taken=taken,
                registered=registered,
                reserved=reserved,
                pace=pace,
                skill_source=skill_source,
                skill_scores=skill_scores,
                start_date=start_date,
                exclude_days=exclude_days,
                skip_weeks=skip_weeks,
                exam_date=exam_date,
                plan_constraints=plan_constraints,
                modules=modules or [],
                progress=progress,
                feedback=feedback,
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

    # ── Stream the answer tokens (em-dash-free, output-safety-screened; mid-stream break →
    # explicit error). safe_output_stream is the SECOND perimeter: it screens the model's own
    # output for a governance-prompt leak or attacker-persona adoption and halts the answer if
    # one appears, so a single input-gate bypass cannot stream an unfiltered breach. ──
    try:
        for token in safe_output_stream(_no_em_dashes(reply.tokens)):
            yield TokenEvent(token=token)
    except Exception as exc:  # noqa: BLE001, surface, never swallow, a stream break
        logger.warning("answer stream broke: %s", exc)
        yield ErrorEvent(message=_STREAM_BROKE_MESSAGE)
        yield DoneEvent(route=decision.route)
        return

    # ── Groundedness check (post-answer): the claim-support verdict over the streamed
    # answer is only known once it is fully generated, so it is surfaced here as a
    # trailing trace phase (any disclaimer already rode the answer stream itself). ──
    if reply.grounding_check is not None and reply.grounding_check.phase is not None:
        yield PhaseEvent(phase=reply.grounding_check.phase)

    # ── Skill-gap HITL gate (ask before pacing) ───────────────────────────────
    if reply.skill_gate is not None:
        yield reply.skill_gate

    # ── Pace HITL gate (ask before planning) ───────────────────────────────────
    if reply.pace_request is not None:
        yield reply.pace_request

    # ── Structured study plan (rendered as a schedule card) ────────────────────
    if reply.plan is not None:
        yield PlanEvent(plan=reply.plan, constraints=reply.plan_constraints)

    # ── The course-selection tool (1+ choosable courses) ───────────────────────
    if reply.suggestion is not None:
        yield reply.suggestion

    # ── Course-lock: steer a "switch course" ask to a fresh chat ───────────────
    if reply.new_chat is not None:
        yield reply.new_chat

    # ── Assessor practice card + CTA buttons ────────────────────────────────────
    if reply.practice is not None:
        yield reply.practice
    if reply.actions is not None:
        yield reply.actions

    yield DoneEvent(route=decision.route, suggested=reply.suggestion is not None)
