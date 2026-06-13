"""Route node — decides where a (clean) turn goes: Foundry IQ, Work IQ, or general.

Tool scope: **none.** The router classifies intent only. It uses the course
grounding index as a *signal* (does the catalog have content for this?), but does
not answer. The deterministic classifier is the offline path and the fallback
whenever the model is unparseable or unreachable — routing must never hard-fail.
"""

from __future__ import annotations

import json
import re

from app.agent.contracts import PhaseName, PhaseStatus, PhaseTelemetry, Route, RouteDecision
from app.agent.grounding import CourseGrounding, get_grounding
from app.agent.llm import AllProvidersDown, Capability, ModelRouter
from app.agent.recommend import vertical_from_text
from app.config import Settings, get_settings

# "Help me choose / explore courses" signals → Recommend (profile- or topic-scoped).
_RECOMMEND_RE = re.compile(
    r"\b(suggest|recommend|which)\b.{0,40}\bcourse"
    r"|\bcourse\b.{0,20}\b(for me|suggestion|recommendation)"
    r"|\b(explore|show|find|browse|see|list|view)\b.{0,25}\bcourses?"
    r"|\bcourses?\s+(in|on|about|for|related)\b"
    r"|what\s+(should|do|can)\s+i\s+(learn|take|study|do|start)"
    r"|what\s+(courses|verticals|tracks|topics|paths?)\b"
    r"|what(?:'s| is)\s+next|where\s+(do|should)\s+i\s+start"
    r"|help\s+me\s+(choose|pick|decide|get\s+started|start)"
    r"|(based\s+on|fits?)\s+my\s+(role|profile|schedule|work)"
    r"|i('?d| would)\s+like\s+to\s+(explore|learn|study|take)"
    r"|recommend\s+(me\s+)?(a|some|something)",
    re.IGNORECASE,
)
# "Build / adjust my study plan / schedule" → Study Plan.
_PLAN_RE = re.compile(
    r"\b(study\s+plan|study\s+schedule|learning\s+plan|prep\s+plan|prepare\s+plan)"
    r"|\b(build|make|create|give|generate|draft|rebuild|redo|adjust|change|update)\b.{0,20}\b(plan|schedule)"
    r"|\b(plan|schedule)\b.{0,20}\b(my|the)\s+(study|learning|prep|week)"
    r"|how\s+should\s+i\s+(study|prepare|schedule)|when\s+do\s+i\s+study"
    # Schedule edits (start later, skip a day, move things) imply a re-plan.
    r"|\b(start|begin)\b.{0,20}\b(after|post|from|on|in|next|later)\b"
    r"|\b(move|push|shift|bump)\b.{0,20}\b(plan|schedule|study|start|later|back|forward)\b"
    r"|\b(skip|avoid|don'?t\s+use|free\s+up|can'?t\s+(do|study))\b.{0,20}"
    r"\b(mon|tue|wed|thu|fri|sat|sun|monday|tuesday|wednesday|thursday|friday|"
    r"saturday|sunday|this\s+week|that\s+hour|the\s+\d)",
    re.IGNORECASE,
)
# Warm onboarding / small talk → Greeting.
_GREETING_INTENT_RE = re.compile(
    r"^\s*(hi|hey|hello|yo|sup|hiya|good\s+(morning|afternoon|evening)|"
    r"thanks?|thank\s+you|who\s+are\s+you|what\s+can\s+you\s+do|"
    r"what\s+do\s+you\s+do|help\b|get\s+started)\b",
    re.IGNORECASE,
)
# "Ask about my own work" signals → Work IQ.
_WORK_RE = re.compile(
    r"\b(my\s+(schedule|calendar|week|day|meetings?|workload|capacity|hours|time)"
    r"|when\s+should\s+i\s+study|how\s+much\s+time|free\s+time|focus\s+time|on[\s-]?call"
    r"|too\s+busy|fit\s+(this|it|study)\s+(in|around)|this\s+week\b)",
    re.IGNORECASE,
)
# Clearly-not-our-domain topics → general with a stronger nudge.
_OFF_DOMAIN_RE = re.compile(
    r"\b(weather|football|cricket|soccer|world\s+cup|movie|film|recipe|cook|sport|"
    r"politics|election|celebrity|stock|crypto|joke|game\s+of\s+thrones|horoscope)\b",
    re.IGNORECASE,
)
_GREETING_RE = re.compile(
    r"^\s*(hi|hey|hello|yo|sup|good\s+(morning|afternoon|evening)|thanks?|thank\s+you|"
    r"how\s+are\s+you|what\s+can\s+you\s+do|who\s+are\s+you)\b",
    re.IGNORECASE,
)

_ROUTE_SYSTEM = (
    "You route a message in an enterprise learning platform that teaches Azure across five "
    "tracks: Cloud & Backend, Data Engineering, AI/ML, DevOps & Platform, Architecture & "
    "Security. ANY question about these — data, data science, AI, ML, cloud, devops, security, "
    "architecture, a certification, courses, verticals, or what to learn — is ON-TOPIC "
    "(off_topic near 0). Only truly unrelated things (sports, weather, cooking, personal "
    "trivia) are off_topic (near 1).\n"
    "Choose ONE route:\n"
    "- greeting: hi/hello/thanks/who are you/what can you do (onboarding small talk).\n"
    "- recommend: asks to suggest/recommend/explore courses, what to learn next, what tracks "
    "or verticals exist, or help choosing (in ANY of the five tracks).\n"
    "- study_plan: asks to build/make a study plan or schedule, or how/when to study.\n"
    "- foundry_iq: asks about the CONTENT of a specific course/cert/Azure topic.\n"
    "- work_iq: asks about THEIR OWN schedule, workload, meetings, capacity, or study timing.\n"
    "- general: only genuinely off-platform topics.\n"
    'Reply ONLY with JSON: {"route":"greeting|recommend|study_plan|foundry_iq|work_iq|general",'
    '"reasoning":"<short>","off_topic":0..1,"confidence":0..1}.'
)


def classify(text: str, *, grounding: CourseGrounding | None = None) -> RouteDecision:
    """Deterministic intent classifier (offline path + fallback for the online path).

    Priority: plan → recommend → greeting → work → course-content → off-topic → general.
    Plan outranks recommend so "build me a study plan" plans for the chosen course.
    """
    if _PLAN_RE.search(text):
        return RouteDecision(
            route=Route.STUDY_PLAN,
            reasoning="Asks for a study plan/schedule — build one for the chosen course.",
            off_topic=0.0,
            confidence=0.78,
        )
    if _RECOMMEND_RE.search(text):
        return RouteDecision(
            route=Route.RECOMMEND,
            reasoning="Asks for a course recommendation — match to their profile.",
            off_topic=0.0,
            confidence=0.75,
        )
    if _GREETING_INTENT_RE.search(text) and len(text.split()) <= 6:
        return RouteDecision(
            route=Route.GREETING,
            reasoning="Greeting / onboarding — welcome and invite a course choice.",
            off_topic=0.0,
            confidence=0.7,
        )
    if _WORK_RE.search(text):
        return RouteDecision(
            route=Route.WORK_IQ,
            reasoning="Mentions the learner's own schedule / workload.",
            off_topic=0.0,
            confidence=0.7,
        )
    grounding = grounding or get_grounding()
    if grounding.search(text, k=1):
        return RouteDecision(
            route=Route.FOUNDRY_IQ,
            reasoning="Names a course or topic in the catalog — answer + offer to start it.",
            off_topic=0.0,
            confidence=0.7,
        )
    if _OFF_DOMAIN_RE.search(text):
        return RouteDecision(
            route=Route.GENERAL,
            reasoning="Off-platform topic — answer briefly, then steer back to learning.",
            off_topic=0.85,
            confidence=0.6,
        )
    off = 0.1 if _GREETING_RE.search(text) else 0.5
    return RouteDecision(
        route=Route.GENERAL,
        reasoning="No course or work-context match — general assistance.",
        off_topic=off,
        confidence=0.5,
    )


def _telemetry(decision: RouteDecision, *, model: str | None, tier: int | None) -> PhaseTelemetry:
    return PhaseTelemetry(
        phase=PhaseName.ROUTE,
        status=PhaseStatus.PASSED,
        summary=f"Routed to {decision.route.value}",
        reasoning=decision.reasoning,
        route=decision.route,
        model=model,
        tier=tier,
    )


def route(
    text: str,
    *,
    router: ModelRouter | None = None,
    grounding: CourseGrounding | None = None,
    settings: Settings | None = None,
) -> tuple[RouteDecision, PhaseTelemetry]:
    """Decide the route for a clean turn, with telemetry for the trace."""
    settings = settings or get_settings()
    if settings.llm_offline:
        decision = classify(text, grounding=grounding)
        return decision, _telemetry(decision, model="heuristic", tier=None)

    router = router or ModelRouter(settings)
    try:
        result = router.complete(
            Capability.FAST,
            [{"role": "system", "content": _ROUTE_SYSTEM}, {"role": "user", "content": text}],
            json_mode=True,
            max_tokens=120,
        )
        decision = _parse_decision(result.text, text, grounding)
        return decision, _telemetry(decision, model=result.model, tier=result.tier)
    except AllProvidersDown:
        decision = classify(text, grounding=grounding)
        return decision, _telemetry(decision, model="heuristic (providers down)", tier=None)


def _parse_decision(raw: str, text: str, grounding: CourseGrounding | None) -> RouteDecision:
    """Parse the model's JSON; correct it when it over-rejects an on-platform topic."""
    try:
        data = json.loads(raw)
        decision = RouteDecision(
            route=Route(str(data["route"])),
            reasoning=str(data.get("reasoning", "")) or "Model routing.",
            off_topic=float(data.get("off_topic", 0.0)),
            confidence=float(data.get("confidence", 0.6)),
        )
    except (json.JSONDecodeError, KeyError, ValueError, TypeError):
        return classify(text, grounding=grounding)

    # Explicit plan / schedule-edit phrases ("build a plan", "start after June 30",
    # "skip Mondays") are high-signal and deterministic; the LLM often misroutes
    # them to work_iq or general, so the regex intent wins.
    if _PLAN_RE.search(text):
        return RouteDecision(
            route=Route.STUDY_PLAN,
            reasoning="Explicit study-plan or schedule-edit request.",
            off_topic=0.0,
            confidence=0.85,
        )

    # The LLM sometimes flags an on-platform learning topic (data science, AI, a
    # vertical) as off-topic and dumps it to GENERAL. Trust the grounded heuristic
    # over that: if the deterministic classifier finds a real on-platform route,
    # or the text names one of our tracks, use it instead of a bad nudge.
    if decision.route is Route.GENERAL and decision.off_topic >= 0.4:
        heuristic = classify(text, grounding=grounding)
        if heuristic.route is not Route.GENERAL:
            return heuristic
        if vertical_from_text(text) is not None:
            return RouteDecision(
                route=Route.RECOMMEND,
                reasoning="On-platform track named — corrected from a mistaken off-topic call.",
                off_topic=0.1,
                confidence=0.6,
            )
    return decision
