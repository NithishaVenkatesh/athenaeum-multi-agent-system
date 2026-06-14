# Skill-Gap Assessment Flow — Design

**Date:** 2026-06-14
**Status:** Approved (design); pending implementation plan
**Area:** ayanakoji agent pipeline (`ayanakoji/backend`, `ayanakoji/frontend`)

## Summary

Insert a skill-gap assessment step into the chat pipeline **between accepting a
course and choosing a pace**. After the course map is shown, the learner is asked
whether they're a fresher or want a quick skill check. The check is a multi-tab
card (one tab per module, 4 random MCQ/MSQ each) graded instantly. The per-module
scores adjust each module's time budget — gated by pace direction — and the
resulting study plan is shown as a **preview that is not written to the schedule
until the learner approves it**.

This reuses existing infrastructure: the per-module choice banks
(`BankChoiceQuestion`), set-match grading, `estimate_module_minutes()` (base/pace
time), `PACE_FACTOR`, the `balloon_warning` overrun message, and the
`PaceRequestEvent` → REST → derived-state HITL pattern.

## Goals

- Ask "fresher or skill check?" after the course map, before pace/plan.
- Skill check: 4 random MCQ/MSQ per module, rendered correctly (MCQ = single
  select, MSQ = multi select), Claude-style option-card selection.
- Instant per-module + overall scoring on submit; no LLM grading in the path.
- Collect an **optional** deadline after scoring.
- Adjust per-module time by skill, **gated by pace** (rules below), and clearly
  surface base time → pace-corrected time → skill-corrected time per module and
  as a plan total.
- LOUD warning when the plan cannot finish by the deadline at the chosen pace.
- Do **not** persist the schedule automatically. Show a preview, accept text
  corrections, and only write module deadlines on explicit approval.

## Non-goals

- No LLM-graded (open-ended) questions in the skill check.
- No change to the post-completion assessment sessions (`assessment_router.py`).
- No change to module sequencing/locking (skill only changes minutes, not order).

## Decisions (locked)

| Decision | Choice |
| --- | --- |
| Normal pace skill direction | **Both** (lessen mastered, extend weak) |
| Slow pace skill direction | **Lessen only** (never adds) |
| Fast pace skill direction | **Extend only** (never removes) |
| Skill adjustment cap | **Conservative ±20%** at the score extremes |
| Neutral midpoint | `s = 0.5` (2 of 4 correct) → no change |
| Fresher path | **Treat as weak everywhere** (`s = 0` on all modules) — same code path as scoring 0 |
| Quiz content | **MCQ + MSQ only**, instant set-match grading |
| Deadline input | Folded into the **Skill Result card** (one step), optional |
| Time breakdown display | Per-module **and** plan total |

## Conversational flow

```
CHOSEN (course accepted, course map shown)
  └─ study-plan request
       ▼
  [Skill Gate card] — "Fresher in this topic, or take a quick skill check?"
       ├─ "I'm a fresher" ──────────────► skill_source=fresher (weak everywhere)
       └─ "Take skill check"
            ▼
       [Skill Assessment card]  ← multi-tab: one tab/module, 4 random MCQ/MSQ each
            ▼ submit all
       [Skill Result card]  ← per-module score + overall + OPTIONAL deadline input
            ▼ continue (with/without deadline)
       [Pace card]  ← existing slower / normal / faster
            ▼ pick pace
       [Plan PREVIEW card]  ← base → pace-corrected → skill-corrected per module,
            │                  LOUD warning if it can't finish by the deadline.
            │                  NOT written to the schedule yet.
            ├─ text corrections ─► re-runs scheduler agent ─► new preview
            └─ "Approve" button ─► writes deadlines onto modules → PLANNED
```

The fresher branch skips the quiz and the score view, jumps to the deadline+pace
steps, and carries `s = 0` for every module into the identical correction code.

## Skill-correction math

Per module, `s ∈ [0,1]` = fraction of its 4 questions correct (0, .25, .5, .75,
1). Midpoint `s = 0.5` is neutral.

```
raw_factor = 1 − MAX_SKILL_ADJ · (2s − 1)        # MAX_SKILL_ADJ = 0.20
   s=1.0 (mastered) → 0.80   (−20%, lessen)
   s=0.5 (half)     → 1.00   (no change)
   s=0.0 (weak)     → 1.20   (+20%, extend)
```

Pace gates the direction:

```
slower → gated = min(1.0, raw_factor)   # lessen only
faster → gated = max(1.0, raw_factor)   # extend only
normal → gated = raw_factor             # both
```

Three surfaced numbers per module:

- **base** = `estimate_module_minutes(m, NORMAL)`
- **pace-corrected** = `estimate_module_minutes(m, pace)`
- **skill-corrected** = round-to-15(`pace-corrected × gated`) → the
  `estimated_minutes` the scheduler uses.

Delta labeled "−X min removed (you've got this)" or "+X min added (skill gap)".
Plan totals sum each of the three columns.

New pure function (in `study_plan.py`):

```python
def apply_skill_correction(pace_minutes: int, score: float, pace: Pace,
                           max_adj: float = 0.20) -> int: ...
```

`build_study_plan` gains `skill_scores: dict[str, float] | None`. A module with no
score (no bank / fewer than 4 questions / not assessed and not fresher) is treated
as **neutral** (`s = 0.5`, factor 1.0).

## Backend changes

### Events (`app/agent/contracts.py`)
- `SkillGateRequestEvent` — prompt + two options (fresher / take check).
- `SkillAssessmentEvent` — `catalog_id`, `title`, and per-module tabs each with 4
  sampled questions (`id`, `prompt`, `kind` `mcq|msq`, `choices`). **No correct
  answers leaked.**
- `SkillResultEvent` — per-module scores, overall, and the deadline prompt.
- `PlanEvent` gains `preview: bool` (default `False`).
- `ModulePlan` gains `base_minutes: int`, `pace_minutes: int`,
  `skill_delta: int` (signed, minutes).
- `StudyPlan` gains `awaiting_approval: bool` and the three plan totals.
- All added to the `PipelineEvent` union.

### State machine (`app/agent/state.py`)
- Add `ASSESSED` (skill done, pace not set) between `CHOSEN` and `PACED`.
- `derive_course_state` takes `skill_source` and gates: `CHOSEN` when
  `catalog_id` set and `skill_source is None`; `ASSESSED` when `skill_source` set
  and `pace is None`; `PACED` when pace set and no persisted modules; `PLANNED`
  once modules are persisted (approval).

### Persistence (`app/courses/models.py`, `repository.py`)
- `Course.skill_source: str | None` ("fresher" | "assessment").
- `Course.skill_scores: dict[str, float] | None` (module_id → fraction correct).
- Deadline reuses `plan_exam_date`; pace reuses `pace`.
- The previewed plan is **not** stored; approval recomputes deterministically and
  calls `replace_modules`.

### REST endpoints (`app/courses/router.py` or a new `skill_router.py`)
- `POST /api/courses/{id}/skill/start` → sample `min(4, available)` choice
  questions per module from the banks; return the quiz (no answers).
- `POST /api/courses/{id}/skill/grade` → set-match grade, store `skill_scores` +
  `skill_source="assessment"`; return the per-module + overall report.
- `POST /api/courses/{id}/skill/fresher` → set `skill_source="fresher"`,
  `skill_scores` = all-zero.
- `POST /api/courses/{id}/deadline` → set `plan_exam_date` (optional/clearable).
- `POST /api/courses/{id}/plan/approve` → recompute plan, `replace_modules` (write
  `complete_before` deadlines), transition to `PLANNED`.
- `POST /api/courses/{id}/pace` already exists.

### Orchestrator / answer agent
- `answer_study_plan`: in `CHOSEN` emit `SkillGateRequestEvent`; in `ASSESSED`
  emit `PaceRequestEvent`; in `PACED` build with `skill_scores` and emit
  `PlanEvent(preview=True)`. Text corrections in preview re-run the scheduler
  agent and emit a new preview.
- `_stream_turn` `finally`: **remove** the unconditional `replace_modules`;
  persistence now happens only in the approve endpoint. Constraints persistence
  on preview turns is retained.

## Frontend changes

- `SkillGateCard` — two buttons (fresher / take check).
- `SkillAssessmentCard` — tabbed, one tab per module; MCQ = radio, MSQ = checkbox
  with "select all that apply"; per-tab completion indicator; submit disabled
  until every question is answered. Claude-style option-card selection styling,
  consistent with the existing scholarly-atelier cards.
- `SkillResultCard` — per-module score bars + overall + optional deadline picker
  with a "no deadline" choice; continue advances to pace.
- `StudyPlanCard` preview mode — base → pace-corrected → skill-corrected per
  module and as totals, the LOUD overrun warning, an **Approve** button, and
  free-text corrections. Only Approve writes deadlines.
- `api.ts` — handlers for the new events; new client calls for the endpoints.
- All cards persisted into message `meta` to survive reload (existing pattern).

## Edge cases

- Module with no bank or <4 questions → sample what exists; zero questions →
  neutral (factor 1.0), shown as "no check available."
- Retake allowed (overwrites `skill_scores`).
- Sequential module lock unaffected.
- No deadline given → no overrun warning; plan still previews and requires
  approval.
- Approve recomputes from persisted facts (pace, skill_scores, constraints,
  calendar) — safe because the plan is a pure function of them.

## Testing

- `apply_skill_correction`: three paces × extremes (s=0, s=1) × midpoint (s=0.5),
  and fresher (s=0) — assert lessen-only/extend-only/both gating and ±20% caps.
- Set-match grading: MCQ exact, MSQ exact set, partial/over-selection = wrong.
- `build_study_plan` with `skill_scores`: per-module base/pace/skill columns,
  totals, neutral fallback for unscored modules.
- Preview does not persist modules; approve persists deadlines onto modules.
- Deadline-overrun warning fires using skill-corrected totals.
- State transitions: CHOSEN → ASSESSED → PACED → PLANNED with the new facts.
