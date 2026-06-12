---
title: Suggested multi-agent architecture (Challenge A) with IQ grounding per agent
tags: [challenge-a, multi-agent, architecture, foundry-iq, work-iq, fabric-iq]
status: stable
sources:
  - Reasoning Agents starter kit (pasted 2026-06-12)
updated: 2026-06-12
related: [challenge-a-brief, foundry-iq, work-iq, fabric-iq, reasoning-patterns]
---

# Multi-agent architecture (starter-kit suggestion)

Five agents. Each has a recommended IQ grounding — this mapping is the backbone of the "Best Use of IQ Tools" story.

| # | Agent | Primary role | Recommended grounding |
|---|-------|--------------|----------------------|
| 1 | **Learning Path Curator** | Suggest learning paths + material | **Foundry IQ** KB of approved learning content; optional Microsoft Learn MCP |
| 2 | **Study Plan Generator** | Content → practical study schedule | **Fabric IQ** semantic layer (certification, role, skill areas, recommended hours); synthetic historical outcomes |
| 3 | **Engagement Agent** | Keep learner progressing | **Work IQ** (work context, communication patterns, preferred timing) |
| 4 | **Assessment Agent** | Evaluate readiness | **Foundry IQ** (grounded question generation) + **Fabric IQ** (scoring thresholds) |
| 5 | **Manager Insights Agent** | Team-level visibility | **Work IQ** (capacity signals) + **Fabric IQ** (semantic analysis of learning metrics) |

## Per-agent behavioural requirements

**Curator**: map certification target → skills + resources; return **cited content**, never unsupported free text.
**Plan Generator**: role-level milestones; allocate hours vs workload; sequence by difficulty/prerequisites.
**Engagement**: pick reminder times from work rhythm; adapt to workload/focus windows; no one-size-fits-all reminders.
**Assessment**: credible cited questions from approved content; score vs known certification criteria; feed results back into planning loop; surface aggregate readiness.
**Manager Insights**: summarise by team/role/track; highlight capacity-constrained teams and exam-risk areas; **no sensitive personal data exposure**.

## End-to-end flow (e2e demo script skeleton)

1. Learner asks for certification prep help
2. Foundry IQ retrieves grounded learning materials + certification guidance from approved KB
3. Fabric IQ interprets structured data (required skills by role, recommended hours, prior synthetic outcomes)
4. Work IQ identifies realistic study windows per member (meeting load, focus patterns)
5. Study Plan Generator produces capacity-aware team schedule
6. Engagement Agent schedules nudges around peak work periods
7. Assessment Agent generates grounded questions, evaluates readiness
8. Manager Insights surfaces team progress/risk/readiness
9. Ready → recommend next cert; not ready → **loop back to step 5** ← the visible reasoning loop judges want

## Suggested IQ implementation patterns (from kit)

- **Foundry IQ**: KB from synthetic guidance docs / markdown / PDFs → connect agents → **require citations** in answers and assessments.
- **Fabric IQ**: model entities (learner, certification, role, skill gap, readiness score, recommended hours) + relationships/rules (prerequisites, role alignment, pass thresholds) → drive recommendations + manager summaries.
- **Work IQ**: treat meetings/focus time/collab load as contextual inputs → choose study windows, reminder timing, escalation thresholds; keep outputs supportive and privacy-conscious.

## Hosted deployment story (recommended for final solution)

Hosted Agents in Foundry Agent Service: package agent as container → push to ACR → Foundry pulls, provisions compute, assigns Entra agent identity, exposes dedicated endpoint; platform handles scaling, state persistence, observability. Suggested pattern: top-level hosted **entry agent** focused on orchestration/routing; task-specific sub-agents; Foundry IQ = grounding, Fabric IQ = semantics, Work IQ = work context; no secrets in image; minimal sandbox size; immutable versions.
