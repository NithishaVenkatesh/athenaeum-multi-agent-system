export const meta = {
  name: 'author-assessments',
  description:
    'Author + adversarially review one assessment question bank per Athenaeum module (5 MCQ/MSQ + 3 LLM), grounded strictly on the module markdown. Returns validated bank JSON per module.',
  whenToUse:
    'Run to (re)generate per-module assessment question banks for ayanakoji/assessments. Pass args.modules (course_id, module_id, title, summary, objectives, grounded_skills, content_path).',
  phases: [
    { title: 'Author', detail: 'one author agent per module, grounded on the module markdown' },
    { title: 'Review', detail: 'review agent gates relevance/grounding/quality; fix loop on fail' },
  ],
}

// ── Structured-output schemas ────────────────────────────────────────────────
const CHOICE = {
  type: 'object',
  additionalProperties: false,
  required: ['id', 'module_id', 'prompt', 'kind', 'choices', 'correct_answers'],
  properties: {
    id: { type: 'string' },
    module_id: { type: 'string' },
    prompt: { type: 'string' },
    kind: { type: 'string', enum: ['mcq', 'msq'] },
    choices: { type: 'array', minItems: 4, maxItems: 4, items: { type: 'string' } },
    correct_answers: { type: 'array', minItems: 1, maxItems: 4, items: { type: 'string' } },
  },
}
const LLM = {
  type: 'object',
  additionalProperties: false,
  required: ['id', 'module_id', 'prompt', 'reference_answer'],
  properties: {
    id: { type: 'string' },
    module_id: { type: 'string' },
    prompt: { type: 'string' },
    reference_answer: { type: 'string' },
  },
}
const BANK_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['course_id', 'module_id', 'module_title', 'choices', 'llm'],
  properties: {
    course_id: { type: 'string' },
    module_id: { type: 'string' },
    module_title: { type: 'string' },
    choices: { type: 'array', minItems: 5, maxItems: 5, items: CHOICE },
    llm: { type: 'array', minItems: 3, maxItems: 3, items: LLM },
  },
}
const REVIEW_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['pass', 'relevance_ok', 'grounding_ok', 'quality_ok', 'issues'],
  properties: {
    pass: { type: 'boolean' },
    relevance_ok: { type: 'boolean' },
    grounding_ok: { type: 'boolean' },
    quality_ok: { type: 'boolean' },
    issues: { type: 'array', items: { type: 'string' } },
  },
}

// ── Shared standard (kept in sync with .claude/skills/assessment-authoring) ───
const STANDARD = `
AUTHORING STANDARD (follow exactly):
- Choices test: EXACTLY 5 questions. Each has EXACTLY 4 distinct options.
  - kind "mcq" => EXACTLY 1 correct option; kind "msq" => 2+ correct options.
  - Use a deliberate mix: about 3-4 mcq and 1-2 msq.
  - Distractors must be plausible and wrong for a real reason (common misconceptions,
    adjacent-but-different services, right idea/wrong context). No filler / joke / "none of the above".
  - Difficulty spread: >=1 recall/definition, most at application level, ideally one that
    distinguishes two things the module contrasts. Not trivial — skimming headings must NOT pass.
  - Every entry in correct_answers must appear VERBATIM in that question's choices.
- LLM test: EXACTLY 3 open-ended questions that demand a genuine explanation
  ("Explain why...", "Compare X and Y for...", "Walk through how you would..."). Each has a
  complete, correct reference_answer (~3-6 sentences) naming the specific services/steps/tradeoffs.
  Cover three DIFFERENT facets of the module.
- IDs (deterministic): choices => <module_id>-c01..-c05 ; llm => <module_id>-l01..-l03.
  Every nested module_id equals the module's id.
GROUNDING (critical): Use ONLY concepts, services, commands, limits and tradeoffs that the
module markdown EXPLICITLY discusses. Do NOT introduce outside Azure facts, pricing, or trivia
the module does not cover. If unsure a fact is in the module, do not ask about it.`

function authorPrompt(mod) {
  return `You are authoring the assessment question bank for ONE module of the Athenaeum learning platform.

Module: ${mod.module_id} — "${mod.title}" (course ${mod.course_id})
Summary: ${mod.summary}
Objectives: ${(mod.objectives || []).join(' | ')}
Grounded skills: ${(mod.grounded_skills || []).join(' | ')}

FIRST, use the Read tool to read the full module teaching content at:
${mod.content_path}
Ground every question and every answer key strictly in that text.

${STANDARD}

Return the bank as the structured object: course_id="${mod.course_id}", module_id="${mod.module_id}",
module_title="${mod.title}", 5 choices, 3 llm. Your structured output IS the deliverable.`
}

function reviewPrompt(mod, bank) {
  return `You are an adversarial reviewer of an assessment question bank for module ${mod.module_id} — "${mod.title}".

FIRST, use the Read tool to read the module's teaching content at:
${mod.content_path}

Then judge this candidate bank (JSON):
${JSON.stringify(bank)}

Gate on THREE criteria, being strict:
- relevance_ok: every question is about THIS module's subject (not the course in general).
- grounding_ok: every question AND every correct answer / reference answer is supported by the
  module text above. Anything requiring knowledge not in the module => grounding_ok=false.
- quality_ok: distractors are plausible, keys are unambiguously correct, mcq has exactly 1 correct
  and msq has 2+, difficulty is appropriate (NOT trivial / "too dumb"), prompts are unambiguous,
  there are exactly 5 choices (4 options each) and 3 llm with reference answers, ids follow
  <module_id>-c0N / -l0N.

pass = relevance_ok AND grounding_ok AND quality_ok. List every concrete problem in issues
(empty if pass). Be specific enough that an author can fix each item.`
}

function fixPrompt(mod, bank, review) {
  return `Revise the assessment bank for module ${mod.module_id} — "${mod.title}" to fix the reviewer's issues.

Module content to ground on (use the Read tool):
${mod.content_path}

Current bank (JSON):
${JSON.stringify(bank)}

Reviewer issues to resolve:
${review.issues.map((i) => '- ' + i).join('\n')}

${STANDARD}

Return the corrected full bank as the structured object (5 choices, 3 llm). Keep good questions;
only change what the issues require.`
}

// ── Per-module: author -> review -> (fix -> review)* up to 2 retries ──────────
async function authorOne(mod) {
  let bank = await agent(authorPrompt(mod), {
    label: `author:${mod.module_id}`,
    phase: 'Author',
    schema: BANK_SCHEMA,
  })
  if (!bank) return { module_id: mod.module_id, bank: null, review: null, attempts: 0 }

  let review = await agent(reviewPrompt(mod, bank), {
    label: `review:${mod.module_id}`,
    phase: 'Review',
    schema: REVIEW_SCHEMA,
  })

  let attempts = 1
  while (review && !review.pass && attempts <= 2) {
    const fixed = await agent(fixPrompt(mod, bank, review), {
      label: `fix${attempts}:${mod.module_id}`,
      phase: 'Author',
      schema: BANK_SCHEMA,
    })
    if (!fixed) break
    bank = fixed
    review = await agent(reviewPrompt(mod, bank), {
      label: `review${attempts + 1}:${mod.module_id}`,
      phase: 'Review',
      schema: REVIEW_SCHEMA,
    })
    attempts++
  }

  return { module_id: mod.module_id, course_id: mod.course_id, bank, review, attempts }
}

const modules = (args && args.modules) || []
log(`Authoring ${modules.length} module banks (5 MCQ/MSQ + 3 LLM each)…`)
const results = await parallel(modules.map((m) => () => authorOne(m)))

const passed = results.filter((r) => r && r.review && r.review.pass).length
const failed = results.filter((r) => r && (!r.review || !r.review.pass))
log(`Done. ${passed}/${results.length} passed review; ${failed.length} flagged.`)

return { results, passed, flagged: failed.map((r) => r && r.module_id) }
