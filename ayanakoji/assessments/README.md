# Assessment Question Banks

Authored, static **question banks** — one per Athenaeum catalog module. This
directory is *content + schema only* (no Python). The backend
(`backend/app/assessments/`) seeds these JSON files into a separate
`assessments.db` and mirrors them to Azure Blob Storage.

## Layout

```
assessments/
  banks/<course_id>/<module_id>.json   # 60 files (15 courses x 4 modules)
  schema/bank.schema.json              # JSON Schema — validation source of truth
  README.md
```

## What a bank holds

Each `<module_id>.json` carries **two tests** for one module:

- **Choices test** — exactly **10** questions, each MCQ (one correct) or MSQ
  (two or more correct), 4 options each.
- **LLM test** — exactly **3** open-ended questions, each with a reference
  answer for grading.

See [`schema/bank.schema.json`](schema/bank.schema.json) for the exact shape and
[`../../.claude/skills/assessment-authoring/SKILL.md`](../../.claude/skills/assessment-authoring/SKILL.md)
for the authoring standard.

## ID convention (stable, deterministic)

- Choice question: `<module_id>-c<NN>` (`cb-c01-m01-c01` … `-c10`)
- LLM question: `<module_id>-l<NN>` (`cb-c01-m01-l01` … `-l03`)

## Grounding rule

Questions are grounded **purely and explicitly** on the module's own teaching
content (`athenaeum/content/.../module-NN-*.md`, resolved by
`app.catalog.content.get_module_content`). Nothing is asked that the module does
not actually discuss.

## Validation

`backend/app/assessments/validation.py` validates every bank against the schema
*plus* semantic rules the schema can't express:

- `mcq` ⇒ exactly 1 correct; `msq` ⇒ ≥ 2 correct.
- every `correct_answers` entry appears verbatim in that question's `choices`.
- all ids unique within a file and matching the file's `module_id`.

CI runs this validation over all 60 banks (see `.github/workflows/ci.yml`).
