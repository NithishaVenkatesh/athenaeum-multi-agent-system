---
title: Fabric IQ — semantic layer / ontology (and how we ground it without a cookbook)
tags: [fabric-iq, concept]
status: volatile
sources:
  - microsoft/iq-series Fabric-IQ/README.md ("Coming Soon" as of 2026-06-12)
  - https://blog.fabric.microsoft.com/blog/introducing-fabric-iq
  - Reasoning Agents starter kit description
updated: 2026-06-12
related: [microsoft-iq-overview, agent-architecture, synthetic-data]
---

# Fabric IQ

**Status caveat**: the IQ Series repo has **no Fabric IQ episodes or cookbooks yet** ("Coming Soon"). Everything actionable comes from the starter kit description + the Fabric IQ announcement blog.

## What Microsoft says it is

- A **semantic foundation** within Microsoft Fabric: brings **data, meaning, and actions** into a single semantic layer.
- **Ontology at the core**: connects people, processes, systems, actions, rules, and data into unified business **entities and relationships** so humans and AI can reason and act with confidence.
- Hackathon framing: "uses ontologies and knowledge graphs to give business meaning to enterprise data, enabling AI agents to reason over real business concepts."

## Starter-kit fit for Challenge A

- Model relationships: employee ↔ role ↔ certification ↔ skill gap ↔ pass threshold ↔ study plan
- Analyse completion rates, pass likelihoods, workforce readiness gaps
- Reuse semantic meaning across analytics, planning, and agent experiences

## Implementation strategy for us (no public SDK path in the series)

Realistic options, by effort:

1. **Ontology-as-code (recommended for the deadline)** — define the semantic model (entities, relationships, rules: prerequisites, role alignment, pass thresholds) as a typed module/JSON ontology seeded from the synthetic Fabric IQ dataset; Study Plan Generator and Manager Insights agents reason **through** it (queries like `skill_gap(learner, cert)`, `readiness(learner)`), and docs/diagram present it explicitly as the Fabric IQ-pattern semantic layer.
2. **Real Fabric** (only if time + capacity allows) — Fabric workspace, OneLake table from the synthetic data, semantic model; optionally surfaced to Foundry IQ via a OneLake knowledge source.

Either way, the README should cite the Fabric IQ blog as the design reference and be explicit about which level of integration was implemented — judges reward honesty over hand-waving (Reliability & Safety 20%).
