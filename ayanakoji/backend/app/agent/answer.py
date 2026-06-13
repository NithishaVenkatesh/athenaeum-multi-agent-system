"""The three answer agents the router dispatches to.

- ``answer_general``, no tools; a helpful reply plus a platform nudge whose
  strength scales with how off-topic the turn is.
- ``answer_foundry``, tool scope: course grounding only. Grounded, cited answer
  over approved catalog content, followed by the 'pursue this course?' tool.
- ``answer_work``, tool scope: the Work IQ persona read only. A work-aware reply
  grounded in the learner's own (synthetic) schedule signals.

Every agent returns an :class:`AgentReply`: telemetry (built once the winning
provider tier is known), a token iterator, the grounding sources, and an optional
course suggestion. Online answers stream via the model router; offline answers
stream a deterministic reply word-by-word (mirroring ``courses/service.py``).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date

from app.agent.contracts import (
    CourseSuggestion,
    GroundingSource,
    NewChatEvent,
    Pace,
    PaceRequestEvent,
    PhaseName,
    PhaseStatus,
    PhaseTelemetry,
    Route,
    RouteDecision,
    StudyPlan,
    SuggestionEvent,
    TakenCourse,
)
from app.agent.grounding import CourseGrounding, get_grounding
from app.agent.guards import plan_narration_is_grounded, strip_unknown_citations
from app.agent.llm import Capability, ModelRouter, StreamHandle
from app.agent.recommend import (
    recommend_courses,
    recommend_overview,
    vertical_from_text,
    verticals_from_text,
)
from app.agent.study_plan import build_study_plan
from app.catalog.loader import get_course as get_catalog_course
from app.config import Settings, get_settings
from app.workiq.models import Persona
from app.workiq.repository import WorkIQRepository, get_repository


@dataclass
class AgentReply:
    """A streamed answer plus the telemetry + grounding the user is shown."""

    telemetry: PhaseTelemetry
    tokens: Iterator[str]
    sources: list[GroundingSource] = field(default_factory=list)
    suggestion: SuggestionEvent | None = None
    plan: StudyPlan | None = None
    pace_request: PaceRequestEvent | None = None
    new_chat: NewChatEvent | None = None


def _offline_stream(text: str) -> Iterator[str]:
    """Stream a fixed reply word-by-word so the offline path looks live."""
    for word in text.split(" "):
        yield word + " "


def _collect(handle: StreamHandle) -> str:
    """Drain a model stream to a single string so a grounding guard can run on it.

    Grounded routes (foundry, study plan) buffer the full narration, validate it
    against the deterministic sources, then re-stream the cleaned text. Correctness
    beats live tokens where a fabricated citation or number would otherwise leak.
    """
    return "".join(handle.tokens).strip()


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
    "courses, one short sentence, not pushy."
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
        "Be helpful and concise. Do not use em dashes; use commas or periods. "
        + _nudge_for(decision.off_topic)
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
        f"addresses it directly, {lead.snippet} You can dig deeper in the linked modules "
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
    course = grounding.suggest(text, catalog_id=catalog_id)
    # Course-lock: never offer to start a DIFFERENT course in a chat that already
    # has one. We still answer the content question; we just don't pitch a switch.
    if catalog_id is not None and (course is None or course.catalog_id != catalog_id):
        course = None
    suggestion = (
        SuggestionEvent(prompt="Want to start this course?", options=[course])
        if course is not None
        else None
    )
    reasoning = (
        f"Grounded on {len(sources)} approved module(s): {', '.join(s.ref for s in sources)}."
        if sources
        else "No approved content matched, answering with an explicit 'not covered'."
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
        "not cover the question, say so plainly, never invent content. Do not use em "
        "dashes; use commas or periods.\n\nSOURCES:\n" + (_sources_block(sources) or "(none)")
    )
    handle = router.stream(
        Capability.WORKHORSE,
        [{"role": "system", "content": system}, {"role": "user", "content": text}],
        max_tokens=800,
    )
    # Buffer + scrub any fabricated [module-id] the model invents (guard at runtime).
    cleaned = strip_unknown_citations(_collect(handle), sources)
    return AgentReply(
        telemetry=_answer_telemetry(
            summary="Answered from approved course content",
            reasoning=reasoning,
            route=Route.FOUNDRY_IQ,
            sources=sources,
            model=handle.model,
            tier=handle.tier,
        ),
        tokens=_offline_stream(cleaned),
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
        "timing and load. Quote only these numbers; do not invent figures. Do not use em "
        "dashes; use commas or periods. If meeting load is above 20 h/week, recommend a "
        "lighter plan.\n\nWORK SIGNALS: " + _work_facts(persona)
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


# ── Greeting + Recommend (course selection; tool scope: persona + catalog) ──────


# "What tracks / verticals / courses exist" → show the platform's breadth.
_BREADTH_RE = re.compile(
    r"what\s+(verticals|tracks|topics|paths?|courses|areas)\b"
    r"|what\s+can\s+i\s+learn|all\s+(the\s+)?(courses|tracks|verticals)"
    r"|what\s+(do|does)\s+(you|the platform)\s+(offer|teach|have)",
    re.IGNORECASE,
)


def _recommend_for(
    persona: Persona | None, taken: list[TakenCourse], *, text: str = ""
) -> list[CourseSuggestion]:
    """Course options for a persona, honoring an explicitly requested topic.

    If the message names a vertical (e.g. "data science"), recommend from THAT
    track; if it asks about the platform's breadth, show one course per track;
    otherwise fall back to the learner's profile.
    """
    requested = verticals_from_text(text) if text else []
    if requested:
        # Span every track the learner named (e.g. "data and AI"), best first,
        # de-duped, instead of collapsing a multi-topic ask to one guess.
        merged: list[CourseSuggestion] = []
        seen: set[str] = set()
        for vert in requested[:2]:
            for option in recommend_courses(vertical=vert, target_cert="", taken=taken, k=2):
                if option.catalog_id not in seen:
                    seen.add(option.catalog_id)
                    merged.append(option)
        return merged[:3]
    if text and _BREADTH_RE.search(text):
        return recommend_overview()
    if persona is None:
        return []
    return recommend_courses(
        vertical=persona.vertical,
        target_cert=persona.learning.target_cert,
        taken=taken,
        role_title=persona.role_title,
        k=3,
    )


def _locked_title(catalog_id: str | None) -> str | None:
    """The display title of the course a chat is locked to, if any."""
    if not catalog_id:
        return None
    course = get_catalog_course(catalog_id)
    return course.title if course else catalog_id


def answer_greeting(
    text: str,
    *,
    persona_id: str,
    taken: list[TakenCourse],
    catalog_id: str | None = None,
    repo: WorkIQRepository | None = None,
    settings: Settings | None = None,
) -> AgentReply:
    """Warm welcome that invites the learner to pick a course (offers a head start).

    Course-lock: once a chat is linked to a course, the greeting welcomes the
    learner back to THAT course and does not re-offer other courses to pick.
    """
    settings = settings or get_settings()
    repo = repo or get_repository()
    persona = repo.get_persona(persona_id)
    who = f" {persona.codename}" if persona else ""

    locked_title = _locked_title(catalog_id)
    if locked_title is not None:
        greeting = (
            f"Hi{who}, welcome back. This chat is your workspace for {locked_title}. "
            "Ask me anything about it, build or adjust your study plan, or open the Modules tab "
            "to keep going. To explore a different course, start a new chat."
        )
        return AgentReply(
            telemetry=_answer_telemetry(
                summary="Welcomed the learner back to their course",
                reasoning=f"Greeting in a chat already linked to {locked_title} (course-locked).",
                route=Route.GREETING,
                sources=[],
                model="offline" if settings.llm_offline else None,
                tier=None,
            ),
            tokens=_offline_stream(greeting),
        )

    options = _recommend_for(persona, taken)
    greeting = (
        f"Hi{who}, welcome to Athenaeum. I help you choose and prepare for an Azure "
        "certification course. Tell me a topic or cert you're aiming for, or say "
        "“suggest a course” and I'll recommend one that fits your role."
    )
    suggestion = (
        SuggestionEvent(prompt="Or jump straight in, here's a fit for your path:", options=options)
        if options
        else None
    )
    return AgentReply(
        telemetry=_answer_telemetry(
            summary="Welcomed the learner and invited a course choice",
            reasoning=(
                f"Greeting; offered {len(options)} profile-based option(s)."
                if options
                else "Greeting; no profile options available."
            ),
            route=Route.GREETING,
            sources=[],
            model="offline" if settings.llm_offline else None,
            tier=None,
        ),
        tokens=_offline_stream(greeting),
        suggestion=suggestion,
    )


def _track_name(vertical: str) -> str:
    return vertical.replace("-", " ").title()


def _recommend_narration(
    options: list[CourseSuggestion], *, persona: Persona | None, requested_vertical: str | None
) -> str:
    titles = ", ".join(o.title for o in options)
    if requested_vertical is not None:
        return (
            f"Here are courses in the {_track_name(requested_vertical)} track you asked about: "
            f"{titles}. Pick one below to start preparing."
        )
    if persona is not None:
        return (
            f"Based on your work as a {persona.role_title} heading toward "
            f"{persona.learning.target_cert}, here's what I'd suggest next: {titles}. "
            "Pick one below to start preparing."
        )
    return f"Here's what I'd suggest: {titles}. Pick one below to start preparing."


def _course_locked_reply(locked_title: str, *, offline: bool) -> AgentReply:
    """One course per chat: decline to suggest another, point to a fresh chat."""
    message = (
        f"This chat is set up for {locked_title}, so I keep it to that one course, your plan, "
        "modules, and progress all stay in here. To explore or start a different course, open a "
        "new chat and I'll recommend from there."
    )
    return AgentReply(
        telemetry=_answer_telemetry(
            summary="Held the chat to its course (one course per chat)",
            reasoning=f"Chat is locked to {locked_title}; declined a cross-course suggestion.",
            route=Route.RECOMMEND,
            sources=[],
            model="offline" if offline else None,
            tier=None,
        ),
        tokens=_offline_stream(message),
        new_chat=NewChatEvent(
            prompt="Want a different course? Start a new chat to keep this one clean.",
            current_title=locked_title,
        ),
    )


def answer_recommend(
    text: str,
    *,
    persona_id: str,
    taken: list[TakenCourse],
    catalog_id: str | None = None,
    router: ModelRouter | None = None,
    repo: WorkIQRepository | None = None,
    settings: Settings | None = None,
) -> AgentReply:
    """Recommend course(s), honoring a requested topic over the profile default.

    Course-lock: if this chat already has a course, recommending another would
    fork its plan/progress, so we decline and steer to a new chat instead.
    """
    settings = settings or get_settings()
    locked_title = _locked_title(catalog_id)
    if locked_title is not None:
        return _course_locked_reply(locked_title, offline=settings.llm_offline)

    repo = repo or get_repository()
    persona = repo.get_persona(persona_id)
    options = _recommend_for(persona, taken, text=text)
    requested_vertical = vertical_from_text(text)

    if not options:
        reply = (
            "I couldn't find a profile to base a recommendation on. Tell me which Azure topic "
            "or certification you're interested in and I'll point you to the right course."
        )
        return AgentReply(
            telemetry=_answer_telemetry(
                summary="No profile to recommend from",
                reasoning=f"No persona '{persona_id}' or no eligible courses.",
                route=Route.RECOMMEND,
                sources=[],
                model="offline" if settings.llm_offline else None,
                tier=None,
            ),
            tokens=_offline_stream(reply),
        )

    suggestion = SuggestionEvent(
        prompt="Pick one to start preparing:" if len(options) > 1 else "Want to start this course?",
        options=options,
    )
    scope = (
        f"the {_track_name(requested_vertical)} track (as requested)"
        if requested_vertical is not None
        else f"{persona.role_title} -> {persona.learning.target_cert}"
        if persona is not None
        else "the catalog"
    )
    reasoning = (
        f"Recommended {len(options)} course(s) for {scope}: "
        + ", ".join(o.catalog_id for o in options)
        + "."
    )

    if settings.llm_offline:
        return AgentReply(
            telemetry=_answer_telemetry(
                summary="Recommended courses to choose from",
                reasoning=reasoning,
                route=Route.RECOMMEND,
                sources=[],
                model="offline",
                tier=None,
            ),
            tokens=_offline_stream(
                _recommend_narration(
                    options, persona=persona, requested_vertical=requested_vertical
                )
            ),
            suggestion=suggestion,
        )

    router = router or ModelRouter(settings)
    catalogue = "; ".join(f"{o.title} ({o.cert}, {o.level})" for o in options)
    learner_ctx = (
        f"The learner asked about the {_track_name(requested_vertical)} track."
        if requested_vertical is not None
        else f"Learner: {persona.role_title}, working toward {persona.learning.target_cert}."
        if persona is not None
        else "No learner profile available."
    )
    system = (
        "You are Athenaeum's enrollment advisor. Recommend ONLY from the candidate courses "
        "below. Be warm and brief (2-3 sentences) and end by inviting them to pick one. Do not "
        "invent courses. Do not use em dashes; use commas or periods.\n\n"
        f"{learner_ctx}\nCANDIDATES: {catalogue}"
    )
    handle = router.stream(
        Capability.WORKHORSE,
        [{"role": "system", "content": system}, {"role": "user", "content": text}],
        max_tokens=400,
    )
    return AgentReply(
        telemetry=_answer_telemetry(
            summary="Recommended courses to choose from",
            reasoning=reasoning,
            route=Route.RECOMMEND,
            sources=[],
            model=handle.model,
            tier=handle.tier,
        ),
        tokens=handle.tokens,
        suggestion=suggestion,
    )


# ── Study plan (tool scope: catalog course modules + Work IQ schedule) ──────────


_PACE_PROMPT = (
    "Before I build your plan, how do you want to pace it? Slower spreads the work out, "
    "normal is balanced, faster is intensive."
)


def _plan_offline_narration(plan: StudyPlan) -> str:
    first = plan.modules[0] if plan.modules else None
    deadline = f" Aim to finish “{first.title}” by {first.complete_before}." if first else ""
    return (
        f"(offline mode) Here's your {plan.weeks}-week, {plan.pace.value}-paced plan for "
        f"{plan.title}. {plan.capacity_reason} That's {plan.weekly_study_hours:g} h/week across "
        f"{len(plan.modules)} modules ({plan.total_hours:g} h total). You'll work through them in "
        f"order, each with a complete-by date.{deadline} See the schedule below."
    )


def _plan_facts(plan: StudyPlan) -> str:
    mods = "; ".join(
        f"#{m.sequence} {m.title} ({m.estimated_minutes} min, by {m.complete_before})"
        for m in plan.modules
    )
    sess = ", ".join(f"{s.day} {s.start}-{s.end} ({s.source})" for s in plan.sessions)
    return (
        f"course={plan.title} ({plan.cert}); pace={plan.pace.value}; "
        f"weekly_hours={plan.weekly_study_hours}; total_hours={plan.total_hours}; "
        f"weeks={plan.weeks}; capacity_reason={plan.capacity_reason}; "
        f"sessions=[{sess}]; modules=[{mods}]"
    )


def _need_course_reply(
    persona: Persona | None, taken: list[TakenCourse], *, offline: bool
) -> AgentReply:
    options = _recommend_for(persona, taken)
    reply = (
        "Let's pick a course first, then I'll build a study plan around your schedule. "
        "Here are options that fit your role."
        if options
        else "Choose a course first and I'll build a study plan that fits your schedule."
    )
    return AgentReply(
        telemetry=_answer_telemetry(
            summary="Need a chosen course before planning",
            reasoning="No course linked, offered options to choose first."
            if options
            else "No course linked and no profile to recommend from.",
            route=Route.STUDY_PLAN,
            sources=[],
            model="offline" if offline else None,
            tier=None,
        ),
        tokens=_offline_stream(reply),
        suggestion=SuggestionEvent(prompt="Pick a course to plan for:", options=options)
        if options
        else None,
    )


def answer_study_plan(
    text: str,
    *,
    persona_id: str,
    catalog_id: str | None,
    taken: list[TakenCourse],
    pace: Pace | None = None,
    start_date: date | None = None,
    exclude_days: frozenset[str] = frozenset(),
    skip_weeks: frozenset[int] = frozenset(),
    router: ModelRouter | None = None,
    repo: WorkIQRepository | None = None,
    settings: Settings | None = None,
) -> AgentReply:
    """Build the calendar-grounded plan for the chat's chosen course.

    State-gated: if no course is linked → offer course options; if a course is
    linked but no pace is set → ask the pace (HITL); only with both → build.
    """
    settings = settings or get_settings()
    repo = repo or get_repository()
    persona = repo.get_persona(persona_id)
    course = get_catalog_course(catalog_id) if catalog_id else None

    if course is None or persona is None:
        return _need_course_reply(persona, taken, offline=settings.llm_offline)

    # HITL gate: ask the pace before planning.
    if pace is None:
        return AgentReply(
            telemetry=_answer_telemetry(
                summary="Asked the learner's pace before planning",
                reasoning="Course chosen but no pace set, pace gates the plan.",
                route=Route.STUDY_PLAN,
                sources=[],
                model="offline" if settings.llm_offline else None,
                tier=None,
            ),
            tokens=_offline_stream(
                f"Before I build your plan for {course.title}, how fast do you want to go?"
            ),
            pace_request=PaceRequestEvent(
                catalog_id=course.id, title=course.title, prompt=_PACE_PROMPT
            ),
        )

    plan = build_study_plan(
        catalog_id=course.id,
        title=course.title,
        cert=course.primary_cert,
        persona=persona,
        pace=pace,
        start_date=start_date or date.today(),
        exclude_days=exclude_days,
        skip_weeks=skip_weeks,
        settings=settings,
    )
    # A schedule edit can remove every study slot; say so instead of an empty plan.
    if plan is not None and not plan.sessions:
        return AgentReply(
            telemetry=_answer_telemetry(
                summary="No study time left after the schedule edit",
                reasoning=f"exclude_days={sorted(exclude_days)} removed all slots.",
                route=Route.STUDY_PLAN,
                sources=[],
                model="offline" if settings.llm_offline else None,
                tier=None,
            ),
            tokens=_offline_stream(
                "Those constraints leave no study time in your week. Free up a day or loosen "
                "the limits and I'll rebuild the plan."
            ),
        )
    if plan is None:  # course has no modules, should not happen for catalog courses
        return AgentReply(
            telemetry=_answer_telemetry(
                summary="Could not build a plan",
                reasoning=f"No modules found for course '{course.id}'.",
                route=Route.STUDY_PLAN,
                sources=[],
                model="offline" if settings.llm_offline else None,
                tier=None,
            ),
            tokens=_offline_stream(
                "I couldn't find the module breakdown for that course to plan against."
            ),
        )

    reasoning = (
        f"Calendar-grounded plan for {course.title}: {plan.weeks} weeks @ "
        f"{plan.weekly_study_hours}h/wk ({plan.pace.value} pace); {plan.capacity_reason}"
    )

    if settings.llm_offline:
        return AgentReply(
            telemetry=_answer_telemetry(
                summary="Built a calendar-grounded study plan",
                reasoning=reasoning,
                route=Route.STUDY_PLAN,
                sources=[],
                model="offline",
                tier=None,
            ),
            tokens=_offline_stream(_plan_offline_narration(plan)),
            plan=plan,
        )

    router = router or ModelRouter(settings)
    system = (
        "You are Athenaeum's study coach presenting a study plan. The plan below was computed "
        "deterministically from the learner's real calendar, narrate it warmly in 3-4 "
        "sentences. Quote ONLY the numbers and dates given; never invent figures. Note that the "
        "study time comes from slots already in their week and modules are done in order with a "
        "complete-by date each. Do not use em dashes; use commas or periods. End by "
        "encouraging them to start module 1.\n\nPLAN: " + _plan_facts(plan)
    )
    handle = router.stream(
        Capability.WORKHORSE,
        [{"role": "system", "content": system}, {"role": "user", "content": text}],
        max_tokens=500,
    )
    # Buffer the narration and number-guard it: if the model invented any figure not
    # in the deterministic plan, fall back to the provably-grounded offline narration.
    narration = _collect(handle)
    if not narration or not plan_narration_is_grounded(narration, plan):
        narration = _plan_offline_narration(plan)
    return AgentReply(
        telemetry=_answer_telemetry(
            summary="Built a calendar-grounded study plan",
            reasoning=reasoning,
            route=Route.STUDY_PLAN,
            sources=[],
            model=handle.model,
            tier=handle.tier,
        ),
        tokens=_offline_stream(narration),
        plan=plan,
    )
