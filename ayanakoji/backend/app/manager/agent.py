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
from app.agent.guards import stream_grounded
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
        "capacity",
        "capacity & workload",
        re.compile(r"\b(capacity|meeting|focus|workload|bandwidth|busy|load|time)\b", re.I),
    ),
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
            r"\b(engag|active|started|completion|taken|assessment|activity|progress)\b", re.I
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
    r, c, e = insights.readiness, insights.capacity, insights.engagement
    parts = [
        f"team={insights.team_name}",
        f"members={insights.member_count}",
        f"readiness GO={r.go}, CONDITIONAL={r.conditional}, NOT_YET={r.not_yet}",
        f"avg_meeting_hours_per_week={c.avg_meeting_hours_per_week}",
        f"avg_focus_hours_per_week={c.avg_focus_hours_per_week}",
        f"members_over_heavy_meeting_load={c.high_meeting_load_count}",
    ]
    if insights.cert_targets:
        parts.append(
            "cert_targets="
            + "; ".join(
                f"{t.cert} {t.ready_count}/{t.member_count} GO" for t in insights.cert_targets
            )
        )
    engagement = (
        f"platform_engagement: active={e.members_active}/{e.members_total}, "
        f"attempted={e.assessments_attempted}, passed={e.assessments_passed}"
    )
    engagement += (
        f", pass_rate={e.pass_rate:.0%}" if e.pass_rate is not None else ", no graded attempts yet"
    )
    parts.append(engagement)
    tr = insights.track_record
    if tr.decided:
        rate = f"{tr.pass_rate:.0%}" if tr.pass_rate is not None else "n/a"
        parts.append(f"prior_exam_pass_rate={rate} ({tr.passed}/{tr.decided} on record)")
    if insights.sprint_goal:
        parts.append(f"sprint_goal={insights.sprint_goal}")
    return "; ".join(parts)


def _sources(insights: TeamInsights) -> list[GroundingSource]:
    r, c, e = insights.readiness, insights.capacity, insights.engagement
    sources = [
        GroundingSource(
            ref="team.readiness",
            title="Team readiness",
            snippet=f"GO {r.go}, CONDITIONAL {r.conditional}, NOT_YET {r.not_yet}",
            kind="work",
        ),
        GroundingSource(
            ref="team.capacity",
            title="Team capacity",
            snippet=(
                f"avg {c.avg_meeting_hours_per_week}h meetings / "
                f"{c.avg_focus_hours_per_week}h focus per week"
            ),
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
    if insights.track_record.decided:
        tr = insights.track_record
        rate = f"{tr.pass_rate:.0%}" if tr.pass_rate is not None else "n/a"
        sources.append(
            GroundingSource(
                ref="team.track_record",
                title="Prior exam track record",
                snippet=f"{tr.passed}/{tr.decided} passed previously ({rate})",
                kind="work",
            )
        )
    return sources


_AGGREGATE_RULE = (
    " These are TEAM-LEVEL AGGREGATES only. Never attribute a figure to a named individual, never "
    "reveal or estimate any single person's data, and never list members by name. If asked about a "
    "specific person or to break figures down per individual, briefly say you only report "
    "team-level aggregates and decline. Quote only the figures provided below; do not invent "
    "numbers."
)


def _system(insights: TeamInsights) -> str:
    return (
        "You are Athenaeum's manager insights assistant for a team lead. Help them understand "
        "their team's certification readiness, capacity, certification-target progress, and "
        "platform engagement. Be concise and specific. Do not use em dashes; use commas or periods."
        + _AGGREGATE_RULE
        + _NO_LEAK
        + _NO_OVERRIDE
        + "\n\nTEAM AGGREGATES: "
        + _facts(insights)
    )


def _offline_narration(insights: TeamInsights, topic: str) -> str:
    r, c, e = insights.readiness, insights.capacity, insights.engagement
    head = (
        f"(offline mode) For {insights.team_name} ({insights.member_count} members): "
        f"{r.go} ready (GO), {r.conditional} conditional, {r.not_yet} not yet ready."
    )
    if topic == "capacity":
        body = (
            f" Capacity: about {c.avg_meeting_hours_per_week}h of meetings and "
            f"{c.avg_focus_hours_per_week}h of focus time per week on average, with "
            f"{c.high_meeting_load_count} member(s) over the heavy-meeting line."
        )
    elif topic == "engagement":
        if e.has_activity:
            rate = f"{e.pass_rate:.0%}" if e.pass_rate is not None else "n/a"
            body = (
                f" Platform engagement: {e.members_active} of {e.members_total} members active, "
                f"{e.assessments_passed} of {e.assessments_attempted} graded attempts passed "
                f"(pass rate {rate})."
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
            f" Capacity averages {c.avg_meeting_hours_per_week}h meetings / "
            f"{c.avg_focus_hours_per_week}h focus per week."
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
            detail="WORKHORSE capability · max 700 tokens · streamed · aggregate-only",
            model=handle.model,
        )
    )
    steps.append(
        TraceStep(
            label="Citation guard",
            passed=True,
            detail="Streaming: any fabricated module id is dropped inline",
        )
    )
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
    # Empty allow-set: scrub any fabricated module id, and (since there are no
    # course sources) never append the course-specific grounding disclaimer.
    return tel, stream_grounded(handle.tokens, [])


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
