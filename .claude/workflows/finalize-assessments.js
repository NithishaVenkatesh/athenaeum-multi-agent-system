export const meta = {
  name: 'finalize-assessments',
  description:
    'Recovery pass for assessment banks: review-and-finalize already-authored candidate banks (cheap), and fully author the modules whose author agent failed. Returns a validated bank + review per module.',
  whenToUse:
    'Run after a partial author-assessments run. Pass args.items: {course_id, module_id, title, content_path, candidate_path?}. candidate_path => review/correct existing bank; absent => author fresh.',
  phases: [
    { title: 'Finalize', detail: 'review-and-correct candidate banks' },
    { title: 'Author', detail: 'author + review modules with no candidate' },
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
const BANK = {
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
const FINALIZE_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['bank', 'pass', 'relevance_ok', 'grounding_ok', 'quality_ok', 'issues'],
  properties: {
    bank: BANK,
    pass: { type: 'boolean' },
    relevance_ok: { type: 'boolean' },
    grounding_ok: { type: 'boolean' },
    quality_ok: { type: 'boolean' },
    issues: { type: 'array', items: { type: 'string' } },
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

const STANDARD = `
AUTHORING STANDARD (follow exactly):
- Choices test: EXACTLY 5 questions, each with EXACTLY 4 distinct options.
  kind "mcq" => EXACTLY 1 correct; kind "msq" => 2+ correct. Mix ~3-4 mcq and 1-2 msq.
  Distractors plausible and wrong for a real reason; no filler/joke options. Difficulty
  spread (>=1 recall, most application-level, ideally one contrast). Not trivial.
  Every correct_answers entry must appear VERBATIM in that question's choices.
- LLM test: EXACTLY 3 open-ended questions demanding a real explanation, each with a
  complete correct reference_answer (~3-6 sentences) naming specific services/steps/tradeoffs.
  Cover three DIFFERENT facets.
- IDs: choices => <module_id>-c01..-c05 ; llm => <module_id>-l01..-l03. Every nested
  module_id equals the module id.
GROUNDING: use ONLY concepts the module markdown EXPLICITLY discusses; no outside facts.`

function finalizePrompt(item) {
  return `You are reviewing and finalizing an already-drafted assessment bank for module ${item.module_id} — "${item.title}" (course ${item.course_id}).

Use the Read tool to read TWO files:
1. The module's teaching content: ${item.content_path}
2. The candidate bank to review: ${item.candidate_path}

Judge it strictly on relevance_ok, grounding_ok, quality_ok (mcq=1 correct, msq=2+, 5 choices
of 4 options, 3 llm with reference answers, ids <module_id>-c0N/-l0N, grounded only in the
module). ${STANDARD}

If the candidate is already correct, return it UNCHANGED as "bank" with pass=true and empty
issues. If it has fixable problems, CORRECT them and return the corrected bank, listing what you
changed in issues (still set the *_ok flags to reflect the FINAL bank you return, so pass=true
once corrected). Your returned "bank" must always be schema-valid.`
}

function authorPrompt(item) {
  return `You are authoring the assessment question bank for module ${item.module_id} — "${item.title}" (course ${item.course_id}).

FIRST use the Read tool to read the full module teaching content:
${item.content_path}
Ground every question and answer strictly in that text.
${STANDARD}

Return the bank object: course_id="${item.course_id}", module_id="${item.module_id}",
module_title="${item.title}", 5 choices, 3 llm.`
}

function reviewPrompt(item, bank) {
  return `Adversarially review this assessment bank for module ${item.module_id} — "${item.title}".
FIRST Read the module content: ${item.content_path}
Bank: ${JSON.stringify(bank)}
Gate strictly on relevance_ok, grounding_ok, quality_ok (definitions as standard). pass = all three.
List concrete issues (empty if pass).`
}

async function finalizeCandidate(item) {
  const r = await agent(finalizePrompt(item), {
    label: `finalize:${item.module_id}`,
    phase: 'Finalize',
    schema: FINALIZE_SCHEMA,
  })
  if (!r) return { module_id: item.module_id, course_id: item.course_id, bank: null, review: null }
  return {
    module_id: item.module_id,
    course_id: item.course_id,
    bank: r.bank,
    review: { pass: r.pass, relevance_ok: r.relevance_ok, grounding_ok: r.grounding_ok, quality_ok: r.quality_ok, issues: r.issues },
    source: 'finalized',
  }
}

async function authorFresh(item) {
  let bank = await agent(authorPrompt(item), { label: `author:${item.module_id}`, phase: 'Author', schema: BANK })
  if (!bank) return { module_id: item.module_id, course_id: item.course_id, bank: null, review: null }
  let review = await agent(reviewPrompt(item, bank), { label: `review:${item.module_id}`, phase: 'Author', schema: REVIEW_SCHEMA })
  let attempts = 1
  while (review && !review.pass && attempts <= 2) {
    const fixed = await agent(
      `Revise the bank for ${item.module_id} to fix these issues, grounding on ${item.content_path} (Read it):\n${(review.issues || []).map((i) => '- ' + i).join('\n')}\nCurrent: ${JSON.stringify(bank)}\n${STANDARD}\nReturn the corrected full bank.`,
      { label: `fix${attempts}:${item.module_id}`, phase: 'Author', schema: BANK },
    )
    if (!fixed) break
    bank = fixed
    review = await agent(reviewPrompt(item, bank), { label: `review${attempts + 1}:${item.module_id}`, phase: 'Author', schema: REVIEW_SCHEMA })
    attempts++
  }
  return { module_id: item.module_id, course_id: item.course_id, bank, review, source: 'authored' }
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
log(`Finalizing ${items.length} modules (${items.filter((i) => i.candidate_path).length} candidates, ${items.filter((i) => !i.candidate_path).length} fresh)…`)

const results = await parallel(
  items.map((it) => () => (it.candidate_path ? finalizeCandidate(it) : authorFresh(it))),
)
const passed = results.filter((r) => r && r.review && r.review.pass).length
log(`Done. ${passed}/${results.length} passed.`)
return { results, passed }
