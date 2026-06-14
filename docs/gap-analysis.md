# Gap Analysis — implemented vs planned

Date: 2026-06-13. Compares the shipped Ayanakoji app against the Challenge A brief
([kb/challenge/challenge-a-brief.md](../kb/challenge/challenge-a-brief.md)) and the
master plan ([kb/planning/master-plan.md](../kb/planning/master-plan.md)).

## Brief's 7-step learner loop — coverage

| Step | Brief | Status | Notes |
|---|---|---|---|
| 1 | Learner provides topics | ✅ Done | Chat entry; greeting + intent routing |
| 2 | Learning Path Curator (grounded content for goals/role) | 🟡 Partial | Foundry-IQ-pattern grounding + course recommendation are in; no explicit skill-gap → resource curation step |
| 3 | Study Plan Generator (schedule from content, workload-aware) | ✅ Done | Calendar-grounded, pace, module-level, sequential, deadlines |
| 4 | Engagement Agent (reminders adapt to work patterns/focus windows) | 🟡 Partial | Sessions are placed in real focus windows; no separate reminder-plan artifact |
| 5 | Assessment Agent (grounded cited questions, readiness) | ❌ Not built | Biggest gap. Module completion is a manual stub, not a test |
| 6 | Pass → advance / Fail → loop back | ❌ Not built | Depends on the assessment + readiness verdict |
| 7 | Manager Insights (team progress, risk, completion) | ❌ Not built | Data exists in Work IQ; no manager agent or manager UI/role-gate |

## Brief's 6 capabilities

| Capability | Status |
|---|---|
| 1. Cert ↔ role ↔ skill mapping | 🟡 Implicit via Work IQ persona (role→cert) + catalog (cert→modules); no explicit skill model |
| 2. Team-level + role-based study plans | 🟡 Role/profile plans done; **team-level** aggregation not built |
| 3. Grounded, cited practice questions | ❌ Not built (assessment) |
| 4. Feedback on team + individual progress | 🟡 Individual module progress done; team feedback not built |
| 5. Adapt schedules to work context + capacity | ✅ Done (real calendar capacity) + NL schedule edits |
| 6. Manager-level readiness/risk insight | ❌ Not built (data present in Work IQ; agent/UI absent) |

## Submission validity gate

| Requirement | Status |
|---|---|
| Multi-agent system aligned to scenario | ✅ gate→router→{greeting/recommend/foundry/work/general/study_plan} |
| Uses Foundry SDK and/or MAF | ✅ Azure OpenAI via Foundry SDK (Azure-first). MAF deferred (plain-Python spine = build-spec CORE) |
| Reasoning + multi-step across agents | ✅ State-conditioned graph + inspectable trace |
| Integrates external tools / APIs / MCP | 🟡 Deterministic grounding/recommender as tools; **MS Learn MCP** + live MCP retrieval not wired |
| ≥1 Microsoft IQ layer | ✅ **Live Foundry IQ** (Azure AI Search agentic retrieve) on the answer path + offline lexical fallback; Work IQ provider (honestly labelled) |
| Synthetic data only | ✅ |
| Demoable; interactions explained | ✅ Live app + trace panel |
| Documentation (agents, flow, tools, data) | 🟡 In code + this doc; a top-level architecture README pending |

## Master-plan §13 algorithms

| Algorithm | Status |
|---|---|
| Capacity Calculator | ✅ Done — but **grounded in the real calendar**, not the §13 `×0.6` heuristic (intentional upgrade) |
| Largest-Remainder allocator | 🟡 Replaced with sequential week-packing into real slots (defensible for module scheduling) |
| Slot Selector | ✅ Done (focus-window placement) |
| Readiness Scorer | ❌ Not built (assessment) |
| Risk Scorer | ❌ Not built (manager) |
| BKT (knowledge tracing) | ❌ Not built (EXTRA, cut-together with cross-session memory per plan) |

## Other planned-but-not-built (honest gaps)

- **Live Foundry IQ KB**: runtime grounds on the catalog (Foundry-IQ-pattern). The
  `athenaeum` package has Azure AI Search KB ingestion but it is not wired into the
  request path. Documented as available-not-provisioned.
- **MAF Workflows graph**: plain-Python orchestrator ships (build-spec CORE); MAF is EXTRA.
- **Azure Prompt Shields**: the gate is Azure-classifier-first + Groq Prompt Guard fallback;
  Prompt Shields (Content Safety) would be the Azure-native purpose-built guard (needs a
  Content Safety resource).
- **Cross-session memory**, **A2A**, **hosted deploy**, **RAGAS/PyRIT eval suite**: EXTRA.

## What's solid (done + tested)

Entry pipeline, layered injection gate (Azure-first), Azure→Groq model routing,
course selection (greeting/recommend/foundry, topic-aware), calendar-grounded
module-level study plan with pace + deadlines, **natural-language schedule editing**,
Modules navigation pages with sequential completion, DB persistence (courses,
modules, pace, schedule edits, per-message artifacts), state machine, number-match
grounding guard, inspectable trace, CI (backend/frontend/e2e/secret-scan).

## Recommended next phases (in order)

1. **Assessment Agent** (brief 5): grounded cited questions per module → deterministic
   scorer → readiness verdict; completion-by-test replaces the manual stub.
2. **Pass→advance / Fail→loop** (brief 6): wire the verdict into the plan loop + BKT-lite
   re-weighting of weak modules.
3. **Manager path** (brief 7, capability 6): manager principal + role gate; Progress
   Aggregator + Risk Scorer (Work IQ team data already present) + a manager view.
4. **Team-level plans** (capability 2) + **Curator skill-gap step** (brief 2).
5. EXTRAs: live Foundry IQ KB binding, MS Learn MCP, eval harness, MAF showpiece.
