---
title: Judging rubric and what it implies for build priorities
tags: [hackathon, judging, plan]
status: stable
sources:
  - Hackathon platform page (pasted 2026-06-12)
  - Reasoning Agents challenge starter kit
  - OFFICIAL RULES.md
updated: 2026-06-12
related: [official-rules, reasoning-patterns, plan]
---

# Judging rubric

Two slightly different weightings exist. The **challenge-level rubric** (Reasoning Agents page) is what the track judges use; official rules add the community vote.

| Criterion | Challenge page | Official rules (overall) |
|-----------|---------------|--------------------------|
| Accuracy & Relevance | 25% | 20% |
| Reasoning & Multi-step Thinking | 25% | 20% |
| Creativity & Originality | 15% | 15% |
| User Experience & Presentation | 15% | 15% |
| Reliability & Safety | 20% | 20% |
| Community vote (Discord poll) | — | 10% |

## Implications — where points are won

**50% of the score is Accuracy+Reasoning.** Priorities, in order:

1. **Meet every stated submission requirement** (multi-agent, Foundry/Agent Framework, ≥1 IQ layer, synthetic data, demoable, documented). Accuracy = "meets challenge requirements" — a checklist, not vibes.
2. **Make reasoning visible.** Decomposition, planning, agent collaboration must be observable in the demo: show orchestration traces, the assessment→loop-back decision, query plans from Foundry IQ (`include_activity=True` returns the planner's subqueries — show it).
3. **Reliability & Safety (20%)**: guardrails, citation-or-refuse behavior ("I don't know" when KB has no answer), no secrets, synthetic-data hygiene, evaluation harness. Cheap points most teams skip.
4. **UX & Presentation (15%)**: clean demo flow + polished README/diagram. The 5-min video is the judging surface — script it.
5. **Creativity (15%)**: a distinctive twist on Challenge A, not architecture-by-numbers.
6. **Community vote (10%)**: post progress on Discord, ask for votes (no inducements — prohibited).

## "Highly valued extras" (verbatim from the starter kit)

- Evaluations, telemetry, or observability
- Advanced reasoning patterns
- Responsible AI controls and fallbacks
- A clear hosted deployment story for the final solution
