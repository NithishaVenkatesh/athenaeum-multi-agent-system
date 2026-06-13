"""Typed contracts for the agentic chat pipeline + the SSE event protocol.

Two families live here:

- **Agent I/O** — the strict Pydantic outputs each pipeline node produces
  (``InjectionVerdict``, ``RouteDecision``, ``CourseSuggestion``) and the shared
  ``GroundingSource`` / ``PhaseTelemetry`` the user is shown as the grounding for
  every step.
- **Pipeline events** — the discriminated union the orchestrator streams to the
  browser over SSE (``PhaseEvent``, ``TokenEvent``, ``SuggestionEvent``,
  ``BlockedEvent``, ``ErrorEvent``, ``DoneEvent``). The frontend switches on
  ``type``; nothing is ever streamed that isn't one of these.

Everything here is PII-safe by contract: telemetry carries summaries and
reasoning, never raw user text or secrets.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class Route(StrEnum):
    """Where the router sends a turn after the injection gate clears."""

    FOUNDRY_IQ = "foundry_iq"  # course-content questions → grounded, cited answer
    WORK_IQ = "work_iq"  # the learner's own schedule / workload / capacity
    GENERAL = "general"  # everything else → helpful answer + platform nudge


class PhaseName(StrEnum):
    GATE = "injection_gate"
    ROUTE = "router"
    ANSWER = "answer"


class PhaseStatus(StrEnum):
    RUNNING = "running"
    PASSED = "passed"
    BLOCKED = "blocked"
    ERROR = "error"


# ── Agent outputs ──────────────────────────────────────────────────────────────


class InjectionVerdict(BaseModel):
    """Output of the prompt-injection / jailbreak gate."""

    blocked: bool
    reason: str = Field(description="Why it was (not) blocked — shown in telemetry")
    confidence: float = Field(ge=0, le=1, default=0.5)


class RouteDecision(BaseModel):
    """Output of the router: where to send the turn and how off-topic it is."""

    route: Route
    reasoning: str = Field(description="Why this route — shown to the user as grounding")
    off_topic: float = Field(
        ge=0,
        le=1,
        default=0.0,
        description="0=on-platform learning, 1=far off (drives nudge strength)",
    )
    confidence: float = Field(ge=0, le=1, default=0.5)


class GroundingSource(BaseModel):
    """One citation backing an answer — a module, a work signal, etc."""

    ref: str = Field(description="Stable id: module id, work-signal field, …")
    title: str
    snippet: str = Field(description="The supporting span, trimmed")
    kind: Literal["course", "work", "catalog"] = "course"
    url: str | None = None


class CourseSuggestion(BaseModel):
    """The 'are you willing to pursue this course?' tool offered after a course answer."""

    catalog_id: str = Field(description="Athenaeum course id to link on accept")
    title: str
    cert: str = Field(description="Certification the course ladders toward")
    pitch: str = Field(description="One-line reason to pursue it")
    prep_points: list[str] = Field(
        default_factory=list, description="What the learner would prepare / commit to"
    )


class PhaseTelemetry(BaseModel):
    """PII-safe, per-phase reasoning + grounding the user sees beneath each step."""

    phase: PhaseName
    status: PhaseStatus
    summary: str = Field(description="Human-readable one-liner for this phase")
    reasoning: str = Field(default="", description="The agent's reasoning (grounding)")
    provider: str | None = None
    model: str | None = None
    tier: int | None = Field(default=None, description="Fallback tier that answered (1-4)")
    latency_ms: int | None = None
    route: Route | None = None
    sources: list[GroundingSource] = Field(default_factory=list)


# ── Pipeline events (the SSE wire protocol) ────────────────────────────────────


class PhaseEvent(BaseModel):
    type: Literal["phase"] = "phase"
    phase: PhaseTelemetry


class TokenEvent(BaseModel):
    type: Literal["token"] = "token"
    token: str


class SuggestionEvent(BaseModel):
    type: Literal["suggestion"] = "suggestion"
    suggestion: CourseSuggestion


class BlockedEvent(BaseModel):
    """Jailbreak / injection blocked — the frontend toasts this and stops."""

    type: Literal["blocked"] = "blocked"
    reason: str = Field(description="User-facing toast text (no raw input echoed)")


class ErrorEvent(BaseModel):
    """An explicit, user-facing failure — never a silent drop."""

    type: Literal["error"] = "error"
    message: str


class DoneEvent(BaseModel):
    type: Literal["done"] = "done"
    route: Route | None = None
    suggested: bool = False


PipelineEvent = (
    PhaseEvent | TokenEvent | SuggestionEvent | BlockedEvent | ErrorEvent | DoneEvent
)
