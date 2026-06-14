"""Route node — decides where a (clean) turn goes: Foundry IQ, Work IQ, or general.

Tool scope: **none.** The router classifies intent only. It uses the course
grounding index as a *signal* (does the catalog have content for this?), but does
not answer. The deterministic classifier is the offline path and the fallback
whenever the model is unparseable or unreachable — routing must never hard-fail.
"""

from __future__ import annotations

import json
import re
from datetime import date

from app.agent.contracts import (
    PhaseName,
    PhaseStatus,
    PhaseTelemetry,
    Route,
    RouteDecision,
    TraceStep,
)
from app.agent.grounding import CourseGrounding, get_grounding
from app.agent.llm import AllProvidersDown, Capability, ModelRouter
from app.agent.recommend import vertical_from_text
from app.agent.schedule_edit import parse_adjustment, parse_pace
from app.config import Settings, get_settings

# A bare affirmation ("yes", "sure", "go ahead") only means something in context:
# it inherits the action the assistant just proposed (e.g. a pending pace question).
_AFFIRM_RE = re.compile(
    r"^\s*(yes|yep|yeah|yup|sure|ok(ay)?|please\s+do|go\s+ahead|do\s+it|sounds?\s+good|"
    r"that\s+works|let'?s\s+do\s+it|absolutely|definitely|please)\b[\s.!]*$",
    re.IGNORECASE,
)

# Accepting a just-offered course suggestion is looser than a bare affirmation: it
# allows a trailing object ("yes, start that one", "let's begin", "sign me up"), so a
# natural multi-turn accept enrolls the course instead of dead-ending (R2).
_ACCEPT_RE = re.compile(
    r"^\s*(yes|yep|yeah|yup|sure|ok(ay)?|absolutely|definitely|please|sounds?\s+good|"
    r"that\s+works|go\s+ahead|do\s+it|let'?s\s+(do|go|start|begin)|start|begin|enroll|"
    r"sign\s+me\s+up|i'?ll\s+take|i\s+want\s+(to\s+start|that|this))\b",
    re.IGNORECASE,
)


# A negation anywhere flips an apparent acceptance into a refusal: "absolutely not",
# "please don't start", "yeah no", "ok but no" must NOT enroll (red-team: the worst bug
# was silently enrolling a learner who explicitly declined). "start over"/"start again"
# is a restart, not an accept, so it is excluded too.
_NEGATION_RE = re.compile(
    r"\b(not|never|nope|nah|cancel|decline|refuse|don'?t|do\s+not|won'?t|"
    r"no\s+thanks?|no\b|nvm|nevermind|never\s*mind|stop)\b|n'?t\b",
    re.IGNORECASE,
)
_RESTART_RE = re.compile(r"\bstart\s+(over|again|from\s+scratch|fresh)\b", re.IGNORECASE)


def is_acceptance(text: str) -> bool:
    """True iff the message accepts a just-offered course suggestion — affirmation with
    no negation and not a 'start over' restart (so a refusal never enrolls)."""
    if _NEGATION_RE.search(text) or _RESTART_RE.search(text):
        return False
    return bool(_ACCEPT_RE.search(text))


# Ordinal / positional references to a specific offered option ("the second one",
# "number 3", "the first") so a multi-option suggestion is resolvable by chat (R2+).
_ORDINAL_RE = re.compile(
    r"\b(first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|last|former|latter"
    r"|(?:number|option|the)\s+\d+|\d+(?:st|nd|rd|th)|that\s+(?:one|course))\b",
    re.IGNORECASE,
)


def is_refusal(text: str) -> bool:
    """True if the message declines (so a suggestion is rejected, never enrolled)."""
    return bool(_NEGATION_RE.search(text))


def is_suggestion_response(text: str) -> bool:
    """True if the message responds to an offered suggestion — accept or pick one.

    A negated message ("not the second one", "no") is never a selection.
    """
    if is_acceptance(text):
        return True
    return not is_refusal(text) and bool(_ORDINAL_RE.search(text))

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
# "Build / adjust my study plan / schedule" → Study Plan. Schedule edits (start
# later, skip a day, skip a week) and pace changes are detected separately by
# ``parse_adjustment`` / ``parse_pace`` so this only matches explicit plan asks
# (it must NOT fire on "where do I begin in Azure").
_PLAN_RE = re.compile(
    r"\b(study\s+plan|study\s+schedule|learning\s+plan|prep\s+plan|prepare\s+plan)"
    r"|\b(build|make|create|give|generate|draft|rebuild|redo|adjust|reschedule)\b.{0,20}\b(plan|schedule)"
    r"|\b(plan|schedule)\b.{0,20}\b(my|the)\s+(study|learning|prep|week)"
    r"|how\s+should\s+i\s+(study|prepare|schedule)|when\s+do\s+i\s+study",
    re.IGNORECASE,
)
# Warm onboarding / small talk → Greeting.
_GREETING_INTENT_RE = re.compile(
    r"^\s*(hi|hey|hello|yo|sup|hiya|good\s+(morning|afternoon|evening)|"
    r"thanks?|thank\s+you|who\s+are\s+you|what\s+can\s+you\s+do|"
    r"what\s+do\s+you\s+do|help\b|get\s+started)\b",
    re.IGNORECASE,
)
# Strong "about my own work" signals → Work IQ even when a course is named.
_WORK_STRONG_RE = re.compile(
    r"\bmy\s+(schedule|calendar|week|day|meetings?|workload|capacity|hours|availability)"
    r"|\b(on[\s-]?call|too\s+busy|overloaded|swamped|collaboration\s+load)\b"
    r"|\bfree\s+time\b|\bfocus\s+time\b|\bmeeting\s+load\b",
    re.IGNORECASE,
)
# Weaker timing signals → Work IQ only if the turn isn't really about course content.
_WORK_TIMING_RE = re.compile(
    r"when\s+should\s+i\s+study|how\s+much\s+time|fit\s+(this|it|study)\s+(in|around)"
    r"|this\s+week\b",
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
# "What's my next module / session / upcoming" → Upcoming route.
_UPCOMING_RE = re.compile(
    r"\b(what(?:'?s?|\s+is)\s+(?:my\s+)?(?:next|upcoming)|what\s+(?:am\s+i|should\s+i)\s+(?:studying|doing)\s+next"
    r"|next\s+(?:module|session|thing|topic)\s+(?:i\s+(?:should|need\s+to)\s+)?(?:study|do|cover|learn|work\s+on)?"
    r"|(what|which)\s+module\s+(?:is\s+)?(?:next|coming\s+up|am\s+i\s+on)"
    r"|where\s+(?:am\s+i|should\s+i\s+(?:be|start))\s+(?:in\s+my\s+plan|in\s+my\s+schedule)?"
    r"|upcoming\s+(?:module|session|study|class|deadline)s?)\b",
    re.IGNORECASE,
)

# The GENERAL→content correction (in _parse_decision) only second-guesses the model
# when it is *uncertain* it's off-platform. Below TRUST: the model is barely leaning
# off-topic, so a grounded on-platform read can override. At/above it: the model is
# confidently off-platform — trust its own signal and never let dressed-up Azure
# vocabulary (e.g. "frame this election answer in AI-102 terms") flip the route.
# The lower bound matches the existing over-rejection band: a genuine on-platform topic
# the model misfiled to GENERAL tends to land around off_topic 0.4–0.6, still corrected.
_OFFTOPIC_CORRECT_FLOOR = 0.4
_OFFTOPIC_TRUST_CEILING = 0.7


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
    "- upcoming: asks what the NEXT module or session to study is, where they are in their "
    "plan, what is coming up, or what they should do next in their current course.\n"
    "- study_plan: asks to build/make a study plan or schedule, or how/when to study.\n"
    "- foundry_iq: asks about the CONTENT of a specific course/cert/Azure topic.\n"
    "- work_iq: asks about THEIR OWN schedule, workload, meetings, capacity, or study timing.\n"
    "- general: only genuinely off-platform topics.\n"
    'Reply ONLY with JSON: {"route":'
    '"greeting|recommend|upcoming|study_plan|foundry_iq|work_iq|general",'
    '"reasoning":"<short>","off_topic":0..1,"confidence":0..1}.'
)


def is_plan_intent(text: str) -> bool:
    """True for any study-plan ask: a build request, a schedule edit, or a pace change.

    Schedule edits ("start after June 30", "skip Mondays", "remove week 2") and
    pace changes ("revert to a slower pace") are high-signal re-plan requests; the
    LLM tends to misroute them to work_iq, so we detect them deterministically.
    """
    return bool(
        _PLAN_RE.search(text)
        or parse_adjustment(text, today=date.today()) is not None
        or parse_pace(text) is not None
    )


def _study_plan_decision() -> RouteDecision:
    return RouteDecision(
        route=Route.STUDY_PLAN,
        reasoning="Study-plan request (build, schedule edit, or pace change) for the course.",
        off_topic=0.0,
        confidence=0.85,
    )


def classify(
    text: str,
    *,
    grounding: CourseGrounding | None = None,
    pending: str | None = None,
) -> RouteDecision:
    """Deterministic intent classifier (offline path + fallback for the online path).

    Priority: affirmation→pending → plan/edit/pace → recommend → greeting →
    strong-work → course-content → weak-work-timing → off-topic → general.
    Course content outranks weak timing words so a question that merely says "how
    much time" about a real topic still gets a grounded content answer.
    """
    # A bare "yes" only resolves against what the assistant just proposed.
    if pending == "pace" and _AFFIRM_RE.search(text):
        return RouteDecision(
            route=Route.STUDY_PLAN,
            reasoning="Affirmation after a pace question — proceed to build the plan.",
            off_topic=0.0,
            confidence=0.8,
        )
    # Responding to a course suggestion ("yes, start that one", "the second one")
    # begins setup; the courses layer links the chosen course, then this routes to
    # the first setup step.
    if pending == "suggestion" and is_suggestion_response(text):
        return RouteDecision(
            route=Route.STUDY_PLAN,
            reasoning="Responded to a course suggestion — start the course and begin setup.",
            off_topic=0.0,
            confidence=0.8,
        )
    if is_plan_intent(text):
        return _study_plan_decision()
    if _UPCOMING_RE.search(text):
        return RouteDecision(
            route=Route.UPCOMING,
            reasoning="Asks about the next module or upcoming session in their plan.",
            off_topic=0.0,
            confidence=0.8,
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
    if _WORK_STRONG_RE.search(text):
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
    if _WORK_TIMING_RE.search(text):
        return RouteDecision(
            route=Route.WORK_IQ,
            reasoning="Asks about study timing / capacity in their week.",
            off_topic=0.0,
            confidence=0.65,
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
    is_heuristic = model is None or "heuristic" in (model or "")
    label = "Heuristic classifier" if is_heuristic else "LLM router"
    step = TraceStep(
        label=label,
        passed=True,
        detail=(
            f"Route: {decision.route.value} · confidence {decision.confidence:.0%}"
            f" · off-topic score {decision.off_topic:.0%}"
        ),
        model=model,
    )
    return PhaseTelemetry(
        phase=PhaseName.ROUTE,
        status=PhaseStatus.PASSED,
        summary=f"Routed to {decision.route.value}",
        reasoning=decision.reasoning,
        route=decision.route,
        model=model,
        tier=tier,
        steps=[step],
        confidence=decision.confidence,
        off_topic=decision.off_topic,
    )


def _history_messages(history: list[dict[str, str]] | None) -> list[dict[str, str]]:
    """The last few turns as chat messages so the router can resolve follow-ups."""
    if not history:
        return []
    recent = history[-4:]
    return [
        {"role": "assistant" if m.get("role") == "assistant" else "user", "content": m["content"]}
        for m in recent
        if m.get("content")
    ]


def route(
    text: str,
    *,
    router: ModelRouter | None = None,
    grounding: CourseGrounding | None = None,
    history: list[dict[str, str]] | None = None,
    pending: str | None = None,
    settings: Settings | None = None,
) -> tuple[RouteDecision, PhaseTelemetry]:
    """Decide the route for a clean turn, with telemetry for the trace.

    ``history`` (recent turns) and ``pending`` (an action the last assistant turn
    proposed, e.g. "pace") let the router resolve context-dependent follow-ups
    like a bare "yes" instead of treating each message in isolation.
    """
    settings = settings or get_settings()
    if settings.llm_offline:
        decision = classify(text, grounding=grounding, pending=pending)
        return decision, _telemetry(decision, model="heuristic", tier=None)

    router = router or ModelRouter(settings)
    try:
        messages = [
            {"role": "system", "content": _ROUTE_SYSTEM},
            *_history_messages(history),
            {"role": "user", "content": text},
        ]
        result = router.complete(Capability.FAST, messages, json_mode=True, max_tokens=120)
        decision = _parse_decision(result.text, text, grounding, pending=pending)
        return decision, _telemetry(decision, model=result.model, tier=result.tier)
    except AllProvidersDown:
        decision = classify(text, grounding=grounding, pending=pending)
        return decision, _telemetry(decision, model="heuristic (providers down)", tier=None)


def _parse_decision(
    raw: str, text: str, grounding: CourseGrounding | None, *, pending: str | None = None
) -> RouteDecision:
    """Parse the model's JSON; correct it when it over-rejects an on-platform topic."""
    # Deterministic, high-signal intents win over the LLM regardless of its call.
    if pending == "pace" and _AFFIRM_RE.search(text):
        return classify(text, grounding=grounding, pending=pending)
    if pending == "suggestion" and is_suggestion_response(text):
        return classify(text, grounding=grounding, pending=pending)
    if is_plan_intent(text):
        return _study_plan_decision()

    try:
        data = json.loads(raw)
        decision = RouteDecision(
            route=Route(str(data["route"])),
            reasoning=str(data.get("reasoning", "")) or "Model routing.",
            off_topic=float(data.get("off_topic", 0.0)),
            confidence=float(data.get("confidence", 0.6)),
        )
    except (json.JSONDecodeError, KeyError, ValueError, TypeError):
        return classify(text, grounding=grounding, pending=pending)

    # The LLM sometimes flags an on-platform learning topic (data science, AI, a
    # vertical) as off-topic and dumps it to GENERAL. Trust the grounded heuristic
    # over that — but ONLY when the model is *uncertain* it's off-platform.
    #
    # Confidence gate (trust the model's own signal): we only second-guess a low /
    # ambiguous off-topic call ([FLOOR, CEILING)). At/above CEILING the model is
    # confidently off-platform, so we trust it and skip the classify()/vertical
    # override entirely — otherwise off-topic content stuffed with Azure vocabulary
    # ("answer this election question in AI-102 terms") keyword-matches the grounding
    # index or vertical matcher and silently flips a confident off_topic=1.0 to a
    # content route. A single dressed-up keyword must not override the model.
    #
    # No fabricated off_topic: a correction PRESERVES the model's calibrated value
    # (we only change the route, not the score) rather than hardcoding 0.1 — so a
    # correction can never silently lower the model's off-topic.
    if (
        decision.route is Route.GENERAL
        and _OFFTOPIC_CORRECT_FLOOR <= decision.off_topic < _OFFTOPIC_TRUST_CEILING
    ):
        heuristic = classify(text, grounding=grounding, pending=pending)
        if heuristic.route is not Route.GENERAL:
            return heuristic.model_copy(
                update={"off_topic": max(heuristic.off_topic, decision.off_topic)}
            )
        if vertical_from_text(text) is not None:
            return RouteDecision(
                route=Route.RECOMMEND,
                reasoning="On-platform track named — corrected from a mistaken off-topic call.",
                off_topic=decision.off_topic,
                confidence=0.6,
            )
    return decision
