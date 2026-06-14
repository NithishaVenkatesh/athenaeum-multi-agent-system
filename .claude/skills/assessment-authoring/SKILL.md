---
name: assessment-authoring
description: >
  Author module assessment question banks for the Athenaeum learner workspace — a
  10-question MCQ/MSQ "choices" test and a 3-question open-ended "LLM" test per module,
  as one JSON file grounded purely on that module's own teaching content. Use this skill
  whenever a task says "author the assessment", "write questions for a module", "generate
  the question bank", "build the module test", or hands you a module id to make questions
  for. Always use it so every bank hits the same grounding, difficulty, and schema bar.
---

# Assessment Authoring

You are authoring the **assessment question bank** for one Athenaeum module. The
output is a single JSON file that two tests live in: a **choices test** (5 MCQ/MSQ
questions) and an **LLM test** (3 open-ended questions with reference answers). A
learner takes these to prove they actually understood the module; a later grader
cites the `correct_answers` / `reference_answer` as ground truth. Weak, generic, or
off-module questions fail that job.

## The prime directive: ground only on what the module actually teaches

Your single source of truth is **the module's own markdown body**, resolved by
`app.catalog.content.get_module_content(module_id)` (also readable at
`ayanakoji/athenaeum/content/<vertical>/<course>/module-NN-*.md`). The catalog
`objectives` / `grounded_skills` tell you scope; the **markdown body is what was
actually discussed**.

- **Only ask about concepts, services, commands, limits, and tradeoffs that the
  module text explicitly discusses.** If the body never mentions it, it is out of
  bounds — even if it is "obviously related" Azure knowledge.
- Do **not** import outside facts, pricing, SLAs, or trivia the module doesn't cover.
- Do **not** invent fake limits/numbers. If you assert a concrete fact in a key or
  reference answer, the module must support it.
- Reuse the module's own fictional scenarios/entities where natural; keep any new
  ones obviously fictional (e.g. "Northwind Logistics", "the `orders-ingest` job").

If you find yourself reaching for knowledge not in the body, stop and pick a
concept the module does teach.

## What you produce

One JSON object conforming to `ayanakoji/assessments/schema/bank.schema.json`.
Write it to `ayanakoji/assessments/banks/<course_id>/<module_id>.json`.

```json
{
  "course_id": "cb-c01",
  "module_id": "cb-c01-m01",
  "module_title": "<exact module title>",
  "choices": [ /* exactly 10 */ ],
  "llm":     [ /* exactly 3 */ ]
}
```

### ID convention (deterministic — do not improvise)
- Choice questions: `<module_id>-c01` … `<module_id>-c10`
- LLM questions:    `<module_id>-l01` … `<module_id>-l03`

## The choices test — 10 questions

Each question: `{ id, module_id, prompt, kind, choices[4], correct_answers[] }`.

- **`kind`**: `"mcq"` = exactly **one** correct option; `"msq"` = **two or more**
  correct. Use a deliberate **mix**: aim for ~6–7 MCQ and ~3–4 MSQ per bank. MSQ is
  for "select all that apply" concepts the module genuinely presents as a set.
- **4 options** each, all distinct, all plausible to someone who skimmed the module.
- **Distractors must be plausible and wrong for a real reason** — common
  misconceptions, adjacent-but-different services, right idea/wrong context. No
  filler ("None of the above", joke options, obviously-absurd choices).
- **Difficulty spread** across the 5: at least one recall/definition, most at
  application/"which would you use and why" level, ideally one that requires
  distinguishing two things the module contrasts. Not too dumb — a learner who only
  read headings should not pass.
- Every entry in `correct_answers` must appear **verbatim** in that question's
  `choices`. MCQ has 1 correct; MSQ has ≥2.

## The LLM test — 3 questions

Each: `{ id, module_id, prompt, reference_answer }`.

- The **prompt** demands a genuine explanation: "Explain why…", "Compare X and Y
  for…", "Walk through how you would…", "A team hits <situation from the module> —
  what's happening and how do you fix it?". Not answerable with one word.
- The **reference_answer** is a complete, correct answer (≈3–6 sentences) covering
  the points a grader should look for. It must be fully supported by the module and
  specific enough to grade against — name the services/steps/tradeoffs, not vague
  generalities.
- Cover three *different* facets of the module; don't ask the same thing three ways.

## Self-review before you emit (you are also graded by a review agent)

A separate review agent will reject the bank unless it passes all three. Pre-check
yourself:

1. **Relevance** — every question is about this module's subject, not the course
   in general.
2. **Grounding** — every question and every key/reference answer is supported by
   the module's markdown body, with nothing requiring outside knowledge.
3. **Quality** — distractors are plausible, keys are unambiguously correct, MSQ/MCQ
   `kind` matches the number of correct answers, difficulty is appropriate (not
   trivial), prompts are clear and unambiguous, and the JSON conforms to the schema
   (10 choices, 3 llm, 4 options each, ids correct).

If anything fails, fix it before writing the file.

## Commit discipline

Author and validate **one module at a time**, then commit that single file:

```
feat(assessments): author question bank for <module_id> (<module_title>)
```

Never batch many modules into one commit — per-module commits keep each bank
independently reviewable and revertible.
