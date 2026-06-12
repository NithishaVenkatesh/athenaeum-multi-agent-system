---
title: Work IQ — architecture, protocols (REST/A2A/MCP), CLI, enablement
tags: [work-iq, concept, a2a, mcp, rest, howto]
status: stable
sources:
  - microsoft/iq-series Work-IQ episodes 1–2 + labs
  - https://learn.microsoft.com/microsoft-365/copilot/extensibility/work-iq
updated: 2026-06-12
related: [microsoft-iq-overview, agent-architecture]
---

# Work IQ

Workplace intelligence layer behind Microsoft 365 Copilot. Four core components: **Chat, Context, Tools, Workspaces**. Transforms M365 + business-system signals into agent-ready intelligence.

## Architecture (lab 1)

- **Data** — everyday work signals + external enterprise data (M365 activity, LOB systems) → real-time awareness
- **Context** — memory of style, preferences, habits, workflows
- **Skills & Tools** — specialized capabilities tailoring agents to tasks

## Work IQ API principles

- **Unified Surface** — one API contract for people- and agent-driven use
- **Response Fidelity** — API responses mirror the interactive Copilot experience
- **Multi-Protocol Runtime** — REST, A2A, MCP are protocol heads on the same orchestration runtime

Security by default: always security-trimmed, delegated + user-scoped access, honors tenant boundaries, sensitivity labels, governance.

## Protocol selection

| Protocol | Use when | Example |
|----------|----------|---------|
| **A2A** (agent→agent) | One agent delegates to another | External HR agent asks BizChat agent for M365 context |
| **MCP** (agent→tool) | Orchestrator needs org context as a tool | GitHub Copilot calls `ask_work_iq` |
| **REST** (human→agent) | Embedding intelligence in apps | Web app posts to Graph `copilot/conversations` |

## Hard prerequisites (decides whether we can use it for real)

- M365 tenant **with Copilot licensing**
- **Tenant admin consent** for the Work IQ application:
  `https://login.microsoftonline.com/{tenant}/adminconsent?client_id=ba081686-5d24-4bc6-a0d6-d034ecffed87`
  (AADSTS errors → run `Enable-WorkIQToolsForTenant.ps1` from github.com/microsoft/work-iq, retry)
- Node.js 22+; Work IQ CLI (`npm i -g @microsoft/workiq` or `npx -y @microsoft/workiq mcp`); `workiq accept-eula`

## Consumption recipes

```bash
# CLI
workiq ask -q "When is my next meeting?"

# MCP server (works in any MCP client incl. our agents)
npx -y @microsoft/workiq mcp        # exposes ask_work_iq tool

# A2A server (lab 2)
workiq a2aserver                    # http://localhost:5100
# agent card: http://localhost:5100/.well-known/agent-card.json
```

REST (Graph beta):

```http
POST https://graph.microsoft.com/beta/copilot/conversations           → {id: conversationId}
POST https://graph.microsoft.com/beta/copilot/conversations/{id}/chat
{"message": {"text": "..."}, "locationHint": {"timeZone": "Asia/Kolkata"}}
```

Graph Explorer permissions used in lab: Mail.Read, People.Read.All, OnlineMeetingTranscript.Read.All, Chat.Read, ChannelMessage.Read.All, ExternalItem.Read.All.

## A2A essentials (lab 2)

- A2A = open protocol for agent discovery + collaboration (multi-turn, delegation, streaming); complementary to MCP (MCP = agent-to-tool).
- Flow: discover via **agent card** → authenticate → send request → stream updates.
- Work IQ's agent card: name "Work IQ Relay Agent", skill `ask_work_iq` ("emails, meetings, files, and other M365 data"), JSONRPC transport, streaming=true, protocol 0.3.0.
- Debug tool: **A2A Inspector** (github.com/a2aproject/a2a-inspector, runs at 127.0.0.1:5001).

## Fallback plan if no licensed tenant

Implement the Engagement Agent against a `WorkContextProvider` interface with two backends: (1) real Work IQ MCP (`ask_work_iq`) when a tenant is available, (2) synthetic work-signals dataset (kb/challenge/synthetic-data.md). Document honestly — kit itself suggests treating work signals as contextual inputs.
