# Per-Module Assessment Question Banks — Design

**Date:** 2026-06-14
**Status:** Approved (design); spec under review
**Project:** ayanakoji (Athenaeum learner workspace)

## 1. Problem & Goal

The Athenaeum catalog has **15 courses × 4 modules = 60 modules**. We need an
authored, static **question bank per module**, with two tests each:

- **Choices test** — exactly **5** questions; each is MCQ (one correct) or MSQ
  (two or more correct). Stored fields: question id, prompt, choices, correct
  choice(s), and the module it maps to.
- **LLM test** — **3** open-ended questions that require an explanation from the
  learner. Stored fields: question id, prompt (question), reference answer, and
  the module it maps to.

Totals: **300 choice questions + 180 LLM questions** across 60 modules.

The questions are **authored content committed to the repo** (authored by the
agent, grounded on each module's catalog metadata), not generated at app
runtime. They are seeded into a **separate SQLite DB** and mirrored to **Azure
Blob Storage**. The backend exposes query functions over the bank.

### Non-goals
- Wiring banks into a learner's live attempt flow (the existing
  `Assessment`/`ChoiceQuestion`/`LlmQuestion` per-learner tables in
  `app/courses/models.py`). Those are **not modified** by this work. Bank →
  attempt instantiation is a future seam.
- Grading/scoring logic. This work delivers the bank + query layer only.
- A frontend surface. Backend + content + pipeline + CI only.

## 2. Authored content: `ayanakoji/assessments/`

The "new subdir in ayanakoji". Pure content + schema, no Python.

```
ayanakoji/assessments/
  banks/<course_id>/<module_id>.json   # 60 files; each holds BOTH tests
  schema/bank.schema.json              # JSON Schema — validation source of truth
  README.md
```

### Module bank file shape (`banks/cb-c01/cb-c01-m01.json`)
```json
{
  "course_id": "cb-c01",
  "module_id": "cb-c01-m01",
  "module_title": "Hosting web APIs with Azure App Service",
  "choices": [
    {
      "id": "cb-c01-m01-c01",
      "module_id": "cb-c01-m01",
      "prompt": "…",
      "kind": "mcq",
      "choices": ["…", "…", "…", "…"],
      "correct_answers": ["…"]
    }
    // …5 total; mix of mcq and msq
  ],
  "llm": [
    {
      "id": "cb-c01-m01-l01",
      "module_id": "cb-c01-m01",
      "prompt": "Explain …",
      "reference_answer": "…"
    }
    // …3 total
  ]
}
```

### ID convention (deterministic, stable)
- Choice: `<module_id>-c<NN>` (`cb-c01-m01-c01` … `-c05`)
- LLM: `<module_id>-l<NN>` (`cb-c01-m01-l01` … `-l03`)

### Schema rules (enforced by `bank.schema.json` + tests)
- Exactly 5 questions with 4 `choices`, exactly 3 `llm`.
- `kind` ∈ {`mcq`,`msq`}; `mcq` ⇒ exactly 1 correct, `msq` ⇒ ≥2 correct.
- Each choice has 4 options; every `correct_answers` entry must appear in
  `choices`.
- All `module_id` fields match the file's module; ids unique within the file and
  follow the convention.
- `reference_answer` non-empty.

## 3. Separate database: `assessments.db`

- New setting `assessments_database_url` (env `ASSESSMENTS_DATABASE_URL`,
  default `sqlite:///./assessments.db`). **Separate engine** from `athenaeum.db`
  — the assessments package owns its own engine module mirroring `app/db.py`'s
  lifecycle (`configure_engine` / `get_engine` / `reset_engine` / `init_db` /
  `get_session` / `session_scope`) so tests can isolate it.
- Tables (new package `app/assessments/models.py`):
  - **`AssessmentBank`** — `id, course_id (idx), module_id (idx), kind, title`
    (120 rows: 2 per module: `choices` + `llm`).
  - **`BankChoiceQuestion`** — `id, bank_id (idx), course_id (idx),
    module_id (idx), prompt, choices[JSON], correct_answers[JSON], kind`.
  - **`BankLlmQuestion`** — `id, bank_id (idx), course_id (idx),
    module_id (idx), prompt, reference_answer`.
- **`loader.py`** — seeds the DB from the JSON banks. Deterministic and
  idempotent (clear-and-reload or upsert by id); mirrors the existing
  `scripts/generate_work_iq.py` determinism discipline.

## 4. Backend query layer: `app/assessments/`

```
app/assessments/
  __init__.py
  engine.py        # separate-DB engine lifecycle
  models.py        # the 3 tables above
  loader.py        # JSON banks -> assessments.db (idempotent)
  repository.py    # pure query functions over a Session
  router.py        # FastAPI endpoints (registered in app/main.py)
  azure_blob.py    # push/pull to Azure Blob
```

### Endpoints (each built+tested+smoked+committed independently)
- `GET /assessments/{assessment_id}` → the bank + its questions (404 if absent).
- `GET /assessments/by-module/{module_id}` → `{ module_id, assessment_ids: [...] }`.
- `GET /assessments/by-course/{course_id}` → `{ course_id, assessment_ids: [...] }`.

Responses use the project's existing envelope conventions (Pydantic schemas in
`app/assessments/router.py`, consistent with `app/courses/router.py`).

## 5. Azure Blob pipeline

- `azure_blob.py` — `push_banks()` uploads each module JSON to container
  `assessment-banks` at key `banks/<course>/<module>.json`; `pull_bank(module_id)`
  / `list_bank_keys()` for cloud reads.
- Auth via `DefaultAzureCredential` (no secrets in repo). New settings:
  `azure_storage_account` (env `AZURE_STORAGE_ACCOUNT`),
  `assessment_blob_container` (default `assessment-banks`).
- Adds `azure-storage-blob>=12` to the existing **optional `foundry`** dep group
  (not installed in the offline default env).
- Scripts:
  - `scripts/assessments_push.py` — author JSON → blob (the "pipeline to get it
    into azure").
  - `scripts/assessments_azure_smoke.py` — download from blob + schema-validate
    ("smoke from azure for the questions"). Credential-gated.

## 6. Authoring engine: skill + workflow + review agent

### Skill — `.claude/skills/assessment-authoring/SKILL.md`
Codifies the authoring standard:
- Ground **only** on the module's catalog `summary` / `objectives` /
  `grounded_skills`. No outside facts, no topics not explicitly in the module.
- 5 choice questions (4 options each): deliberate MCQ/MSQ mix, plausible
  distractors, difficulty spread (recall → application), no trick/ambiguous
  items, exactly-correct keys.
- 3 LLM questions: require genuine explanation; each has a complete, correct
  reference answer a grader can score against.
- The JSON schema, the id convention, and the per-module commit discipline.

### Workflow — `.claude/workflows/author-assessments`
Per-module pipeline (fan-out across 60 modules):
1. **Author agent** — reads the module's catalog metadata, emits the bank JSON
   (5 choices + 3 llm) following the skill.
2. **Review agent** (required) — gates the questions on:
   - **Relevance** to the module.
   - **Grounding** — purely and explicitly tied to topics discussed in the
     module; reject anything inferring beyond module content.
   - **Quality** — appropriately challenging ("not too dumb"), valid keys, clean
     distractors, schema-conformant.
   Returns pass/fail + specific fixes.
3. **Fix loop** — on fail, the author agent revises against the review feedback;
   re-review until pass (bounded retries).
4. Validated JSON written to `banks/…`; **commit per module**.

## 7. Tests, smoke, CI — applied to every step

- **Unit tests** (pytest, in `ayanakoji/backend/tests/`): schema validation,
  loader idempotency, repository functions, each endpoint, blob push/pull
  (mocked). Coverage stays ≥ 80% (CI gate).
- **In-session smoke**: `scripts/assessments_smoke.py` (build DB from JSON, query
  all three paths) run locally each step; `scripts/assessments_azure_smoke.py`
  run after the push step (credential-gated).
- **CI** (`.github/workflows/ci.yml`): the existing `backend` job already lints,
  type-checks, and tests the new package. Add a deterministic
  **bank-validation** step: validate all 60 JSON files against the schema and
  assert counts (5 choices + 3 llm/module), mirroring the existing Work IQ
  `git diff --exit-code` determinism check. Azure smoke is **not** in CI
  (credential-gated, manual).

## 8. Granular execution order

Each numbered item = implement → test script → in-session smoke → commit.

1. Scaffold `ayanakoji/assessments/` (dirs, `bank.schema.json`, README) +
   `assessment-authoring` skill file.
2. Separate-DB engine + models + loader (+ unit tests).
3. **Author all 60 modules** via the workflow (author → review → fix → commit
   per module).
4. Repository + `GET /assessments/{id}` endpoint (+ tests, smoke).
5. `GET /assessments/by-module/{module_id}` (+ tests, smoke).
6. `GET /assessments/by-course/{course_id}` (+ tests, smoke).
7. Azure Blob push pipeline (+ tests, local smoke).
8. Run push; **Azure smoke** (cloud read + validate).
9. CI bank-validation step.

## 9. Risks & mitigations

- **Question quality at scale (480 items).** Mitigated by the mandatory review
  agent + schema gate + per-module commits (easy to revise one module).
- **Grounding drift.** Review agent explicitly rejects anything beyond module
  content; author agent is given only the module's metadata.
- **Azure creds absent in CI/offline.** Blob steps are credential-gated and
  excluded from CI; everything else is fully offline-testable.
- **Two DBs in one process.** Isolated engine module + dependency override in
  tests prevents cross-contamination with `athenaeum.db`.
