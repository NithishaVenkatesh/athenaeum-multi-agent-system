# Skill-Gap Assessment Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Insert a skill-gap assessment step between course-accept and pace selection so the study plan adjusts each module's time by what the learner already knows, shown as a preview that is written to the schedule only on explicit approval.

**Architecture:** Extend the existing chat pipeline with one new HITL event (`SkillGateRequestEvent`) and a set of REST actions (`/skill/start`, `/skill/grade`, `/skill/fresher`, `/deadline`, `/plan/approve`), mirroring the existing `PaceRequestEvent` → REST → derived-state pattern. The per-module choice banks and set-match grading are reused. Skill scores feed a new pure function `apply_skill_correction` that is gated by pace direction. The chat path stops persisting modules directly; it stages them in `Course.pending_modules`, and `/plan/approve` promotes that staged plan to real `CourseModule` rows.

**Tech Stack:** FastAPI + SQLModel (SQLite, `athenaeum.db` for the workspace, `assessments.db` for banks), Pydantic v2 contracts, a synchronous generator SSE pipeline; Next.js (App Router, client components) + React + framer-motion + lucide + a local `Button` UI; pytest (backend), vitest/RTL (frontend).

**Reference spec:** [docs/superpowers/specs/2026-06-14-skill-gap-assessment-flow-design.md](../specs/2026-06-14-skill-gap-assessment-flow-design.md)

---

## Conventions used throughout

- Backend tests run from the backend dir: `cd ayanakoji/backend && python -m pytest <path> -v`.
- Frontend commands run from `ayanakoji/frontend` (use the repo's package manager; commands below use `npm`).
- Commit after every green step. Commit messages follow `feat|fix|test(scope): …`.
- The pace direction rules (locked decisions): **slower = lessen only**, **faster = extend only**, **normal = both**. Skill cap **±20%** at score extremes; neutral midpoint at score `0.5`. Fresher = score `0.0` on every module (same code path).

---

## Phase 1 — Skill-correction math (pure functions in `study_plan.py`)

### Task 1.1: `skill_factor` + `apply_skill_correction`

**Files:**
- Modify: `ayanakoji/backend/app/agent/study_plan.py` (add constants + two functions after `estimate_module_minutes`, ~line 113)
- Test: `ayanakoji/backend/tests/test_skill_correction.py`

- [ ] **Step 1: Write the failing test**

```python
# ayanakoji/backend/tests/test_skill_correction.py
"""Skill-gap time correction: pace-gated, ±20% at the score extremes."""

from __future__ import annotations

import pytest

from app.agent.contracts import Pace
from app.agent.study_plan import apply_skill_correction, skill_factor


@pytest.mark.parametrize(
    ("score", "pace", "expected"),
    [
        # Normal: both directions, ±20% at the extremes, neutral at 0.5.
        (1.0, Pace.NORMAL, 0.80),
        (0.0, Pace.NORMAL, 1.20),
        (0.5, Pace.NORMAL, 1.00),
        (0.75, Pace.NORMAL, 0.90),
        (0.25, Pace.NORMAL, 1.10),
        # Slower: lessen only — mastery shrinks, weakness is clamped to no-change.
        (1.0, Pace.SLOWER, 0.80),
        (0.0, Pace.SLOWER, 1.00),
        (0.5, Pace.SLOWER, 1.00),
        # Faster: extend only — weakness grows, mastery is clamped to no-change.
        (0.0, Pace.FASTER, 1.20),
        (1.0, Pace.FASTER, 1.00),
        (0.5, Pace.FASTER, 1.00),
    ],
)
def test_skill_factor_is_pace_gated(score: float, pace: Pace, expected: float) -> None:
    assert skill_factor(score, pace) == pytest.approx(expected)


def test_fresher_zero_score_extends_only_on_faster_and_normal() -> None:
    # Fresher = score 0.0 everywhere; slower must not pad (lessen-only).
    assert skill_factor(0.0, Pace.SLOWER) == pytest.approx(1.00)
    assert skill_factor(0.0, Pace.NORMAL) == pytest.approx(1.20)
    assert skill_factor(0.0, Pace.FASTER) == pytest.approx(1.20)


def test_apply_skill_correction_rounds_to_granularity_and_respects_direction() -> None:
    # 120 min pace-corrected; mastered (0.8x) → 96 → rounds to 90 (15-min grid).
    assert apply_skill_correction(120, 1.0, Pace.NORMAL) == 90
    # Weak on faster (1.2x) → 144 → rounds to 150.
    assert apply_skill_correction(120, 0.0, Pace.FASTER) == 150
    # Slower never extends: weak score keeps the pace-corrected value.
    assert apply_skill_correction(120, 0.0, Pace.SLOWER) == 120
    # Faster never shrinks: mastered score keeps the pace-corrected value.
    assert apply_skill_correction(120, 1.0, Pace.FASTER) == 120
    # Floor at one granularity unit.
    assert apply_skill_correction(15, 1.0, Pace.NORMAL) >= 15
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ayanakoji/backend && python -m pytest tests/test_skill_correction.py -v`
Expected: FAIL — `ImportError: cannot import name 'apply_skill_correction'`.

- [ ] **Step 3: Implement the functions**

In `ayanakoji/backend/app/agent/study_plan.py`, add these constants next to the existing time constants (after line 45, the `PACE_FACTOR` line):

```python
# --- Skill-gap correction (conservative ±20%, gated by pace direction) ---
MAX_SKILL_ADJ = 0.20  # cap on how far a module's time moves at a score extreme
NEUTRAL_SCORE = 0.5  # midpoint: 2 of 4 correct ⇒ no change; missing score ⇒ neutral
```

Add these two functions immediately after `estimate_module_minutes` (after line 112):

```python
def skill_factor(score: float, pace: Pace, max_adj: float = MAX_SKILL_ADJ) -> float:
    """Per-module time multiplier from a skill score, gated by pace direction.

    ``score`` is the fraction of the module's skill-check questions answered
    correctly (0..1). At ``NEUTRAL_SCORE`` the factor is 1.0. Mastery (high score)
    lessens time; weakness (low score) extends it, by at most ``max_adj`` at the
    extremes. Pace constrains the direction: slower may only lessen, faster may
    only extend, normal may do both (the locked product rules).
    """
    raw = 1.0 - max_adj * (2.0 * score - 1.0)
    if pace is Pace.SLOWER:
        return min(1.0, raw)  # lessen only — never pad a relaxed plan
    if pace is Pace.FASTER:
        return max(1.0, raw)  # extend only — never trim an intensive plan
    return raw  # normal: both directions


def apply_skill_correction(
    pace_minutes: int, score: float, pace: Pace, max_adj: float = MAX_SKILL_ADJ
) -> int:
    """Apply the pace-gated skill factor to a pace-corrected minute budget.

    Re-rounds to the session granularity and floors at one granularity unit so a
    fully-mastered short module never collapses to zero.
    """
    rounded = (
        round(pace_minutes * skill_factor(score, pace, max_adj) / SESSION_GRANULARITY)
        * SESSION_GRANULARITY
    )
    return max(SESSION_GRANULARITY, int(rounded))
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd ayanakoji/backend && python -m pytest tests/test_skill_correction.py -v`
Expected: PASS (all parametrized cases).

- [ ] **Step 5: Commit**

```bash
git add ayanakoji/backend/app/agent/study_plan.py ayanakoji/backend/tests/test_skill_correction.py
git commit -m "feat(study-plan): pace-gated skill-gap time correction (±20%)"
```

---

### Task 1.2: Thread base/pace/skill through `build_study_plan` and `schedule_modules`

**Files:**
- Modify: `ayanakoji/backend/app/agent/contracts.py` (ModulePlan + StudyPlan new fields) — done fully in Task 2.1; for this task add the fields first
- Modify: `ayanakoji/backend/app/agent/study_plan.py` (`ModuleEstimate`, `schedule_modules`, `build_study_plan`)
- Test: `ayanakoji/backend/tests/test_skill_plan_build.py`

> Do Task 2.1's contract field additions (ModulePlan `base_minutes`/`pace_minutes`/`skill_delta`, StudyPlan `awaiting_approval`/`total_base_hours`/`total_pace_hours`) before running this task's test, since the test asserts on them. They are listed here too so this task is self-contained:
>
> In `contracts.py`, `ModulePlan` add (after `estimated_minutes`, line 168):
> ```python
>     base_minutes: int = Field(default=0, description="NORMAL-pace estimate before skill correction")
>     pace_minutes: int = Field(default=0, description="Chosen-pace estimate before skill correction")
>     skill_delta: int = Field(default=0, description="Signed minutes skill added (+) or removed (-)")
> ```
> In `contracts.py`, `StudyPlan` add (after `total_hours`, line 184):
> ```python
>     total_base_hours: float = Field(default=0.0, description="Sum of base (NORMAL) module time")
>     total_pace_hours: float = Field(default=0.0, description="Sum of pace-corrected module time")
>     awaiting_approval: bool = Field(default=False, description="True while shown as an unsaved preview")
> ```

- [ ] **Step 1: Write the failing test**

```python
# ayanakoji/backend/tests/test_skill_plan_build.py
"""build_study_plan applies skill scores and exposes the base/pace/skill breakdown."""

from __future__ import annotations

from datetime import date

from app.agent.contracts import Pace
from app.agent.study_plan import build_study_plan
from app.workiq.repository import get_repository


def _persona():
    # Any learner with calendar capacity; reuse the seeded Work IQ personas.
    repo = get_repository()
    personas = repo.list_personas(learners_only=True)
    return repo.get_persona(personas[0].employee_id)


def _catalog_course_id() -> str:
    # A known seeded course with modules and banks.
    return "de-c01"


def test_skill_scores_shrink_mastered_modules_on_normal_pace() -> None:
    persona = _persona()
    cid = _catalog_course_id()
    start = date(2026, 6, 15)

    baseline = build_study_plan(
        catalog_id=cid, title="t", cert="c", persona=persona,
        pace=Pace.NORMAL, start_date=start,
    )
    assert baseline is not None
    mastered = {m.module_id: 1.0 for m in baseline.modules}
    corrected = build_study_plan(
        catalog_id=cid, title="t", cert="c", persona=persona,
        pace=Pace.NORMAL, start_date=start, skill_scores=mastered,
    )
    assert corrected is not None
    # Every module: skill-corrected ≤ pace-corrected, and the breakdown is exposed.
    for m in corrected.modules:
        assert m.pace_minutes == next(
            b.estimated_minutes for b in baseline.modules if b.module_id == m.module_id
        )
        assert m.estimated_minutes <= m.pace_minutes
        assert m.skill_delta == m.estimated_minutes - m.pace_minutes
        assert m.base_minutes > 0
    assert corrected.total_pace_hours >= corrected.total_hours
    assert corrected.total_base_hours > 0


def test_missing_skill_score_is_neutral_no_change() -> None:
    persona = _persona()
    cid = _catalog_course_id()
    start = date(2026, 6, 15)
    baseline = build_study_plan(
        catalog_id=cid, title="t", cert="c", persona=persona,
        pace=Pace.NORMAL, start_date=start,
    )
    # Empty scores dict ⇒ all modules neutral ⇒ identical to no skill data.
    neutral = build_study_plan(
        catalog_id=cid, title="t", cert="c", persona=persona,
        pace=Pace.NORMAL, start_date=start, skill_scores={},
    )
    assert baseline is not None and neutral is not None
    assert [m.estimated_minutes for m in baseline.modules] == [
        m.estimated_minutes for m in neutral.modules
    ]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ayanakoji/backend && python -m pytest tests/test_skill_plan_build.py -v`
Expected: FAIL — `build_study_plan() got an unexpected keyword argument 'skill_scores'`.

- [ ] **Step 3: Implement the dataclass + threading**

In `study_plan.py`, add a dataclass after `ModuleInfo` (after line 70):

```python
@dataclass(frozen=True)
class ModuleEstimate:
    """A module's time budget broken into base, pace-corrected, and skill-corrected."""

    module: ModuleInfo
    base_minutes: int  # NORMAL pace, no skill
    pace_minutes: int  # chosen pace, no skill
    skill_minutes: int  # chosen pace + skill (what gets scheduled)
```

Add a helper after `apply_skill_correction`:

```python
def _module_score(scores: dict[str, float] | None, module_id: str) -> float:
    """The skill score for a module, defaulting to neutral when not assessed."""
    if not scores:
        return NEUTRAL_SCORE
    return scores.get(module_id, NEUTRAL_SCORE)
```

Change `schedule_modules` to take `list[ModuleEstimate]` and emit the breakdown. Replace its signature and body header (lines 291-299) and the loop/ModulePlan construction (lines 314-374) as follows:

```python
def schedule_modules(
    estimates: list[ModuleEstimate],
    slots: list[WeeklySlot],
    start_date: date,
    skip_weeks: frozenset[int] = frozenset(),
    reserved: frozenset[ReservedInterval] = frozenset(),
    skip_dates: frozenset[str] = frozenset(),
    max_session_minutes: int | None = None,
) -> list[ModulePlan]:
    """Fill the repeating weekly slots with modules in order; deadline per module.

    ``skip_weeks`` are plan-week numbers the learner said they're occupied in.
    ``reserved`` are absolute (date, start, end) intervals taken by other courses.
    ``skip_dates`` are ISO date strings for PTO/on-call days — any slot that falls
    on one of these dates is skipped entirely (the work flows to the next slot).
    Each module is scheduled by its ``skill_minutes``; the base and pace-corrected
    figures ride along onto the ModulePlan for the breakdown the learner sees.
    """
    if not slots:
        return []
    plans: list[ModulePlan] = []
    week = _next_open_week(1, skip_weeks)
    slot_idx = 0
    cursor = slots[0].start  # position within the current slot

    for seq, est in enumerate(estimates, start=1):
        module = est.module
        remaining = est.skill_minutes
        blocks: list[ScheduledBlock] = []
        last_week = week
        while remaining > 0:
            slot = slots[slot_idx]
            if cursor < slot.start:
                cursor = slot.start
            day_iso = block_date(start_date, week, slot.day).isoformat()
            if day_iso in skip_dates:
                seg_start, seg_end = slot.end, slot.end
            elif reserved:
                seg_start, seg_end = _free_segment(day_iso, cursor, slot.end, reserved)
            else:
                seg_start, seg_end = cursor, slot.end
            avail = seg_end - seg_start
            if avail < _MIN_SLOT_MINUTES:
                if seg_end < slot.end:
                    cursor = seg_end
                    continue
                slot_idx += 1
                if slot_idx >= len(slots):
                    slot_idx = 0
                    week = _next_open_week(week + 1, skip_weeks)
                cursor = slots[slot_idx].start
                continue
            cursor = seg_start
            cap = max_session_minutes if max_session_minutes else avail
            take = min(remaining, avail, cap)
            blocks.append(
                ScheduledBlock(
                    week=week,
                    day=slot.day,
                    start=_to_hhmm(cursor),
                    end=_to_hhmm(cursor + take),
                    minutes=take,
                )
            )
            last_week = week
            cursor += take
            remaining -= take
            if max_session_minutes and take >= max_session_minutes and remaining > 0:
                cursor = slot.end
        complete_before = start_date + timedelta(days=last_week * 7)
        plans.append(
            ModulePlan(
                module_id=module.module_id,
                title=module.title,
                sequence=seq,
                estimated_minutes=est.skill_minutes,
                base_minutes=est.base_minutes,
                pace_minutes=est.pace_minutes,
                skill_delta=est.skill_minutes - est.pace_minutes,
                scheduled=blocks,
                complete_before=complete_before.isoformat(),
                objectives=list(module.objectives),
            )
        )
    return plans
```

In `build_study_plan`, add the `skill_scores` parameter and compute the breakdown. Change the signature (add the param before `settings`, line 396) and the estimate/total/return blocks (lines 411-471):

```python
    skill_scores: dict[str, float] | None = None,
    settings: Settings | None = None,
) -> StudyPlan | None:
```

Replace the estimate + totals (lines 411-412) with:

```python
    estimates = [
        ModuleEstimate(
            module=m,
            base_minutes=estimate_module_minutes(m, Pace.NORMAL),
            pace_minutes=estimate_module_minutes(m, pace),
            skill_minutes=apply_skill_correction(
                estimate_module_minutes(m, pace), _module_score(skill_scores, m.module_id), pace
            ),
        )
        for m in modules
    ]
    total_minutes = sum(e.skill_minutes for e in estimates)
    total_base_minutes = sum(e.base_minutes for e in estimates)
    total_pace_minutes = sum(e.pace_minutes for e in estimates)
```

In the `return StudyPlan(...)` block (lines 458-471) add the three new fields:

```python
        total_hours=round(total_minutes / 60, 1),
        total_base_hours=round(total_base_minutes / 60, 1),
        total_pace_hours=round(total_pace_minutes / 60, 1),
        weeks=weeks,
```
(keep the rest of the kwargs; `awaiting_approval` defaults False and is set by the answer agent later.)

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd ayanakoji/backend && python -m pytest tests/test_skill_plan_build.py tests/test_skill_correction.py -v`
Expected: PASS.

- [ ] **Step 5: Run the existing study-plan tests to catch the `schedule_modules` signature change**

Run: `cd ayanakoji/backend && python -m pytest tests/ -k "study_plan or schedule" -v`
Expected: Some existing tests that build `schedule_modules(estimates=[(module, minutes)], ...)` will now FAIL. Fix each by wrapping tuples in `ModuleEstimate(module=m, base_minutes=mins, pace_minutes=mins, skill_minutes=mins)` (use the same `mins` for all three where the test only cared about scheduling). Re-run until green.

- [ ] **Step 6: Commit**

```bash
git add ayanakoji/backend/app/agent/study_plan.py ayanakoji/backend/app/agent/contracts.py ayanakoji/backend/tests/test_skill_plan_build.py
git commit -m "feat(study-plan): skill_scores in build_study_plan + base/pace/skill breakdown"
```

---

## Phase 2 — Contracts + state machine

### Task 2.1: `SkillGateRequestEvent` + contract fields

> The ModulePlan/StudyPlan field additions were front-loaded into Task 1.2. This task adds the event and finishes the union.

**Files:**
- Modify: `ayanakoji/backend/app/agent/contracts.py`
- Test: `ayanakoji/backend/tests/test_skill_contracts.py`

- [ ] **Step 1: Write the failing test**

```python
# ayanakoji/backend/tests/test_skill_contracts.py
from __future__ import annotations

from app.agent.contracts import SkillGateRequestEvent


def test_skill_gate_request_defaults() -> None:
    e = SkillGateRequestEvent(catalog_id="de-c01", title="Data Eng", prompt="New here?")
    dumped = e.model_dump(mode="json")
    assert dumped["type"] == "skill_gate_request"
    assert dumped["options"] == ["fresher", "assessment"]
    assert dumped["catalog_id"] == "de-c01"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ayanakoji/backend && python -m pytest tests/test_skill_contracts.py -v`
Expected: FAIL — `ImportError: cannot import name 'SkillGateRequestEvent'`.

- [ ] **Step 3: Implement**

In `contracts.py`, add after `PaceRequestEvent` (after line 277):

```python
class SkillGateRequestEvent(BaseModel):
    """Ask whether the learner is a fresher or wants a skill check (a HITL gate)."""

    type: Literal["skill_gate_request"] = "skill_gate_request"
    catalog_id: str
    title: str
    prompt: str = Field(description="The question shown above the two choices")
    options: list[str] = Field(default_factory=lambda: ["fresher", "assessment"])
```

Add it to the `PipelineEvent` union (line 307-317):

```python
PipelineEvent = (
    PhaseEvent
    | TokenEvent
    | SuggestionEvent
    | PlanEvent
    | PaceRequestEvent
    | SkillGateRequestEvent
    | NewChatEvent
    | BlockedEvent
    | ErrorEvent
    | DoneEvent
)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd ayanakoji/backend && python -m pytest tests/test_skill_contracts.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ayanakoji/backend/app/agent/contracts.py ayanakoji/backend/tests/test_skill_contracts.py
git commit -m "feat(contracts): SkillGateRequestEvent + add to pipeline union"
```

---

### Task 2.2: `ASSESSED` state + `derive_course_state(skill_source=…)`

**Files:**
- Modify: `ayanakoji/backend/app/agent/state.py`
- Test: `ayanakoji/backend/tests/test_skill_state.py`

- [ ] **Step 1: Write the failing test**

```python
# ayanakoji/backend/tests/test_skill_state.py
from __future__ import annotations

from app.agent.contracts import Pace
from app.agent.state import CourseState, derive_course_state


def test_chosen_until_skill_then_assessed_then_paced() -> None:
    base = dict(catalog_id="de-c01", module_count=0, completed_count=0)
    assert derive_course_state(pace=None, skill_source=None, **base) == CourseState.CHOSEN
    assert derive_course_state(pace=None, skill_source="fresher", **base) == CourseState.ASSESSED
    assert derive_course_state(pace=Pace.NORMAL, skill_source="assessment", **base) == CourseState.PACED


def test_modules_present_overrides_to_planned() -> None:
    assert (
        derive_course_state(
            catalog_id="de-c01", pace=Pace.NORMAL, skill_source="assessment",
            module_count=5, completed_count=0,
        )
        == CourseState.PLANNED
    )


def test_no_catalog_is_new() -> None:
    assert (
        derive_course_state(catalog_id=None, pace=None, skill_source=None, module_count=0, completed_count=0)
        == CourseState.NEW
    )
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ayanakoji/backend && python -m pytest tests/test_skill_state.py -v`
Expected: FAIL — `derive_course_state() got an unexpected keyword argument 'skill_source'`.

- [ ] **Step 3: Implement**

In `state.py`, add `ASSESSED` to the enum (after `CHOSEN`, line 27):

```python
    ASSESSED = "assessed"  # skill check done (or fresher), pace not set
```

Replace `derive_course_state` (lines 33-49) with:

```python
def derive_course_state(
    *,
    catalog_id: str | None,
    pace: Pace | None,
    skill_source: str | None,
    module_count: int,
    completed_count: int,
) -> CourseState:
    """Compute the course state from the persisted facts (pure)."""
    if not catalog_id:
        return CourseState.NEW
    if module_count == 0:
        if skill_source is None:
            return CourseState.CHOSEN
        if pace is None:
            return CourseState.ASSESSED
        return CourseState.PACED
    if completed_count == 0:
        return CourseState.PLANNED
    if completed_count >= module_count:
        return CourseState.COMPLETED
    return CourseState.IN_PROGRESS
```

Update `transition_note` (lines 52-64) so the `STUDY_PLAN` gate map includes the new state and the updated CHOSEN copy:

```python
    gate = {
        CourseState.NEW: "no course → choose one first",
        CourseState.CHOSEN: "course set, no skill check → ask fresher / skill check",
        CourseState.ASSESSED: "skill check done → ask pace",
        CourseState.PACED: "pace set → build the plan preview",
        CourseState.PLANNED: "plan exists → rebuild preview / open Modules",
        CourseState.IN_PROGRESS: "in progress → rebuild keeps completed modules",
        CourseState.COMPLETED: "course completed → recommend what's next",
    }[state]
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd ayanakoji/backend && python -m pytest tests/test_skill_state.py -v`
Expected: PASS.

- [ ] **Step 5: Find and fix existing `derive_course_state` callers**

Run: `cd ayanakoji/backend && grep -rn "derive_course_state(" app tests`
Expected: the call in `app/courses/router.py:436` and any tests. They are updated in Task 5.1; for now run `python -m pytest tests/test_skill_state.py -v` only. (The router call is fixed in Phase 5.)

- [ ] **Step 6: Commit**

```bash
git add ayanakoji/backend/app/agent/state.py ayanakoji/backend/tests/test_skill_state.py
git commit -m "feat(state): ASSESSED state; derive_course_state gates on skill_source"
```

---

## Phase 3 — Persistence (new Course fields + guarded SQLite migration)

### Task 3.1: `Course.skill_source`, `skill_scores`, `pending_modules`

**Files:**
- Modify: `ayanakoji/backend/app/courses/models.py`
- Test: `ayanakoji/backend/tests/test_course_skill_fields.py`

- [ ] **Step 1: Write the failing test**

```python
# ayanakoji/backend/tests/test_course_skill_fields.py
from __future__ import annotations

from app.courses.models import Course


def test_course_has_skill_fields_with_safe_defaults() -> None:
    c = Course(persona_id="emp-1", chat_name="x")
    assert c.skill_source is None
    assert c.skill_scores == {}
    assert c.pending_modules == []
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ayanakoji/backend && python -m pytest tests/test_course_skill_fields.py -v`
Expected: FAIL — `AttributeError: 'Course' object has no attribute 'skill_source'`.

- [ ] **Step 3: Implement**

In `models.py`, add to `Course` after `plan_constraints` (after line 74):

```python
    # Skill-gap check: source ("fresher"|"assessment") and per-module fraction
    # correct (module_id → 0..1). Drives the pace-gated time correction.
    skill_source: str | None = Field(default=None)
    skill_scores: dict[str, float] = Field(default_factory=dict, sa_type=JSON)
    # Staged study-plan modules awaiting the learner's approval. Promoted to real
    # CourseModule rows by POST /plan/approve; the chat path never writes modules.
    pending_modules: list[dict[str, Any]] = Field(default_factory=list, sa_type=JSON)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd ayanakoji/backend && python -m pytest tests/test_course_skill_fields.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ayanakoji/backend/app/courses/models.py ayanakoji/backend/tests/test_course_skill_fields.py
git commit -m "feat(models): Course.skill_source/skill_scores/pending_modules"
```

---

### Task 3.2: Guarded SQLite column migration for existing `athenaeum.db`

`SQLModel.create_all` does not ALTER existing tables, so a running dev DB needs the three new columns added. Add an idempotent migration that runs at startup.

**Files:**
- Read first: `ayanakoji/backend/app/db.py` (find `init_db`)
- Modify: `ayanakoji/backend/app/db.py`
- Test: `ayanakoji/backend/tests/test_course_column_migration.py`

- [ ] **Step 1: Read `db.py` to locate `init_db` and the engine accessor**

Run: `cd ayanakoji/backend && grep -n "def init_db\|engine\|create_all\|def get_engine" app/db.py`
Expected: note the engine object name and where `init_db` calls `create_all`.

- [ ] **Step 2: Write the failing test**

```python
# ayanakoji/backend/tests/test_course_column_migration.py
from __future__ import annotations

from sqlalchemy import create_engine, text

from app.db import ensure_course_columns


def test_ensure_course_columns_adds_missing_columns_idempotently() -> None:
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        # A pre-existing 'course' table missing the new columns.
        conn.execute(text("CREATE TABLE course (id TEXT PRIMARY KEY, persona_id TEXT, chat_name TEXT)"))
    ensure_course_columns(engine)
    ensure_course_columns(engine)  # second run must be a no-op, not an error
    with engine.begin() as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(course)"))}
    assert {"skill_source", "skill_scores", "pending_modules"} <= cols
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd ayanakoji/backend && python -m pytest tests/test_course_column_migration.py -v`
Expected: FAIL — `ImportError: cannot import name 'ensure_course_columns'`.

- [ ] **Step 4: Implement**

In `app/db.py`, add this function (SQLite-specific, additive, safe to re-run) and call it from `init_db` right after `create_all`:

```python
from sqlalchemy import text  # add to imports if not present
from sqlalchemy.engine import Engine  # add to imports if not present


# New nullable/defaulted columns added after the initial release. SQLite's
# create_all never ALTERs an existing table, so add any missing ones in place.
_COURSE_ADDED_COLUMNS: dict[str, str] = {
    "skill_source": "TEXT",
    "skill_scores": "JSON",
    "pending_modules": "JSON",
}


def ensure_course_columns(engine: Engine) -> None:
    """Add any missing additive columns to the `course` table (idempotent)."""
    with engine.begin() as conn:
        existing = {row[1] for row in conn.execute(text("PRAGMA table_info(course)"))}
        for name, sql_type in _COURSE_ADDED_COLUMNS.items():
            if name not in existing:
                conn.execute(text(f"ALTER TABLE course ADD COLUMN {name} {sql_type}"))
```

In `init_db` (wherever `create_all` for the workspace tables is called), add after it:

```python
    ensure_course_columns(engine)
```
(Use the actual engine variable name found in Step 1.)

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd ayanakoji/backend && python -m pytest tests/test_course_column_migration.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add ayanakoji/backend/app/db.py ayanakoji/backend/tests/test_course_column_migration.py
git commit -m "feat(db): idempotent migration adding course skill/pending columns"
```

---

## Phase 4 — Answer agent gating + orchestrator threading

### Task 4.1: Skill gate in `answer_study_plan`; `AgentReply.skill_gate`; skill into both build paths

**Files:**
- Modify: `ayanakoji/backend/app/agent/answer.py`
- Modify: `ayanakoji/backend/app/agent/scheduler.py` (thread `skill_scores` through `SchedulerContext` → `build_plan_from_args`)
- Test: `ayanakoji/backend/tests/test_answer_skill_gate.py`

- [ ] **Step 1: Write the failing test**

```python
# ayanakoji/backend/tests/test_answer_skill_gate.py
"""answer_study_plan asks the skill gate before pace, and previews after pace."""

from __future__ import annotations

from datetime import date

from app.agent.answer import answer_study_plan
from app.agent.contracts import Pace
from app.config import get_settings


def _offline_settings():
    s = get_settings()
    # Tests run offline; confirm the deterministic path.
    assert s.llm_offline
    return s


def test_no_skill_source_returns_skill_gate_not_pace() -> None:
    reply = answer_study_plan(
        "build me a plan", persona_id="emp-1", catalog_id="de-c01", taken=[],
        pace=None, skill_source=None, skill_scores=None,
        start_date=date(2026, 6, 15), settings=_offline_settings(),
    )
    assert reply.skill_gate is not None
    assert reply.skill_gate.catalog_id == "de-c01"
    assert reply.pace_request is None
    assert reply.plan is None


def test_skill_done_no_pace_returns_pace_request() -> None:
    reply = answer_study_plan(
        "build me a plan", persona_id="emp-1", catalog_id="de-c01", taken=[],
        pace=None, skill_source="assessment", skill_scores={"de-c01-m01": 1.0},
        start_date=date(2026, 6, 15), settings=_offline_settings(),
    )
    assert reply.skill_gate is None
    assert reply.pace_request is not None
    assert reply.plan is None


def test_skill_and_pace_builds_preview_with_awaiting_approval() -> None:
    reply = answer_study_plan(
        "build me a plan", persona_id="emp-1", catalog_id="de-c01", taken=[],
        pace=Pace.NORMAL, skill_source="assessment",
        skill_scores={"de-c01-m01": 1.0}, start_date=date(2026, 6, 15),
        settings=_offline_settings(),
    )
    assert reply.skill_gate is None and reply.pace_request is None
    assert reply.plan is not None
    assert reply.plan.awaiting_approval is True
```

> Replace `persona_id="emp-1"` and `catalog_id="de-c01"` with a real seeded persona employee_id and a real catalog course id if those differ (check `app/workiq` seed data and the catalog json). The test asserts structure, not specific personas.

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ayanakoji/backend && python -m pytest tests/test_answer_skill_gate.py -v`
Expected: FAIL — `answer_study_plan() got an unexpected keyword argument 'skill_source'`.

- [ ] **Step 3: Implement — `AgentReply.skill_gate` + import + prompt constant**

In `answer.py`, add to the `from app.agent.contracts import (...)` block (after `SuggestionEvent`, line 35): `SkillGateRequestEvent,`.

Add to `AgentReply` (after `pace_request`, line 65):

```python
    skill_gate: SkillGateRequestEvent | None = None
```

Find the existing `_PACE_PROMPT` constant (grep for it) and add next to it:

```python
_SKILL_PROMPT = (
    "Are you new to this topic, or do you want a quick skill check so I can tailor the time "
    "per module?"
)
```

- [ ] **Step 4: Implement — insert the skill gate + thread skill_scores**

In `answer_study_plan`, add the two new parameters to the signature (after `pace: Pace | None = None`, line 1069):

```python
    skill_source: str | None = None,
    skill_scores: dict[str, float] | None = None,
```

Immediately after the `steps = [...]` course/persona lookup block (after line 1099, before the `# HITL gate: ask the pace` block) insert the skill gate:

```python
    # Skill gate (before pace): without a skill source we don't know how to weight
    # each module's time, so ask fresher vs. skill check first.
    if skill_source is None:
        steps.append(
            TraceStep(
                label="Skill gate",
                passed=False,
                detail="No skill check yet — asking fresher vs. quick check",
            )
        )
        return AgentReply(
            telemetry=_answer_telemetry(
                summary="Asked the skill-gap check before pacing",
                reasoning="Course chosen but no skill check; skill gates module weighting.",
                route=Route.STUDY_PLAN,
                sources=[],
                model="offline" if settings.llm_offline else None,
                tier=None,
                steps=steps,
            ),
            tokens=_offline_stream(
                f"Before we pace {course.title}, are you new to this topic or want a quick skill check?"
            ),
            skill_gate=SkillGateRequestEvent(
                catalog_id=course.id, title=course.title, prompt=_SKILL_PROMPT
            ),
        )
```

Pass `skill_scores` to the **offline** `build_study_plan` call (line 1136-1148) by adding `skill_scores=skill_scores,` before `settings=settings,`.

For the **offline** preview return (the `return AgentReply(... plan=plan)` at lines 1217-1229), mark it as a preview. Replace `plan=plan,` with `plan=plan.model_copy(update={"awaiting_approval": True}),`.

For the **online** path, pass skill into the scheduler context. In the `ctx = SchedulerContext(...)` construction (lines 1240-1255) add `skill_scores=skill_scores,` as a field. Then at the **online** preview return (the `return AgentReply(...)` that sets `plan=final_plan` near line 1289), change it to `plan=final_plan.model_copy(update={"awaiting_approval": True}),`.

- [ ] **Step 5: Implement — thread skill_scores in `scheduler.py`**

In `scheduler.py`, add to `SchedulerContext` (after `max_session_minutes`, line 150):

```python
    skill_scores: dict[str, float] | None = None
```

In `build_plan_from_args`, pass it to `build_study_plan` (in the call at lines 227-242) by adding `skill_scores=ctx.skill_scores,` before `settings=settings,`.

- [ ] **Step 6: Run the test to verify it passes**

Run: `cd ayanakoji/backend && python -m pytest tests/test_answer_skill_gate.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add ayanakoji/backend/app/agent/answer.py ayanakoji/backend/app/agent/scheduler.py ayanakoji/backend/tests/test_answer_skill_gate.py
git commit -m "feat(answer): skill gate before pace; skill_scores into both plan paths; preview flag"
```

---

### Task 4.2: Thread `skill_source`/`skill_scores` through `run_pipeline` and `_dispatch`; yield `skill_gate`

**Files:**
- Modify: `ayanakoji/backend/app/agent/orchestrator.py`
- Test: `ayanakoji/backend/tests/test_pipeline_skill_gate.py`

- [ ] **Step 1: Write the failing test**

```python
# ayanakoji/backend/tests/test_pipeline_skill_gate.py
from __future__ import annotations

from datetime import date

from app.agent.contracts import SkillGateRequestEvent
from app.agent.orchestrator import run_pipeline
from app.agent.state import CourseState


def test_pipeline_emits_skill_gate_in_chosen_state() -> None:
    events = list(
        run_pipeline(
            "build me a study plan",
            persona_id="emp-1",
            catalog_id="de-c01",
            skill_source=None,
            skill_scores=None,
            start_date=date(2026, 6, 15),
            course_state=CourseState.CHOSEN,
        )
    )
    assert any(isinstance(e, SkillGateRequestEvent) for e in events)
```

> Use a real seeded persona/catalog id as in Task 4.1. The router must route "build me a study plan" to STUDY_PLAN offline; if the offline router needs a linked course to do so, the `catalog_id` argument here satisfies that.

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ayanakoji/backend && python -m pytest tests/test_pipeline_skill_gate.py -v`
Expected: FAIL — `run_pipeline() got an unexpected keyword argument 'skill_source'`.

- [ ] **Step 3: Implement**

In `orchestrator.py`:

Add `SkillGateRequestEvent,` to the `from app.agent.contracts import (...)` block (after `RouteDecision`, line 47 area).

Add two parameters to `run_pipeline` (after `pace: Pace | None = None,`, line 155):

```python
    skill_source: str | None = None,
    skill_scores: dict[str, float] | None = None,
```

Add the same two parameters to `_dispatch` (after `pace: Pace | None,`, line 95):

```python
    skill_source: str | None,
    skill_scores: dict[str, float] | None,
```

In `_dispatch`, pass them to `answer_study_plan` (the `Route.STUDY_PLAN` branch, lines 122-137) by adding before `router=router,`:

```python
            skill_source=skill_source,
            skill_scores=skill_scores,
```

In `run_pipeline`, pass them into the `_dispatch(...)` call (lines 216-234) by adding after `pace=pace,`:

```python
                skill_source=skill_source,
                skill_scores=skill_scores,
```

Yield the skill gate after the tokens stream and before the pace gate. Insert before the `# ── Pace HITL gate` block (before line 253):

```python
    # ── Skill-gap HITL gate (ask before pacing) ───────────────────────────────
    if reply.skill_gate is not None:
        yield reply.skill_gate
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd ayanakoji/backend && python -m pytest tests/test_pipeline_skill_gate.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ayanakoji/backend/app/agent/orchestrator.py ayanakoji/backend/tests/test_pipeline_skill_gate.py
git commit -m "feat(orchestrator): thread skill_source/skill_scores; yield skill gate event"
```

---

## Phase 5 — Courses router: stage instead of persist; approve endpoint

### Task 5.1: `_stream_turn` threads skill fields, stages `pending_modules`, captures `skill_gate` meta

**Files:**
- Modify: `ayanakoji/backend/app/courses/router.py`
- Test: `ayanakoji/backend/tests/test_stream_turn_preview.py` (and fix existing stream tests)

- [ ] **Step 1: Write the failing test**

```python
# ayanakoji/backend/tests/test_stream_turn_preview.py
"""The chat path stages a plan into pending_modules; it never writes CourseModule."""

from __future__ import annotations

import json

from app.courses.repository import CourseRepository
from app.db import session_scope


def _collect(course_id: str, text: str) -> list[dict]:
    from app.courses.router import _stream_turn

    events = []
    for chunk in _stream_turn(course_id, text):
        line = chunk.strip()
        if line.startswith("data:"):
            events.append(json.loads(line[5:].strip()))
    return events


def test_plan_turn_stages_pending_modules_without_persisting(seeded_course_paced):
    """seeded_course_paced: a course linked to de-c01 with skill_source+pace set, no modules."""
    course_id = seeded_course_paced
    events = _collect(course_id, "build me a study plan for this course")
    assert any(e["type"] == "plan" for e in events)
    with session_scope() as s:
        repo = CourseRepository(s)
        course = repo.get(course_id)
        assert course.pending_modules, "preview should stage pending_modules"
        assert repo.list_modules(course_id) == [], "no CourseModule rows until approval"
```

> Add a `seeded_course_paced` fixture to `tests/conftest.py` that creates a Course with `catalog_id="de-c01"`, `skill_source="assessment"`, `skill_scores={...}`, `pace="normal"`, and returns its id. Follow the existing course-creation fixtures already in `conftest.py`.

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ayanakoji/backend && python -m pytest tests/test_stream_turn_preview.py -v`
Expected: FAIL — pending_modules empty / CourseModule rows present (old behavior persists modules).

- [ ] **Step 3: Implement — read skill fields + thread + derive state**

In `router.py`, in `_stream_turn`, after the `exam_date = ...` line (line 430) add:

```python
        skill_source = current.skill_source
        skill_scores = current.skill_scores or None
```

Update the `derive_course_state(...)` call (lines 436-441) to pass `skill_source`:

```python
        course_state = derive_course_state(
            catalog_id=current.catalog_id,
            pace=pace,
            skill_source=skill_source,
            module_count=len(existing_modules),
            completed_count=sum(1 for m in existing_modules if m.completed),
        )
```

Add a meta collector next to the others (after `meta_pace`, line 449):

```python
        meta_skill_gate: dict[str, object] | None = None
```

Pass the skill fields into `run_pipeline(...)` (the call at lines 465-482) by adding after `pace=pace,`:

```python
                skill_source=skill_source,
                skill_scores=skill_scores,
```

In the event loop (lines 483-506), capture the skill gate. Add a branch after the `elif event.type == "pace_request":` branch (line 497-498):

```python
                elif event.type == "skill_gate_request":
                    meta_skill_gate = payload
```

- [ ] **Step 4: Implement — stage pending_modules instead of persisting; add to meta**

In the `finally` block, replace the module-persist line (lines 510-511):

```python
            if plan_modules is not None:
                stream_repo.replace_modules(current.id, plan_modules)
```
with:

```python
            if plan_modules is not None:
                # Stage the previewed plan; it becomes real modules only on approval.
                current.pending_modules = plan_modules
                stream_repo.save(current)
```

In the `meta` dict built for the assistant turn (lines 518-524) add the skill gate key:

```python
                meta: dict[str, object] = {
                    "phases": phases,
                    "suggestion": meta_suggestion,
                    "plan": meta_plan,
                    "pace_request": meta_pace,
                    "skill_gate": meta_skill_gate,
                    "new_chat": meta_new_chat,
                }
```

- [ ] **Step 5: Run the new test + fix existing stream/persist tests**

Run: `cd ayanakoji/backend && python -m pytest tests/test_stream_turn_preview.py -v`
Expected: PASS.

Run the broader suite to find tests that assumed a plan turn persists modules:
Run: `cd ayanakoji/backend && python -m pytest tests/ -k "stream or plan or module or course" -v`
Expected: any test asserting `list_modules(...)` is non-empty right after a plan turn now FAILS. Update each to call the approve endpoint (Task 5.2) before asserting persisted modules, or assert on `pending_modules` for the preview. Re-run until green.

- [ ] **Step 6: Commit**

```bash
git add ayanakoji/backend/app/courses/router.py ayanakoji/backend/tests/test_stream_turn_preview.py ayanakoji/backend/tests/conftest.py
git commit -m "feat(courses): chat path stages pending_modules (preview); capture skill_gate meta"
```

---

### Task 5.2: `POST /plan/approve` promotes the staged plan

**Files:**
- Modify: `ayanakoji/backend/app/courses/router.py`
- Test: `ayanakoji/backend/tests/test_plan_approve.py`

- [ ] **Step 1: Write the failing test**

```python
# ayanakoji/backend/tests/test_plan_approve.py
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app  # adjust import to the FastAPI app factory/instance
from app.courses.repository import CourseRepository
from app.db import session_scope

client = TestClient(app)


def test_approve_promotes_pending_modules(seeded_course_with_pending):
    """seeded_course_with_pending: course with pending_modules staged, no CourseModule rows."""
    course_id = seeded_course_with_pending
    resp = client.post(f"/api/courses/{course_id}/plan/approve")
    assert resp.status_code == 200
    modules = resp.json()
    assert len(modules) >= 1
    with session_scope() as s:
        repo = CourseRepository(s)
        assert repo.list_modules(course_id), "modules persisted after approval"
        assert repo.get(course_id).pending_modules == [], "staging cleared after approval"


def test_approve_without_pending_is_409(seeded_course_paced):
    resp = client.post(f"/api/courses/{seeded_course_paced}/plan/approve")
    assert resp.status_code == 409
```

> Add a `seeded_course_with_pending` fixture: a Course with `pending_modules` set to a small list of valid module dicts (`module_id`, `title`, `sequence`, `estimated_minutes`, `complete_before`, `scheduled`). Mirror the shape `replace_modules` consumes.

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ayanakoji/backend && python -m pytest tests/test_plan_approve.py -v`
Expected: FAIL — 404/405 (route does not exist).

- [ ] **Step 3: Implement**

In `router.py`, add after `set_pace` (after line 537):

```python
@router.post(
    "/{course_id}/plan/approve",
    response_model=list[ModuleRead],
    summary="Approve the staged study plan: write its modules + deadlines",
)
def approve_plan(course_id: str, session: SessionDep) -> list[ModuleRead]:
    """Promote the previewed plan (``Course.pending_modules``) to real modules.

    This is the only path that writes ``CourseModule`` rows / deadlines — the chat
    path stages a preview and waits for this explicit approval (the learner's
    'put it on my schedule' confirmation). Idempotent staging is then cleared.
    """
    repo = CourseRepository(session)
    course = _require(repo.get(course_id), course_id)
    pending = course.pending_modules or []
    if not pending:
        raise HTTPException(status_code=409, detail="No plan to approve — build one first.")
    repo.replace_modules(course_id, pending)
    course.pending_modules = []
    repo.save(course)
    return _to_module_read(repo.list_modules(course_id))
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd ayanakoji/backend && python -m pytest tests/test_plan_approve.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ayanakoji/backend/app/courses/router.py ayanakoji/backend/tests/test_plan_approve.py
git commit -m "feat(courses): POST /plan/approve promotes staged plan to modules"
```

---

## Phase 6 — Skill REST endpoints (new `skill_router.py`) + schemas

### Task 6.1: `AssessmentRepository.get_choice_question_by_id`

Grading re-fetches each bank question by its authored id (the quiz is sampled fresh and not persisted), so add a by-id lookup.

**Files:**
- Modify: `ayanakoji/backend/app/assessments/repository.py`
- Test: `ayanakoji/backend/tests/test_bank_choice_by_id.py`

- [ ] **Step 1: Read the repository to confirm imports + model name**

Run: `cd ayanakoji/backend && grep -n "class AssessmentRepository\|BankChoiceQuestion\|def get_bank\|def choice_questions\|def get_llm_question_by_id" app/assessments/repository.py`
Expected: confirm `BankChoiceQuestion` is imported and the session attribute name (e.g. `self._session`).

- [ ] **Step 2: Write the failing test**

```python
# ayanakoji/backend/tests/test_bank_choice_by_id.py
from __future__ import annotations

from app.assessments.engine import session_scope as assessment_session_scope
from app.assessments.repository import AssessmentRepository


def test_get_choice_question_by_id_round_trips() -> None:
    # de-c01-m01-c01 is a seeded authored bank choice id.
    with assessment_session_scope() as s:
        repo = AssessmentRepository(s)
        q = repo.get_choice_question_by_id("de-c01-m01-c01")
        assert q is not None
        assert q.module_id == "de-c01-m01"
        assert q.correct_answers  # non-empty
```

> Replace `de-c01-m01-c01` with a real authored id from `ayanakoji/assessments/banks/de-c01/de-c01-m01.json` if it differs. If the assessment session helper is named differently (Step 1), use that.

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd ayanakoji/backend && python -m pytest tests/test_bank_choice_by_id.py -v`
Expected: FAIL — `AttributeError: 'AssessmentRepository' object has no attribute 'get_choice_question_by_id'`.

- [ ] **Step 4: Implement**

In `app/assessments/repository.py`, add (next to `get_llm_question_by_id`):

```python
    def get_choice_question_by_id(self, question_id: str) -> BankChoiceQuestion | None:
        """Fetch one authored bank choice question by its id (for skill grading)."""
        return self._session.get(BankChoiceQuestion, question_id)
```
(Ensure `BankChoiceQuestion` is in the module imports.)

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd ayanakoji/backend && python -m pytest tests/test_bank_choice_by_id.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add ayanakoji/backend/app/assessments/repository.py ayanakoji/backend/tests/test_bank_choice_by_id.py
git commit -m "feat(assessments): get_choice_question_by_id for skill grading"
```

---

### Task 6.2: Skill-flow schemas

**Files:**
- Modify: `ayanakoji/backend/app/courses/schemas.py`
- Test: covered by Task 6.3's endpoint tests (no standalone test).

- [ ] **Step 1: Implement the DTOs**

In `app/courses/schemas.py`, append:

```python
# ── Skill-gap check (pre-study, choice-only, feeds scheduling) ────────────────

QUESTIONS_PER_MODULE = 4


class SkillCheckQuestion(BaseModel):
    """One sampled bank choice question — correct answers withheld."""

    id: str = Field(description="Authored bank question id, e.g. 'de-c01-m01-c03'")
    prompt: str
    kind: str  # "mcq" | "msq"
    choices: list[str]


class SkillCheckModule(BaseModel):
    """One tab of the skill check: a module and its sampled questions."""

    module_id: str
    title: str
    questions: list[SkillCheckQuestion]


class SkillCheckRead(BaseModel):
    """The full multi-tab skill check for a course."""

    catalog_id: str
    title: str
    modules: list[SkillCheckModule]


class SkillAnswer(BaseModel):
    """One submitted answer keyed by the authored bank question id."""

    module_id: str
    question_id: str
    selections: list[str]


class SkillGradeBody(BaseModel):
    answers: list[SkillAnswer]


class SkillModuleScore(BaseModel):
    module_id: str
    title: str
    correct: int
    total: int
    fraction: float = Field(ge=0, le=1, description="correct / total (0..1)")


class SkillResultRead(BaseModel):
    """Per-module + overall skill score; ``fresher`` marks the no-quiz path."""

    catalog_id: str
    overall_fraction: float = Field(ge=0, le=1)
    modules: list[SkillModuleScore]
    fresher: bool = False


class SetDeadline(BaseModel):
    """Set or clear the optional target deadline (ISO date)."""

    deadline: str | None = Field(default=None, description="ISO date YYYY-MM-DD, or null to clear")
```

- [ ] **Step 2: Commit**

```bash
git add ayanakoji/backend/app/courses/schemas.py
git commit -m "feat(schemas): skill-check DTOs"
```

---

### Task 6.3: `skill_router.py` — start, grade, fresher, deadline

**Files:**
- Create: `ayanakoji/backend/app/courses/skill_router.py`
- Modify: wherever routers are registered (find with grep) to `include_router(skill_router.router)`
- Test: `ayanakoji/backend/tests/test_skill_endpoints.py`

- [ ] **Step 1: Find where routers are registered**

Run: `cd ayanakoji/backend && grep -rn "include_router" app`
Expected: the module (likely `app/main.py`) that registers `courses.router`, `assessment_router.router`, etc.

- [ ] **Step 2: Write the failing test**

```python
# ayanakoji/backend/tests/test_skill_endpoints.py
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app  # adjust to the actual app import
from app.courses.repository import CourseRepository
from app.db import session_scope

client = TestClient(app)


def test_start_returns_four_questions_per_module(seeded_course_chosen):
    """seeded_course_chosen: a course linked to de-c01, no skill source yet."""
    course_id = seeded_course_chosen
    resp = client.post(f"/api/courses/{course_id}/skill/start")
    assert resp.status_code == 200
    body = resp.json()
    assert body["catalog_id"] == "de-c01"
    assert len(body["modules"]) >= 1
    for mod in body["modules"]:
        assert 1 <= len(mod["questions"]) <= 4
        for q in mod["questions"]:
            assert q["kind"] in ("mcq", "msq")
            assert "correct_answers" not in q  # never leaked


def test_grade_stores_scores_and_appends_message(seeded_course_chosen):
    course_id = seeded_course_chosen
    start = client.post(f"/api/courses/{course_id}/skill/start").json()
    answers = []
    for mod in start["modules"]:
        for q in mod["questions"]:
            answers.append({"module_id": mod["module_id"], "question_id": q["id"], "selections": []})
    resp = client.post(f"/api/courses/{course_id}/skill/grade", json={"answers": answers})
    assert resp.status_code == 200
    result = resp.json()
    assert 0.0 <= result["overall_fraction"] <= 1.0
    with session_scope() as s:
        course = CourseRepository(s).get(course_id)
        assert course.skill_source == "assessment"
        assert course.skill_scores  # populated
        # The score landed in the transcript with a skill_result meta.
        assert any((m.get("meta") or {}).get("skill_result") for m in course.messages)


def test_fresher_sets_zero_scores_for_every_module(seeded_course_chosen):
    course_id = seeded_course_chosen
    resp = client.post(f"/api/courses/{course_id}/skill/fresher")
    assert resp.status_code == 200
    with session_scope() as s:
        course = CourseRepository(s).get(course_id)
        assert course.skill_source == "fresher"
        assert course.skill_scores and all(v == 0.0 for v in course.skill_scores.values())


def test_deadline_sets_and_clears(seeded_course_chosen):
    course_id = seeded_course_chosen
    client.post(f"/api/courses/{course_id}/skill/fresher")
    client.post(f"/api/courses/{course_id}/deadline", json={"deadline": "2026-08-01"})
    with session_scope() as s:
        assert CourseRepository(s).get(course_id).plan_exam_date == "2026-08-01"
    client.post(f"/api/courses/{course_id}/deadline", json={"deadline": None})
    with session_scope() as s:
        assert CourseRepository(s).get(course_id).plan_exam_date is None
```

> Add a `seeded_course_chosen` fixture: a Course linked to `de-c01` (set `catalog_id`, `status=1`), no `skill_source`. Reuse the catalog id your seed data actually has.

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd ayanakoji/backend && python -m pytest tests/test_skill_endpoints.py -v`
Expected: FAIL — 404 (routes not registered).

- [ ] **Step 4: Implement `skill_router.py`**

Create `ayanakoji/backend/app/courses/skill_router.py`:

```python
"""Skill-gap check endpoints: the pre-study, choice-only quiz that weights time.

Distinct from the post-completion assessment sessions in ``assessment_router``:
this samples 4 choice questions per module across the whole course, grades them
instantly by set-match, stores per-module fractions on the course, and writes a
``skill_result`` message into the transcript so the score survives reload. The
fresher path is the same code with a score of 0 on every module.
"""

from __future__ import annotations

import random
from collections import defaultdict
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.agent.study_plan import course_modules
from app.assessments.engine import get_session as get_assessment_session
from app.assessments.repository import AssessmentRepository
from app.catalog.loader import default_catalog_path
from app.catalog.loader import get_course as get_catalog_course
from app.config import get_settings
from app.courses.repository import CourseRepository
from app.courses.schemas import (
    QUESTIONS_PER_MODULE,
    SetDeadline,
    SkillCheckModule,
    SkillCheckQuestion,
    SkillCheckRead,
    SkillGradeBody,
    SkillModuleScore,
    SkillResultRead,
)
from app.db import get_session

router = APIRouter(prefix="/api/courses", tags=["skill"])

SessionDep = Annotated[Session, Depends(get_session)]
AssessmentSessionDep = Annotated[Session, Depends(get_assessment_session)]


def _require_linked(repo: CourseRepository, course_id: str):
    course = repo.get(course_id)
    if course is None:
        raise HTTPException(status_code=404, detail=f"course '{course_id}' not found")
    if not course.catalog_id:
        raise HTTPException(status_code=409, detail="Choose a course before the skill check.")
    return course


def _modules_for(catalog_id: str):
    settings = get_settings()
    path = str(settings.athenaeum_catalog_path or default_catalog_path())
    return course_modules(path, catalog_id)


@router.post("/{course_id}/skill/start", response_model=SkillCheckRead, summary="Sample the skill check")
def start_skill_check(
    course_id: str, session: SessionDep, asmtsession: AssessmentSessionDep
) -> SkillCheckRead:
    """Sample up to 4 choice questions per module from the authored banks."""
    repo = CourseRepository(session)
    course = _require_linked(repo, course_id)
    a_repo = AssessmentRepository(asmtsession)
    catalog = get_catalog_course(course.catalog_id)
    out: list[SkillCheckModule] = []
    for m in _modules_for(course.catalog_id):
        choice_bank = []
        for bid in a_repo.assessment_ids_for_module(m.module_id):
            bank = a_repo.get_bank(bid)
            if bank and bank.kind == "choices":
                choice_bank = a_repo.choice_questions(bank.id)
                break
        sample = random.sample(choice_bank, min(QUESTIONS_PER_MODULE, len(choice_bank)))
        out.append(
            SkillCheckModule(
                module_id=m.module_id,
                title=m.title,
                questions=[
                    SkillCheckQuestion(id=q.id, prompt=q.prompt, kind=q.kind, choices=list(q.choices))
                    for q in sample
                ],
            )
        )
    return SkillCheckRead(
        catalog_id=course.catalog_id,
        title=catalog.title if catalog else course.catalog_id,
        modules=out,
    )


@router.post("/{course_id}/skill/grade", response_model=SkillResultRead, summary="Grade the skill check")
def grade_skill_check(
    course_id: str, body: SkillGradeBody, session: SessionDep, asmtsession: AssessmentSessionDep
) -> SkillResultRead:
    """Set-match grade per module, store fractions, and post a transcript message."""
    repo = CourseRepository(session)
    course = _require_linked(repo, course_id)
    a_repo = AssessmentRepository(asmtsession)
    title_by_id = {m.module_id: m.title for m in _modules_for(course.catalog_id)}

    by_module: dict[str, list] = defaultdict(list)
    for ans in body.answers:
        by_module[ans.module_id].append(ans)

    scores: dict[str, float] = {}
    module_scores: list[SkillModuleScore] = []
    for module_id, answers in by_module.items():
        correct = 0
        for ans in answers:
            bank_q = a_repo.get_choice_question_by_id(ans.question_id)
            if bank_q is not None and set(ans.selections) == set(bank_q.correct_answers):
                correct += 1
        total = len(answers)
        fraction = round(correct / total, 4) if total else 0.0
        scores[module_id] = fraction
        module_scores.append(
            SkillModuleScore(
                module_id=module_id,
                title=title_by_id.get(module_id, module_id),
                correct=correct,
                total=total,
                fraction=fraction,
            )
        )

    course.skill_source = "assessment"
    course.skill_scores = scores
    repo.save(course)

    overall = round(sum(scores.values()) / len(scores), 4) if scores else 0.0
    result = SkillResultRead(catalog_id=course.catalog_id, overall_fraction=overall, modules=module_scores)
    summary = (
        f"Here's how you did across {len(module_scores)} modules "
        f"({round(overall * 100)}% overall). I'll lighten the modules you've got down and give a "
        "little more room where it's thinner. Do you have a target deadline?"
    )
    repo.append_message(course, role="assistant", content=summary, meta={"skill_result": result.model_dump(mode="json")})
    return result


@router.post("/{course_id}/skill/fresher", response_model=SkillResultRead, summary="Skip the check as a fresher")
def skill_fresher(course_id: str, session: SessionDep) -> SkillResultRead:
    """Mark the learner a fresher: score 0 on every module (same correction path)."""
    repo = CourseRepository(session)
    course = _require_linked(repo, course_id)
    scores = {m.module_id: 0.0 for m in _modules_for(course.catalog_id)}
    course.skill_source = "fresher"
    course.skill_scores = scores
    repo.save(course)
    result = SkillResultRead(catalog_id=course.catalog_id, overall_fraction=0.0, modules=[], fresher=True)
    summary = (
        "No problem, I'll treat this as a fresh start and give each module a little more room. "
        "Do you have a target deadline?"
    )
    repo.append_message(course, role="assistant", content=summary, meta={"skill_result": result.model_dump(mode="json")})
    return result


@router.post("/{course_id}/deadline", status_code=204, summary="Set or clear the target deadline")
def set_deadline(course_id: str, body: SetDeadline, session: SessionDep) -> None:
    """Persist the optional target deadline onto ``plan_exam_date`` (drives overrun warning)."""
    repo = CourseRepository(session)
    course = repo.get(course_id)
    if course is None:
        raise HTTPException(status_code=404, detail=f"course '{course_id}' not found")
    if body.deadline:
        try:
            date.fromisoformat(body.deadline)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="deadline must be ISO YYYY-MM-DD") from exc
        course.plan_exam_date = body.deadline
    else:
        course.plan_exam_date = None
    repo.save(course)
```

Register it where the other routers are included (from Step 1), e.g. in `app/main.py`:

```python
from app.courses import skill_router as courses_skill_router
...
app.include_router(courses_skill_router.router)
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd ayanakoji/backend && python -m pytest tests/test_skill_endpoints.py -v`
Expected: PASS.

- [ ] **Step 6: Run the whole backend suite**

Run: `cd ayanakoji/backend && python -m pytest tests/ -q`
Expected: green. Fix any remaining fallout from the persist→stage change (Task 5.1, Step 5).

- [ ] **Step 7: Commit**

```bash
git add ayanakoji/backend/app/courses/skill_router.py ayanakoji/backend/app/main.py ayanakoji/backend/tests/test_skill_endpoints.py ayanakoji/backend/tests/conftest.py
git commit -m "feat(courses): skill-check endpoints (start/grade/fresher/deadline)"
```

---

## Phase 7 — Frontend

> All paths are under `ayanakoji/frontend/`. Components are client components following the existing `pace-chooser.tsx` / `study-plan-card.tsx` patterns: `"use client"`, framer-motion, lucide icons, the local `@/components/ui/button`. Per `AGENTS.md`, do not reach for unfamiliar Next.js APIs — these are plain React + the one `next/link` already used in the codebase.

### Task 7.1: API client — types, event handler, calls

**Files:**
- Modify: `ayanakoji/frontend/src/lib/api.ts`
- Test: `ayanakoji/frontend/src/lib/api.test.ts` (add a dispatch case test if a test file exists; else skip the unit test and rely on Task 7.6 integration)

- [ ] **Step 1: Add types + extend existing models**

In `api.ts`, extend `ModulePlan` (lines 276-284) with the breakdown:

```typescript
export interface ModulePlan {
  module_id: string;
  title: string;
  sequence: number;
  estimated_minutes: number;
  base_minutes: number;
  pace_minutes: number;
  skill_delta: number;
  scheduled: ScheduledBlock[];
  complete_before: string;
  objectives: string[];
}
```

Extend `StudyPlan` (lines 286-298) with the new fields:

```typescript
export interface StudyPlan {
  catalog_id: string;
  title: string;
  cert: string;
  pace: Pace;
  weekly_study_hours: number;
  total_hours: number;
  total_base_hours: number;
  total_pace_hours: number;
  weeks: number;
  start_date: string;
  modules: ModulePlan[];
  sessions: StudySession[];
  capacity_reason: string;
  balloon_warning: string | null;
  awaiting_approval: boolean;
}
```

> This also adds `balloon_warning` (always sent by the backend, previously untyped) so the LOUD overrun warning in Task 7.5 type-checks.

Add the skill types after `PaceRequest` (after line 305):

```typescript
export interface SkillGateRequest {
  catalog_id: string;
  title: string;
  prompt: string;
  options: string[]; // ["fresher", "assessment"]
}

export interface SkillCheckQuestion {
  id: string;
  prompt: string;
  kind: "mcq" | "msq";
  choices: string[];
}

export interface SkillCheckModule {
  module_id: string;
  title: string;
  questions: SkillCheckQuestion[];
}

export interface SkillCheck {
  catalog_id: string;
  title: string;
  modules: SkillCheckModule[];
}

export interface SkillModuleScore {
  module_id: string;
  title: string;
  correct: number;
  total: number;
  fraction: number;
}

export interface SkillResult {
  catalog_id: string;
  overall_fraction: number;
  modules: SkillModuleScore[];
  fresher: boolean;
}

export interface SkillAnswer {
  module_id: string;
  question_id: string;
  selections: string[];
}
```

Extend `MessageMeta` (lines 75-81):

```typescript
export interface MessageMeta {
  phases?: PhaseTelemetry[];
  suggestion?: Suggestion | null;
  plan?: StudyPlan | null;
  pace_request?: PaceRequest | null;
  skill_gate?: SkillGateRequest | null;
  skill_result?: SkillResult | null;
  new_chat?: NewChat | null;
}
```

- [ ] **Step 2: Add the pipeline event + handler**

Extend the `PipelineEvent` union (lines 307-322) with a skill-gate variant:

```typescript
  | {
      type: "skill_gate_request";
      catalog_id: string;
      title: string;
      prompt: string;
      options: string[];
    }
```

Extend `StreamHandlers` (lines 324-334):

```typescript
  onSkillGate?: (request: SkillGateRequest) => void;
```

Add a `case` in `dispatchEvent` (after the `pace_request` case, line 404):

```typescript
    case "skill_gate_request":
      handlers.onSkillGate?.({
        catalog_id: event.catalog_id,
        title: event.title,
        prompt: event.prompt,
        options: event.options,
      });
      break;
```

- [ ] **Step 3: Add the client calls**

After `setPace` (after line 439) add:

```typescript
/** Sample the multi-tab skill check (4 questions per module). */
export function startSkillCheck(courseId: string): Promise<SkillCheck> {
  return requestJson<SkillCheck>(`/api/courses/${courseId}/skill/start`, {
    method: "POST",
  });
}

/** Grade the skill check; stores per-module scores and posts a transcript message. */
export function gradeSkillCheck(
  courseId: string,
  answers: SkillAnswer[],
): Promise<SkillResult> {
  return requestJson<SkillResult>(`/api/courses/${courseId}/skill/grade`, {
    method: "POST",
    body: JSON.stringify({ answers }),
  });
}

/** Skip the check as a fresher (score 0 on every module). */
export function skillFresher(courseId: string): Promise<SkillResult> {
  return requestJson<SkillResult>(`/api/courses/${courseId}/skill/fresher`, {
    method: "POST",
  });
}

/** Set or clear the optional target deadline. */
export async function setDeadline(
  courseId: string,
  deadline: string | null,
): Promise<void> {
  await fetch(`${API_BASE_URL}/api/courses/${courseId}/deadline`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ deadline }),
  });
}

/** Approve the staged plan: write its modules + deadlines. */
export function approvePlan(courseId: string): Promise<CourseModuleProgress[]> {
  return requestJson<CourseModuleProgress[]>(
    `/api/courses/${courseId}/plan/approve`,
    { method: "POST" },
  );
}
```

> `CourseModuleProgress` is declared later in the file (line 443). TypeScript hoists type references, so the forward reference is fine.

- [ ] **Step 4: Verify the type-check passes**

Run: `cd ayanakoji/frontend && npm run typecheck` (or `npx tsc --noEmit`)
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add ayanakoji/frontend/src/lib/api.ts
git commit -m "feat(api): skill-check types, event handler, and client calls"
```

---

### Task 7.2: `SkillGateCard` (fresher vs. skill check)

**Files:**
- Create: `ayanakoji/frontend/src/components/chat/skill-gate-card.tsx`

- [ ] **Step 1: Implement**

```tsx
"use client";

/**
 * The skill-gap gate — shown after a course is accepted, before pacing. The
 * learner says they're new (fresher) or opts into a quick per-module skill check.
 */

import { motion, useReducedMotion } from "framer-motion";
import { GraduationCap, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { SkillGateRequest } from "@/lib/api";

export function SkillGateCard({
  request,
  busy,
  onFresher,
  onTakeCheck,
}: {
  request: SkillGateRequest;
  busy: boolean;
  onFresher: () => void;
  onTakeCheck: () => void;
}) {
  const reduce = useReducedMotion();
  return (
    <motion.div
      initial={reduce ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
      className="border-brand/30 bg-card/70 max-w-[78%] space-y-2 rounded-2xl rounded-bl-md border p-3 shadow-sm"
    >
      <p className="text-foreground/90 px-1 text-xs font-medium text-pretty">{request.prompt}</p>
      <div className="grid grid-cols-2 gap-2">
        <Button
          variant="outline"
          onClick={onFresher}
          disabled={busy}
          className="h-auto flex-col gap-1 py-2.5 text-xs"
        >
          <span className="text-brand">
            <GraduationCap className="size-4" />
          </span>
          <span className="font-medium">I&apos;m new to this</span>
          <span className="text-[10px] opacity-70">Skip the check</span>
        </Button>
        <Button
          onClick={onTakeCheck}
          disabled={busy}
          className="h-auto flex-col gap-1 py-2.5 text-xs"
        >
          <span>
            <Sparkles className="size-4" />
          </span>
          <span className="font-medium">Quick skill check</span>
          <span className="text-[10px] opacity-70">4 questions / module</span>
        </Button>
      </div>
    </motion.div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add ayanakoji/frontend/src/components/chat/skill-gate-card.tsx
git commit -m "feat(chat): SkillGateCard (fresher vs skill check)"
```

---

### Task 7.3: `SkillAssessmentCard` (multi-tab quiz)

**Files:**
- Create: `ayanakoji/frontend/src/components/chat/skill-assessment-card.tsx`
- Test: `ayanakoji/frontend/src/components/chat/skill-assessment-card.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// skill-assessment-card.test.tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SkillAssessmentCard } from "./skill-assessment-card";
import type { SkillCheck } from "@/lib/api";

const CHECK: SkillCheck = {
  catalog_id: "de-c01",
  title: "Data Eng",
  modules: [
    {
      module_id: "m1",
      title: "Module One",
      questions: [
        { id: "q1", prompt: "Pick one", kind: "mcq", choices: ["A", "B"] },
      ],
    },
  ],
};

describe("SkillAssessmentCard", () => {
  it("disables submit until every question is answered, then submits answers", () => {
    const onSubmit = vi.fn();
    render(<SkillAssessmentCard check={CHECK} busy={false} onSubmit={onSubmit} />);

    const submit = screen.getByRole("button", { name: /submit/i });
    expect(submit).toBeDisabled();

    fireEvent.click(screen.getByLabelText("A"));
    expect(submit).toBeEnabled();

    fireEvent.click(submit);
    expect(onSubmit).toHaveBeenCalledWith([
      { module_id: "m1", question_id: "q1", selections: ["A"] },
    ]);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ayanakoji/frontend && npx vitest run src/components/chat/skill-assessment-card.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

```tsx
"use client";

/**
 * The multi-tab skill check. One tab per module, each with up to 4 questions.
 * MCQ renders single-select (radio), MSQ multi-select (checkbox, "select all that
 * apply"). Submit unlocks only when every question across every tab is answered.
 */

import { motion, useReducedMotion } from "framer-motion";
import { Check } from "lucide-react";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import type { SkillAnswer, SkillCheck } from "@/lib/api";

type Selections = Record<string, string[]>; // question id → chosen choice texts

function toggle(list: string[], value: string, single: boolean): string[] {
  if (single) return [value];
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
}

export function SkillAssessmentCard({
  check,
  busy,
  onSubmit,
}: {
  check: SkillCheck;
  busy: boolean;
  onSubmit: (answers: SkillAnswer[]) => void;
}) {
  const reduce = useReducedMotion();
  const [tab, setTab] = useState(0);
  const [selections, setSelections] = useState<Selections>({});

  const allQuestions = useMemo(
    () => check.modules.flatMap((m) => m.questions.map((q) => ({ moduleId: m.module_id, q }))),
    [check],
  );
  const answeredCount = allQuestions.filter(({ q }) => (selections[q.id]?.length ?? 0) > 0).length;
  const complete = answeredCount === allQuestions.length && allQuestions.length > 0;
  const active = check.modules[tab];

  function moduleAnswered(moduleId: string): boolean {
    const mod = check.modules.find((m) => m.module_id === moduleId);
    return !!mod && mod.questions.every((q) => (selections[q.id]?.length ?? 0) > 0);
  }

  function submit() {
    const answers: SkillAnswer[] = allQuestions.map(({ moduleId, q }) => ({
      module_id: moduleId,
      question_id: q.id,
      selections: selections[q.id] ?? [],
    }));
    onSubmit(answers);
  }

  return (
    <motion.div
      initial={reduce ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
      className="border-brand/30 bg-card/70 max-w-[88%] space-y-3 rounded-2xl rounded-bl-md border p-3 shadow-sm"
    >
      {/* Tabs: one per module, with a completion tick */}
      <div className="flex flex-wrap gap-1.5">
        {check.modules.map((m, i) => (
          <button
            key={m.module_id}
            type="button"
            onClick={() => setTab(i)}
            className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] transition-colors ${
              i === tab
                ? "border-brand bg-brand/10 text-brand"
                : "border-border/60 text-muted-foreground hover:text-foreground"
            }`}
          >
            {moduleAnswered(m.module_id) && <Check className="size-3" />}
            <span className="max-w-[10rem] truncate">{m.title}</span>
          </button>
        ))}
      </div>

      {/* Active tab questions */}
      {active && (
        <ol className="space-y-3">
          {active.questions.map((q) => {
            const single = q.kind === "mcq";
            const chosen = selections[q.id] ?? [];
            return (
              <li key={q.id} className="space-y-1.5">
                <p className="text-foreground text-xs font-medium text-pretty">
                  {q.prompt}
                  {!single && (
                    <span className="text-muted-foreground ml-1 text-[10px]">(select all that apply)</span>
                  )}
                </p>
                <div className="space-y-1">
                  {q.choices.map((choice) => {
                    const picked = chosen.includes(choice);
                    return (
                      <label
                        key={choice}
                        className={`flex cursor-pointer items-center gap-2 rounded-lg border px-2.5 py-1.5 text-xs transition-colors ${
                          picked ? "border-brand bg-brand/5" : "border-border/60 hover:bg-accent/40"
                        }`}
                      >
                        <input
                          aria-label={choice}
                          type={single ? "radio" : "checkbox"}
                          name={q.id}
                          checked={picked}
                          onChange={() =>
                            setSelections((prev) => ({ ...prev, [q.id]: toggle(chosen, choice, single) }))
                          }
                          className="accent-brand"
                        />
                        <span className="text-pretty">{choice}</span>
                      </label>
                    );
                  })}
                </div>
              </li>
            );
          })}
        </ol>
      )}

      <div className="flex items-center justify-between gap-2">
        <span className="text-muted-foreground text-[11px]">
          {answeredCount}/{allQuestions.length} answered
        </span>
        <Button size="sm" disabled={!complete || busy} onClick={submit} className="text-xs">
          Submit skill check
        </Button>
      </div>
    </motion.div>
  );
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd ayanakoji/frontend && npx vitest run src/components/chat/skill-assessment-card.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ayanakoji/frontend/src/components/chat/skill-assessment-card.tsx ayanakoji/frontend/src/components/chat/skill-assessment-card.test.tsx
git commit -m "feat(chat): SkillAssessmentCard (multi-tab MCQ/MSQ quiz)"
```

---

### Task 7.4: `SkillResultCard` (scores + optional deadline)

**Files:**
- Create: `ayanakoji/frontend/src/components/chat/skill-result-card.tsx`

- [ ] **Step 1: Implement**

```tsx
"use client";

/**
 * The skill-check result: per-module score bars + overall, plus an optional
 * deadline picker. "Continue" persists the deadline (or none) and advances to the
 * pace step. Re-rendered from the persisted skill_result meta on reload.
 */

import { motion, useReducedMotion } from "framer-motion";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import type { SkillResult } from "@/lib/api";

export function SkillResultCard({
  result,
  done,
  busy,
  onContinue,
}: {
  result: SkillResult;
  done: boolean;
  busy: boolean;
  onContinue: (deadline: string | null) => void;
}) {
  const reduce = useReducedMotion();
  const [deadline, setDeadline] = useState<string>("");

  return (
    <motion.div
      initial={reduce ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
      className="border-brand/30 bg-card/70 max-w-[82%] space-y-3 rounded-2xl rounded-bl-md border p-3 shadow-sm"
    >
      {!result.fresher && (
        <>
          <div className="flex items-baseline justify-between">
            <span className="text-foreground text-xs font-semibold">Skill check</span>
            <span className="text-brand text-sm font-bold tabular-nums">
              {Math.round(result.overall_fraction * 100)}%
            </span>
          </div>
          <ul className="space-y-1.5">
            {result.modules.map((m) => (
              <li key={m.module_id} className="space-y-0.5">
                <div className="flex items-center justify-between text-[11px]">
                  <span className="text-foreground/90 max-w-[14rem] truncate">{m.title}</span>
                  <span className="text-muted-foreground tabular-nums">
                    {m.correct}/{m.total}
                  </span>
                </div>
                <div className="bg-border/50 h-1.5 overflow-hidden rounded-full">
                  <div
                    className="bg-brand h-full rounded-full"
                    style={{ width: `${Math.round(m.fraction * 100)}%` }}
                  />
                </div>
              </li>
            ))}
          </ul>
        </>
      )}

      <div className="space-y-1.5">
        <label className="text-foreground/90 text-[11px] font-medium">
          Target deadline (optional)
        </label>
        <input
          type="date"
          value={deadline}
          disabled={done || busy}
          onChange={(e) => setDeadline(e.target.value)}
          className="border-border/60 bg-background w-full rounded-lg border px-2.5 py-1.5 text-xs"
        />
      </div>

      <Button
        size="sm"
        disabled={done || busy}
        onClick={() => onContinue(deadline || null)}
        className="text-xs"
      >
        {done ? "Continuing…" : "Continue to pace"}
      </Button>
    </motion.div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add ayanakoji/frontend/src/components/chat/skill-result-card.tsx
git commit -m "feat(chat): SkillResultCard (scores + optional deadline)"
```

---

### Task 7.5: `StudyPlanCard` preview mode (base→pace→skill breakdown + Approve)

**Files:**
- Modify: `ayanakoji/frontend/src/components/chat/study-plan-card.tsx`

- [ ] **Step 1: Implement**

Extend the component props and rendering. Change the signature (line 64) to:

```tsx
export function StudyPlanCard({
  plan,
  courseId,
  approveState,
  busy,
  onApprove,
}: {
  plan: StudyPlan;
  courseId?: string;
  approveState?: "idle" | "approving" | "approved";
  busy?: boolean;
  onApprove?: () => void;
}) {
```

Add a per-module skill-delta line. Inside the module `<li>`, after the existing `fmtMinutes(m.estimated_minutes)` span (line 118), add a breakdown that only shows when skill changed the time:

```tsx
                {m.skill_delta !== 0 && (
                  <>
                    <span aria-hidden>·</span>
                    <span className={m.skill_delta < 0 ? "text-emerald-600" : "text-amber-600"}>
                      {m.skill_delta < 0
                        ? `${fmtMinutes(-m.skill_delta)} off (you've got this)`
                        : `${fmtMinutes(m.skill_delta)} added (skill gap)`}
                    </span>
                    <span className="text-muted-foreground/70">
                      base {fmtMinutes(m.base_minutes)} → pace {fmtMinutes(m.pace_minutes)}
                    </span>
                  </>
                )}
```

After the `capacity_reason` paragraph (line 103), add the LOUD warning when present (the field already exists on the backend `StudyPlan.balloon_warning`; add it to the `StudyPlan` TS interface in Task 7.1 if not already — add `balloon_warning?: string | null;`):

```tsx
      {plan.balloon_warning && (
        <p className="border-l-2 border-amber-500 bg-amber-500/10 pl-2.5 text-[11px] font-medium text-amber-700">
          {plan.balloon_warning}
        </p>
      )}
```

Replace the "Open the Modules tab" footer (lines 147-154) so that a preview shows an Approve action, and an approved plan links to Modules:

```tsx
      {plan.awaiting_approval && approveState !== "approved" ? (
        <div className="flex items-center gap-2">
          <Button size="sm" disabled={busy || approveState === "approving"} onClick={onApprove} className="text-xs">
            {approveState === "approving" ? "Putting it on your schedule…" : "Approve & schedule"}
          </Button>
          <span className="text-muted-foreground text-[10px]">
            Or tell me what to change and I&apos;ll re-plan.
          </span>
        </div>
      ) : (
        courseId && (
          <Link
            href={`/chat/${courseId}/modules`}
            className="bg-brand text-brand-foreground hover:bg-brand/90 inline-flex h-8 items-center rounded-lg px-3 text-xs font-medium transition-colors"
          >
            Open the Modules tab ›
          </Link>
        )
      )}
```

Add the `Button` import at the top: `import { Button } from "@/components/ui/button";`.

> Also add `balloon_warning?: string | null;` to the `StudyPlan` interface in `api.ts` (Task 7.1) — the backend has always sent it; it was simply not typed.

- [ ] **Step 2: Type-check**

Run: `cd ayanakoji/frontend && npm run typecheck`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add ayanakoji/frontend/src/components/chat/study-plan-card.tsx ayanakoji/frontend/src/lib/api.ts
git commit -m "feat(chat): study-plan preview mode (skill breakdown, warning, approve)"
```

---

### Task 7.6: Wire the flow into `chat-view.tsx`

**Files:**
- Modify: `ayanakoji/frontend/src/components/chat/chat-view.tsx`

- [ ] **Step 1: Extend imports + `AssistantTurn`**

Add imports (top of file):

```tsx
import { SkillGateCard } from "@/components/chat/skill-gate-card";
import { SkillAssessmentCard } from "@/components/chat/skill-assessment-card";
import { SkillResultCard } from "@/components/chat/skill-result-card";
```
and from `@/lib/api` add:
```tsx
  approvePlan,
  gradeSkillCheck,
  listModules,
  setDeadline,
  skillFresher,
  startSkillCheck,
  type SkillAnswer,
  type SkillCheck,
  type SkillGateRequest,
  type SkillResult,
```

Extend `AssistantTurn` (lines 47-60) with skill + approval fields:

```tsx
  skillGate: SkillGateRequest | null;
  skillCheck: SkillCheck | null; // ephemeral: the active quiz (not persisted)
  skillBusy: boolean;
  skillResult: SkillResult | null;
  deadlineDone: boolean;
  approveState: "idle" | "approving" | "approved";
```

Add the same defaults to `emptyAssistantTurn()` (lines 64-79):

```tsx
    skillGate: null,
    skillCheck: null,
    skillBusy: false,
    skillResult: null,
    deadlineDone: false,
    approveState: "idle",
```

- [ ] **Step 2: Map persisted meta on reload**

In the `getCourse(...).then(...)` mapper (lines 163-181), first compute whether the skill step is already resolved (a `skill_result` message exists), so the gate is not re-offered on reload. Add this just before `setTurns(...)` (inside the `.then`):

```tsx
        const skillResolved = loaded.messages.some((m) => m.meta?.skill_result);
```

Then add to the assistant object built in the mapper:

```tsx
                  // Suppress the gate once the skill step is resolved (it lives on
                  // an earlier turn than the skill_result message).
                  skillGate: skillResolved ? null : (m.meta?.skill_gate ?? null),
                  skillCheck: null,
                  skillBusy: false,
                  skillResult: m.meta?.skill_result ?? null,
                  deadlineDone: false,
                  approveState: "idle",
```

For approval-on-reload, derive from persisted modules: after the mapper, fetch modules once and, if non-empty, mark the latest plan turn approved. Simplest robust approach — call `listModules(loaded.id)` and if it returns rows, set `approveState: "approved"` on the last assistant turn that has a `plan`. Add this in the `.then` after `setTurns(...)`:

```tsx
        listModules(loaded.id)
          .then((mods) => {
            if (!active || mods.length === 0) return;
            setTurns((prev) => {
              const next = [...prev];
              for (let i = next.length - 1; i >= 0; i -= 1) {
                const t = next[i];
                if (t.kind === "assistant" && t.plan) {
                  next[i] = { ...t, approveState: "approved" };
                  break;
                }
              }
              return next;
            });
          })
          .catch(() => {});
```
(import `listModules` from `@/lib/api`.)

- [ ] **Step 3: Add the stream handler**

In `streamMessage(...)` handlers (lines 234-249) add:

```tsx
        onSkillGate: (skillGate) => patchLastAssistant((t) => ({ ...t, skillGate })),
```

- [ ] **Step 4: Add the action handlers**

Add these functions next to `handlePace` (after line 318):

```tsx
  function patchTurnAt(index: number, patch: (t: AssistantTurn) => AssistantTurn) {
    setTurns((prev) => updateAssistant(prev, index, patch));
  }

  async function handleTakeSkillCheck(index: number) {
    if (!activeCourseId) return;
    patchTurnAt(index, (t) => ({ ...t, skillBusy: true }));
    try {
      const check = await startSkillCheck(activeCourseId);
      patchTurnAt(index, (t) => ({ ...t, skillCheck: check, skillBusy: false }));
    } catch {
      patchTurnAt(index, (t) => ({ ...t, skillBusy: false }));
      toast.error("Could not start the skill check", { description: "Please try again." });
    }
  }

  async function handleFresher(index: number) {
    if (!activeCourseId) return;
    patchTurnAt(index, (t) => ({ ...t, skillBusy: true }));
    try {
      const result = await skillFresher(activeCourseId);
      patchTurnAt(index, (t) => ({ ...t, skillResult: result, skillGate: null, skillBusy: false }));
    } catch {
      patchTurnAt(index, (t) => ({ ...t, skillBusy: false }));
      toast.error("Could not continue", { description: "Please try again." });
    }
  }

  async function handleSubmitSkill(index: number, answers: SkillAnswer[]) {
    if (!activeCourseId) return;
    patchTurnAt(index, (t) => ({ ...t, skillBusy: true }));
    try {
      const result = await gradeSkillCheck(activeCourseId, answers);
      patchTurnAt(index, (t) => ({ ...t, skillResult: result, skillCheck: null, skillBusy: false }));
    } catch {
      patchTurnAt(index, (t) => ({ ...t, skillBusy: false }));
      toast.error("Could not grade the skill check", { description: "Please try again." });
    }
  }

  async function handleDeadlineContinue(index: number, deadline: string | null) {
    if (!activeCourseId) return;
    patchTurnAt(index, (t) => ({ ...t, deadlineDone: true }));
    try {
      await setDeadline(activeCourseId, deadline);
      await handleSend("Build me a study plan for this course");
    } catch {
      patchTurnAt(index, (t) => ({ ...t, deadlineDone: false }));
      toast.error("Could not save the deadline", { description: "Please try again." });
    }
  }

  async function handleApprove(index: number) {
    if (!activeCourseId) return;
    patchTurnAt(index, (t) => ({ ...t, approveState: "approving" }));
    try {
      await approvePlan(activeCourseId);
      patchTurnAt(index, (t) => ({ ...t, approveState: "approved" }));
      toast.success("Scheduled", { description: "Your modules now have deadlines." });
      void reloadCourses();
    } catch {
      patchTurnAt(index, (t) => ({ ...t, approveState: "idle" }));
      toast.error("Could not schedule the plan", { description: "Please try again." });
    }
  }
```

- [ ] **Step 5: Render the cards**

In the assistant-turn JSX (lines 348-384), add the skill cards before the `{turn.paceRequest && ...}` block, and pass approval props to the plan card. Replace the `{turn.plan && ...}` line and add the skill blocks:

```tsx
                {turn.skillGate && !turn.skillCheck && !turn.skillResult && (
                  <SkillGateCard
                    request={turn.skillGate}
                    busy={busy || turn.skillBusy}
                    onFresher={() => handleFresher(index)}
                    onTakeCheck={() => handleTakeSkillCheck(index)}
                  />
                )}
                {turn.skillCheck && !turn.skillResult && (
                  <SkillAssessmentCard
                    check={turn.skillCheck}
                    busy={busy || turn.skillBusy}
                    onSubmit={(answers) => handleSubmitSkill(index, answers)}
                  />
                )}
                {turn.skillResult && (
                  <SkillResultCard
                    result={turn.skillResult}
                    done={turn.deadlineDone}
                    busy={busy}
                    onContinue={(deadline) => handleDeadlineContinue(index, deadline)}
                  />
                )}
                {turn.paceRequest && (
                  <PaceChooser
                    request={turn.paceRequest}
                    chosen={turn.paceChosen}
                    busy={busy || turn.paceChosen !== null}
                    onChoose={(pace) => handlePace(index, pace)}
                  />
                )}
                {turn.plan && (
                  <StudyPlanCard
                    plan={turn.plan}
                    courseId={activeCourseId}
                    approveState={turn.approveState}
                    busy={busy}
                    onApprove={() => handleApprove(index)}
                  />
                )}
```

- [ ] **Step 6: Extend the HITL input lock to the quiz**

The pace lock already disables typing while a pace is pending. Extend it so the quiz also locks free text (a half-answered quiz shouldn't be abandoned by typing). Update `paceLocked` (lines 324-326):

```tsx
  const lastTurn = turns[turns.length - 1];
  const lastAssistant = lastTurn?.kind === "assistant" ? lastTurn : null;
  const paceLocked = Boolean(lastAssistant?.paceRequest) && lastAssistant?.paceChosen == null;
  const quizLocked = Boolean(lastAssistant?.skillCheck);
  const inputLocked = paceLocked || quizLocked;
```
and pass `locked={inputLocked}` to `<ChatComposer ... />` (line 402).

> The skill *gate* (fresher vs. check) and the plan *preview* deliberately do NOT lock input: a learner may type a question at the gate, and the preview accepts free-text corrections that re-plan.

- [ ] **Step 7: Type-check + run frontend tests**

Run: `cd ayanakoji/frontend && npm run typecheck && npx vitest run`
Expected: no type errors; tests pass.

- [ ] **Step 8: Commit**

```bash
git add ayanakoji/frontend/src/components/chat/chat-view.tsx
git commit -m "feat(chat): wire skill-gap flow (gate, quiz, result, deadline, approve)"
```

---

## Phase 8 — End-to-end verification

### Task 8.1: Manual end-to-end walkthrough (offline)

**Files:** none (verification only)

- [ ] **Step 1: Start backend + frontend**

Run backend offline (so no model keys are needed) and the frontend dev server. Confirm `LLM_OFFLINE`/`llm_offline` is set for the backend (check `app/config.py`).

- [ ] **Step 2: Walk the full flow and confirm each gate**

In a fresh chat:
1. Ask for a course → accept a suggested course.
2. "Build me a study plan" → **Skill Gate card** appears (not the pace card).
3. Click **Quick skill check** → multi-tab quiz; each module tab shows up to 4 questions; MCQ = radio, MSQ = checkbox; submit is disabled until all answered.
4. Submit → **Skill Result card** with per-module bars + overall %, and a deadline input.
5. Enter a near deadline (to force an overrun) → Continue → **Pace card**.
6. Pick **Faster** → **Plan preview**: per-module shows "+X added (skill gap)" only (faster never trims), the LOUD overrun warning appears, and an **Approve & schedule** button (modules NOT yet in the Modules tab).
7. Type a correction ("skip weekends") → a new preview appears; still not scheduled.
8. Click **Approve & schedule** → toast; open the **Modules** tab → modules now exist with deadlines.
9. Reload the chat → score card, plan preview, and approved state all restore from persisted meta/modules.

- [ ] **Step 3: Confirm the pace-direction rules visually**

Repeat with **Slower** pace and a fresher: confirm no per-module padding appears (slower + fresher = lessen-only, so weakness adds nothing). Repeat with **Normal** and a mixed score: confirm strong modules show "off" and weak modules show "added".

- [ ] **Step 4: Final full-suite run + commit any fixes**

Run: `cd ayanakoji/backend && python -m pytest tests/ -q`
Run: `cd ayanakoji/frontend && npm run typecheck && npx vitest run`
Expected: all green.

---

## Appendix — spec coverage map

| Spec requirement | Task(s) |
| --- | --- |
| Ask fresher vs. skill check after course map, before pace | 4.1, 4.2, 7.2, 7.6 |
| Multi-tab card, 4 random MCQ/MSQ per module, rendered correctly | 6.3 (start), 7.3 |
| Instant per-module + overall scoring | 6.3 (grade), 6.1 |
| Optional deadline after scoring | 6.3 (deadline), 7.4 |
| Pace choice after deadline | existing pace gate, ordered after skill (4.1) |
| Skill correction gated by pace (slow=lessen, fast=extend, normal=both, ±20%) | 1.1, 1.2 |
| Fresher = weak everywhere (same path) | 6.3 (fresher), 1.1 |
| LOUD warning if deadline unmet at pace | reuses `balloon_warning`; surfaced 7.5 |
| Don't fill schedule until approved; wait for button or text | 5.1 (stage), 5.2 (approve), 7.5/7.6 |
| Text corrections re-plan the preview | existing scheduler path; preview not persisted (5.1) |
| Show base / pace-corrected / skill-corrected per module + totals | 1.2 (compute), 7.5 (display) |
| Slow: only lessen; Fast: only extend (skill) | 1.1 (`skill_factor` gating) |
| On approval, put deadlines on modules | 5.2 (`replace_modules`) |
| Cards survive reload | meta capture (5.1, 6.3) + reload mapping (7.6) |
