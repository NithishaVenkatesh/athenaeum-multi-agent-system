---
title: Synthetic data — rules and starter datasets
tags: [synthetic-data, requirement, challenge-a, reference]
status: stable
sources:
  - Reasoning Agents starter kit (pasted 2026-06-12)
updated: 2026-06-12
related: [compliance, challenge-a-brief, foundry-iq]
---

# Synthetic data (REQUIRED — synthetic only, no PII ever)

Guardrails: fabricated identifiers (`L-1001`, `EMP-001`, `TEAM-A`); no real names/emails/doc titles/customer records; representative but obviously fictional; validate generated outputs before demos; README must declare data synthetic + demo-only.

## Dataset 1: Learner performance

```json
[
  {"learner_id": "L-1001", "role": "Cloud Engineer", "certification": "AZ-204", "practice_score_avg": 67, "hours_studied": 18, "exam_outcome": "Fail"},
  {"learner_id": "L-1002", "role": "DevOps Engineer", "certification": "AZ-400", "practice_score_avg": 82, "hours_studied": 24, "exam_outcome": "Pass"},
  {"learner_id": "L-1003", "role": "Data Engineer", "certification": "DP-203", "practice_score_avg": 74, "hours_studied": 20, "exam_outcome": "Pass"}
]
```

## Dataset 2: Work activity signals (Work IQ stand-in)

```json
[
  {"employee_id": "EMP-001", "meeting_hours_per_week": 22, "focus_hours_per_week": 10, "preferred_learning_slot": "Morning"},
  {"employee_id": "EMP-002", "meeting_hours_per_week": 15, "focus_hours_per_week": 18, "preferred_learning_slot": "Afternoon"}
]
```

## Dataset 3: Fabric IQ semantic model seed

```json
{
  "certifications": [
    {"id": "AZ-204", "skills": ["API Development", "Azure Functions", "Storage"], "recommended_hours": 20},
    {"id": "AZ-400", "skills": ["CI/CD", "Monitoring", "GitHub Actions"], "recommended_hours": 25}
  ]
}
```

## Synthetic documents (→ Foundry IQ knowledge sources)

**Engineering Certification Enablement Guide**: role → primary/secondary cert (Cloud Eng: AZ-204/AZ-305; DevOps: AZ-400); study pattern 1–2h daily, weekly checkpoints, target 75% practice score before exam.

**Quarterly Team Learning Report**: avg study time 21h, pass rate 68%; observation: >20 study hours AND >75% practice score ⇒ stronger outcomes.

**Workload Insights Report**: >20 meeting h/wk ⇒ lower study completion; optimal at 12–18 meeting hours + ≥15 focus hours; recommendation: schedule learning blocks in focus-heavy periods.

## Embedded rules to encode in agents

- Pass threshold heuristic: practice ≥75% AND hours ≥ recommended ⇒ ready
- Workload rule: meeting hours > 20/wk ⇒ reduce weekly study load, extend timeline
- Slot selection: schedule in `preferred_learning_slot` within focus windows

## Quality checklist before loading into Foundry IQ (adapted from kit)

- Originality (all fictional), safety (no secrets/PII), consistency (same names everywhere),
  retrievability (clear headings/tags/summaries), small focused chunks,
  mutable state kept separate from static reference docs.
