"""Live red-team battery for the deterministic schedule-edit parser.

Target: ``app.agent.schedule_edit.parse_adjustment`` / ``parse_pace``. This parser
runs in ALL modes (offline + online) and feeds ``router_agent.is_plan_intent``,
which calls ``parse_adjustment(text, today=...)`` on EVERY inbound message to decide
plan-intent routing. So a parse bug is live-impacting:

  * an exception → ``is_plan_intent`` raises mid-classify → a replyless/500 turn;
  * a self-contradictory adjustment (e.g. all 7 weekdays excluded) → the downstream
    study-plan builder has zero schedulable days → a bricked / nonsense plan;
  * an absurd week number (week 999999) survives the span guard → the builder is
    asked to drop a week that doesn't exist.

Oracle is STRUCTURAL, not semantic, so no LLM judge is needed (the parser is
deterministic): a case PASSES when the parser neither raises nor returns an
internally self-contradictory / out-of-bounds adjustment. ``passed=True`` means NO
undesired behavior. We still construct ``live_settings()`` per the campaign contract
(every battery asserts the LIVE path), but the parser itself is provider-free.

Shape copied from ``agent_audit.attacks_gate``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta

from app.agent.contracts import Pace
from app.agent.router_agent import is_plan_intent
from app.agent.schedule_edit import (
    ScheduleAdjustment,
    parse_adjustment,
    parse_pace,
)

from agent_audit.harness import CaseResult, live_settings

LAYER = "schedule"

# A fixed "today" so date math is reproducible across rounds (the live router uses
# date.today(), but the parser is a pure function of (text, today); pinning it keeps
# the oracle deterministic while still exercising the exact same code path).
_TODAY = date(2026, 6, 14)

# Sane bounds for a learner-facing study plan. A start more than ~3y out, a negative
# offset, or a "skip week" number beyond a year of plan weeks is nonsense the parser
# should never emit, because the plan builder will choke on it.
_MAX_START_AHEAD = timedelta(days=366 * 3)
_MAX_START_BEHIND = timedelta(days=366)  # a start far in the past bricks the plan
_MAX_PLAN_WEEK = 104  # two years of weekly modules is already generous
_ALL_SEVEN = frozenset({"mon", "tue", "wed", "thu", "fri", "sat", "sun"})


@dataclass(frozen=True)
class SchedCase:
    """One schedule-edit attack.

    ``checker`` receives the (no-exception) parse result and returns ``(ok, detail)``
    where ``ok=True`` means the output is structurally sane. ``expect_drops`` lists
    weekday codes a clearly-stated exclusion must contain (dropped-constraint cases).
    """

    case_id: str
    category: str
    text: str
    severity: str = "high"
    checker: Callable[[ScheduleAdjustment | None], tuple[bool, str]] | None = None


# ── Oracle helpers ────────────────────────────────────────────────────────────────


def _sane(adj: ScheduleAdjustment | None) -> tuple[bool, str]:
    """The default structural oracle: an adjustment must not be self-contradictory.

    Checks every field that downstream plan-building relies on:
      * exclude_days must not be ALL seven (=> no study day can ever be scheduled);
      * a start date must sit within a believable window of ``today``;
      * skip-week numbers must be positive and within a sane plan horizon.
    """
    if adj is None:
        return True, "no adjustment (benign)"
    if adj.exclude_days == _ALL_SEVEN:
        return False, "excludes ALL 7 weekdays — no study day is schedulable (bricks plan)"
    if adj.start_date is not None:
        if adj.start_date > _TODAY + _MAX_START_AHEAD:
            return False, f"start_date absurdly far future: {adj.start_date.isoformat()}"
        if adj.start_date < _TODAY - _MAX_START_BEHIND:
            return False, f"start_date absurdly far past: {adj.start_date.isoformat()}"
    if adj.exam_date is not None and adj.exam_date > _TODAY + _MAX_START_AHEAD:
        return False, f"exam_date absurdly far future: {adj.exam_date.isoformat()}"
    bad_weeks = sorted(w for w in adj.skip_weeks if w < 1 or w > _MAX_PLAN_WEEK)
    if bad_weeks:
        return False, f"skip_weeks out of sane plan range (1..{_MAX_PLAN_WEEK}): {bad_weeks}"
    return True, "structurally sane"


def _needs_excludes(*codes: str) -> Callable[[ScheduleAdjustment | None], tuple[bool, str]]:
    """A dropped-constraint oracle: the named weekday codes MUST all be excluded.

    Used for clearly-stated multi-day / 'no weekends' exclusions the parser must not
    silently drop. Still routes through ``_sane`` first so an all-7 brick still fails.
    """

    wanted = frozenset(codes)

    def check(adj: ScheduleAdjustment | None) -> tuple[bool, str]:
        ok, detail = _sane(adj)
        if not ok:
            return ok, detail
        got = adj.exclude_days if adj else frozenset()
        missing = wanted - got
        if missing:
            return False, f"silently dropped exclusion(s): {sorted(missing)} (got {sorted(got)})"
        return True, f"all required exclusions present: {sorted(wanted)}"

    return check


# ── Cases ─────────────────────────────────────────────────────────────────────────

_CASES: tuple[SchedCase, ...] = (
    # ---- CRASH (crit): any input that raises is a live replyless turn ----
    SchedCase(
        "overflow_days",
        "crash",
        "start in 99999999999999999999 days",
        "crit",
    ),
    SchedCase(
        "overflow_days_cint",
        "crash",
        "begin in 100000000000 days from now",
        "crit",
    ),
    SchedCase(
        "overflow_weeks_oob",
        "crash",
        "start in 100000000 weeks",
        "crit",
    ),
    SchedCase(
        "absurd_month_word",
        "crash",
        "start after the 99th of Febtober and skip yesterday before next week",
        "crit",
    ),
    SchedCase(
        "rtl_emoji_dates",
        "crash",
        "🗓️ابدأ start after June 30th ⏰ skip ‮monday‬ every other Blursday 你好",
        "crit",
    ),
    SchedCase(
        "overlong_input",
        "crash",
        "x" * 200_000 + " start after June 30 and skip weeks 2 to 9",
        "crit",
    ),
    SchedCase(
        "neg_weeks_word_salad",
        "crash",
        "start in -5 weeks, remove weeks 1 to 999999, only mondays but skip monday 🙂",
        "crit",
    ),
    # ---- NONSENSE / UNSAFE (high): self-contradictory or out-of-bounds output ----
    SchedCase(
        "only_then_skip_same_day",
        "contradiction",
        "schedule me only on mondays but skip monday",
        "high",
    ),
    SchedCase(
        "only_tue_skip_tue",
        "contradiction",
        "study only tuesdays and skip tuesday this week",
        "high",
    ),
    SchedCase(
        "exclude_all_seven",
        "nonsense",
        "skip mon tue wed thu fri sat sun please",
        "high",
    ),
    SchedCase(
        "exclude_all_seven_listed",
        "nonsense",
        "avoid mon, avoid tue, avoid wed, avoid thu, avoid fri, avoid sat, avoid sun",
        "high",
    ),
    SchedCase(
        "absurd_week_range",
        "nonsense",
        "remove weeks 1 to 999999",
        "high",
    ),
    SchedCase(
        "absurd_single_week",
        "nonsense",
        "I'm busy in week 99999999999999999999",
        "high",
    ),
    SchedCase(
        "inverted_week_range",
        "nonsense",
        "I'm away weeks 10 to 2",
        "high",
    ),
    # ---- DROPPED constraint (med): a clear exclusion must be honored in full ----
    SchedCase(
        "no_weekends",
        "dropped_constraint",
        "no weekends please, I only have time on weekdays",
        "med",
        checker=_needs_excludes("sat", "sun"),
    ),
    SchedCase(
        "skip_three_days",
        "dropped_constraint",
        "skip mon, tue and wed every week",
        "med",
        checker=_needs_excludes("mon", "tue", "wed"),
    ),
    # ---- CONTRADICTION / PACE (med): conflicting pace cues must not be ambiguous ----
    SchedCase(
        "pace_faster_and_slower",
        "pace_contradiction",
        "make it faster but also slower, I can't decide",
        "med",
    ),
)


# ── Runner ──────────────────────────────────────────────────────────────────────


def _check_pace_consistency(case: SchedCase) -> tuple[bool, str]:
    """For pace-contradiction cases: a conflicting message must not parse to BOTH.

    ``parse_pace`` returns a single ``Pace`` so it can't literally return two, but a
    contradictory message resolving to a confident FASTER/SLOWER (rather than None or
    a neutral NORMAL) is a silent guess the planner would act on. We accept None or
    NORMAL as the only non-misleading outcomes for an explicit self-contradiction.
    """
    try:
        pace = parse_pace(case.text)
    except Exception as exc:  # noqa: BLE001 — any raise is itself the finding
        return False, f"parse_pace raised {type(exc).__name__}: {exc}"
    if pace in (None, Pace.NORMAL):
        return True, f"non-misleading pace for contradiction: {pace}"
    return False, f"resolved contradictory pace to a confident {pace} (silent guess)"


def _run_case(case: SchedCase) -> CaseResult:
    # Campaign contract: assert the LIVE path is configured even though the parser
    # itself is provider-free (so a battery is never silently scored offline).
    live_settings()

    if case.category == "pace_contradiction":
        passed, detail = _check_pace_consistency(case)
        return CaseResult(
            case_id=case.case_id,
            category=case.category,
            passed=passed,
            detail=detail,
            severity=case.severity,
            observed=f"parse_pace={parse_pace(case.text)!r}",
        )

    # Any exception from parse_adjustment OR from is_plan_intent (the live caller) is
    # a crash finding — fail closed.
    try:
        adj = parse_adjustment(case.text, today=_TODAY)
    except Exception as exc:  # noqa: BLE001
        return CaseResult(
            case_id=case.case_id,
            category=case.category,
            passed=False,
            detail=f"parse_adjustment RAISED {type(exc).__name__}: {str(exc)[:120]}",
            severity="crit",
            error=False,
            observed=f"input={case.text[:80]!r}",
        )
    try:
        # Mirror the exact live entry point: router calls this on every message.
        is_plan_intent(case.text)
    except Exception as exc:  # noqa: BLE001
        return CaseResult(
            case_id=case.case_id,
            category=case.category,
            passed=False,
            detail=f"is_plan_intent RAISED {type(exc).__name__}: {str(exc)[:120]}",
            severity="crit",
            error=False,
            observed=f"input={case.text[:80]!r}",
        )

    checker = case.checker or _sane
    ok, detail = checker(adj)
    observed = (
        "adj=None"
        if adj is None
        else (
            f"start={adj.start_date} excl={sorted(adj.exclude_days)} "
            f"weeks={sorted(adj.skip_weeks)} exam={adj.exam_date}"
        )
    )
    return CaseResult(
        case_id=case.case_id,
        category=case.category,
        passed=ok,
        detail=detail,
        severity=case.severity,
        observed=observed[:300],
    )


def run() -> list[CaseResult]:
    """Run the full schedule-edit battery once against the live (provider-free) parser."""
    return [_run_case(c) for c in _CASES]
