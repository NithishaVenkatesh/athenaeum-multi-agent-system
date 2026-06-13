---
kind: course
id: as-c01
vertical: architecture-security
course_id: as-c01
title: Designing Azure Infrastructure
level: foundational
grounded_on: "AZ-305 skills outline (2026-04-17), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/az-305
synthetic: true
prereqs: []
objectives: []
---

# Designing Azure Infrastructure

Most cloud failures are not coding failures — they are design failures that surface months later as a runaway bill, a latency complaint, or a 3 a.m. outage. This course teaches you to make the foundational infrastructure decisions that determine whether an Azure workload is cheap, fast, and resilient, or none of those. You will learn to read a workload's real requirements and translate them into a defensible choice of compute, network, storage, and application architecture — and to write down *why* you chose each one.

## Who this is for

You are a developer, infrastructure engineer, or aspiring solution architect who can already deploy individual Azure resources but has not yet had to defend an end-to-end design to stakeholders. You are comfortable with the portal and basic `az` CLI commands. No prior architecture course is assumed — this is the entry point for the Cloud Solution Architecture & Security vertical, and later courses (Identity, Governance & Resilience; Zero-Trust Security Architecture) build directly on the design instincts you form here.

## What you'll be able to do

- Derive infrastructure requirements from a workload description instead of guessing.
- Recommend between virtual machines, containers, serverless, and batch compute with a clear rationale.
- Design network connectivity, load balancing, and routing that balance reach, performance, and security.
- Choose relational and non-relational storage that fits access patterns, durability needs, and budget.
- Compose messaging, events, caching, and API integration into a coherent application architecture.
- Document a design as a decision matrix that survives review by peers and finance.

## Module path

This course is four sequential modules; each builds on the last.

1. **Designing compute solutions** — match VMs, containers, serverless, and batch to workload requirements and cost.
2. **Designing network solutions** — connect to the internet and on-premises, then optimize routing, load balancing, and security.
3. **Designing data storage solutions** — pick relational and non-relational stores, tiers, and a cost/performance balance.
4. **Designing application architecture** — wire services together with messaging, events, caching, API integration, and automated deployment.

## Prerequisites

None — this is an entry point for the vertical. You should be able to create resources in the Azure portal, read a basic `az` command, and reason about an application's request volume and data shape. Familiarity with HTTP, TCP/IP fundamentals, and the difference between SQL and NoSQL will make the storage and network modules land faster, but each module re-establishes the concepts it depends on.

## How this fits the bigger picture

Architecture is the discipline of making *reversible* decisions cheaply and *irreversible* decisions carefully. The infrastructure choices in this course — compute model, network topology, storage engine, integration style — are among the most expensive to reverse once a workload is in production, so they reward deliberate design. A compute model chosen by habit, a storage engine forced to do a job it was never built for, or a synchronous call where a queue belonged: each looks harmless on a whiteboard and becomes a recurring cost or an outage in production. The habit this course builds is to slow down at exactly these decision points, write the requirements first, and let them choose the service rather than the reverse. Everything in the rest of the vertical sits on top of this foundation: identity and governance assume you know what resources exist and how they connect; resilience and business continuity assume you understand the failure modes of the compute and data tiers you chose; Zero-Trust security assumes a network and application topology to secure. Microsoft frames this kind of design work through the Azure Well-Architected Framework — five pillars of reliability, security, cost optimization, operational excellence, and performance efficiency — and you will see those tradeoffs surface in every module. By the end you will not just know which services exist; you will know how to *choose among them and write down why*, which is the actual job of an architect.
