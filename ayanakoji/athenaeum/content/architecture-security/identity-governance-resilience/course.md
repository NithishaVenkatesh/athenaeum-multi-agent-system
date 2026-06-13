---
kind: course
id: as-c02
vertical: architecture-security
course_id: as-c02
title: Identity, Governance & Resilience
level: intermediate
grounded_on: "AZ-305 skills outline (2026-04-17), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/az-305
synthetic: true
prereqs: [as-c01]
objectives: []
---

# Identity, Governance & Resilience

Choosing the right virtual machine size is the easy part of cloud architecture. The hard part is everything that surrounds the workload: who is allowed to reach it, how the organization keeps a thousand subscriptions from drifting into chaos, what you can see when something breaks at 3 a.m., and whether the business survives the loss of a region. These concerns cut across every workload, rarely have a single correct answer, and are where most production incidents and audit findings actually originate. This course teaches you to design them deliberately, as an architect who will sign their name to a design document and defend it in a review — weighing trade-offs out loud rather than reaching for a default.

## Who this is for

You are a cloud engineer, solution architect, or platform lead who can already pick compute, network, and storage for a workload — the skills from **Designing Azure Infrastructure** (as-c01). You now need to design the connective tissue: identity, governance, observability, and business continuity. You are comfortable reading Azure resource hierarchies and have seen Microsoft Entra ID, RBAC, and Azure Monitor in passing, even if you have never designed them from scratch.

## What you'll be able to do

- Recommend an authentication and identity-management solution that balances user experience, hybrid reach, and Zero-Trust controls.
- Design an authorization model using Azure RBAC, custom roles, and Privileged Identity Management, and centralize secrets in Key Vault.
- Structure management groups, subscriptions, and resource groups, and enforce consistency with Azure Policy and a tagging strategy.
- Design a logging and monitoring solution: where logs land, how they are routed, and how alerts and workbooks turn telemetry into action.
- Design backup, disaster recovery, and high-availability solutions that meet explicit recovery-time and recovery-point objectives.

## Module path

This course is four sequential modules; each builds on the last.

1. **Designing identity and access** — authentication, identity management, authorization, and secret management as a single coherent design.
2. **Designing governance** — management-group hierarchies, subscription topology, Azure Policy, tagging, and compliance at scale.
3. **Designing logging and monitoring** — what to collect, where to route it, and how to make telemetry actionable.
4. **Designing business continuity** — backup, disaster recovery, and high availability tied to RTO and RPO.

## Prerequisites

Completion of **Designing Azure Infrastructure** (as-c01), or equivalent experience designing Azure compute, networking, and storage. You should understand subscriptions, resource groups, and the basic Azure resource manager model, and have a working mental picture of Microsoft Entra ID as a directory and identity provider. No prior security-operations experience is assumed; the Zero-Trust depth comes in the next course, **Zero-Trust Security Architecture** (as-c03).

## How this fits the bigger picture

Infrastructure design answers "what runs where." This course answers the questions a real architecture review actually dwells on: can we prove who did what, can we govern hundreds of subscriptions without a human gatekeeper, can we see failures before customers do, and can we recover. These four concerns map directly onto pillars of the Azure Well-Architected Framework — security, operational excellence, and reliability — and they reinforce one another in practice: the diagnostic settings you design for monitoring are enforced by the governance policies you design for compliance, and the identity model you choose determines who can even reach the recovery controls. Treating them as one connected system, rather than four checklists, is what separates a platform from a pile of subscriptions. Master them and you stop designing isolated workloads and start designing platforms. The course is grounded on the AZ-305 design skills, but the goal is durable judgment: given a workload's requirements and constraints, recommend a design and explain the trade-offs you accepted, because in architecture there is rarely a single correct answer, only a defensible one.
