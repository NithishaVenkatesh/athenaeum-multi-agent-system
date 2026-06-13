# Knowledge Base Index (Vectorless DB)

This is a **vectorless knowledge base**: plain markdown files with YAML frontmatter tags.
Retrieval = grep, not embeddings.

## How to retrieve

```bash
# Find every doc carrying a tag
grep -rl "foundry-iq" kb --include="*.md"

# Find docs by tag in frontmatter only
grep -rl -A2 "^tags:" kb | grep "synthetic-data"

# Full-text search
grep -rin "reasoning effort" kb
```

## Conventions

Every doc starts with frontmatter:

```yaml
---
title: Human-readable title
tags: [domain-tag, type-tag, ...]
status: stable | draft | volatile
sources: [origin URLs / repos]
updated: YYYY-MM-DD
related: [other-doc-slugs]
---
```

- **One topic per file**, small chunks, clear headings — same retrievability rules we'll apply to the Foundry IQ data pack later.
- `status: volatile` = re-verify before relying on it (deadlines, preview APIs).

## Tag taxonomy

| Kind | Tags |
|------|------|
| IQ layers | `foundry-iq` `work-iq` `fabric-iq` `microsoft-iq` |
| Hackathon | `hackathon` `rules` `judging` `submission` `compliance` `deadline` `prizes` |
| Challenge | `challenge-a` `enterprise-learning` `multi-agent` `architecture` `synthetic-data` `reasoning-patterns` |
| Tech | `azure` `sdk` `code` `mcp` `a2a` `rest` `agent-framework` `agent-service` `hosted-agents` `deployment` `infra` `evaluation` |
| Doc type | `concept` `howto` `requirement` `reference` `decision` `plan` |

## Documents

### hackathon/
- [overview.md](hackathon/overview.md) — What Agents League is, tracks, dates, links. `hackathon` `concept`
- [official-rules.md](hackathon/official-rules.md) — Entry mechanics, eligibility, what a valid submission contains. `hackathon` `rules` `submission` `requirement`
- [judging-rubric.md](hackathon/judging-rubric.md) — Scoring rubric + what judges reward, mapped to build priorities. `hackathon` `judging`
- [compliance.md](hackathon/compliance.md) — Disclaimer, prohibited content, security checklist before pushing/submitting. `hackathon` `compliance` `requirement`

### challenge/
- [challenge-a-brief.md](challenge/challenge-a-brief.md) — Challenge A (Enterprise Learning System) scenario, baseline flow, submission requirements. `challenge-a` `requirement`
- [agent-architecture.md](challenge/agent-architecture.md) — The 5 agents, IQ grounding per agent, end-to-end flow. `challenge-a` `multi-agent` `architecture`
- [synthetic-data.md](challenge/synthetic-data.md) — Synthetic-data rules + example datasets/documents from the starter kit. `synthetic-data` `requirement`
- [reasoning-patterns.md](challenge/reasoning-patterns.md) — Reasoning patterns, evals, Responsible AI, hosted-agent deployment story. `reasoning-patterns` `evaluation` `hosted-agents`

### iq/
- [microsoft-iq-overview.md](iq/microsoft-iq-overview.md) — The three IQ layers in one page + IQ Series repo map. `microsoft-iq` `concept`
- [foundry-iq.md](iq/foundry-iq.md) — Knowledge sources, knowledge bases, agentic retrieval, reasoning efforts, MCP endpoint. `foundry-iq` `concept`
- [foundry-iq-code.md](iq/foundry-iq-code.md) — Working Python SDK recipes (from MS cookbooks): index → knowledge source → KB → retrieve → agent wiring. `foundry-iq` `sdk` `code` `howto`
- [work-iq.md](iq/work-iq.md) — Architecture (Data/Context/Skills+Tools), REST vs A2A vs MCP, CLI, tenant enablement, agent card. `work-iq` `concept` `a2a` `mcp` `rest`
- [fabric-iq.md](iq/fabric-iq.md) — Ontology/semantic layer concept, official status, how we ground it in this project. `fabric-iq` `concept`
- [azure-setup.md](iq/azure-setup.md) — Deploy-to-Azure infra, env vars, regions, model deployments, free-tier gotchas. `azure` `infra` `howto`

### planning/
- [master-plan.md](planning/master-plan.md) — **CANONICAL plan (v4)**: decisions, architecture, IQ, orchestration, security, eval, cost, rubric traceability. `plan` `master`
- [build-spec.md](planning/build-spec.md) — **Exact code-level build reference**: repo tree, Pydantic contracts, orchestrator skeletons, SDK call patterns, per-module DoD. Buildable with no extra context. `plan` `code` `reference`
- [plan.md](planning/plan.md) — v1 system-design reference (superseded by master-plan). `plan`
