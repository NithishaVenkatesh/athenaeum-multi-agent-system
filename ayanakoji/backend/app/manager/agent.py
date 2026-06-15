"""The Manager Insights chat — a self-contained, fully-guarded answer lane.

This mirrors the learner pipeline's security and trace UI WITHOUT routing through
it (so no shared agent file is modified). It composes the same building blocks by
import:

- the injection gate ``screen`` (regex + heuristic + Prompt Guard + Prompt Shields
  + Azure RAI), identical to the learner pipeline;
- the prompt-leak / behavioral-override defenses ``_NO_LEAK`` / ``_NO_OVERRIDE``;
- the streaming citation guard ``stream_grounded`` (run with an empty allow-set, so
  any fabricated module id is scrubbed and no course-specific disclaimer leaks);
- the same SSE event + ``PhaseTelemetry`` contracts, so the frontend renders the
  same gate -> route -> answer trace.

On top of those it adds one manager-specific guard: the system prompt is
aggregate-only and refuses to surface any individual's figures. The lane can only
ever see the team aggregates passed in (a :class:`TeamInsights`), so per-learner
leakage is impossible by construction.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator

from app.agent.answer import _NO_LEAK, _NO_OVERRIDE
from app.agent.contracts import (
    BlockedEvent,
    DoneEvent,
    ErrorEvent,
    GroundingSource,
    PhaseEvent,
    PhaseName,
    PhaseStatus,
    PhaseTelemetry,
    PipelineEvent,
    TokenEvent,
    TraceStep,
)
from app.agent.gate import screen
from app.agent.guards import numbers_in, strip_unknown_citations, ungrounded_numbers
from app.agent.llm import AllProvidersDown, Capability, ModelRouter
from app.config import Settings, get_settings
from app.manager.schemas import TeamInsights

logger = logging.getLogger(__name__)

# User-facing copy kept identical to the learner orchestrator so the experience matches.
_BLOCKED_MESSAGE = (
    "That message looks like an attempt to override how I work, so I can't act on it. "
    "I'm here to help you understand your team's certification readiness and capacity, ask me "
    "about readiness, risks, or workload and we'll dig in."
)
_SERVICES_DOWN_MESSAGE = (
    "Sorry, the AI services are unavailable right now. Please try again in a moment."
)
_STREAM_BROKE_MESSAGE = "The reply was interrupted before it finished. Please resend your message."

# Em dashes are banned in user-facing copy (the standing product rule, mirrored from
# the learner orchestrator so a manager answer obeys the same style).
_EM_DASHES = str.maketrans({"—": ", ", "–": "-", "―": ", "})


def _no_em_dashes(tokens: Iterator[str]) -> Iterator[str]:
    for token in tokens:
        yield token.translate(_EM_DASHES)


def _offline_stream(text: str) -> Iterator[str]:
    """Stream a fixed reply word-by-word so the offline path looks live."""
    for word in text.split(" "):
        yield word + " "


# ── Sub-topic routing (deterministic; gives the trace a real ROUTE phase) ────────

_TOPIC_PATTERNS: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "readiness",
        "exam readiness",
        re.compile(r"\b(ready|readiness|exam|pass|risk|go\b|conditional|not[_\s-]?yet)\b", re.I),
    ),
    (
        "cert_progress",
        "certification progress",
        re.compile(r"\b(cert|certification|az-?\d|target|coverage|track)\b", re.I),
    ),
    (
        "engagement",
        "platform engagement",
        re.compile(
            r"\b(engag|active|started|complet|taken|assessment|activity|progress|course)\b", re.I
        ),
    ),
)


def _classify(text: str) -> tuple[str, PhaseTelemetry]:
    """Pick the manager sub-topic for this turn (keyword, deterministic)."""
    for key, label, pattern in _TOPIC_PATTERNS:
        if pattern.search(text):
            return key, _route_telemetry(label, matched=True)
    return "overview", _route_telemetry("team overview", matched=False)


def _route_telemetry(label: str, *, matched: bool) -> PhaseTelemetry:
    return PhaseTelemetry(
        phase=PhaseName.ROUTE,
        status=PhaseStatus.PASSED,
        summary=f"Routed to {label}",
        reasoning=f"Manager question classified as '{label}'.",
        steps=[
            TraceStep(
                label="Manager router",
                passed=True,
                detail=(
                    f"Keyword match -> {label}"
                    if matched
                    else "No specific sub-topic matched -> team overview"
                ),
            )
        ],
    )


# ── Grounding (the aggregate facts the answer may use) ───────────────────────────


def _facts(insights: TeamInsights) -> str:
    r, e = insights.readiness, insights.engagement
    # Labels are explicit so the model never conflates a count of PEOPLE (members_*)
    # with a count of test attempts / modules (assessments_*, modules_*).
    parts = [
        f"team_name={insights.team_name}",
        f"members_total={insights.member_count} (people on the team)",
        # readiness = how many PEOPLE are at each level, from real course completion.
        f"members_GO={r.go} (people fully ready)",
        f"members_CONDITIONAL={r.conditional} (people in progress)",
        f"members_NOT_YET={r.not_yet} (people not started)",
    ]
    if insights.by_seniority:
        # Aggregate cohorts (each band has >=2 people; sub-threshold bands are already
        # suppressed in the service), so these are team-level breakdowns, never individuals.
        parts.append(
            "readiness_by_seniority (people per band)="
            + "; ".join(
                f"{c.label}: GO={c.go}, CONDITIONAL={c.conditional}, NOT_YET={c.not_yet} "
                f"(of {c.total})"
                for c in insights.by_seniority
            )
        )
    if insights.cert_targets:
        parts.append(
            "cert_targets (people ready / people targeting that cert)="
            + "; ".join(
                f"{t.cert}: {t.ready_count} of {t.member_count} members GO"
                for t in insights.cert_targets
            )
        )
    # engagement = ACTIVITY counts. assessments_* and modules_* are test attempts /
    # modules, NOT people; only members_active_in_platform counts people here.
    parts.append(f"members_active_in_platform={e.members_active} (people with >=1 graded attempt)")
    parts.append(f"assessments_attempted={e.assessments_attempted} (test attempts, NOT people)")
    parts.append(f"assessments_passed={e.assessments_passed} (test attempts, NOT people)")
    parts.append(f"modules_passed={e.modules_with_a_pass} (distinct modules, NOT people)")
    parts.append(
        f"assessment_pass_rate={e.pass_rate:.0%}"
        if e.pass_rate is not None
        else "assessment_pass_rate=n/a (no graded attempts yet)"
    )
    return "; ".join(parts)


def _allowed_numbers(insights: TeamInsights) -> set[str]:
    """Every figure the answer may legitimately state.

    The model is grounded ONLY on ``_facts(insights)`` (the system prompt), so the
    legitimate numbers are exactly those, plus the percentages a reader could derive
    from them (readiness shares and per-cert ready ratios). Any number outside this set
    in the model's reply is treated as invented and triggers the grounded fallback,
    mirroring the learner study-plan number guard in ``app.agent.answer``.
    """
    allowed = numbers_in(_facts(insights))
    r = insights.readiness
    if r.total:
        for n in (r.go, r.conditional, r.not_yet):
            allowed |= numbers_in(str(round(n / r.total * 100)))
    for t in insights.cert_targets:
        if t.member_count:
            allowed |= numbers_in(str(round(t.ready_count / t.member_count * 100)))
    for c in insights.by_seniority:
        if c.total:
            allowed |= numbers_in(str(round(c.go / c.total * 100)))
    return allowed


# A number stated right before a people-noun ("8 members", "8 engineers", "8 of 10
# people") is a claim about how many PEOPLE. It must equal a real member-level count;
# otherwise the model has conflated a non-people figure (e.g. assessment attempts) with
# members. This mirrors the learner pipeline's role guard (``guards.role_violations``),
# which binds "<N> modules/weeks" to the plan's real values.
# ``(?<!-)`` so a digit that is part of a hyphenated code (a cert id like "AZ-305") is
# NOT read as a people-count: "the AZ-305 members" must not flag 305 as a bad member count.
_MEMBER_NOUN_RE = re.compile(
    r"(?<!-)\b(\d+)\s+(?:of\s+(?:the\s+)?\d+\s+)?(?:team\s+)?"
    r"(?:members?|engineers?|people|persons?|teammates?|colleagues?|individuals?)\b",
    re.I,
)


def _member_numbers(insights: TeamInsights) -> set[str]:
    """Every legitimate count of PEOPLE the answer may state."""
    r, e = insights.readiness, insights.engagement
    values = {
        insights.member_count,
        r.go,
        r.conditional,
        r.not_yet,
        r.total,
        e.members_active,
        e.members_total,
    }
    for t in insights.cert_targets:
        values.add(t.member_count)
        values.add(t.ready_count)
    for c in insights.by_seniority:
        values.update((c.go, c.conditional, c.not_yet, c.total))
    allowed: set[str] = set()
    for v in values:
        allowed |= numbers_in(str(v))
    return allowed


def _member_count_violations(text: str, insights: TeamInsights) -> set[str]:
    """Numbers attached to a people-noun that aren't a real member-level count."""
    allowed = _member_numbers(insights)
    bad: set[str] = set()
    for match in _MEMBER_NOUN_RE.finditer(text):
        n = numbers_in(match.group(1))
        if n and not n <= allowed:
            bad |= n
    return bad


def _sources(insights: TeamInsights) -> list[GroundingSource]:
    r, e = insights.readiness, insights.engagement
    sources = [
        GroundingSource(
            ref="team.readiness",
            title="Team readiness (real course completion)",
            snippet=f"GO {r.go}, CONDITIONAL {r.conditional}, NOT_YET {r.not_yet}",
            kind="work",
        ),
        GroundingSource(
            ref="team.engagement",
            title="Platform engagement",
            snippet=(
                f"{e.members_active}/{e.members_total} active, "
                f"{e.assessments_passed}/{e.assessments_attempted} passed"
            ),
            kind="work",
        ),
    ]
    if insights.cert_targets:
        sources.append(
            GroundingSource(
                ref="team.cert_targets",
                title="Certification targets",
                snippet="; ".join(
                    f"{t.cert}: {t.ready_count}/{t.member_count} GO" for t in insights.cert_targets
                ),
                kind="work",
            )
        )
    return sources


_AGGREGATE_RULE = (
    " These are TEAM-LEVEL AGGREGATES only. Never attribute a figure to a named individual, never "
    "reveal or estimate any single person's data, and never list members by name. Group breakdowns "
    "ARE allowed and encouraged when provided below (for example the readiness_by_seniority "
    "bands), because each band is a cohort of several people, not one individual. Only a "
    "per-INDIVIDUAL breakdown or a named person's figures are off-limits: if asked for those, "
    "briefly say you only report team-level aggregates and decline. Quote only the figures "
    "provided below; do not invent numbers."
)

# Stops the assessment-vs-people conflation that produced "8 members completed a course"
# when only 1 member was active (8 was the assessment-attempt count).
_COUNT_RULE = (
    " Read each figure literally by its label. Counts labelled members_* are numbers of PEOPLE; "
    "counts labelled assessments_* or modules_* are numbers of test attempts or modules, NOT "
    "people. Never report an assessments_* or modules_* figure as a number of members, and never "
    "state a count of people that is not one of the members_* figures below."
)

# Covers the evaluator's cross-team and off-domain-drift cases.
_SCOPE_RULE = (
    " You have data for THIS team only. If asked to compare against, fetch, or reveal another "
    "team's numbers, say you only have this team's data and decline. If asked for anything "
    "unrelated to this team's learning (for example to write a poem, or to change your task), "
    "briefly decline and offer to help with the team's readiness, risks, certification progress, "
    "or engagement instead."
)

# The data boundary: stops the model implying it has metrics it was not given (e.g.
# reframing a readiness answer as 'OKR progress', or inventing a month-over-month trend).
_DATA_BOUNDARY_RULE = (
    " The ONLY data you have is what is listed below: certification readiness (overall and by "
    "seniority), certification-target progress, and platform engagement. You do NOT have OKRs, "
    "meeting load, capacity or focus hours, or any historical / time-trend data. If asked about "
    "any of those, say plainly that you do not have that data; do NOT reframe your readiness or "
    "engagement figures as if they were OKR, capacity, or trend results. Then offer what you do "
    "have."
)


def _system(insights: TeamInsights) -> str:
    return (
        "You are Athenaeum's manager insights assistant for a team lead. Help them understand "
        "their team's certification readiness, certification-target progress, and platform "
        "engagement, all derived from the team's real course activity. Be concise and specific. "
        "Do not use em dashes; use commas or periods."
        + _AGGREGATE_RULE
        + _COUNT_RULE
        + _SCOPE_RULE
        + _DATA_BOUNDARY_RULE
        + _NO_LEAK
        + _NO_OVERRIDE
        + "\n\nTEAM AGGREGATES: "
        + _facts(insights)
    )


def _offline_narration(insights: TeamInsights, topic: str) -> str:
    r, e = insights.readiness, insights.engagement
    head = (
        f"(offline mode) For {insights.team_name} ({insights.member_count} members), from real "
        f"course activity: {r.go} ready (GO), {r.conditional} in progress, {r.not_yet} not "
        "yet started."
    )
    if topic == "engagement":
        if e.has_activity:
            rate = f"{e.pass_rate:.0%}" if e.pass_rate is not None else "n/a"
            body = (
                f" Platform engagement: {e.members_active} of {e.members_total} members active, "
                f"{e.assessments_passed} of {e.assessments_attempted} graded attempts passed "
                f"(pass rate {rate}), {e.modules_with_a_pass} modules passed."
            )
        else:
            body = (
                f" Platform engagement: none of the {e.members_total} members have taken an "
                "assessment in the platform yet."
            )
    elif topic == "cert_progress" and insights.cert_targets:
        body = (
            " Certification targets: "
            + "; ".join(
                f"{t.cert} {t.ready_count}/{t.member_count} ready" for t in insights.cert_targets
            )
            + "."
        )
    else:
        body = (
            f" Readiness is from real completion: a member is GO once they finish a course in "
            f"their certification path. {r.go} of {insights.member_count} are there."
        )
    tail = ""
    if insights.risks:
        tail = " Top risk: " + insights.risks[0].detail
    return head + body + tail


# How many prior turns of context to carry into a follow-up answer.
_HISTORY_TURNS = 6


def _history_messages(history: list[dict[str, str]] | None) -> list[dict[str, str]]:
    """The recent user/assistant turns, trimmed, for follow-up context."""
    if not history:
        return []
    return [
        {"role": h["role"], "content": h["content"]}
        for h in history[-_HISTORY_TURNS:]
        if h.get("role") in ("user", "assistant") and h.get("content")
    ]


def _answer(
    text: str,
    insights: TeamInsights,
    topic: str,
    sources: list[GroundingSource],
    *,
    history: list[dict[str, str]] | None,
    router: ModelRouter | None,
    settings: Settings,
) -> tuple[PhaseTelemetry, Iterator[str]]:
    """Build the answer phase: telemetry + a token iterator (offline or live)."""
    reasoning = f"Grounded on aggregate team signals: {_facts(insights)}."
    steps = [
        TraceStep(
            label="Aggregate grounding",
            passed=True,
            detail=f"Team-level only ({len(sources)} aggregate source(s)); no per-learner data.",
        )
    ]

    if settings.llm_offline:
        steps.append(
            TraceStep(label="LLM generation", passed=True, detail="offline mode", model="offline")
        )
        tel = PhaseTelemetry(
            phase=PhaseName.ANSWER,
            status=PhaseStatus.PASSED,
            summary="Answered from aggregate team signals",
            reasoning=reasoning,
            sources=sources,
            model="offline",
            steps=steps,
        )
        return tel, _offline_stream(_offline_narration(insights, topic))

    active_router = router or ModelRouter(settings)
    # ``stream`` raises AllProvidersDown synchronously (it pulls the first token to pick a
    # winning rung), so a total outage surfaces here and is handled by the caller.
    handle = active_router.stream(
        Capability.WORKHORSE,
        [
            {"role": "system", "content": _system(insights)},
            *_history_messages(history),
            {"role": "user", "content": text},
        ],
        max_tokens=700,
    )
    steps.append(
        TraceStep(
            label="LLM generation",
            passed=True,
            detail="WORKHORSE capability · max 700 tokens · aggregate-only",
            model=handle.model,
        )
    )

    # Buffer the won stream so the WHOLE answer can be number-guarded before any token
    # reaches the client. This mirrors the learner study-plan guard (app/agent/answer.py):
    # if the model states any figure the aggregates don't support, fall back to the
    # provably-grounded deterministic narration rather than show an invented number.
    try:
        raw: str | None = "".join(handle.tokens)
    except AllProvidersDown:
        raise
    except Exception as exc:  # noqa: BLE001 — mid-stream break: use the grounded fallback
        logger.warning("manager chat stream broke mid-generation: %s", exc)
        raw = None

    if raw is None:
        final_text = _offline_narration(insights, topic)
        cite_ok, num_ok = False, False
        cite_detail = "Stream interrupted before scrubbing"
        num_detail = "Stream interrupted; used the grounded team narration"
    else:
        # Empty allow-set: drop any fabricated module id (there are no course sources).
        clean = strip_unknown_citations(raw, [])
        cite_ok, cite_detail = True, "Any fabricated module id removed (buffered)"
        # Two checks: (1) no ungrounded figure at all; (2) no number attached to a
        # people-noun ("8 members") that isn't a real member-level count.
        bad = ungrounded_numbers(clean, _allowed_numbers(insights))
        bad_members = _member_count_violations(clean, insights)
        num_ok = not bad and not bad_members
        if num_ok:
            final_text = clean
            num_detail = "All figures verified against the team aggregates"
        else:
            final_text = _offline_narration(insights, topic)
            reasons = []
            if bad:
                reasons.append(f"ungrounded figure(s) {sorted(bad)}")
            if bad_members:
                reasons.append(f"miscounted people {sorted(bad_members)}")
            num_detail = "; ".join(reasons) + " — used the grounded team narration"
            # Log so a systematic model regression (every answer falling back) is
            # observable, not silent — the user still gets a grounded reply.
            logger.warning("manager chat number guard fell back: %s", num_detail)

    steps.append(TraceStep(label="Citation guard", passed=cite_ok, detail=cite_detail))
    steps.append(TraceStep(label="Number guard", passed=num_ok, detail=num_detail))
    tel = PhaseTelemetry(
        phase=PhaseName.ANSWER,
        status=PhaseStatus.PASSED,
        summary="Answered from aggregate team signals",
        reasoning=reasoning,
        sources=sources,
        model=handle.model,
        tier=handle.tier,
        steps=steps,
    )
    return tel, _offline_stream(final_text)


def run_manager_chat(
    text: str,
    *,
    insights: TeamInsights,
    history: list[dict[str, str]] | None = None,
    router: ModelRouter | None = None,
    settings: Settings | None = None,
) -> Iterator[PipelineEvent]:
    """Run one manager turn through gate -> route -> grounded answer, yielding SSE events.

    Same shape and guards as the learner pipeline (so the frontend trace renders
    identically), but self-contained and aggregate-only.
    """
    settings = settings or get_settings()
    if router is None and not settings.llm_offline:
        router = ModelRouter(settings)

    # ── Node 1: injection gate (identical to the learner pipeline) ─────────────
    verdict, gate_tel = screen(text, router=router, history=history, settings=settings)
    yield PhaseEvent(phase=gate_tel)
    if verdict.blocked:
        yield BlockedEvent(reason=_BLOCKED_MESSAGE)
        yield DoneEvent()
        return

    # ── Node 2: sub-topic router (gives the trace a real ROUTE phase) ──────────
    topic, route_tel = _classify(text)
    yield PhaseEvent(phase=route_tel)

    # ── Node 3: grounded, aggregate-only answer ────────────────────────────────
    sources = _sources(insights)
    try:
        answer_tel, tokens = _answer(
            text, insights, topic, sources, history=history, router=router, settings=settings
        )
    except AllProvidersDown:
        logger.warning("all providers down while answering manager chat")
        yield ErrorEvent(message=_SERVICES_DOWN_MESSAGE)
        yield DoneEvent()
        return

    yield PhaseEvent(phase=answer_tel)
    try:
        for token in _no_em_dashes(tokens):
            yield TokenEvent(token=token)
    except Exception as exc:  # noqa: BLE001 — surface a stream break, never swallow
        logger.warning("manager chat stream broke: %s", exc)
        yield ErrorEvent(message=_STREAM_BROKE_MESSAGE)
        yield DoneEvent()
        return

    yield DoneEvent()
