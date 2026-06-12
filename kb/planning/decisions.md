---
title: Decision log
tags: [decision, plan]
status: volatile
sources: [internal]
updated: 2026-06-12
related: [plan]
---

# Decision log

Format: `D-### | date | decision | why | revisit-if`

- **D-001** | 2026-06-12 | Knowledge base + planning = vectorless markdown KB (`kb/` + frontmatter tags, grep retrieval) | zero infra, agent-greppable, mirrors the retrievability rules we apply to the Foundry IQ data pack | n/a
- **D-002** | 2026-06-12 | Target **Challenge A (Enterprise Learning System)**, Reasoning Agents track | user choice | n/a
- **D-003** | 2026-06-12 | Foundry IQ = the deep, real IQ integration; Fabric IQ via ontology-as-code; Work IQ behind a provider interface (real MCP if tenant available, else synthetic signals) | Foundry IQ fully documented + runnable; Fabric IQ has no public cookbook; Work IQ needs licensed tenant + admin consent | tenant access confirmed → flip Work IQ to real |
- **D-004** | 2026-06-12 | Pin `azure-search-documents==12.1.0b1`; models `text-embedding-3-large` + `gpt-4o-mini`; region `eastus2` | exactly what MS cookbooks use; agentic retrieval region support | SDK GA / quota issues |
