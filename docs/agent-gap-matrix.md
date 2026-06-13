# Agent Gap Matrix — implemented vs planned vs hackathon, better, obsolescence

Date: 2026-06-14. Consolidates the two prior docs and adds the missing **obsolescence**
lens. For each agent in `ayanakoji/backend/app/agent/`, four columns:

1. **Implemented vs planned** — what the master-plan / build-spec specified vs what ships.
2. **Hackathon expectation** — what the Challenge A brief + starter-kit architecture expect, and the gap.
3. **Make better** — the highest-value improvement (detail in [agent-failure-analysis.md](agent-failure-analysis.md)).
4. **Obsolescence vector** — the planned/future component that *replaces or absorbs* this agent.

Companions: [gap-analysis.md](gap-analysis.md) (product/step coverage), [agent-failure-analysis.md](agent-failure-analysis.md) (failure modes).

## Planned vs current agent map

The brief's starter-kit names **5 agents**; we built a **chat-centric slice** of them.

| Brief agent (kb/challenge/agent-architecture.md) | Planned grounding | Current implementation |
|---|---|---|
| 1. Learning Path Curator | Foundry IQ KB + MS Learn MCP | `recommend.py` + `grounding.py` + `answer_foundry` (deterministic, no skill-gap step) |
| 2. Study Plan Generator | Work IQ + content | `study_plan.py` + `answer_study_plan` (calendar-grounded) ✅ closest to plan |
| 3. Engagement Agent | Work IQ | 🟡 partial — sessions land in focus windows; no nudge/reminder agent |
| 4. Assessment Agent | Foundry IQ + Fabric IQ | ❌ not built — module completion is a manual stub |
| 5. Manager Insights Agent | Work IQ + Fabric IQ | ❌ not built — Work IQ team data exists, no agent/role-gate |
| (infra) Entry/orchestration agent | MAF / Foundry Agent Service | `orchestrator.py` plain-Python + `gate.py` + `router_agent.py` |

---

## Per-agent matrix

### Injection gate (`gate.py`)
- **Impl vs planned**: Plan = "Azure Prompt Shields (Content Safety) as the native guard." Built = regex → Azure-LLM classifier → Groq Prompt Guard 2 → fail-open. A defensible, layered stand-in; the *purpose-built native* layer (Prompt Shields) is not provisioned.
- **Hackathon**: Brief doesn't mandate a gate; it's our own reliability/safety guardrail (aligns with "reasoning across agents" + responsible-AI optics). No explicit gap vs brief.
- **Better**: fail-closed mode for the double-outage case; ensemble the Azure + guard scores instead of short-circuit; multilingual coverage (see analysis §1).
- **Obsolescence**: **Azure Prompt Shields** (a Content Safety resource) makes the regex+LLM pre-filter redundant for input screening; the regex layer survives only as the offline/$0 floor. A MAF "guard" node would absorb `screen()`.

### Router (`router_agent.py`)
- **Impl vs planned**: Plan = a top-level entry/orchestration agent that routes to sub-agents. Built = heuristic `classify` + LLM `route` with deterministic overrides. Matches intent; it's hand-tuned regex, not a learned/declarative policy.
- **Hackathon**: Satisfies "multi-step decision-making across agents" + "interactions clearly explained" (the trace). Gap: routing is single-platform-aware but has no tool/plan schema a judge can inspect declaratively.
- **Better**: tighten remaining misroutes; richer follow-up resolution beyond affirmations (analysis §2, §0-C1).
- **Obsolescence**: a **MAF Workflow graph** (declarative nodes/edges) replaces the imperative `_dispatch` + regex precedence; a fine-tuned/structured-output router model replaces the regex heuristics. The heuristic survives only as the offline fallback.

### Grounding — Foundry-IQ-pattern (`grounding.py`)
- **Impl vs planned**: Plan = **Foundry IQ KB** of approved content with **required citations**. Built = deterministic keyword retrieval over the catalog JSON, LRU-cached, cited by module id. Honest stand-in ("Foundry-IQ-pattern"); it is lexical, not semantic, and not the real KB.
- **Hackathon**: Directly serves "≥1 Microsoft IQ layer" + "grounded, cited answers." Gap: it's a *pattern*, not a provisioned Foundry IQ index; lexical recall misses paraphrases (analysis §3).
- **Better**: synonyms/two-letter topics/cert-normalization already added; next is an embedding tier.
- **Obsolescence**: **live Foundry IQ (Azure AI Search) KB** behind the same `search`/`suggest` surface makes the keyword scorer obsolete; **MS Learn MCP** absorbs the "what content exists" half of Curator. The `athenaeum` package already has KB ingestion, just unwired.

### Recommend — Learning Path Curator half (`recommend.py`)
- **Impl vs planned**: Plan = curate content for goals **and role**, including a **skill-gap → resource** step (brief step 2). Built = deterministic ladder ranking by vertical/order/prereq. No skill model.
- **Hackathon**: Partially serves Curator. Gap: no explicit skill-gap reasoning, no cert↔role↔skill map (capability 1 is only implicit via persona + catalog).
- **Better**: multi-vertical (done); a real skill-gap step; word-boundary keywords.
- **Obsolescence**: a **Foundry IQ + skills-graph Curator agent** (role→skill-gap→KB resources) supersedes the hand-rolled ladder; **Fabric IQ** semantic scoring replaces the keyword vertical-vote.

### Greeting (`answer_greeting`)
- **Impl vs planned**: Not a planned agent — an onboarding affordance we added so the chat-first slice has a warm entry. Now course-lock-aware.
- **Hackathon**: Demo polish; not a brief requirement.
- **Better**: stop re-greeting on "thanks"; richer onboarding once Curator lands.
- **Obsolescence**: folds into the **entry/orchestration agent**; disappears as a standalone once routing handles onboarding declaratively.

### Work IQ answerer (`answer_work`)
- **Impl vs planned**: Plan = Work IQ as **contextual input** to timing/engagement, "supportive and privacy-conscious." Built = read-only persona aggregates (meeting/focus hours, preferred slot). Matches the IQ-as-context intent; shallower than the calendar the planner uses.
- **Hackathon**: Serves "≥1 IQ layer" (Work IQ) + "adapt to work context." Gap: PII scrubbing deliberately skipped; answers don't reach the day-level calendar.
- **Better**: give it the day schedule for specific timing questions; wire the PII hook (analysis §7).
- **Obsolescence**: a **provisioned Work IQ connector** (real calendar/Graph signals) replaces the synthetic persona read; **Fabric IQ** absorbs the "is this load risky" judgement currently implicit in the >20h heuristic.

### Study Plan Generator (`study_plan.py` + `answer_study_plan`)
- **Impl vs planned**: Plan = master-plan §13 (Capacity Calculator ×0.6, Largest-Remainder allocator, Slot Selector). Built = **calendar-grounded** capacity (intentional upgrade over ×0.6), sequential week-packing, real slot selection. This is the **most complete** agent and *exceeds* the §13 heuristic.
- **Hackathon**: Fully serves "Study Plan Generator… workload-aware" (step 3) + capability 5. Strongest demo asset.
- **Better**: PTO/on-call/multi-week modelling, backward planning from an exam date, difficulty weighting, sliver coalescing (analysis §5).
- **Obsolescence**: hardest to obsolete (it's deterministic + auditable, which is a feature). A **Fabric IQ** layer could replace the fixed estimate constants with learned per-module effort; an exam-date-anchored solver would supersede forward packing. The algorithm stays; its constants get data-driven.

### Schedule edit (`schedule_edit.py`)
- **Impl vs planned**: Not in the original plan — a natural-language edit layer we added (start-shift, day-exclude, now pace + skip-weeks). Deterministic, testable.
- **Hackathon**: Strengthens "adapt schedules to work context" (capability 5) and shows reasoning. Bonus, not required.
- **Better**: time-window edits, un-exclude, weekday-relative starts (analysis §6).
- **Obsolescence**: an **LLM-extract-then-validate** edit layer (structured output against the same schema) absorbs the regex grammar while keeping the deterministic guard; reduces the agent to a validator.

### State machine (`state.py`)
- **Impl vs planned**: Plan = state-conditioned graph (master-plan §5). Built = derived `CourseState` (new→…→completed) conditioning the route. Matches intent.
- **Hackathon**: Supports "multi-step reasoning across agents" + the inspectable trace. Gap: no FAILED/at-risk states (needs assessment).
- **Better**: at-risk/failed states; honor COMPLETED→recommend (analysis §10).
- **Obsolescence**: **MAF Workflow** state/edges make the hand-derived enum redundant; an **assessment-driven** readiness state replaces count-derived completion.

### Guards (`guards.py`)
- **Impl vs planned**: Plan = "Reliability via guardrails + rule-based tests" (cert-prep winner pattern). Built = number-match + citation-existence, now **wired at runtime** (buffered validate-then-stream).
- **Hackathon**: Directly serves "grounded, cited" + reliability optics. On-plan.
- **Better**: extend to all agents' prose, not just plan/foundry; semantic faithfulness checks.
- **Obsolescence**: a **RAGAS/PyRIT eval harness** (EXTRA in the plan) plus Foundry IQ's native citation enforcement absorb most of these; the rule guards remain as the cheap CI tripwire.

### ModelRouter (`llm.py`)
- **Impl vs planned**: Plan = capability-keyed Azure→Groq fallback, Foundry SDK first (burns Azure credits). Built exactly that, + per-call timeout. On-plan.
- **Hackathon**: Satisfies "uses Foundry SDK." Gap: only gpt-4o-mini deployed, so the Azure fallback rung is the same model; REASONING tier unused on the hot path.
- **Better**: retry/backoff on transient errors; diversify the Azure fallback deployment (analysis §9).
- **Obsolescence**: **Foundry Agent Service / hosted agents** (platform-managed model routing, identity, scaling) make the hand-rolled chain unnecessary for deployment; the chain survives for local/offline dev.

### Orchestrator (`orchestrator.py`)
- **Impl vs planned**: Plan = "plain-Python spine = build-spec CORE; **MAF is EXTRA**." Built = synchronous generator streaming typed events. On-plan, intentionally pre-MAF.
- **Hackathon**: Satisfies "multi-agent + reasoning across agents + interactions explained." Gap: validity gate wants "uses MAF and/or Foundry SDK" — we have Foundry SDK; **MAF is the showpiece not yet built**.
- **Better**: thread fuller history; emit artifacts before the token stream so a break doesn't drop them (analysis §11).
- **Obsolescence**: a **MAF Workflows graph** replaces the imperative spine entirely (nodes = agents, edges = accepts); **A2A** + **Foundry Agent Service** replace in-process dispatch with networked hosted agents.

---

## Entirely missing planned agents (no current code)

| Agent | Brief role | Planned grounding | Why it matters | First build |
|---|---|---|---|---|
| **Assessment Agent** | grounded, cited readiness questions; pass/fail | Foundry IQ + Fabric IQ | Biggest gap; closes the 7-step loop (steps 5-6); completion becomes by-test not manual | grounded MCQ generator → deterministic scorer → readiness verdict |
| **Engagement Agent** | adaptive nudges/reminders around focus windows | Work IQ | Brief step 4; we place sessions but emit no reminder plan | reminder-plan artifact keyed to focus windows + lateness |
| **Manager Insights Agent** | team progress, risk, completion | Work IQ + Fabric IQ | Brief step 7 + capability 6; manager persona + role-gate absent | manager principal + Progress Aggregator + Risk Scorer + manager view |
| **Fabric IQ layer** | semantic scoring / thresholds | — | Named for Assessment + Manager + capacity; currently hand-tuned constants | semantic scoring service behind a thin interface |

---

## Obsolescence roadmap (what retires what)

The current agents are honest **stand-ins**; each retires when its planned counterpart lands:

| When this lands… | …this current agent is obsoleted/absorbed |
|---|---|
| Live **Foundry IQ KB** (Azure AI Search) | `grounding.py` keyword scorer → thin KB client |
| **MS Learn MCP** | external-content half of Curator (`recommend`/`foundry`) |
| **Azure Prompt Shields** | gate's regex+LLM input screen → offline floor only |
| **Fabric IQ** | Work IQ risk heuristic, study-plan constants, assessment thresholds |
| **MAF Workflows** | `orchestrator.py` spine + `state.py` enum + router `_dispatch` |
| **Foundry Agent Service** (hosted) | `llm.py` chain (deployment), local FastAPI process |
| **Assessment loop** | manual module-completion stub, count-derived COMPLETED state |
| **RAGAS/PyRIT eval** | most rule guards (kept as the CI tripwire) |

Net: the deterministic, auditable cores (study-plan algorithm, number/citation guards, offline routing/grounding fallbacks) are deliberately **non-obsolete** — they remain the $0, credential-free, testable floor under whatever managed layer replaces the online path. Everything reaching an external model or KB is a swappable stand-in by design.
