---
title: Reasoning patterns, evaluation, and deployment extras
tags: [reasoning-patterns, evaluation, hosted-agents, agent-framework, howto]
status: stable
sources:
  - Reasoning Agents starter kit (pasted 2026-06-12)
updated: 2026-06-12
related: [judging-rubric, agent-architecture]
---

# Reasoning patterns and best practices (worth 25% + extras)

## Patterns the kit explicitly names

- **Planner–Executor** — separate planning from action execution
- **Critic / Verifier** — validation layer before final answer
- **Self-reflection & iteration** — review/refine when confidence is low
- **Role-based specialisation** — clear agent responsibilities, no overlap

Application to Challenge A:
- Study Plan Generator = Planner; Engagement Agent = Executor of the schedule
- Assessment Agent = Critic/Verifier in the readiness loop (fail ⇒ replan = visible iteration)
- A grounding-verifier step on Curator/Assessment outputs ("is every claim cited?") is a cheap, demoable Critic

## Foundry best practices (verbatim themes)

- Telemetry, trace logs, visual workflows to understand collaboration
- Evaluation via test cases, scoring rubrics, or human review
- Responsible AI across app logic AND data design

Key docs: Foundry Control Plane overview · Evaluate generative AI apps in Foundry · Evaluate AI agents with Foundry SDK · Responsible AI in Foundry · Microsoft Agent Framework docs/tutorials · AI Agents for Beginners.

## Recommended tool integrations

External tools / APIs / MCP "where they add real value": Microsoft Learn MCP server (cert content), code interpreter (scoring math), Foundry IQ MCP endpoint (knowledge), memory in Foundry Agent Service (state).

## Evaluation harness (cheap "highly valued extra")

Minimum viable: a small test set of (learner profile, expected plan properties) and (question, must-be-cited) cases; assert citations present, schedule ≤ capacity, pass/fail loop branches correctly. Log agent traces; show one trace in the demo.

## Troubleshooting table (from kit)

| Issue | Fix |
|-------|-----|
| `ModuleNotFoundError: azure` | deps into the active venv |
| Auth errors | check env vars/permissions (`az login`, RBAC) |
| Poor retrieval quality | review knowledge source content + grounding design |
| Generic agent answers | tighten role instructions, improve grounding |
| Synthetic data too realistic | simplify identifiers, replace sensitive-looking values |
| Unrealistic reminder logic | revisit interpretation of work signals |
