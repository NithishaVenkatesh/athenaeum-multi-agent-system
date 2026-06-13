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
    """Where the router sends a turn after the injection gate clears.

    The whole stage is about getting the learner to *choose a course*, so the
    onboarding intents (greeting, recommend) are first-class routes.
    """

    GREETING = "greeting"  # hi / hey / who are you → warm welcome + invite to pick a course
    RECOMMEND = "recommend"  # "suggest a course" / "what next" → profile-based options to choose
    FOUNDRY_IQ = "foundry_iq"  # a named course/topic → grounded answer + offer to start it
    STUDY_PLAN = "study_plan"  # "make me a study plan" → workload-aware schedule for the course
    WORK_IQ = "work_iq"  # the learner's own schedule / workload / capacity
    GENERAL = "general"  # off-topic → helpful answer + steer back to learning


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
    """One choosable course in a suggestion. Accepting it links it to the chat."""

    catalog_id: str = Field(description="Athenaeum course id to link on accept")
    title: str
    cert: str = Field(description="Certification the course ladders toward")
    level: str = Field(default="", description="foundational | intermediate | advanced")
    pitch: str = Field(description="One-line description of the course")
    reason: str = Field(default="", description="Why it fits THIS learner (profile-based)")
    prep_points: list[str] = Field(
        default_factory=list, description="What the learner would prepare / commit to"
    )


class TakenCourse(BaseModel):
    """A course the learner has already linked to a chat (their progress so far)."""

    catalog_id: str
    status: int = Field(description="Course.status encoding: 0 new, +N attempt N, -N passed on N")


# ── Study plan (calendar-grounded, module-level completion plan) ────────────────


class Pace(StrEnum):
    """How fast the learner wants to move (scales per-module time budgets)."""

    SLOWER = "slower"
    NORMAL = "normal"
    FASTER = "faster"


class StudySession(BaseModel):
    """One recurring weekly study slot taken from the learner's real calendar."""

    day: str = Field(description="Weekday, e.g. 'tue'")
    slot: str = Field(description="Morning | Afternoon | Evening")
    start: str = Field(description="HH:MM")
    end: str = Field(description="HH:MM")
    duration_minutes: int
    source: str = Field(default="", description="Calendar block this slot came from")


class ScheduledBlock(BaseModel):
    """A concrete session (in a specific week) that covers part of a module."""

    week: int = Field(ge=1)
    day: str
    start: str
    end: str
    minutes: int


class ModulePlan(BaseModel):
    """One module in the sequence, with its computed budget, slots, and deadline."""

    module_id: str
    title: str
    sequence: int = Field(ge=1, description="1-based order; modules are done sequentially")
    estimated_minutes: int = Field(description="Computed from content + pace (no exposed factor)")
    scheduled: list[ScheduledBlock] = Field(
        default_factory=list, description="The calendar sessions that cover this module"
    )
    complete_before: str = Field(description="ISO date the module should be finished by")
    objectives: list[str] = Field(default_factory=list)


class StudyPlan(BaseModel):
    """A calendar-grounded, module-level completion plan (deterministic; §13)."""

    catalog_id: str
    title: str
    cert: str
    pace: Pace
    weekly_study_hours: float = Field(description="Grounded in the learner's real free calendar")
    total_hours: float
    weeks: int
    start_date: str = Field(description="ISO date the plan starts")
    modules: list[ModulePlan]
    sessions: list[StudySession] = Field(description="The recurring weekly study slots")
    capacity_reason: str = Field(description="Which real calendar slots back the weekly load")


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
    """One or more courses the learner can choose from (the course-selection tool)."""

    type: Literal["suggestion"] = "suggestion"
    prompt: str = Field(description="Framing line, e.g. 'Want to start this?' or 'Pick one:'")
    options: list[CourseSuggestion] = Field(min_length=1)


class BlockedEvent(BaseModel):
    """Jailbreak / injection blocked — the frontend toasts this and stops."""

    type: Literal["blocked"] = "blocked"
    reason: str = Field(description="User-facing toast text (no raw input echoed)")


class ErrorEvent(BaseModel):
    """An explicit, user-facing failure — never a silent drop."""

    type: Literal["error"] = "error"
    message: str


class PlanEvent(BaseModel):
    """A generated study plan rendered as a structured schedule card."""

    type: Literal["plan"] = "plan"
    plan: StudyPlan


class PaceRequestEvent(BaseModel):
    """Ask the learner their pace before building a plan (a HITL gate)."""

    type: Literal["pace_request"] = "pace_request"
    catalog_id: str
    title: str
    prompt: str = Field(description="The question shown above the pace choices")
    options: list[Pace] = Field(default_factory=lambda: [Pace.SLOWER, Pace.NORMAL, Pace.FASTER])


class DoneEvent(BaseModel):
    type: Literal["done"] = "done"
    route: Route | None = None
    suggested: bool = False


PipelineEvent = (
    PhaseEvent
    | TokenEvent
    | SuggestionEvent
    | PlanEvent
    | PaceRequestEvent
    | BlockedEvent
    | ErrorEvent
    | DoneEvent
)
