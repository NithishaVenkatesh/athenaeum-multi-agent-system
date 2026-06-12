---
title: Build plan — Challenge A against the June 14 deadline
tags: [plan, challenge-a]
status: volatile
sources: [internal]
updated: 2026-06-12
related: [decisions, progress, judging-rubric, agent-architecture]
---

# Build plan

**Deadline: June 14, 2026, 11:59 PM PT** (= June 15, ~12:29 PM IST). Today June 12 → ~2.5 days. Plan is MVP-first; every phase ends demoable.

## Phase 0 — Foundation (≤ half day)

- [ ] Azure: one-click deploy the IQ-series stack (kb/iq/azure-setup.md) OR reuse existing Foundry project
- [ ] Repo scaffold: `src/`, `data/synthetic/`, `.env` git-ignored, pinned deps
- [ ] Synthetic data pack committed (kb/challenge/synthetic-data.md datasets + 3 guidance docs as markdown)

## Phase 1 — Foundry IQ ground truth (core, ~half day)

- [ ] Index synthetic cert docs → knowledge source(s) → knowledge base (kb/iq/foundry-iq-code.md recipes)
- [ ] Verify retrieval with citations + activity log at low/medium reasoning effort
- [ ] Wire KB to an agent via MCP (`knowledge_base_retrieve`)

## Phase 2 — The five agents + orchestration (~1 day)

Order by demo value:
1. Learning Path Curator (Foundry IQ, citations-or-refuse)
2. Assessment Agent (Foundry IQ questions + ontology thresholds, pass/fail → loop-back)
3. Study Plan Generator (Fabric IQ-pattern ontology module: skill gaps, hours, capacity)
4. Engagement Agent (Work IQ provider: real MCP if tenant, else synthetic signals)
5. Manager Insights Agent (aggregates, no personal data exposure)
- [ ] Orchestrator implementing the baseline flow incl. the fail→replan loop
- [ ] Trace/telemetry logging of every agent hop (judges: visible reasoning)

## Phase 3 — Extras that score (~half day)

- [ ] Mini evaluation set (citation presence, capacity respected, loop branching)
- [ ] Guardrails: input validation, "I don't know" fallback, output schema checks
- [ ] Simple UI or clean CLI transcript for the demo

## Phase 4 — Submission package (reserve ~half day, June 14)

- [ ] README: problem, features, agents/orchestration/tools/data sources, synthetic-data disclaimer
- [ ] Architecture diagram (required!)
- [ ] Demo video ≤5 min (script: e2e flow steps 1–9 from kb/challenge/agent-architecture.md)
- [ ] Repo public; secret scan; submit on platform; MS Learn usernames ready
- [ ] Discord post for community vote

## Cut lines (if time runs out)

Keep: Curator + Assessment + loop + Foundry IQ + README/video. Cut first: hosted-agent deployment → real Work IQ tenant → UI polish → Manager Insights.

## Open blockers

- Platform registration/profile activation (email issue from previous session — verify resolved before June 14!)
- Decide Work IQ real-vs-synthetic (depends on tenant access)
