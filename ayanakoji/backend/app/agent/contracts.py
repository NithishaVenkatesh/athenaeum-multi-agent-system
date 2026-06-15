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
    UPCOMING = "upcoming"  # "what's my next module / session" → next scheduled module + deadline
    PROGRESS = "progress"  # "how much have I completed / how many left" → own completion status
    PRACTISE_MODULE = "practise_module"  # "quiz me on this module" → assessor practice round
    TAKE_EVALUATION = "take_evaluation"  # "I'm ready for the test" → CTA to the module evaluation
    GO_TO_MODULE = "go_to_module"  # "open / study the module" → CTA to the module page
    FEEDBACK = "feedback"  # "feedback on my failed test" → grounded review of a test in THIS course
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


class TraceStep(BaseModel):
    """One sub-step within a pipeline phase, shown in the grounding trace.

    Used by the injection gate (regex → Azure → Prompt Guard) and the router
    (heuristic vs LLM call) so the full decision chain is visible, not just the
    final verdict.
    """

    label: str = Field(
        description="Layer name: Regex pre-filter | Azure LLM classifier | Groq Prompt Guard 2 | …"
    )
    passed: bool | None = Field(
        default=None,
        description="True=passed, False=blocked, None=informational (unavailable/skipped)",
    )
    detail: str = Field(description="Human-readable outcome with scores, thresholds, or patterns")
    model: str | None = Field(default=None, description="Model / service identifier if applicable")


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
    third_party: bool = Field(
        default=False,
        description="True if the turn asks about a person OTHER than the learner "
        "(a named person, colleague, or manager); drives the cross-user decline",
    )


class FeedbackResolution(BaseModel):
    """Which test an in-chat feedback ask resolved to, computed in the courses layer.

    The pipeline is pure of the DB, so the courses layer resolves the target (the
    learner's most recent miss in this course, a named module's miss, a cross-course
    redirect, or nothing failed) and hands the answer inputs in as this value. The
    FEEDBACK dispatch then grounds on ``material`` + ``performance`` without re-reading.
    """

    kind: Literal["answer", "redirect", "none"]
    # answer: the resolved test + its grounding inputs.
    module_id: str | None = None
    module_title: str | None = None
    type: str | None = Field(default=None, description="'choices' | 'llm'")
    material: str = Field(default="", description="Trimmed module material to ground on")
    performance: str = Field(default="", description="What the learner actually got wrong")
    score: float | None = None
    passed: bool | None = None
    # redirect: the other course whose chat the learner should use instead.
    other_course_title: str | None = None
    # The course this chat is locked to (for both answer + redirect copy).
    this_course_title: str = ""


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
    passed: bool = Field(
        default=False,
        description="True once every module's tests are passed (derived from test results)",
    )


class CourseProgress(BaseModel):
    """One of the learner's enrolled courses, with its completion + next module.

    Used to answer 'show my enrolled courses' and 'upcoming modules across my
    courses'. All fields are the current learner's own data.
    """

    catalog_id: str
    title: str
    passed: bool = False
    modules_total: int = Field(default=0, ge=0)
    modules_completed: int = Field(default=0, ge=0)
    next_module_title: str | None = None
    next_module_due: str | None = None
    is_current: bool = Field(default=False, description="The course this chat is locked to")


class ProgressSnapshot(BaseModel):
    """The learner's OWN completion status, precomputed at the call site (deterministic).

    Cross-course counts come from the persona's linked chats; the current chat's
    per-module detail is derived separately from the plan modules. Every field is
    the current learner's own data, so the progress answer never touches the
    cross-user safety path that work_iq carries.
    """

    courses_total: int = Field(default=0, ge=0, description="Distinct linked courses")
    courses_completed: int = Field(default=0, ge=0, description="Of those, fully passed")
    current_title: str | None = Field(
        default=None, description="Title of the course this chat is locked to, if any"
    )
    courses: list[CourseProgress] = Field(
        default_factory=list,
        description="Per-course enrollment + next module (for listing / cross-course upcoming)",
    )


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
    base_minutes: int = Field(default=0, description="NORMAL-pace estimate before skill correction")
    pace_minutes: int = Field(default=0, description="Chosen-pace estimate before skill correction")
    skill_delta: int = Field(default=0, description="Signed minutes skill added (+) or removed (-)")
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
    total_base_hours: float = Field(default=0.0, description="Sum of base (NORMAL) module time")
    total_pace_hours: float = Field(default=0.0, description="Sum of pace-corrected module time")
    weeks: int
    start_date: str = Field(description="ISO date the plan starts")
    modules: list[ModulePlan]
    sessions: list[StudySession] = Field(description="The recurring weekly study slots")
    capacity_reason: str = Field(description="Which real calendar slots back the weekly load")
    balloon_warning: str | None = Field(
        default=None,
        description="Set when the plan stretches unrealistically long or overruns an exam date",
    )
    awaiting_approval: bool = Field(
        default=False,
        description="True while shown as an unsaved preview (not yet on the schedule)",
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
    state: str | None = Field(default=None, description="Course state at this turn (state graph)")
    sources: list[GroundingSource] = Field(default_factory=list)
    steps: list[TraceStep] = Field(
        default_factory=list,
        description="Sub-step chain for this phase (gate layers, router decision, …)",
    )
    confidence: float | None = Field(
        default=None, description="Decision confidence 0..1 (gate or router)"
    )
    off_topic: float | None = Field(
        default=None, description="Router off-topic score 0..1 (0=on-platform, 1=far off)"
    )


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
    """A generated study plan rendered as a structured schedule card.

    ``constraints`` carries the scheduling constraints the agent inferred this turn
    so the courses layer can persist them; they then stick across re-plans.
    """

    type: Literal["plan"] = "plan"
    plan: StudyPlan
    constraints: dict[str, object] | None = None


class PaceRequestEvent(BaseModel):
    """Ask the learner their pace before building a plan (a HITL gate)."""

    type: Literal["pace_request"] = "pace_request"
    catalog_id: str
    title: str
    prompt: str = Field(description="The question shown above the pace choices")
    options: list[Pace] = Field(default_factory=lambda: [Pace.SLOWER, Pace.NORMAL, Pace.FASTER])


class SkillGateRequestEvent(BaseModel):
    """Ask whether the learner is a fresher or wants a skill check (a HITL gate)."""

    type: Literal["skill_gate_request"] = "skill_gate_request"
    catalog_id: str
    title: str
    prompt: str = Field(description="The question shown above the two choices")
    options: list[str] = Field(default_factory=lambda: ["fresher", "assessment"])


class NewChatEvent(BaseModel):
    """Steer the learner to another chat (a fresh one, or the course's existing one).

    Two cases share this event:
    - **Locked chat** — the learner asks to switch course in a chat that already
      has one; the frontend offers a 'Start a new chat' button (no target).
    - **Already registered elsewhere** — the learner explicitly asks for a course
      that is already linked to *another* chat; ``target_course_id`` is set and the
      frontend offers a button that opens THAT chat instead of forking a duplicate.
    """

    type: Literal["new_chat"] = "new_chat"
    prompt: str = Field(description="User-facing line explaining the one-course-per-chat rule")
    current_title: str | None = Field(default=None, description="The course this chat is locked to")
    target_course_id: str | None = Field(
        default=None, description="Existing chat to open (set when the course is in another chat)"
    )
    target_title: str | None = Field(
        default=None, description="Display title of the course/chat the button opens"
    )


class DoneEvent(BaseModel):
    type: Literal["done"] = "done"
    route: Route | None = None
    suggested: bool = False


class PracticeQuestion(BaseModel):
    """One generated practice MCQ.

    ``correct`` and ``explanation`` are the answer key: ``exclude=True`` keeps them
    out of every serialization, so the client never receives them. They remain
    readable on the live object so the submit endpoint can grade server-side.
    """

    id: str
    prompt: str
    kind: Literal["mcq"] = "mcq"
    choices: list[str]
    correct: str = Field(exclude=True)
    explanation: str = Field(default="", exclude=True)


class PracticeEvent(BaseModel):
    """A generated practice round for the learner's current module (rendered as a card)."""

    type: Literal["practice"] = "practice"
    module_id: str
    title: str
    questions: list[PracticeQuestion] = Field(min_length=1)


class Action(BaseModel):
    """One CTA button in chat. The frontend builds the URL from the kind + module_id."""

    kind: Literal["take_evaluation", "go_to_module", "practice_again"]
    label: str
    module_id: str | None = None


class ActionEvent(BaseModel):
    """One or more CTA buttons rendered beneath an assistant turn."""

    type: Literal["action"] = "action"
    prompt: str | None = None
    actions: list[Action] = Field(min_length=1)


PipelineEvent = (
    PhaseEvent
    | TokenEvent
    | SuggestionEvent
    | PlanEvent
    | PaceRequestEvent
    | SkillGateRequestEvent
    | NewChatEvent
    | PracticeEvent
    | ActionEvent
    | BlockedEvent
    | ErrorEvent
    | DoneEvent
)
