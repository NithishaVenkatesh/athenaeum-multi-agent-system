export const meta = {
  name: 'augment-assessments',
  description:
    'Add 5 MORE distinct MCQ/MSQ questions (ids c06-c10) to each module bank, grounded on the module markdown and NOT overlapping the existing 5. Author + adversarial review. Returns the 5 new questions per module.',
  whenToUse:
    'Run to expand each choices test from 5 to 10 questions. Pass args.items: {course_id, module_id, title, content_path, bank_path}.',
  phases: [
    { title: 'Author', detail: 'author 5 new non-overlapping questions per module' },
    { title: 'Review', detail: 'review grounding/quality/non-duplication; fix loop' },
  ],
}

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
const NEW_CHOICES_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['new_choices'],
  properties: {
    new_choices: { type: 'array', minItems: 5, maxItems: 5, items: CHOICE },
  },
}
const REVIEW_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['pass', 'relevance_ok', 'grounding_ok', 'quality_ok', 'no_overlap_ok', 'issues'],
  properties: {
    pass: { type: 'boolean' },
    relevance_ok: { type: 'boolean' },
    grounding_ok: { type: 'boolean' },
    quality_ok: { type: 'boolean' },
    no_overlap_ok: { type: 'boolean' },
    issues: { type: 'array', items: { type: 'string' } },
  },
}

const STANDARD = `
STANDARD for the 5 NEW questions (ids <module_id>-c06 .. -c10, in order):
- Each has EXACTLY 4 distinct options. kind "mcq" => EXACTLY 1 correct; "msq" => 2+ correct.
  Across the 5 new ones use a mix (~3 mcq, ~2 msq).
- Distractors plausible and wrong for a real reason; no filler/joke options. Vary difficulty;
  not trivial — skimming headings must not pass.
- Every correct_answers entry appears VERBATIM in that question's choices. module_id is the module id.
GROUNDING: use ONLY concepts the module markdown EXPLICITLY discusses; no outside facts.
NON-OVERLAP: the 5 new questions must test DIFFERENT facts/concepts than the existing 5 — do not
rephrase or re-key an existing question. Prefer corners of the module the existing 5 didn't cover.`

function authorPrompt(item) {
  return `You are adding 5 NEW multiple-choice/multiple-select questions to an existing assessment bank for module ${item.module_id} — "${item.title}" (course ${item.course_id}).

Use the Read tool to read TWO files:
1. The module's teaching content: ${item.content_path}
2. The EXISTING bank (its 5 current questions are c01..c05): ${item.bank_path}

Author 5 NEW questions with ids ${item.module_id}-c06 through ${item.module_id}-c10.
${STANDARD}

Return ONLY the 5 new questions as "new_choices". Do NOT repeat or restate any of the existing c01..c05.`
}

function reviewPrompt(item, newChoices) {
  return `Adversarially review 5 NEW assessment questions for module ${item.module_id} — "${item.title}".

Read the module content: ${item.content_path}
Read the existing bank (c01..c05): ${item.bank_path}

Candidate NEW questions (should be c06..c10):
${JSON.stringify(newChoices)}

Gate strictly:
- relevance_ok: each is about this module's subject.
- grounding_ok: each question and every correct answer is supported by the module text.
- quality_ok: 4 options each, mcq has exactly 1 correct and msq 2+, plausible distractors,
  unambiguous, not trivial, ids are c06..c10 in order.
- no_overlap_ok: none of the 5 duplicates or merely rephrases an existing c01..c05 question.
pass = all four true. List concrete issues (empty if pass).`
}

function fixPrompt(item, newChoices, review) {
  return `Revise the 5 NEW questions for module ${item.module_id} to fix the reviewer's issues.
Read the module content: ${item.content_path}
Read the existing bank (c01..c05) to avoid overlap: ${item.bank_path}
Current new questions: ${JSON.stringify(newChoices)}
Issues to fix:
${(review.issues || []).map((i) => '- ' + i).join('\n')}
${STANDARD}
Return the corrected 5 new questions as "new_choices" (ids c06..c10).`
}

async function augmentOne(item) {
  let out = await agent(authorPrompt(item), {
    label: `author:${item.module_id}`,
    phase: 'Author',
    schema: NEW_CHOICES_SCHEMA,
  })
  if (!out) return { module_id: item.module_id, course_id: item.course_id, new_choices: null, review: null }
  let newChoices = out.new_choices

  let review = await agent(reviewPrompt(item, newChoices), {
    label: `review:${item.module_id}`,
    phase: 'Review',
    schema: REVIEW_SCHEMA,
  })
  let attempts = 1
  while (review && !review.pass && attempts <= 2) {
    const fixed = await agent(fixPrompt(item, newChoices, review), {
      label: `fix${attempts}:${item.module_id}`,
      phase: 'Author',
      schema: NEW_CHOICES_SCHEMA,
    })
    if (!fixed) break
    newChoices = fixed.new_choices
    review = await agent(reviewPrompt(item, newChoices), {
      label: `review${attempts + 1}:${item.module_id}`,
      phase: 'Review',
      schema: REVIEW_SCHEMA,
    })
    attempts++
  }
  return { module_id: item.module_id, course_id: item.course_id, new_choices: newChoices, review, attempts }
}

let parsed = args
if (typeof parsed === 'string') {
  try {
    parsed = JSON.parse(parsed)
  } catch (e) {
    parsed = null
  }
}
const items = Array.isArray(parsed) ? parsed : (parsed && parsed.items) || []
log(`Augmenting ${items.length} module banks with 5 new choices each…`)
const results = await parallel(items.map((it) => () => augmentOne(it)))
const passed = results.filter((r) => r && r.review && r.review.pass).length
log(`Done. ${passed}/${results.length} passed review.`)
return { results, passed }
