---
title: Build Spec — Enterprise Learning Agent (exact code-level reference)
tags: [build-spec, reference, code, challenge-a, foundry, maf]
status: active
sources: [master-plan.md, foundry-iq-code.md, research-findings.md, verified web 2026-06-13 (MAF Workflows, Foundry Agent Service, Foundry Workflows, MS Learn MCP)]
updated: 2026-06-13
related: [master-plan, plan, decisions]
---

# Build Spec — exact code-level reference

> **Purpose.** The [master-plan.md](master-plan.md) decides *what/why*. This file is the *exact how* — precise enough to implement the whole system **with no additional context**. Every contract, signature, file path, SDK call pattern, and Definition-of-Done is here. Where an SDK surface is version-sensitive it is marked **⚠VERIFY** (confirm against the installed package in the hour-1 spike) — these are few and isolated behind adapters.
>
> **Principle:** strict types at every boundary (Pydantic v2), deterministic-over-LLM where a formula is exact, 3-tier fallback ending in a zero-credential mock, componentized prompts (<600 tok), one source of truth per fact.

---

## 1. Tech stack & versions

```
Python 3.11
# --- Foundry / Azure (the agents, IQ, telemetry, eval) ---
azure-ai-projects            # AIProjectClient: agents, threads, runs, telemetry, get_openai_client
azure-ai-agents              # agent definitions/tools (if split from projects) ⚠VERIFY which package owns PromptAgentDefinition/MCPTool
azure-identity               # DefaultAzureCredential
azure-search-documents       # Foundry IQ: KnowledgeBase + KnowledgeBaseRetrievalClient ⚠VERIFY version+api-version (align to installed; 2026-05-01-preview for activity log/effort, 2026-04-01 GA extractive)
azure-ai-evaluation          # evaluators (real class names — build-spec §13)
azure-ai-contentsafety       # input/output content safety
azure-ai-textanalytics       # PII detection (recognize_pii_entities)
azure-monitor-opentelemetry  # OTel → App Insights
# --- Orchestration spine (graph control in code) ---
agent-framework              # MAF: WorkflowBuilder, executors, edges ⚠VERIFY import surface
# --- App / infra ---
pydantic>=2                  # contracts
fastapi + uvicorn + jinja2   # thin UI (tabs + Admin Trace) — server-rendered + HTMX
httpx                        # MS Learn MCP (build-time) + any REST
sqlmodel / sqlite3           # state, cache, traces, BKT log (WAL)
# --- Dev / CI ---
pytest pytest-cov ruff mypy pip-audit gitleaks
pyrit ragas                  # EXTRA red-team/eval (OSS, local, $0)
```

**Config (frozen dataclass; fail loud on missing/placeholder — winner's `_is_placeholder`):**
```python
# src/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    foundry_project_endpoint: str
    azure_openai_endpoint: str
    search_endpoint: str
    model_workhorse: str = "gpt-4o-mini"        # forward: gpt-4.1-mini (retires 2026-10-01)
    model_reasoning: str = "o4-mini"            # ⚠VERIFY deployable on student sub; forward: current GA o-series (retires 2026-10-16)
    model_embed: str = "text-embedding-3-large"
    region: str = "eastus2"
    orchestrator: str = "maf"                   # "maf" | "python"
    force_mock_mode: bool = False               # zero-credential path
    work_iq_backend: str = "synthetic"          # "synthetic" | "mcp"
    fabric_iq_backend: str = "code"             # "code" | "fabric"
    capture_message_content: bool = False       # True only local-dev-synthetic (§19)
    model_config = {"env_file": ".env"}

def load_settings() -> Settings:
    s = Settings()
    for k, v in s.model_dump().items():         # fail loud on placeholders
        if isinstance(v, str) and v.startswith(("<", "TODO", "changeme")):
            raise RuntimeError(f"Config placeholder not set: {k}={v}")
    return s
```

---

## 2. Repo tree (exact)

```
msf-reasoning-agent/
├── README.md                      # rubric→evidence map + Honest Gaps + synthetic disclaimer
├── pyproject.toml                 # deps, ruff, mypy, pytest config
├── .env.example                   # placeholders only; .env git-ignored from commit 1
├── azure.yaml                     # azd app definition
├── infra/                         # Bicep (§14)
│   ├── main.bicep  main.parameters.json
├── .github/workflows/
│   ├── ci.yml                     # Lane 1 offline (every push)
│   └── safety.yml                 # Lane 2 credentialed live-safety (pre-submission)
├── docs/
│   ├── architecture.md  architecture.png   # diagram (embedded in README)
│   ├── demo_script.md             # golden-path video storyboard (§4A of master-plan)
│   ├── qna_playbook.md            # judge Q&A (master-plan §29.2)
│   └── lessons.md                 # incident log + meta-rules (first-class)
├── data/
│   ├── synthetic/                 # generated, committed
│   │   ├── learners.json  work_signals.json  cert_ontology.json
│   │   └── kb/ {enablement_guide.md, team_learning_report.md, workload_insights.md}
│   ├── mock/                      # Tier-3 deterministic fixtures (per cert)
│   └── demo/ personas.db          # pre-seeded demo personas + cached artifacts (§32)
├── src/
│   ├── config.py                  # §1
│   ├── contracts.py               # ALL Pydantic models (§3) — imported by everything, imports nothing
│   ├── orchestrator/
│   │   ├── graph_maf.py           # MAF WorkflowBuilder spine (CORE)
│   │   ├── graph_python.py        # plain-Python fallback (same trace)
│   │   ├── router.py              # triage + principal-bound role gate (§16/§18)
│   │   ├── handoff.py             # AgentHandoff, HandoffChainTracker
│   │   ├── circuit_breaker.py     # invocation/cost/turn caps + hang timeout (§5.6)
│   │   └── session.py             # SessionContext, context manager, SQLite state
│   ├── agents/
│   │   ├── base.py                # build_system_prompt + 3-tier fallback runner (§7)
│   │   ├── definitions/{agent}/   # role.md, constraints.md, examples/  (componentized)
│   │   ├── profiler.py curator.py study_plan.py engagement.py
│   │   ├── assessment_qgen.py readiness.py manager_insights.py
│   │   ├── grounding_verifier.py  # the Critic (evaluator-optimizer)
│   │   └── recommender.py          # EXTRA
│   ├── components/                # deterministic, no LLM (§13)
│   │   ├── skill_gap.py capacity.py allocator.py scorer.py risk.py
│   │   ├── slot_selector.py aggregator.py bkt.py
│   ├── iq/
│   │   ├── foundry_iq.py          # KB build + retrieve(citations, activity) + MCP wiring
│   │   ├── fabric_iq.py           # ontology-as-code engine (code|fabric backend)
│   │   ├── work_context.py        # WorkContextProvider (synthetic|mcp)
│   │   └── ms_learn.py            # MS Learn MCP client (build-time + additive)
│   ├── guardrails/
│   │   ├── pipeline.py            # orchestrator-owned; in+out (§15/§18)
│   │   ├── pii.py                 # 3-layer fail-closed
│   │   ├── injection.py           # regex pre-filter + model-based chunk scanner (quarantine)
│   │   └── rules.py               # G01..Gn guard classes
│   ├── obs/
│   │   ├── telemetry.py           # OTel enable + span attrs (§19)
│   │   └── trace.py               # TraceEvent append-only log + Admin-Trace data shape
│   ├── tools/                     # MCP/tool wrappers w/ 6-component descriptions, strict:true
│   ├── synth/                     # build-time generators (§11/§12)
│   │   ├── data_generator.py  schedule_synthesizer.py
│   └── app/                       # FastAPI thin UI (§ frontend)
│       ├── main.py templates/ {learner,assessment,manager,admin}.html
├── evals/
│   ├── dataset.jsonl              # ~30–40 CORE cases (→150 EXTRA)
│   ├── evaluators_offline.py      # rule-based (zero-credential)
│   └── run_eval.py                # azure-ai-evaluation harness
└── tests/                         # pytest; conftest forces FORCE_MOCK_MODE before import
    ├── conftest.py factories.py
    ├── test_contracts.py test_components_*.py test_guardrails_*.py
    ├── test_orchestrator.py test_injection_wiring.py test_circuit_breaker.py
```

---

## 3. Shared contracts (`src/contracts.py`) — the spine

All boundaries use these. `strict` Pydantic v2; `Field(description=...)` on every field (drives prompt format-instructions). Enums for closed sets.

```python
from enum import Enum
from pydantic import BaseModel, Field

class Role(str, Enum): CLOUD_ENG="Cloud Engineer"; DEVOPS="DevOps Engineer"; DATA_ENG="Data Engineer"
class CertId(str, Enum): AZ204="AZ-204"; AZ400="AZ-400"; DP203="DP-203"; AZ305="AZ-305"
class Slot(str, Enum): MORNING="Morning"; AFTERNOON="Afternoon"; EVENING="Evening"
class Verdict(str, Enum): GO="GO"; CONDITIONAL="CONDITIONAL_GO"; NOT_YET="NOT_YET"
class Severity(str, Enum): BLOCK="BLOCK"; WARN="WARN"; INFO="INFO"
class Principal(str, Enum): LEARNER="learner"; MANAGER="manager"  # bound pre-router (§16)

class LearnerProfile(BaseModel):
    learner_id: str; role: Role; target_cert: CertId
    current_skills: list[str] = Field(default_factory=list)
    experience_years: float = 0; stated_weekly_hours: float = Field(ge=0, le=40)

class SkillGap(BaseModel):
    skill: str; severity: float = Field(ge=0, le=1, description="1=no knowledge, 0=mastered")

class LearningResource(BaseModel):
    skill: str; title: str; citation: str = Field(description="【msg:src†source】 — required, never empty")
    summary: str

class WorkContext(BaseModel):
    employee_id: str; meeting_hours_per_week: float; focus_hours_per_week: float
    preferred_learning_slot: Slot

class CapacityProfile(BaseModel):
    weekly_study_hours: float; timeline_multiplier: float; preferred_slot: Slot

class StudyPlan(BaseModel):
    learner_id: str; total_hours: float; weekly_hours: float
    domain_allocation: dict[str, float]; weeks: int; explanation: str

class ReminderSlot(BaseModel): day: str; hour: int; duration_hours: float
class ReminderPlan(BaseModel):
    learner_id: str; slots: list[ReminderSlot]; message: str  # PLANNED, never sent

class Question(BaseModel):
    domain: str; text: str; options: list[str]; answer_index: int
    citation: str = Field(description="required — traces to KB")
class QuestionSet(BaseModel): cert: CertId; questions: list[Question]

class AssessmentResult(BaseModel):
    learner_id: str; cert: CertId; practice_score: float = Field(ge=0, le=100)
    domain_scores: dict[str, float]; hours_studied: float; hours_recommended: float
    domain_coverage_ratio: float = Field(ge=0, le=1)
class ReadinessReport(BaseModel):
    verdict: Verdict; weak_domains: list[str]; rationale: str  # numbers injected, not inferred

class RemediationPlan(BaseModel):
    learner_id: str; focus_domains: list[str]; extra_hours: float; revised_weeks: int

class RiskFlag(BaseModel):
    learner_id: str; risk: float = Field(ge=0, le=1); band: str  # high/medium/low
class TeamProgressReport(BaseModel):
    team_id: str; avg_score: float; completion_rate: float
    at_risk_count: int; capacity_constrained_count: int
class LearnerSummary(BaseModel):  # MINIMIZED manager projection (§14) — NO narratives/answers
    learner_id: str; role: Role; risk: float; band: str; status: str
class ManagerBrief(BaseModel): team_id: str; summary: str; flagged: list[LearnerSummary]

class AgentHandoff(BaseModel):                                   # §8.1
    task_id: str; original_goal: str; completed_work: str
    artifacts: list[str] = Field(default_factory=list)
    next_agent_instruction: str; context_mode: str = "compacted"
    handoff_depth: int = 0; max_depth: int = 3

class GuardrailResult(BaseModel): guard: str; severity: Severity; passed: bool; detail: str = ""
class TraceEvent(BaseModel):                                     # §19 — append-only
    timestamp: str; agent_name: str; tier_used: int             # 1=Foundry 2=OpenAI 3=Mock
    input_summary: str; output_summary: str
    guardrail_results: list[GuardrailResult] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    query_plan: list[dict] = Field(default_factory=list)        # Foundry IQ activity
    tokens: dict[str, int] = Field(default_factory=dict); loop_count: int = 0
    quarantined_chunks: int = 0

class SessionContext(BaseModel):
    session_id: str; principal: Principal; principal_role_verified: bool
    profile: LearnerProfile | None = None
    plan: StudyPlan | None = None; last_result: AssessmentResult | None = None
    replan_count: int = 0; trace: list[TraceEvent] = Field(default_factory=list)
```

**Output-schema rule:** every LLM agent's output is one of these models; the agent is called with `strict` structured output bound to that model. Downstream agents receive the validated instance, never raw text.

---

## 4. Orchestration spine

### 4.1 MAF graph (CORE) — `src/orchestrator/graph_maf.py`
```python
# ⚠VERIFY import surface against installed agent-framework
from agent_framework import WorkflowBuilder
from .router import triage, is_learner, is_manager
# Agent nodes wrap Foundry agents (agents/base.py run_agent → returns typed model).
# Function nodes wrap deterministic components. Both adapted to MAF Executor protocol.

def build_learner_workflow():
    b = WorkflowBuilder(start_executor=guardrails_in)
    b.add_edge(guardrails_in, triage)
    b.add_edge(triage, profiler, condition=is_learner)
    b.add_edge(profiler, gap_analyzer)
    b.add_edge(gap_analyzer, curator)
    b.add_edge(curator, grounding_verifier)        # evaluator-optimizer (max 2 re-query)
    b.add_edge(grounding_verifier, plan_fanout)
    b.add_edge(plan_fanout, study_plan); b.add_edge(plan_fanout, engagement)  # 1 superstep
    b.add_edge(study_plan, plan_join); b.add_edge(engagement, plan_join)      # barrier
    b.add_edge(plan_join, assessment_qgen)
    b.add_edge(assessment_qgen, grounding_verifier_a)
    b.add_edge(grounding_verifier_a, answer_gate)   # HITL (RequestInfoExecutor)
    b.add_edge(answer_gate, scorer)
    b.add_edge(scorer, readiness)
    b.add_edge(readiness, verdict_router)
    b.add_edge(verdict_router, cert_recommender, condition=is_go)
    b.add_edge(verdict_router, remediation, condition=is_not_yet)
    b.add_edge(remediation, study_plan, condition=loop_ok)   # ⟲ replan
    b.add_edge(remediation, escalate, condition=loop_exhausted)
    return b.build()
# Run: async for ev in workflow.run(input, stream=True): emit TraceEvent per ExecutorCompleted
```

### 4.2 Plain-Python fallback — `src/orchestrator/graph_python.py`
Identical logic, same `TraceEvent` stream. Selected by `settings.orchestrator=="python"` or when MAF import/run fails (auto-degrade, logged).
```python
from concurrent.futures import ThreadPoolExecutor
def run_learner(ctx: SessionContext) -> SessionContext:
    cb = CircuitBreaker(ctx)                       # §5.6, counts invocations (works in mock)
    ctx.profile = call(profiler, ctx, cb)
    gaps = skill_gap(ctx.profile)                  # deterministic
    resources = verify(curator, ctx, gaps, cb)     # evaluator-optimizer loop inside verify()
    with ThreadPoolExecutor(max_workers=2) as ex:  # fan-out (why not asyncio: agent-svc event loop)
        plan_f = ex.submit(study_plan, ctx, resources, cb)
        rem_f  = ex.submit(engagement, ctx, cb)
        ctx.plan, reminder = plan_f.result(), rem_f.result()
    while True:                                     # assessment + replan loop
        qset = verify(assessment_qgen, ctx, gaps, cb)
        answers = answer_gate(qset, ctx)            # HITL
        ctx.last_result = scorer(qset, answers)     # deterministic
        report = readiness(ctx, cb)
        if report.verdict in (Verdict.GO, Verdict.CONDITIONAL):
            ctx.recommendation = recommender(ctx, cb); break
        ctx.replan_count += 1
        if ctx.replan_count > 2: ctx.manager_flag = True; break   # loop counter (§5.5)
        ctx.plan = study_plan(ctx, remediation(ctx).focus_domains, cb)  # ⟲
    return ctx
```

### 4.3 Router + role gate — `src/orchestrator/router.py`
```python
def triage(ctx, msg) -> Principal:
    # ROLE IS BOUND TO THE AUTHENTICATED PRINCIPAL BEFORE THIS RUNS (§18).
    # The LLM classifier may only refine INTENT within the principal's allowed scope.
    if not ctx.principal_role_verified: raise PermissionError
    if ctx.principal == Principal.LEARNER: return Principal.LEARNER   # cannot self-elevate
    return classify_intent(msg)   # manager principal → manager|general
# Manager nodes ALSO hard-check ctx.principal==MANAGER at entry (defense in depth).
```

### 4.4 Circuit breaker — `src/orchestrator/circuit_breaker.py`
```python
class CircuitBreaker:
    MAX_INVOCATIONS=25; MAX_COST_USD=5.0; MAX_TOKENS=50_000
    def check(self):                       # counts INVOCATIONS (non-zero in mock → testable)
        if self.invocations>self.MAX_INVOCATIONS: raise CircuitBreakerTripped("turns")
        if self.cost>self.MAX_COST_USD or self.tokens>self.MAX_TOKENS: raise CircuitBreakerTripped("budget")
async def call_tool(fn,*a,timeout=30,**k):
    try: return await asyncio.wait_for(fn(*a,**k),timeout)   # hang = 52% of bad outcomes
    except asyncio.TimeoutError: return ToolError("hang_timeout")
```

---

## 5. Agent pattern (`src/agents/base.py`) + worked example

### 5.1 Componentized prompt + 3-tier fallback runner
```python
def build_system_prompt(agent: str, ctx: SessionContext) -> str:
    role = read(f"definitions/{agent}/role.md")           # <200 tok
    constraints = read(f"definitions/{agent}/constraints.md")  # <150 tok
    schema = OUTPUT_MODELS[agent].model_json_schema()
    examples = select_examples(agent, ctx.profile.target_cert, n=2)  # cert-specific
    return f"{role}\n\n{constraints}\n\nReturn JSON matching:\n{schema}\n\nExamples:\n{examples}"

def run_agent(agent, ctx, user_input, out_model, *, model, mcp_tools=None) -> BaseModel:
    sys = build_system_prompt(agent, ctx)
    for tier in (1,2,3):
        try:
            raw = TIERS[tier](sys, user_input, model, mcp_tools, out_model)  # Foundry|OpenAI|Mock
            obj = repair_and_validate(raw, out_model)     # 5-layer repair chain (§17 master-plan)
            trace(agent, tier, ctx, obj); return obj
        except Exception as e: log(agent, tier, e); continue
    raise AgentFailure(agent)   # never reached: tier 3 mock always returns a valid out_model
# Tier1: Foundry agent (create_version + responses.create); Tier2: direct AOAI json_schema;
# Tier3: data/mock/{agent}_{cert}.json deterministic fixture.
```

### 5.2 Worked vertical slice — Curator (`src/agents/curator.py` + definitions)
`definitions/curator/role.md`:
```
You are the Learning Path Curator. Given a learner's skill gaps, you return approved
learning resources for each gap. You ONLY recommend content found in the knowledge base.
```
`definitions/curator/constraints.md`:
```
- Call knowledge_base_retrieve BEFORE recommending anything.
- Every resource MUST carry a citation 【msg:src†source】 from the KB. No citation → omit it.
- If the KB has nothing for a gap, say so; never invent a resource.
- Output ONLY JSON matching the schema. No prose outside it.
```
`curator.py`:
```python
def curate(ctx, gaps: list[SkillGap]) -> list[LearningResource]:
    q = "Find approved learning resources for: " + ", ".join(g.skill for g in gaps)
    out = run_agent("curator", ctx, q, LearningResourceList,
                    model=settings.model_workhorse,
                    mcp_tools=["knowledge_base_retrieve"])   # Foundry IQ MCP, low effort
    return out.resources
```
Grounding Verifier wraps it (evaluator-optimizer):
```python
def verify(producer, ctx, *args, cb, max_rounds=2):
    for _ in range(max_rounds+1):
        out = producer(ctx, *args)
        verdict = run_agent("grounding_verifier", ctx, out.model_dump_json(),
                            VerifyResult, model=settings.model_workhorse)
        if verdict.verified: return out
        ctx.retry_hint = f"Uncited: {verdict.uncited_claims}. Re-query with citations."
    return out  # best effort after N; flagged in trace
```
**Curator DoD:** every returned `LearningResource.citation` is non-empty AND its source id exists in the retrieval set (offline citation-target check); KB-miss yields explicit "no approved resource"; mock tier returns a valid list with synthetic citations; one reject→re-query path demoable.

### 5.3 Remaining agents (same pattern; exact I/O, model, guards, DoD)
| Agent | In → Out | Model | Key guard | DoD |
|------|---------|-------|-----------|-----|
| Profiler | text → `LearnerProfile` | workhorse | role/cert ∈ registry else BLOCK | parses the 3 demo personas correctly |
| Assessment Q-Gen | gaps,cert → `QuestionSet` | reasoning | every Q cited; domain proportions ±1 | 10 Qs, all cited, proportional |
| Readiness | `AssessmentResult` → `ReadinessReport` | reasoning | number-match (no invented scores) | rationale numbers == scorer output |
| Study Plan | resources,capacity → `StudyPlan` | workhorse (narrate) | weekly_hours ≤ capacity (BLOCK) | schedule from allocator, not LLM |
| Engagement | plan,workctx → `ReminderPlan` | workhorse (narrate) | slots from slot_selector only | slots in preferred window; not sent |
| Manager Insights | report,flags → `ManagerBrief` | reasoning | only `LearnerSummary` projection; no names in prose | aggregate + own-team drill-down only |
| Grounding Verifier | any output → `VerifyResult` | workhorse | — | flags uncited claims correctly |
| Recommender (EXTRA) | profile,result → `NextCertRecommendation` | workhorse | cited | no speculative cert |

---

## 6. IQ layer

### 6.1 Foundry IQ — `src/iq/foundry_iq.py`
Build (once, P2) and retrieve. Based on verified recipes in [foundry-iq-code.md](../iq/foundry-iq-code.md). ⚠VERIFY api-version/class names against installed `azure-search-documents`.
```python
# BUILD: index(semantic config + vectorizer text-embedding-3-large) → AzureBlobKnowledgeSource
#        → KnowledgeBase(model=gpt-4o-mini, ANSWER_SYNTHESIS, answer_instructions="grounded ONLY...cite")
#        → MCP endpoint: {SEARCH}/knowledgebases/cert-kb/mcp?api-version=...
def retrieve(query, *, effort="low", source="cert-index-source"):
    res = kb_client.retrieve(KnowledgeBaseRetrievalRequest(
        messages=[...query...],
        knowledge_source_params=[SearchIndexKnowledgeSourceParams(
            knowledge_source_name=source, include_references=True)],
        include_activity=True,                      # query plan → TraceEvent (EXTRA/preview)
        retrieval_reasoning_effort=EFFORT[effort])) # GA path: extractive; effort = preview
    return Answer(text=join(res.response), citations=res.references,
                  query_plan=[a.as_dict() for a in (res.activity or [])])
# CORE = GA extractive + deterministic compose + citations; live query-plan = EXTRA (preview).
# If per-request effort doesn't flow via MCP → provision 2 KBs (low/medium).
```

### 6.2 Fabric IQ — `src/iq/fabric_iq.py` (code backend CORE)
```python
ONTOLOGY = load("data/synthetic/cert_ontology.json")   # entities/relationships/rules
def required_skills(cert)->list[str]: ...
def recommended_hours(cert)->int: ...
def pass_threshold(cert)->float: return ONTOLOGY[cert].get("pass_threshold", 75)
def skill_gap(skills, cert)->list[SkillGap]: ...        # set-diff + severity
def readiness(score,hours,cert)->Verdict: ...           # rule from ontology
# backend="fabric" (STRETCH): same signatures, query Fabric IQ Ontology (preview) — adapter only.
```

### 6.3 Work context — `src/iq/work_context.py`
```python
class WorkContextProvider:
    def get_context(self, employee_id) -> WorkContext: ...
# synthetic: read data/synthetic/work_signals.json ; mcp (STRETCH): ask_work_iq tool.
```

### 6.4 MS Learn MCP — `src/iq/ms_learn.py` (build-time + additive)
Build-time: `ms_learn_search`/`ms_learn_fetch` → real cert skill outlines → feed Synthetic Data Generator (§7). Additive runtime tool for Curator/Recommender (live, not persisted).

---

## 7. Synthetic data generators (build-time, offline)

### 7.1 `src/synth/data_generator.py`
```python
# 1. For each cert: ms_learn.fetch(cert) → real skill outline (factual skeleton)
# 2. Generate ORIGINAL synthetic prose docs grounded on outline (no copied text):
#    enablement_guide.md, team_learning_report.md, workload_insights.md
#    frontmatter: grounded_on: "<cert> skills outline, paraphrased"
# 3. Generate learners.json (≥10, incl. edge cases), cert_ontology.json, eval/dataset.jsonl
# 4. Validate: ID consistency, ranges (score 0-100, hours 5-40), obvious-fiction, license-diff vs source
```
Deterministic seed; output committed; never in request path.

### 7.2 `src/synth/schedule_synthesizer.py`
Generates `work_signals.json` — varied meeting/focus/slot distributions that exercise capacity rules (>20 meeting-h case, focus-rich case, each slot). Same shape real Work IQ returns.

---

## 8. Deterministic components (`src/components/`) — exact formulas
Carry the signatures from [master-plan.md](master-plan.md) §13 verbatim: `calculate_capacity`, `allocate_hours` (Largest Remainder), `score_readiness`, `score_risk`, `select_reminder_slots`, plus `bkt.update_mastery` (EXTRA) and `aggregator.aggregate_team`. Each is a pure function with a 1:1 unit test (`test_components_*.py`).

---

## 9. Guardrails (`src/guardrails/`) — orchestrator-owned
```python
# pipeline.run_in(text, ctx) -> raises GuardrailBlock | returns clean
#   G01 PII (3-layer fail-CLOSED §18)  G02 content-safety(F0)  G03 schema  G04 len  G05 loop-count(WARN)
# pipeline.run_out(obj, ctx) -> 
#   G10 citation-present  G11 citation-target-valid  G12 schema  G13 capacity-bound
#   G14 number-match  G15 PII-out(all agents)  G18 injection-scan(quarantine chunk)
# injection.py: regex pre-filter (HouYi 3-part) THEN model-based scanner → quarantine+flag (§15)
```
Every guard = its own class + its own test (`TestG01…`). No agent imports this module.

---

## 10. Observability (`src/obs/`)
`telemetry.enable(capture_message_content=settings.capture_message_content)`; span attrs per §19 (no separate reasoning-token attr — track `completion_tokens`). `trace.py` writes `TraceEvent` rows (PII-scrubbed) to SQLite; Admin-Trace tab reads them. Mock-first: trace renders rich data with zero credentials.

---

## 11. Frontend (`src/app/`) — FastAPI + Jinja/HTMX, thin & intentional
4 routes/tabs (master-plan §21): `/learner`, `/assessment`, `/manager`, `/admin`. Admin reads `TraceEvent` rows → renders hops, tier, query plans, per-hop tokens/cost, guardrail green/red, loop counter, quarantine flags. Runs under `FORCE_MOCK_MODE` (public try-it). No heavy SPA; server-rendered + HTMX for the live pipeline stream.

---

## 12. Infra (`infra/main.bicep`) + RBAC
Resources: AI Search **Standard**, Azure OpenAI (deploy `gpt-4o-mini`, reasoning model, `text-embedding-3-large`), AI Services + Foundry project, Storage (Blob), App Insights + Log Analytics, Container Apps env (EXTRA). Region `eastus2`. RBAC (managed identity): Cognitive Services OpenAI User; Search Index Data Reader/Contributor; Storage Blob Data Reader; Monitoring Metrics Publisher. `azd up` deploys; post-demo hook deletes RG (idle hygiene, §25). One $75 budget alert.

---

## 13. Eval (`evals/`)
`evaluators_offline.py` (zero-credential, CI default): `CitationPresent`, `CitationTargetValid`, `CapacityRespected`, `LoopBranchCorrect`, `SchemaConformance`, `NumberMatch`. `run_eval.py` (EXTRA, credentialed): real `azure.ai.evaluation` classes only — `GroundednessEvaluator`/`GroundednessPro`, `RelevanceEvaluator`, `CoherenceEvaluator`, `ToolCallAccuracyEvaluator`, `IntentResolutionEvaluator`, `TaskAdherenceEvaluator`, `IndirectAttackEvaluator`, `UngroundedAttributesEvaluator` (NOT the nonexistent ones — master-plan §20). `dataset.jsonl` ~30–40 CORE cases.
```jsonl
{"kind":"negative_rejection","query":"...not in KB...","expect":"i don't know"}
{"kind":"boundary","score":74,"hours":20,"cert":"AZ-204","expect_verdict":"NOT_YET"}
{"kind":"loop_escalation","fails":3,"expect_manager_flag":true}
{"kind":"capacity","meeting_hours":22,"expect_weekly_hours_lte":6}
```

## 14. CI (`.github/workflows/`)
`ci.yml` (every push, zero-cred): ruff → mypy → pytest(80%, FORCE_MOCK_MODE) incl. `test_injection_wiring` + `test_circuit_breaker` → offline eval gate → gitleaks → pip-audit → build. `safety.yml` (pre-submission, credentialed): XPIA + PyRIT vs real grounding path, CVSS gates block.

---

## 15. Build order checklist (Definition of Done per step)
1. **Scaffold + contracts** — `src/contracts.py` complete; `test_contracts.py` green; `.env.example`. ✅ when imports resolve and config fails-loud on placeholders.
2. **Mock tier** — `data/mock/` per cert; Tier-3 returns valid models for every agent. ✅ when `FORCE_MOCK_MODE` runs `run_learner` end-to-end, GO and NOT_YET paths, zero credentials.
3. **Deterministic components** — all formulas + 1:1 tests. ✅ when boundary cases pass.
4. **Orchestrator (both spines)** — `graph_python.py` first, then `graph_maf.py`; identical `TraceEvent` stream; `ORCHESTRATOR` flips cleanly. ✅ when `test_orchestrator.py` passes on both.
5. **Admin Trace + circuit breaker** — trace renders from mock; breaker trips in mock test. ✅ visible money shot with no creds.
6. **Foundry IQ** — KB built; Curator/Q-Gen grounded + cited; activity log captured. ✅ citation-target-valid passes on live retrieval.
7. **Guardrails + injection + PII** — pipeline in/out; quarantine works; PII fail-closed. ✅ injection-wiring test + PII tests green.
8. **Agents wired to Foundry (Tier 1/2)** — all 9; fallback verified. ✅ live run matches mock-shape.
9. **Eval offline + dataset** — ✅ all rule-based evaluators pass on dataset.
10. **Frontend tabs + demo personas + golden-path script** — ✅ video-able end-to-end.
11. **Submission artifacts** — README (rubric→evidence + Honest Gaps + synthetic disclaimer), diagram, video, public repo + secret scan, MS Learn usernames.
12. **EXTRAs** (only after 1–11 + video frozen): MAF-if-not-yet, live query-plan trace, real Fabric/Work IQ, A2A, hosted deploy, RAGAS/PyRIT/pass^k, cross-session memory + BKT.

---

*End of build spec. Pair with [master-plan.md](master-plan.md) (why/what). ⚠VERIFY tags = the only places needing a live SDK check; isolate them behind the adapters named above so a signature change is a one-file fix.*
