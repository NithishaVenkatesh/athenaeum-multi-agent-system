# Azure Assessor Agent — Design Spec

**Date:** 2026-06-14
**Status:** Approved (design); pending implementation plan
**Scope:** Add an Azure-backed "assessor agent" to the existing chat agent framework so a learner can practise the module they are currently in, get a pass / not-yet / study verdict, and be routed to the official evaluation or the module via in-chat buttons.

---

## 1. Goal & user-facing behaviour

A learner in a course chat can:

1. **Practise the current module.** Ask to practise/quiz (e.g. "quiz me on this module"). The assessor generates **5 MCQs grounded strictly in the current module's content**, rendered as a question card in chat. The learner answers; the assessor reviews and returns a verdict:
   - **ready** (≥ 4/5 correct) → honest praise + a **Take Evaluation** button.
   - **not yet** (2–3/5) → honest review of what was missed + a **Go to Module** button + motivation.
   - **study** (≤ 1/5) → honest, kind review + a **Go to Module** button + stronger nudge to study.
2. **Jump to the evaluation by asking.** Say "I'm ready for the test" → short confirming reply + a **Take Evaluation** button.
3. **Jump to the module by asking.** Say "take me to the module" / "I want to study the module" → short reply + a **Go to Module** button.

All three behaviours are **hard-gated on the learner deterministically having a current module**. When there is no current module, the assessor never renders a card or button — it replies with a specific, helpful message (see §6).

### Definition: "current module"
The first module in the learner's approved plan whose `completed` flag is `False` — i.e. the module they are working through now. Practice targets **only** this module. Requires an approved plan (`modules` list non-empty with at least one incomplete module).

### Key decisions (locked)
- **MCQ source:** Azure-generated, grounded in the module's markdown content (not the authored bank).
- **Readiness bar:** 5 questions, ≥ 80% (≥ 4 correct) = ready.
- **CTA scope:** Buttons appear both as the practice outcome **and** from direct conversational asks.
- **Practice state model:** Ephemeral JSON on the `Course` row (`practice_active`), mirroring the existing `skill_check_active` precedent. Practice **never** writes to the `Assessment` table and **never** affects official completion/progress.

---

## 2. Existing framework facts this design builds on

- **Pipeline:** `entry → injection gate → router → answer agent`, run in `app/agent/orchestrator.py` (`run_pipeline`, `_dispatch`). Agents return `AgentReply` (streamed tokens + optional structured events). Output is an SSE `PipelineEvent` stream.
- **Routing:** `Route` enum in `app/agent/contracts.py`; deterministic `classify()` regex chain + LLM fallback in `app/agent/router_agent.py` (`_ROUTE_SYSTEM` prompt).
- **Module context:** `modules: list[dict]` is already passed into `run_pipeline`/`_dispatch`; each entry has `module_id` (catalog id, e.g. `cb-c01-m01`), `title`, `sequence`, `completed`.
- **Module content:** `app/catalog/content.py` → `get_module_content(module_id) -> ModuleContent | None` returns the module's markdown body (frontmatter stripped).
- **LLM access:** `app/agent/llm.py` → `ModelRouter` with `Capability.WORKHORSE` (Azure tier 1 → Groq fallback). `router.complete(..., json_mode=True)` for generation; `router.stream(...)` for prose.
- **Existing SSE precedent for a non-pipeline streamed reply:** the grounded feedback endpoint (`POST /api/courses/{course_id}/modules/{module_id}/feedback`) + frontend `streamFeedback()`.
- **Frontend chat:** `app/.../components/chat/chat-view.tsx` renders an `AssistantTurn`; rich content is dispatched by the presence of a turn field (no polymorphic union). MCQ rendering already exists in `skill-assessment-card.tsx` for the shape `{id, prompt, kind, choices}` — a pure presentational component, embeddable.
- **Navigation targets (existing routes):**
  - Evaluation: `/chat/{courseId}/modules/{moduleId}/assessment/choices`
  - Module: `/chat/{courseId}/modules/{moduleId}`

---

## 3. Components & file changes

### Backend

| File | Change |
|------|--------|
| `app/agent/contracts.py` | Add `Route.PRACTISE_MODULE`, `Route.TAKE_EVALUATION`, `Route.GO_TO_MODULE`. Add `PracticeEvent` and `ActionEvent` (+ `Action`) models; add both to the `PipelineEvent` union and as optional fields on `AgentReply`. |
| `app/agent/assessor.py` *(new)* | The assessor logic: `resolve_current_module(modules)`, `generate_practice(...)`, `review_practice(...)`, verdict mapping, prompts, JSON validation + retry/fallback. Keeps `answer.py` from growing. |
| `app/agent/router_agent.py` | Add regex patterns + `classify()` branches for the 3 intents; extend `_ROUTE_SYSTEM`. |
| `app/agent/orchestrator.py` | Import assessor; add `_dispatch` cases for the 3 routes; enforce the **hard module gate** via `resolve_current_module`; emit `PracticeEvent` / `ActionEvent` in the stream generator. |
| `app/courses/models.py` | Add `Course.practice_active: dict | None` (JSON), consistent with `skill_check_active`. |
| `app/courses/practice_router.py` *(new)* | `POST /api/courses/{course_id}/practice/submit` (SSE): read `practice_active`, grade, stream review, emit `ActionEvent`, clear blob. |
| App wiring (`main`/app factory) | Register the new practice router. |
| DB migration | `create_all` won't add the new column to an existing `athenaeum.db`. Add a lightweight startup migration (`ALTER TABLE course ADD COLUMN practice_active …`) guarded by an existence check, or recreate the dev DB. **Must be explicit in the plan.** |

### New contract models (shape)

```python
class PracticeQuestion(BaseModel):
    id: str
    prompt: str
    kind: Literal["mcq"] = "mcq"
    choices: list[str]            # 4 options; NO correct answer sent to client

class PracticeEvent(BaseModel):
    type: Literal["practice"] = "practice"
    module_id: str
    title: str
    questions: list[PracticeQuestion]

class Action(BaseModel):
    kind: Literal["take_evaluation", "go_to_module", "practice_again"]
    label: str
    module_id: str | None = None
    href: str | None = None       # backend-provided nav target where applicable

class ActionEvent(BaseModel):
    type: Literal["action"] = "action"
    prompt: str | None = None
    actions: list[Action]
```

`ActionEvent` is the generic "buttons in a chat message" mechanism the framework currently lacks; it is reusable beyond this feature.

### Server-side practice_active blob (never sent verbatim to client)

```jsonc
{
  "module_id": "cb-c01-m01",
  "title": "…",
  "questions": [
    { "id": "p1", "prompt": "…", "choices": ["…","…","…","…"],
      "correct": "…", "explanation": "…" }
  ]
}
```

### Frontend

| File | Change |
|------|--------|
| `src/lib/api.ts` | Add `PracticeEvent` / `ActionEvent` to the event union; add `onPractice` / `onAction` to `StreamHandlers`; add `streamPractice(courseId, selections, handlers)`. |
| `src/components/chat/chat-view.tsx` | Extend `AssistantTurn` with `practice` and `actions`; wire the two handlers; render the new cards in the turn dispatch block. |
| `src/components/chat/practice-card.tsx` *(new)* | Renders the MCQ round (reusing the question-list rendering pattern from `skill-assessment-card.tsx`, ideally via an extracted `McqQuestionList`). Submit → `streamPractice` → appends a review turn carrying `actions`. |
| `src/components/chat/action-buttons.tsx` *(new)* | Renders CTAs: *Take evaluation* / *Go to module* as `<Link>`s to the existing routes; *Practice again* re-sends a practice message. |

---

## 4. Data flow

### Practice round
1. Learner message → injection gate → router classifies `PRACTISE_MODULE`.
2. `_dispatch` calls `resolve_current_module(modules)`.
   - `None` → graceful no-module reply (§6); **stop** (no card).
   - module found → `generate_practice(module_id, title, router)`:
     - `get_module_content(module_id)` → markdown.
     - Azure `complete(WORKHORSE, …, json_mode=True)` → 5 MCQs with answer key + explanations.
     - Validate (5 items, 4 distinct choices each, `correct ∈ choices`); one retry on invalid; hard failure → apology + Go-to-Module CTA.
3. Persist the full round (with key) to `Course.practice_active`.
4. Stream a short intro message + emit `PracticeEvent` (stems + choices only). Frontend renders `PracticeCard`.

### Submit & review
5. Learner submits selections → `POST /api/courses/{course_id}/practice/submit` (SSE).
6. Endpoint reads `practice_active`, grades deterministically (count exact-match MCQ correct out of 5), maps verdict (≥4 ready / 2–3 not_yet / ≤1 study).
7. `review_practice(...)` streams an honest, motivating review (names missed questions, grounded in module content) via `router.stream(WORKHORSE, …)`.
8. Emit `ActionEvent`:
   - ready → `take_evaluation` (+ optional `practice_again`).
   - not_yet / study → `go_to_module` (+ optional `practice_again`).
9. Clear `practice_active`. Frontend appends a review turn + renders `ActionButtons`.

### Direct CTA asks
- `TAKE_EVALUATION`: hard gate → short confirming reply + `ActionEvent[take_evaluation]`.
- `GO_TO_MODULE`: hard gate → short reply + `ActionEvent[go_to_module]`.

---

## 5. Routing detail

- New regexes in `router_agent.py`:
  - practise: practise/quiz/drill/"warm up"/"give me practice questions".
  - take evaluation: "ready for the (test|evaluation|assessment)", "take the (test|evaluation|assessment)".
  - go to module: "go to / open / take me to / show me / study the module".
- Practise vs. take-evaluation ambiguity (e.g. "test me") is resolved by keeping practise patterns about *practising/quizzing* and evaluation patterns about *taking/being ready for the official test*; the LLM router is the tie-breaker fallback.
- `_ROUTE_SYSTEM` gains one line per new route.
- **The hard gate is enforced in `_dispatch` (where `modules` is available), not in the router.** The router only classifies intent; deterministic module availability decides whether the feature runs or the graceful fallback fires.

---

## 6. No-current-module handling (hard filter)

`resolve_current_module(modules)` returns `None` when the plan is empty/absent or every module is complete. For all three routes, `_dispatch` then streams a **specific** reply (no card, no button):

- **No approved plan** (`modules` empty): "You don't have an active course plan yet — pick a course and I'll build your plan, then you can practise it."
- **All modules complete:** "You've completed every module in this course — there's nothing left to practise here."

These are deterministic text replies routed through the normal token stream + `DoneEvent`.

---

## 7. Error handling

- **Generation invalid/empty after one retry:** stream an honest apology ("I couldn't put together a clean practice set just now"), emit a `go_to_module` `ActionEvent`; do not write `practice_active`.
- **No module content found** (`get_module_content` → `None`): treat as generation failure (cannot ground) → apology + Go-to-Module CTA.
- **Submit with no/stale `practice_active`:** return a clear error event (the round expired) instead of crashing; frontend shows a toast and offers Practice again.
- **LLM provider failure:** handled by the existing `ModelRouter` Azure→Groq fallback chain + circuit breaker; surfaces as the standard error path if all tiers fail.
- Practice grading is deterministic server-side; the answer key never reaches the client.

---

## 8. Testing

**Backend** (extend `tests/test_agent_*`):
- Router classifies the 3 intents from representative phrasings; ambiguous cases land sensibly.
- Hard gate: no plan / all-complete → graceful text, **never** a `PracticeEvent` or `ActionEvent` card.
- `generate_practice`: valid JSON → 5 well-formed MCQs; invalid → retry → fallback CTA; missing content → fallback.
- Verdict mapping: 5/4 → ready+take_evaluation; 3/2 → not_yet+go_to_module; 1/0 → study+go_to_module.
- `practice/submit`: grades correctly; clears `practice_active`; stale blob → error event.

**Frontend** (extend chat tests):
- `PracticeCard` renders questions, collects selections, submits.
- `ActionButtons`: correct `<Link>` targets for take_evaluation / go_to_module; practice_again re-sends.
- `chat-view` dispatches `practice` and `actions` turn fields.

---

## 9. Out of scope (YAGNI)

- Persisted practice history / analytics.
- Practising any module other than the current one.
- Practice affecting official completion, `attempts_to_pass`, or the evaluations endpoint.
- Reusing the authored bank for practice (explicitly chose Azure generation).

---

## 10. Rejected alternatives

- **Assessment rows with `is_practice=True`:** would require auditing every progress/completion query to exclude practice; high blast radius on the hardened progress derivation for no benefit.
- **Stateless / send the answer key to the client:** leaks the key and forces the server to trust client-graded correctness.
- **Hard gate inside the router:** the router doesn't receive `modules`; enforcing in `_dispatch` is the deterministic, correct location.
