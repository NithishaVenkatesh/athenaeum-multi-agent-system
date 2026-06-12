---
title: Challenge A — Enterprise Learning System (the brief)
tags: [challenge-a, enterprise-learning, requirement, multi-agent]
status: stable
sources:
  - Reasoning Agents starter kit (challenge page, pasted 2026-06-12)
updated: 2026-06-12
related: [agent-architecture, synthetic-data, judging-rubric]
---

# Challenge A: Enterprise Learning System

Track: Reasoning Agents (Microsoft Foundry). Build a **multi-agent enterprise learning system** that helps organisations manage internal team certification programmes.

## The system must be able to

1. Understand certification requirements mapped to organisational roles
2. Generate team-level and role-based study plans
3. Provide grounded practice questions from approved knowledge sources
4. Offer feedback on team and individual progress
5. Adapt learning schedules to real work context and team capacity
6. Surface manager-level insights across team readiness and risk

## Baseline flow (verbatim logic)

1. Learner provides topics they want to study
2. **Learning Path Curator** suggests relevant content based on goals and role
3. **Study Plan Generator** converts content into a practical schedule accounting for workload
4. **Engagement Agent** keeps learner on track; reminders adapt to work patterns and focus windows
5. **Assessment Agent** evaluates readiness using grounded, cited questions
6. Pass → recommend next certification/advancement; Fail → **loop back** into preparation workflow
7. **Manager Insights Agent** gives visibility into team progress, risk areas, completion patterns

## Example use cases

- Employee requests a certification study plan that adapts to workload
- Manager wants team learning progress + exam-readiness risk visibility
- Assessment agent generates grounded, cited questions from approved org knowledge
- Planner uses historical study patterns + work signals to recommend realistic study windows

## Development approaches (either is valid)

- **Local**: OSS **Microsoft Agent Framework** (build/test custom agents locally)
- **Cloud**: **Microsoft Foundry** orchestration via UI or SDK
- Tip from kit: Microsoft Learn MCP server can extend capabilities

## Submission requirements (validity gate)

- [ ] Multi-agent system aligned to the challenge scenario
- [ ] Uses Microsoft Foundry (UI or SDK) and/or Microsoft Agent Framework
- [ ] Demonstrates reasoning and multi-step decision-making **across agents**
- [ ] Integrates external tools, APIs, and/or MCP where they add real value
- [ ] Integrates **≥1 Microsoft IQ layer**
- [ ] Synthetic data and synthetic documents only
- [ ] Demoable; agent interactions clearly explained
- [ ] Documentation: agent responsibilities, orchestration flow, tools, data sources

Note: must align to scenario, but **need not follow the suggested architecture exactly**.

## Env setup (from kit)

```env
AZURE_AI_PROJECT_ENDPOINT=<foundry project endpoint>   # Option 1 (recommended)
AZURE_AI_MODEL_DEPLOYMENT=gpt-4o
```

Python 3.10+, venv, `.env` git-ignored. Foundry requires an Azure subscription; free tier has model/quota/region limits — pay-as-you-go or Azure for Students recommended.
