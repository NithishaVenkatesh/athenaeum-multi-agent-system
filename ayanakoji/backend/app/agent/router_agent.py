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
from app.config import Settings, get_settings

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
    "You route a message in an enterprise learning assistant. Choose ONE route:\n"
    "- foundry_iq: asks about course/certification content or an Azure/learning topic.\n"
    "- work_iq: asks about THEIR OWN schedule, workload, meetings, capacity, or study timing.\n"
    "- general: greetings, small talk, or anything else.\n"
    "Also rate off_topic 0..1 (0 = enterprise-learning, 1 = far off such as sports/weather).\n"
    'Reply ONLY with JSON: {"route":"foundry_iq|work_iq|general","reasoning":"<short>",'
    '"off_topic":0..1,"confidence":0..1}.'
)


def classify(text: str, *, grounding: CourseGrounding | None = None) -> RouteDecision:
    """Deterministic intent classifier (offline path + fallback for the online path)."""
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
            reasoning="Matches approved course content in the catalog.",
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


def _parse_decision(
    raw: str, text: str, grounding: CourseGrounding | None
) -> RouteDecision:
    """Parse the model's JSON; fall back to the heuristic on any malformed reply."""
    try:
        data = json.loads(raw)
        return RouteDecision(
            route=Route(str(data["route"])),
            reasoning=str(data.get("reasoning", "")) or "Model routing.",
            off_topic=float(data.get("off_topic", 0.0)),
            confidence=float(data.get("confidence", 0.6)),
        )
    except (json.JSONDecodeError, KeyError, ValueError, TypeError):
        return classify(text, grounding=grounding)
