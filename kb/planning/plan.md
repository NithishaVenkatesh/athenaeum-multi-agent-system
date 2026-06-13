This is a full system design. Going deep on every dimension you listed.

Enterprise Learning Agent Framework — Full System Design
1. Agent Hierarchy (Extended)
The 5-agent starter kit suggestion collapses too many concerns into single agents. Proper decomposition separates LLM-calling agents from deterministic components, and separates reasoning from delivery.

Tier 0 — Orchestration
Entry Agent (Orchestrator)
The only agent the outside world talks to. Routes intent, assembles context, manages session state, owns the fail→replan loop decision. Calls sub-agents via typed contracts. Never does domain reasoning itself.

Context Manager (not an LLM agent — a service)
Reads/writes thread state to Foundry Agent Service. Assembles the SessionContext object passed to every agent. Owns the learner's running profile, current plan, assessment history, and loop count.

Tier 1 — Learner Path Agents
1. Learner Profiler
Free-text intake → structured LearnerProfile. The only agent that reads unconstrained natural language from the user. Outputs a Pydantic model: {learner_id, role, target_cert, current_skills[], experience_years, stated_weekly_hours}. This is the only LLM-calling intake step.

2. Skill Gap Analyzer (deterministic component, no LLM)
LearnerProfile.current_skills vs CertRequirements.required_skills from the Fabric IQ ontology → ordered SkillGap[] by priority. Pure set-difference + weighting logic. No LLM, no ambiguity, perfectly reproducible.

3. Learning Path Curator
SkillGap[] → Foundry IQ query → cited LearningResource[]. One agent, one responsibility: retrieve grounded content for each skill gap, return resources with source citations. Refuses to return anything not cited from the KB.

4. Study Plan Generator
LearningResource[] + CapacityProfile → StudyPlan. Calls the Largest Remainder allocator (deterministic, see §4). LLM role here is only to write the natural-language explanation of the plan — the schedule itself is computed.

5. Engagement Planner
StudyPlan + WorkContext → ReminderPlan. Deterministic slot selection (see §4). LLM writes the reminder message text. Does not send anything — outputs a ReminderPlan with timing and message content.

6. Assessment Question Generator
SkillGap[] + cert_id → QuestionSet (10 questions, domain-proportional). Queries Foundry IQ at medium reasoning effort. Every question must include its source citation. Output validated: all questions traceable to KB.

7. Assessment Scorer (deterministic component, no LLM)
QuestionSet + LearnerAnswers → AssessmentResult {score, domain_scores{}, hours_studied, hours_recommended}. Scoring formula (see §4). Outputs GO / CONDITIONAL_GO / NOT_YET verdict. Pure arithmetic.

8. Readiness Evaluator
Wraps Assessment Scorer output with reasoning narrative. Explains why the verdict was given, which domains are weak, what specifically needs work. LLM-written but grounded in the structured scores — no free hallucination possible because scores are pre-computed.

9. Remediation Planner
Called only on NOT_YET. Takes AssessmentResult.weak_domains[] → targeted RemediationPlan. Identifies which resources to revisit, how many additional hours needed, revised timeline. Calls back to Study Plan Generator with a reduced scope.

10. Certification Recommender
Called only on GO. LearnerProfile + AssessmentResult + Fabric IQ ontology → next certification recommendation with rationale. Foundry IQ grounded. No speculative suggestions.

Tier 2 — Manager Path Agents
11. Progress Aggregator (deterministic component, no LLM)
Aggregates individual AssessmentResult[] and StudyPlan[] across a team into TeamProgressReport {avg_score, completion_rate, at_risk_count, capacity_constrained_count}. Pure arithmetic aggregation.

12. Risk Scorer (deterministic component, no LLM)
Per-learner: risk_score = (1 - practice_score/100) × (1 - hours_studied/hours_recommended) × days_to_exam_weight. Outputs ranked RiskFlag[]. Formula-based, auditable, no LLM.

13. Manager Insights Agent
TeamProgressReport + RiskFlag[] → narrative manager brief. LLM writes the summary. Input is pre-computed structured data — LLM cannot hallucinate numbers because they're provided as facts, not inferred. Output: team-level narrative with no individual name exposure (IDs only, roles only).

Tier 3 — Infrastructure Agents
14. Grounding Verifier (Critic agent)
Called after Curator, Assessment Question Generator, and Readiness Evaluator. Checks every output for citation presence. Prompt: "Does each claim in this output trace to a cited source? Return {verified: bool, uncited_claims: []}." If uncited claims found → blocks output, triggers re-query with stricter grounding instructions. One specific job. Short prompt.

15. Guardrails Pipeline (not an LLM agent — a synchronous pipeline)
Runs before every agent input and after every agent output. See §6 for full spec.

Agent count summary
Type	Count	LLM-calling?
Orchestrator	1	Yes (routing)
Learner path	9	6 LLM + 3 deterministic
Manager path	3	1 LLM + 2 deterministic
Infrastructure	2	1 LLM (Verifier) + 1 pipeline
Total	15	9 LLM agents
2. Integration Map
Every integration listed with what it does, which agents use it, and how.

Microsoft Foundry Agent Service (azure-ai-projects)
Used by: all LLM-calling agents
What it does: agent runtime, thread/state persistence, LLM inference routing
Integration: AIProjectClient → create_agent → create_thread → create_run → poll or stream
Auth: DefaultAzureCredential + RBAC (Cognitive Services User role)
Foundry IQ — Azure AI Search Knowledge Base (azure-search-documents==12.1.0b1)
Used by: Curator, Assessment Question Generator, Grounding Verifier, Certification Recommender
What it does: retrieves grounded, cited answers from synthetic KB docs
Integration: MCP endpoint exposed as knowledge_base_retrieve tool; agents instructed to never answer outside KB
Reasoning effort: low for Curator (query planning), medium for Assessment (iterative refinement), include_activity=True always for trace
Auth: DefaultAzureCredential + Search Index Data Reader role
Microsoft Learn MCP Server
Used by: Curator (additive, not primary), Certification Recommender
What it does: live lookups of real Azure cert objectives, module lists — does not enter the KB, no redistribution
Integration: MCP tool call at agent level alongside knowledge_base_retrieve
Auth: public, no key required
Fabric IQ — Ontology Module (local)
Used by: Skill Gap Analyzer, Study Plan Generator, Assessment Scorer, Risk Scorer, Certification Recommender
What it does: defines entities (Learner, Certification, Role, SkillArea, StudyPlan, ReadinessThreshold), relationships, and rules as queryable Python objects
Integration: synchronous function calls — get_required_skills(cert_id), get_recommended_hours(cert_id), get_pass_threshold(cert_id), skill_gap(learner_skills, cert_id), readiness(score, hours, cert_id)
Cost: zero
Work IQ Provider Interface
Interface: WorkContextProvider.get_context(employee_id) → WorkContext
Backend A (real): Work IQ MCP ask_work_iq tool via npx @microsoft/workiq mcp — requires M365 tenant + Copilot license + admin consent
Backend B (synthetic fallback): reads data/synthetic/work_signals.json — same interface, same return type
Which backend is active: env var WORK_IQ_BACKEND=real|synthetic
Used by: Engagement Planner, Manager Insights Agent, Study Plan Generator (capacity inputs)
Azure Application Insights (OpenTelemetry)
Used by: all agents via project_client.telemetry.enable()
What it does: captures every LLM call, tool call, agent hop as a span with full prompt/response content
Integration: one enable() call at startup, everything else is automatic
Cost: Log Analytics ingestion ~$2-3/GB; demo workload is kilobytes
Azure AI Evaluation (azure-ai-evaluation)
Used by: eval harness (offline CI + live mode)
What it does: Coherence, Relevance, Groundedness evaluators + custom rule-based evaluators
Integration: evaluate(data="evals/dataset.jsonl", evaluators={...}) — runs offline for rule-based, needs Azure OpenAI for LLM-based
Cost: LLM-based evaluators cost a few cents per run at demo scale
Azure Content Safety
Used by: Guardrails Pipeline (input + output)
What it does: hate/violence/sexual/self-harm classification
Integration: ContentSafetyClient.analyze_text() with 5s timeout + regex fallback
Cost: $1.50 per 1,000 API calls — negligible
Azure AI Language (PII Detection)
Used by: Guardrails Pipeline (input only — before anything enters the system)
What it does: detects real names, emails, phone numbers, SSNs in user input
Integration: TextAnalyticsClient.recognize_pii_entities() with loggingOptOut=True
Cost: $1 per 1,000 records — negligible
Azure Blob Storage
Used by: Foundry IQ ingestion pipeline
What it does: stores synthetic KB documents; Foundry IQ auto-builds the ingestion pipeline from the container
Cost: cents at demo scale
3. Data Flow and Orchestration
Learner flow (step by step)

User input
  → Guardrails Pipeline (input: PII check, content safety, schema)
  → Entry Agent (intent classification: learner | manager | assessment)
  → Context Manager (load or create SessionContext)

[LEARNER PATH]
  → Learner Profiler → LearnerProfile (Pydantic)
  → Skill Gap Analyzer (deterministic) → SkillGap[]
  → Learning Path Curator (Foundry IQ) → LearningResource[]
  → Grounding Verifier (critic) → verified or re-query
  → [PARALLEL] Study Plan Generator ∥ Engagement Planner
      Study Plan Generator:
        → Capacity Calculator (deterministic) → CapacityProfile
        → Largest Remainder Allocator (deterministic) → StudySchedule
        → Plan Narrator (LLM) → StudyPlan with explanation
      Engagement Planner:
        → Slot Selector (deterministic) → ReminderSlots
        → Message Writer (LLM) → ReminderPlan
  → Context Manager (persist StudyPlan + ReminderPlan)
  → [LOOP ENTRY — repeatable]
  → Assessment Question Generator (Foundry IQ, medium effort) → QuestionSet
  → Grounding Verifier → verified QuestionSet
  → [USER ANSWERS QUESTIONS] — human-in-the-loop gate
  → Assessment Scorer (deterministic) → AssessmentResult + verdict
  → Readiness Evaluator (LLM narrates result) → ReadinessReport

  [BRANCH]
  GO → Certification Recommender → NextCertRecommendation
  NOT_YET → Remediation Planner → RemediationPlan
           → loop back to Study Plan Generator (targeted scope)
           → loop counter checked: if >2 loops, flag for manager

[MANAGER PATH — runs independently or triggered by loop-back flag]
  → Progress Aggregator (deterministic) → TeamProgressReport
  → Risk Scorer (deterministic) → RiskFlag[]
  → Manager Insights Agent (LLM) → ManagerBrief
  → Grounding Verifier (no fabricated numbers)

All outputs → Guardrails Pipeline (output: schema, citation check, content safety)
All LLM calls → OpenTelemetry span → Application Insights
All agent handoffs → append to session trace log
What runs in parallel
Study Plan Generator and Engagement Planner are independent once LearningResource[] and WorkContext are available. They do not share state. Run concurrently with ThreadPoolExecutor or asyncio.gather. The winner measured ~50% wall-clock reduction doing exactly this.

4. Algorithms — Deterministic Over LLM
These are places where a formula gives correct, auditable, reproducible results. Using an LLM here adds latency, cost, and variance for zero quality gain.

Capacity Calculator

def calculate_capacity(work_context: WorkContext) -> CapacityProfile:
    raw_hours = work_context.focus_hours_per_week
    # Workload rule from KB: >20 meeting hours → reduce study load
    if work_context.meeting_hours_per_week > 20:
        available = raw_hours * 0.6   # 40% overhead from heavy meeting load
        timeline_multiplier = 1.4
    elif work_context.meeting_hours_per_week > 15:
        available = raw_hours * 0.8
        timeline_multiplier = 1.2
    else:
        available = raw_hours * 0.9
        timeline_multiplier = 1.0
    return CapacityProfile(
        weekly_study_hours=min(available, 15),  # cap at 15h/week
        timeline_multiplier=timeline_multiplier,
        preferred_slot=work_context.preferred_learning_slot
    )
Largest Remainder Method (study hour allocation)
Allocates total study hours across skill areas without fractional days and without any area getting zero.


def allocate_hours(skill_gaps: list[SkillGap], total_hours: float) -> dict[str, float]:
    # Weight by gap severity (1.0 = no knowledge, 0.0 = mastered)
    weights = {g.skill: g.severity for g in skill_gaps}
    total_weight = sum(weights.values())
    # Exact quotas (float)
    quotas = {s: (w / total_weight) * total_hours for s, w in weights.items()}
    # Floor allocation — everyone gets their floor
    floors = {s: int(q) for s, q in quotas.items()}
    remainders = {s: quotas[s] - floors[s] for s in quotas}
    # Distribute leftover hours by largest remainder
    leftover = round(total_hours) - sum(floors.values())
    for skill in sorted(remainders, key=remainders.get, reverse=True)[:leftover]:
        floors[skill] += 1
    return floors
Readiness Scorer

def score_readiness(result: AssessmentResult, cert: Certification) -> Verdict:
    practice_ok = result.practice_score >= cert.pass_threshold        # default 75%
    hours_ok = result.hours_studied >= cert.recommended_hours
    score = (
        0.55 * (result.practice_score / 100) +
        0.25 * min(result.hours_studied / cert.recommended_hours, 1.0) +
        0.20 * result.domain_coverage_ratio
    )
    if practice_ok and hours_ok:
        return Verdict.GO
    elif score >= 0.65:
        return Verdict.CONDITIONAL_GO
    else:
        return Verdict.NOT_YET
Risk Scorer

def score_risk(learner: LearnerProgress, exam_date: date) -> float:
    days_remaining = (exam_date - date.today()).days
    days_weight = max(0, 1 - (days_remaining / 30))   # urgency increases within 30 days
    score_gap = max(0, (75 - learner.practice_score) / 75)
    hours_gap = max(0, (learner.hours_recommended - learner.hours_studied) / learner.hours_recommended)
    return (0.4 * score_gap + 0.4 * hours_gap + 0.2 * days_weight)
    # >0.6 = high risk, 0.3-0.6 = medium, <0.3 = low
Slot Selector

def select_reminder_slots(plan: StudySchedule, context: WorkContext) -> list[ReminderSlot]:
    slot_map = {"Morning": (8, 10), "Afternoon": (13, 15), "Evening": (17, 19)}
    start, end = slot_map[context.preferred_learning_slot]
    # Place reminders on days with allocated study hours, in preferred slot
    return [
        ReminderSlot(day=day, hour=start, duration_hours=hours)
        for day, hours in plan.daily_allocation.items()
        if hours > 0
    ]
5. Agent Componentization — No Long Prompts
Every agent is composed of four separate pieces assembled at runtime by the orchestrator. Nothing is hardcoded in a single blob.

Structure of every agent

agent_definition/
  {agent_name}/
    role.md          # 3-5 lines. Who this agent is, what it does, what it never does.
    constraints.md   # Grounding rules, output rules, refusal rules.
    output_schema.py # Pydantic model defining the exact output shape.
    examples/        # 2-3 few-shot examples as separate files, loaded dynamically.
The orchestrator assembles the system prompt at runtime:


def build_system_prompt(agent_name: str, context: SessionContext) -> str:
    role = load("role.md")
    constraints = load("constraints.md")
    schema = json_schema(output_models[agent_name])
    examples = load_examples(agent_name, n=2)
    return f"{role}\n\n{constraints}\n\nOutput schema:\n{schema}\n\nExamples:\n{examples}"
Role files stay under 200 tokens. Constraints stay under 150 tokens. Schema injection is automatic. Examples are selected based on the learner's cert, not hardcoded. Total system prompt: under 600 tokens per agent.

Why this matters
Prompts are version-controlled, diffable, independently testable
Examples can be swapped per cert without touching agent logic
Schema validation is enforced separately from the prompt
Each piece can be evaluated in isolation
6. Guardrails — Per Agent and Pipeline-Level
Pipeline-level (runs for every agent, every time)
Owned exclusively by the orchestrator. No agent imports or knows about the guardrails module.

Input guardrails (before any agent sees the input):

Guard	Method	Severity	Action on trigger
PII Detection	Regex → keyword-context → Azure AI Language	BLOCK	Reject, return "cannot process personal data"
Content Safety	Azure Content Safety API, 5s timeout, regex fallback	BLOCK	Reject input
Schema Validation	Pydantic .model_validate()	BLOCK	Reject with schema error
Input length	len(text) > MAX_CHARS	BLOCK	Truncate or reject
Loop count	session.replan_count > 2	WARN	Flag for manager, allow through
Output guardrails (after any agent returns):

Guard	Method	Severity	Action on trigger
Citation presence	Regex for citation pattern 【source†...】	BLOCK	Trigger re-query with stricter grounding instruction
Schema conformance	Pydantic .model_validate()	BLOCK	Retry agent once, then fall to mock
Capacity bounds	plan.weekly_hours <= capacity.available	BLOCK	Rerun allocator with correct bounds
PII in output	Same three-layer check	BLOCK	Strip or reject
Number hallucination	Output scores/hours match pre-computed values	BLOCK	Replace LLM narrative, use deterministic values
Per-agent specific guardrails
Learner Profiler: if role or cert not in SUPPORTED_ROLES / SUPPORTED_CERTS registry → BLOCK with "unsupported certification" message.

Learning Path Curator: every returned resource must have a citation. If any item in LearningResource[] has citation=None → Grounding Verifier blocks it, re-query with answer_instructions tightened to "cite every claim."

Assessment Question Generator: question count must match domain proportions within ±1. Questions without citations → BLOCK.

Assessment Scorer: scores must be arithmetic result of the formula, not LLM-generated numbers. The scorer is a pure function — it has no LLM call, so no hallucination is possible.

Manager Insights Agent: output must not contain learner names or raw IDs in narrative prose. Regex scan for EMP-\d+ in free-text sections → replace with role label.

7. Security and Auth
Credential management
DefaultAzureCredential everywhere — no API keys in code
.env git-ignored from first commit; .env.example committed with placeholder values
All secrets via environment variables; production uses Azure Key Vault references
Secret scan pre-push: GitHub push protection active on public repos; also run git log --all --full-history -- .env before going public
Container images for Hosted Agents: no credentials baked in; Entra managed identity assigned by Foundry Agent Service
RBAC roles required
Cognitive Services OpenAI User — Azure OpenAI inference
Search Index Data Reader + Search Index Data Contributor — Foundry IQ KB
Storage Blob Data Reader — blob source for KB ingestion
Monitoring Metrics Publisher — App Insights telemetry
What never goes into any store
Real names, emails, employee IDs, org names
Azure connection strings or keys
M365 tokens or Graph API tokens
Any content from real certification exams
8. PII — Three-Layer Detection
Identical to the winner's approach, verified as winning pattern:


Layer 1: Format regexes
  — email, phone, SSN, credit card, IP address patterns
  — runs synchronously, zero latency

Layer 2: Keyword-context regexes
  — "my name is X", "I work at X", "my ssn is X", "employee ID X"
  — catches conversational PII that format regexes miss

Layer 3: Azure AI Language PII API
  — only reached if layers 1+2 pass
  — `loggingOptOut=True` — Microsoft does not log the content
  — 5s timeout; if timeout → WARN not BLOCK (don't let Azure availability
    break the pipeline; log the timeout for review)
Any BLOCK at any layer → input rejected before it reaches any agent. Output checked for PII with the same pipeline, BLOCK severity.

9. Reliability and Fallback
Three-tier agent fallback (for every LLM-calling agent)

Tier 1: Foundry Agent Service SDK (azure-ai-projects)
  — managed agent + thread, full telemetry, citations via MCP

Tier 2: Direct Azure OpenAI (azure-openai)
  — same system prompt, same Pydantic output schema
  — `response_format={"type": "json_object"}`, temperature=0.2
  — no agent runtime, direct chat completion

Tier 3: Deterministic mock engine
  — reads from `data/mock/` fixture files
  — produces structurally valid outputs based on cert_id lookup
  — zero credentials, zero latency, zero cost
  — activates via FORCE_MOCK_MODE=true
All three tiers validate through the same Pydantic schema. Downstream agents cannot tell which tier ran. The demo can never fail because Tier 3 always works.

LLM response cache
SHA-256(tier + model + system_prompt + user_message) → cached response. Cache hits return instantly with no API call. Cache failures (read error, malformed) never break the pipeline — they just miss and call the API. SQLite WAL mode for the cache store.

Schema evolution
Every *_from_dict deserializer has a whitelist filter — unknown keys from older stored records are silently dropped, not raised as errors. Old SQLite rows survive schema changes.

10. Observability
Tracing

# One call at startup
project_client.telemetry.enable(
    destination="azuremonitor",
    capture_message_content=True   # full prompts + responses in spans
)
Every agent hop emits: span name, input messages, output, tool calls, token counts, latency, tier used (1/2/3), loop count.

Foundry IQ activity log
Every KB query with include_activity=True returns the query plan — what subqueries the planner generated, which sources answered. Persist this alongside the agent output:


result = kb_client.retrieve(..., include_activity=True)
trace_log.append({
    "agent": "curator",
    "query_plan": [a.as_dict() for a in result.activity],
    "citations": result.references
})
This is the visible multi-step reasoning the rubric rewards. Surface it in the demo.

Append-only session trace
Every agent invocation appends a TraceEvent to a session-scoped log:


@dataclass
class TraceEvent:
    timestamp: str
    agent_name: str
    tier_used: int        # 1=Foundry, 2=OpenAI, 3=Mock
    input_summary: str    # truncated, no PII
    output_summary: str
    guardrail_results: list[GuardrailResult]
    citations: list[str]
    loop_count: int
Queryable at the end of a session. Surfaced in demo as a trace timeline.

11. Evaluation Harness
Offline eval (no credentials needed)
Rule-based evaluators run in CI with zero Azure calls:


class CitationPresentEvaluator:
    def __call__(self, *, response, **_):
        has_citation = bool(re.search(r'【\d+:\d+†.+?】', response))
        return {"citation_present": int(has_citation), "score": float(has_citation)}

class CapacityRespectedEvaluator:
    def __call__(self, *, plan, capacity, **_):
        ok = plan.weekly_hours <= capacity.available_hours
        return {"capacity_respected": int(ok), "score": float(ok)}

class LoopBranchCorrectEvaluator:
    def __call__(self, *, score, threshold, verdict, **_):
        expected = "GO" if score >= threshold else "NOT_YET"
        correct = verdict == expected
        return {"branch_correct": int(correct), "score": float(correct)}
Live eval (with Azure OpenAI)

from azure.ai.evaluation import evaluate, CoherenceEvaluator, GroundednessEvaluator

evaluate(
    data="evals/dataset.jsonl",
    evaluators={
        "coherence": CoherenceEvaluator(model_config),
        "groundedness": GroundednessEvaluator(model_config),
        "citation": CitationPresentEvaluator(),
        "capacity": CapacityRespectedEvaluator(),
        "loop_branch": LoopBranchCorrectEvaluator(),
    },
    output_path="evals/results.json"
)
Dataset structure

{"learner_profile": {...}, "expected_plan_max_weekly_hours": 10, "expected_resources_min": 3}
{"question": "...", "answer": "...", "must_cite": true, "source_doc": "enablement_guide"}
{"score": 60, "hours": 15, "cert": "AZ-204", "expected_verdict": "NOT_YET"}
Minimum 10 cases per evaluator type. All cases are synthetic. Checked into repo.

12. Synthetic Data Synthesis — Systematic Approach
Synthetic data is generated programmatically from a schema, not typed by hand. This ensures:

Internal consistency (same IDs everywhere)
Correct ranges (scores between 0-100, hours between 5-40)
Deliberate coverage of edge cases (exactly-at-threshold, capacity-constrained, high-risk)

data/synthetic/
  learners.json           # 10 learner profiles covering all roles + certs
  work_signals.json       # 10 work context records, varied meeting/focus hours
  cert_ontology.json      # Fabric IQ seed: certs, skills, thresholds, hours
  kb/
    enablement_guide.md   # "approved content" doc 1
    team_learning_report.md
    workload_insights.md
Edge cases to cover deliberately: learner at exactly 75% (boundary), learner with 22+ meeting hours (workload rule trigger), learner who's studied enough hours but score is low, learner who's passed and needs next cert recommendation, team with mixed pass/fail distribution.

13. Cost — Full Breakdown
All estimates for a 3-day hackathon build + demo workload (~500 agent runs total).

Service	What drives cost	Estimate
Azure AI Search Standard S1	Hourly, 72 hours	~$25
Azure OpenAI text-embedding-3-large	KB ingestion, ~50 docs	<$0.01
Azure OpenAI gpt-4o-mini	KB synthesis, eval calls	~$1-2
Azure OpenAI gpt-4o	LLM-calling agents, 500 runs	~$5-10
Azure Content Safety	~500 input + output checks	~$1
Azure AI Language PII	~500 input checks	~$0.50
App Insights / Log Analytics	Trace data at demo scale	~$0.50
Azure Blob Storage	KB docs ~10MB	~$0.01
Total		~$35–40
All covered by Azure credits. Azure for Students ($100) has room to spare. The AI Search Standard tier is the only significant cost and it's hourly — provision when building, delete when done. Reprovisioning for demo takes ~5 minutes.

Work IQ without a tenant: $0. Fabric IQ as ontology-as-code: $0.

14. Rubric Mapping — What Each Design Decision Scores
Accuracy & Relevance (25%)
Meeting every submission requirement (multi-agent ✓, Foundry ✓, IQ layer ✓, synthetic data ✓)
Foundry IQ grounds every factual claim → citations prevent hallucination
Pydantic contracts at every boundary → type-correct outputs
Deterministic scorers and allocators → arithmetically correct plans
Reasoning & Multi-step Thinking (25%)
15-component pipeline with visible handoffs
Fail→replan loop is observable and logged
Foundry IQ query plans (include_activity=True) surface subquery reasoning
Parallel Study Plan + Engagement Planning shows orchestration
Grounding Verifier is a demoable Critic pattern
Remediation Planner is a demoable self-reflection pattern
Reliability & Safety (20%)
Three-tier fallback: demo cannot fail, zero-credential mock mode always works
17-guard pipeline at every boundary
Three-layer PII detection
Citation-or-refuse: agents cannot hallucinate answers
Schema validation on every inter-agent handoff
Evaluation harness: citation, capacity, loop-branch correctness
Honest documentation of what's real vs synthetic
Creativity & Originality (15%)
Largest Remainder Method for study allocation (deterministic, correct, novel for a hackathon)
Weighted readiness formula with three components
Tri-tier fallback architecture
Grounding Verifier as an explicit Critic agent
Skill Gap Analyzer as a deterministic ontology query, not an LLM guess
Risk Scorer with urgency-weighted formula
UX & Presentation (15%)
You said you're not into UI — the deliverable is the CLI transcript and the 5-min video
Demo script: run the full e2e flow end to end, show the trace log, show one Foundry IQ query plan, show the loop-back branch triggering
Trace timeline surfaced in demo output — judges inspect reasoning, not just results
README maps every rubric criterion to implementation evidence explicitly
15. Things the Rubric Implies But Doesn't Say Explicitly
These are patterns the winner used and the rubric rewards indirectly:

Honest Gaps section in README — under Reliability & Safety. Judges reward honesty (synthetic Work IQ, no real tenant) over claiming things that aren't there.

Q&A playbook / decisions doc — pre-answers the questions judges will ask ("why SQLite not Postgres?", "why ThreadPoolExecutor not asyncio?", "why ontology-as-code for Fabric IQ?"). Eliminates uncertainty in judging.

lessons.md — incident log of what broke, root cause, fix, prevention rule. This is evidence of engineering discipline, which Microsoft's rubric language ("observable, debuggable") rewards directly.

Loop counter visible to manager — if a learner has gone through the fail→replan loop more than twice, the Manager Insights Agent gets flagged. This shows the multi-agent system has cross-agent state awareness, which directly demonstrates "multi-step decision making across agents."

Zero-credential mock mode — makes the demo live-safe and lets any judge run it themselves without Azure access. The winner's community vote advantage was partly because anyone could try it immediately.

Generalise one axis beyond the brief — the winner covered 9 cert families instead of 1. The equivalent here: make the ontology registry-driven so adding a new cert is one JSON entry, not a code change. Shows it's a system, not a demo.
