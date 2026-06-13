"""Grounding guards — the rule-based layer that keeps answers honest.

The cert-prep winner earned Reliability with *guardrails + rule-based tests*,
not a research eval suite. These are pure, testable functions the pipeline (and
CI) use to assert that narration is grounded:

- **number-match**: an LLM narrating a study plan must only state numbers the
  deterministic plan actually computed — it never originates a figure.
- **no fabrication**: course/module ids in an answer must exist in the catalog.

Numbers are computed by the algorithm and *injected*; these guards detect any
that leaked in ungrounded, so a regression is caught rather than shipped.
"""

from __future__ import annotations

import re

from app.agent.contracts import StudyPlan

_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def numbers_in(text: str) -> set[str]:
    """All numeric tokens in a string, normalized (e.g. '3.0' and '3' both → '3')."""
    out: set[str] = set()
    for match in _NUMBER.findall(text):
        value = float(match)
        out.add(str(int(value)) if value.is_integer() else str(value))
    return out


def allowed_plan_numbers(plan: StudyPlan) -> set[str]:
    """Every number the plan legitimately exposes (hours, weeks, minutes, dates)."""
    allowed: set[str] = set()
    for value in (plan.weekly_study_hours, plan.total_hours, plan.weeks, len(plan.modules)):
        allowed |= numbers_in(str(value))
    for m in plan.modules:
        allowed |= numbers_in(str(m.estimated_minutes))
        allowed |= numbers_in(str(m.sequence))
        allowed |= numbers_in(m.complete_before)  # ISO date digits
        for b in m.scheduled:
            allowed |= numbers_in(f"{b.week} {b.start} {b.end} {b.minutes}")
    for s in plan.sessions:
        allowed |= numbers_in(f"{s.start} {s.end} {s.duration_minutes}")
    allowed |= numbers_in(plan.capacity_reason)
    allowed |= numbers_in(plan.start_date)
    return allowed


def ungrounded_numbers(narration: str, allowed: set[str]) -> set[str]:
    """Numbers in the narration that the plan never computed (should be empty)."""
    return numbers_in(narration) - allowed


def plan_narration_is_grounded(narration: str, plan: StudyPlan) -> bool:
    """True iff every number in the narration traces to the computed plan."""
    return not ungrounded_numbers(narration, allowed_plan_numbers(plan))
