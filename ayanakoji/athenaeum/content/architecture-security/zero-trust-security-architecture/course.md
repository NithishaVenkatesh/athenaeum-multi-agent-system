---
kind: course
id: as-c03
vertical: architecture-security
course_id: as-c03
title: Zero-Trust Security Architecture
level: advanced
grounded_on: "SC-100 skills outline (2026-04-27), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/sc-100
synthetic: true
prereqs: [as-c01, as-c02]
objectives: []
---

# Zero-Trust Security Architecture

The hardest part of security architecture is not picking products — it is deciding, across an entire estate, what you will trust, what you will verify, and what you will assume is already compromised. This course teaches you to design a Zero-Trust security architecture the way a senior architect actually does it: starting from business resiliency goals, anchoring every decision to a reference architecture and a benchmark, and then proving the design works through detection, posture management, and data protection. You will leave able to defend an end-to-end security design — not just a list of enabled features — to a security review board.

## Who this is for

You are a solution architect, security engineer, or platform lead who already understands Azure infrastructure and identity, and who is now responsible for the *whole* security posture of a workload or an organization. You should have completed **Designing Azure Infrastructure** (as-c01) and **Identity, Governance & Resilience** (as-c02), because this course assumes you can reason about network topology, resource organization, and identity as a control plane. The work here is architectural and cross-cutting: you will be making tradeoffs that touch identity, network, endpoint, application, and data simultaneously.

## What you'll be able to do

- Translate business resiliency goals into a Zero-Trust security strategy with a defensible modernization sequence.
- Map a proposed design onto the Microsoft Cybersecurity Reference Architectures (MCRA) and the Microsoft cloud security benchmark (MCSB).
- Design a detection-and-response capability that combines XDR and SIEM, and automate it with SOAR.
- Evaluate threat-detection coverage against the MITRE ATT&CK matrix and find the gaps that matter.
- Assess and improve security posture across hybrid and multicloud estates using Defender for Cloud, Secure Score, and Azure Arc.
- Design layered protection for applications and data using WAF, API security, workload identities, encryption, and data classification.

## Module path

This course is four sequential modules; each builds on the last.

1. **Zero-Trust strategy, MCRA, and MCSB** — turn resiliency goals into a strategy anchored to reference architectures and a rapid modernization plan.
2. **Designing security operations** — build detection and response with XDR and SIEM, automate it with SOAR, and measure coverage with MITRE ATT&CK.
3. **Infrastructure and posture management** — evaluate and raise posture across hybrid and multicloud, including containers, using Defender for Cloud, Secure Score, and Arc.
4. **Securing applications and data** — protect the application and data tiers with a lifecycle strategy, WAF, API security, encryption, and data discovery.

## Prerequisites

Completion of **as-c01 (Designing Azure Infrastructure)** and **as-c02 (Identity, Governance & Resilience)**, or equivalent experience. You should be fluent reading `az` CLI and ARM/Bicep, understand how Microsoft Entra ID issues and conditions access, and know the difference between a control plane and a data plane. Familiarity with how logs flow into a central workspace will make the security-operations module land faster, but the module re-establishes that model where it depends on it.

## How this fits the bigger picture

Zero Trust is not a product you buy; it is a design principle — *verify explicitly, use least-privilege access, assume breach* — that you apply across every layer you have already learned to build. This course is the capstone of the architecture-security vertical because it forces you to reason about all of those layers at once and to justify the whole. Microsoft expresses this design philosophy through the MCRA, which shows how the capabilities fit together, and the MCSB, which gives you concrete, auditable controls to map against. The discipline you build here — designing for assumed breach, then proving coverage with telemetry and posture scores — is exactly the work a principal security architect is paid to do, and it is the lens every later security decision in your career will pass through.
