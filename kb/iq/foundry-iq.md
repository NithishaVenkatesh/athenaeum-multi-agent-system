---
title: Foundry IQ — concepts (knowledge sources, knowledge bases, agentic retrieval)
tags: [foundry-iq, concept, mcp, azure]
status: stable
sources:
  - https://github.com/microsoft/iq-series (Foundry-IQ episodes 1–3 + cookbooks)
  - https://learn.microsoft.com/azure/foundry/agents/concepts/what-is-foundry-iq
updated: 2026-06-12
related: [foundry-iq-code, azure-setup, microsoft-iq-overview]
---

# Foundry IQ — concepts

Configurable, **multi-source knowledge layer** for Microsoft Foundry. Built on **Azure AI Search** indexing/retrieval infra. Returns **permission-aware, grounded answers with citations**.

## Core objects

```
Search Index ──► Knowledge Source ──► Knowledge Base ──► (agent / MCP client / SDK query)
   (data)         (one per source)      (topic-centric,        with citations
                                         multi-source,
                                         paired with an LLM)
```

- **Knowledge Source** — how content enters. Types seen in the SDK:
  - `SearchIndexKnowledgeSource` — wraps an existing AI Search index ("indexed")
  - `AzureBlobKnowledgeSource` — point at a blob container; **Foundry IQ auto-builds the ingestion pipeline** (chunking, embedding, indexing)
  - `WebKnowledgeSource` — real-time public web
  - (also supported per docs: SharePoint incl. remote, OneLake/Fabric)
- **Knowledge Base** — pairs ≥1 knowledge sources with an Azure OpenAI model for **agentic retrieval**: query planning → per-source subqueries → ranking → optional answer synthesis. Topic-centric and **reusable** across agents (the ep3 theme: "from isolated pipelines to reusable knowledge").

## Retrieval reasoning effort (ep3 — great demo material)

| Effort | Behaviour |
|--------|-----------|
| `minimal` | Fastest; no LLM planning — direct retrieval |
| `low` | LLM **query planning + source selection** |
| `medium` | **Iterative retrieval with refinement** |

Request with `include_activity=True` → response carries the **activity log / query plan** (subqueries the planner generated, which sources answered). Surfacing this in the UI = visible multi-step reasoning for judges.

## Output modes

- `ANSWER_SYNTHESIS` — synthesized answer + citations (`answer_instructions` customizes tone/grounding)
- (default extractive mode returns ranked chunks/references only)

## MCP endpoint (the integration superpower)

Every knowledge base exposes MCP:

```
https://<search-service>.search.windows.net/knowledgebases/<kb-name>/mcp?api-version=2025-11-01-preview
```

Tool name: `knowledge_base_retrieve`. Connectable from: Foundry Agent Service (via project connection + `MCPTool`), GitHub Copilot in VS Code (`.vscode/mcp.json`, type `sse`, `api-key` header), Copilot CLI, Claude Desktop (via `mcp-remote` proxy). Remote SharePoint sources additionally need `x-ms-query-source-authorization` bearer scoped to `https://search.azure.com/.default`.

## Requirements / gotchas

- Region must support **agentic retrieval** (default used in series: `eastus2`)
- Index needs a **semantic configuration** — required for agentic retrieval
- Vectorizer: `text-embedding-3-large` (3072 dims) used throughout the cookbooks
- SDK: `azure-search-documents==12.1.0b1` (preview!), `azure-ai-projects`, `azure-identity`
- Auth: `DefaultAzureCredential` + RBAC (cookbooks avoid API keys except for MCP client config)
