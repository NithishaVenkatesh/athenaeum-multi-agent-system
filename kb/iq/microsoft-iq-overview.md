---
title: Microsoft IQ — the three intelligence layers
tags: [microsoft-iq, foundry-iq, work-iq, fabric-iq, concept]
status: stable
sources:
  - https://github.com/microsoft/iq-series (aka.ms/iq-series)
  - Hackathon platform page
updated: 2026-06-12
related: [foundry-iq, work-iq, fabric-iq]
---

# Microsoft IQ (one page)

Microsoft IQ = Microsoft's **unified intelligence layer for the enterprise**. Three services; together they let agents "reason, retrieve, and act with deep business context — going beyond traditional RAG."

| Layer | One-liner | Our use in Challenge A |
|-------|-----------|------------------------|
| **Foundry IQ** | Managed knowledge layer: structured + unstructured data across Azure, SharePoint, OneLake, web → **permission-aware, cited, grounded answers** via agentic retrieval (Azure AI Search underneath) | Ground the Curator + Assessment agents in synthetic cert docs; KB exposes an MCP endpoint agents call as a tool |
| **Work IQ** | Workplace intelligence behind M365 Copilot. Four components: **Chat, Context, Tools, Workspaces**. Builds memory from emails/meetings/chats/docs; security-trimmed, delegated, tenant-bounded | Work context for Engagement + Manager Insights (real tenant via Work IQ CLI/MCP/A2A, or synthetic work-signal stand-in) |
| **Fabric IQ** | Semantic layer in Microsoft Fabric; **Ontology at the core** — entities, relationships, rules giving business meaning to data | Model learner/cert/role/skill-gap/threshold entities driving plans + insights |

## IQ Series repo map (aka.ms/iq-series → github.com/microsoft/iq-series)

- **Foundry IQ** — 3 episodes with runnable Jupyter cookbooks:
  1. Unlocking Knowledge for Agents (KS → KB → query → wire to Foundry agent)
  2. Building the Data Pipeline with Knowledge Sources (indexed / blob / web sources)
  3. Querying Multi-Source KBs (reasoning effort levels, MCP connection guides)
- **Work IQ** — 2 episodes with labs:
  1. Data, context, tools at scale (CLI, Copilot CLI MCP, Graph REST)
  2. A2A for context-aware agentic experiences (A2A server, agent card, A2A Inspector)
- **Fabric IQ** — **"Coming soon"** — no cookbook exists yet (as of 2026-06-12). Official refs: "Fabric IQ: The Semantic Foundation for Enterprise AI" blog + Fabric docs.
- **infra/** — one-click Deploy-to-Azure (AI Search Standard, Azure OpenAI `text-embedding-3-large` + `gpt-4o-mini`, AI Services + Foundry project, Blob, RBAC, seeded NASA sample KB).

## Strategic note for the contest

"Best Use of IQ Tools" is a separate $5k prize. The starter kit says one IQ is enough, but the architecture maps **all three** naturally. Realistic ranking of effort:
- Foundry IQ: fully documented, runnable SDK — **do deeply, for real**.
- Work IQ: needs an M365 tenant with Copilot licensing + admin consent — real if tenant available, otherwise honest synthetic work-signal layer labeled as Work IQ-pattern.
- Fabric IQ: no public cookbook; implement the **ontology concept** (entities/relationships/rules as a semantic model) and cite the Fabric IQ blog as the design reference.
