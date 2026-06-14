"""The agentic study-plan scheduler: an LLM tool-calling agent over a deterministic
planner.

This is the hybrid design (master-plan): the *model* interprets the learner's
free-text scheduling intent — open vocabulary, no regex grammar — and calls the
``propose_plan`` tool with structured constraints. The deterministic
``build_study_plan`` does all the date/time math, so every number the learner
sees is still computed and auditable. The model adapts; the engine stays honest.

Constraints the model can express (a superset of what the old regex could parse):
pace, start date, days to skip, plan-weeks to skip, a target exam date, a
time-of-day window ("only evenings", "after 21:00"), a max session length, and
specific dates to avoid (a one-off appointment).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from app.agent.contracts import Pace, StudyPlan
from app.agent.llm import Capability, ModelRouter
from app.agent.study_plan import build_study_plan
from app.config import Settings
from app.workiq.models import Persona

_WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _to_minutes(hhmm: str) -> int | None:
    try:
        hours, minutes = hhmm.split(":")
        total = int(hours) * 60 + int(minutes)
    except (ValueError, AttributeError):
        return None
    return total if 0 <= total <= 24 * 60 else None


def _iso_date(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


# The one tool the scheduling agent drives. All fields optional: the model omits a
# field to keep the plan's current value for it.
PROPOSE_PLAN_TOOL: dict[str, object] = {
    "type": "function",
    "function": {
        "name": "propose_plan",
        "description": (
            "Build the learner's calendar-grounded study plan honoring the given "
            "constraints. Call this once you understand the request. Every field is "
            "optional; omit a field to keep its current value."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pace": {"type": "string", "enum": ["slower", "normal", "faster"]},
                "start_date": {"type": "string", "description": "ISO date YYYY-MM-DD"},
                "exclude_days": {
                    "type": "array",
                    "items": {"type": "string", "enum": list(_WEEKDAYS)},
                    "description": "weekdays to never study on",
                },
                "skip_weeks": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "plan-week numbers (1-based) to leave empty",
                },
                "exam_date": {"type": "string", "description": "ISO target exam date"},
                "earliest_time": {
                    "type": "string",
                    "description": "earliest time of day to study, HH:MM (e.g. '21:00')",
                },
                "latest_time": {
                    "type": "string",
                    "description": "latest time of day to study, HH:MM",
                },
                "max_session_minutes": {
                    "type": "integer",
                    "description": "cap on the length of any single study block",
                },
                "excluded_dates": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "specific ISO dates to avoid (e.g. an appointment)",
                },
            },
        },
    },
}

_SYSTEM = (
    "You are Athenaeum's scheduling agent. The learner wants to build or adjust their study "
    "plan. Infer the scheduling constraints from their message — pace, start date, weekdays to "
    "skip, a time-of-day window, a max session length, a target exam date, or specific dates to "
    "avoid — and call propose_plan ONCE with them. Keep the current setting for anything they "
    "did not mention. After the tool returns, write a warm 2 to 3 sentence summary of the plan. "
    "Quote ONLY numbers and dates the tool returned; never invent figures. If the tool reports a "
    "warning (for example no study time left), explain it plainly and suggest a fix. Do not use "
    "em dashes; use commas or periods."
)


@dataclass(frozen=True)
class SchedulerContext:
    """Everything the scheduler agent needs for one turn (the planner's inputs)."""

    persona: Persona
    catalog_id: str
    title: str
    cert: str
    today: date
    reserved: frozenset[tuple[str, int, int]] = frozenset()
    pace: Pace | None = None
    start_date: date | None = None
    exclude_days: frozenset[str] = frozenset()
    skip_weeks: frozenset[int] = frozenset()
    exam_date: date | None = None


@dataclass
class SchedulerResult:
    """The agent's outcome: the built plan, its narration, and the chosen constraints."""

    plan: StudyPlan | None
    narration: str
    constraints: dict[str, object] = field(default_factory=dict)
    tier: int | None = None
    model: str | None = None


def _baseline_text(ctx: SchedulerContext) -> str:
    return (
        f"pace={ctx.pace.value if ctx.pace else 'normal'}; "
        f"start_date={(ctx.start_date or ctx.today).isoformat()}; "
        f"exclude_days={sorted(ctx.exclude_days) or 'none'}; "
        f"skip_weeks={sorted(ctx.skip_weeks) or 'none'}; "
        f"exam_date={ctx.exam_date.isoformat() if ctx.exam_date else 'none'}; "
        f"today={ctx.today.isoformat()}"
    )


def build_plan_from_args(
    ctx: SchedulerContext, args: dict[str, object], settings: Settings
) -> tuple[StudyPlan | None, dict[str, object]]:
    """Map the model's tool arguments onto the deterministic planner (pure).

    Each field falls back to the turn's baseline when the model omits or malforms
    it, so a partial/garbled tool call still produces a valid plan.
    """
    pace_raw = args.get("pace")
    pace = Pace(pace_raw) if pace_raw in ("slower", "normal", "faster") else (ctx.pace or Pace.NORMAL)
    start = _iso_date(args.get("start_date")) or ctx.start_date or ctx.today
    exclude = (
        frozenset(d for d in args["exclude_days"] if d in _WEEKDAYS)
        if isinstance(args.get("exclude_days"), list)
        else frozenset()
    ) or ctx.exclude_days
    skip = (
        frozenset(int(w) for w in args["skip_weeks"] if isinstance(w, int) and w >= 1)
        if isinstance(args.get("skip_weeks"), list)
        else frozenset()
    ) or ctx.skip_weeks
    exam = _iso_date(args.get("exam_date")) or ctx.exam_date

    time_window: tuple[int, int] | None = None
    lo = _to_minutes(args["earliest_time"]) if isinstance(args.get("earliest_time"), str) else None
    hi = _to_minutes(args["latest_time"]) if isinstance(args.get("latest_time"), str) else None
    if lo is not None or hi is not None:
        time_window = (lo or 0, hi or 24 * 60)

    max_session = (
        int(args["max_session_minutes"])
        if isinstance(args.get("max_session_minutes"), int) and args["max_session_minutes"] > 0  # type: ignore[operator]
        else None
    )
    extra_dates = (
        frozenset(d for d in args["excluded_dates"] if _iso_date(d) is not None)
        if isinstance(args.get("excluded_dates"), list)
        else frozenset()
    )

    plan = build_study_plan(
        catalog_id=ctx.catalog_id,
        title=ctx.title,
        cert=ctx.cert,
        persona=ctx.persona,
        pace=pace,
        start_date=start,
        exclude_days=exclude,
        skip_weeks=skip,
        reserved=ctx.reserved,
        exam_date=exam,
        time_window=time_window,
        max_session_minutes=max_session,
        extra_skip_dates=extra_dates,
        settings=settings,
    )
    constraints: dict[str, object] = {
        "pace": pace.value,
        "start_date": start.isoformat(),
        "exclude_days": sorted(exclude),
        "skip_weeks": sorted(skip),
        "exam_date": exam.isoformat() if exam else None,
        "time_window": list(time_window) if time_window else None,
        "max_session_minutes": max_session,
        "excluded_dates": sorted(extra_dates),
    }
    return plan, constraints


def _plan_summary(plan: StudyPlan) -> dict[str, object]:
    """The auditable facts the model is allowed to narrate (numbers come from here)."""
    return {
        "weeks": plan.weeks,
        "weekly_study_hours": plan.weekly_study_hours,
        "total_hours": plan.total_hours,
        "modules": len(plan.modules),
        "pace": plan.pace.value,
        "first_module": plan.modules[0].title if plan.modules else None,
        "first_complete_before": plan.modules[0].complete_before if plan.modules else None,
        "capacity_reason": plan.capacity_reason,
        "balloon_warning": plan.balloon_warning,
    }


def run_scheduler_agent(
    text: str, ctx: SchedulerContext, router: ModelRouter, *, settings: Settings
) -> SchedulerResult:
    """Run the tool-calling scheduling agent for one turn (online path).

    The model calls ``propose_plan`` with the constraints it inferred; the handler
    builds the plan deterministically and hands back only auditable facts to
    narrate. The built plan is captured for the pipeline to render and persist.
    """
    capture: dict[str, object] = {}

    def propose_plan(args: dict[str, object]) -> dict[str, object]:
        plan, constraints = build_plan_from_args(ctx, args, settings)
        capture["plan"] = plan
        capture["constraints"] = constraints
        if plan is None:
            return {"error": "this course has no modules to plan against"}
        if not plan.sessions:
            return {
                "warning": "no study time is left in the week after these constraints",
                "fix": "free up a day or widen the time window",
            }
        return _plan_summary(plan)

    result = router.run_tools(
        Capability.WORKHORSE,
        [
            {"role": "system", "content": _SYSTEM},
            {
                "role": "user",
                "content": f"Current plan settings: {_baseline_text(ctx)}\n\nLearner says: {text}",
            },
        ],
        tools=[PROPOSE_PLAN_TOOL],
        handlers={"propose_plan": propose_plan},
    )
    return SchedulerResult(
        plan=capture.get("plan"),  # type: ignore[arg-type]
        narration=result.text,
        constraints=capture.get("constraints", {}),  # type: ignore[arg-type]
        tier=result.tier,
        model=result.model,
    )
