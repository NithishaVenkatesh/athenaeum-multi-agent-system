---
kind: course
id: do-c03
vertical: devops-platform
course_id: do-c03
title: Secure DevOps & Observability
level: advanced
grounded_on: "AZ-400 skills outline (2026-04-24), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/az-400
synthetic: true
prereqs: [do-c01, do-c02]
objectives: []
---

# Secure DevOps & Observability

A pipeline that ships fast but leaks credentials, drifts away from its declared infrastructure, or goes dark the moment something breaks is not a platform — it is a liability with good uptime numbers. This course is about closing that gap. You will learn to describe your environments as code so they are reproducible and reviewable, to keep secrets out of source and out of build logs entirely, to catch vulnerable dependencies and exposed keys before they reach production, and to instrument the running system so that when an incident starts, you can see it, trace it, and explain it.

## Who this is for

You are a platform, DevOps, or senior application engineer who already designs branching strategies and authors CI/CD pipelines, and now owns the *security and operability* of what those pipelines deliver. You have completed **Source Control & Collaboration Strategy** (do-c01) and **CI/CD Pipelines & Release Engineering** (do-c02), or you work daily with equivalent practices. You are comfortable reading YAML, calling the `az` CLI, and reasoning about identity. You do not need prior Bicep or KQL experience — this course builds both.

## What you'll be able to do

- Define an infrastructure-as-code strategy and author Bicep that deploys repeatable, source-controlled environments.
- Manage secrets, keys, and certificates centrally and retrieve them at deploy time without ever writing them to disk or logs.
- Replace long-lived service-principal secrets with workload identity federation (OIDC) in both GitHub Actions and Azure Pipelines.
- Design a security-scanning strategy spanning dependencies, source code, secrets, licensing, and container images across the SDLC.
- Configure GitHub Advanced Security and Microsoft Defender for Cloud DevOps capabilities to enforce that strategy automatically.
- Instrument services with Application Insights, follow a request across service boundaries with distributed tracing, and interrogate telemetry with Kusto Query Language.

## Module path

This course is four sequential modules; each builds on the last.

1. **Infrastructure as code with Bicep** — declare environments as reviewable, idempotent code instead of clicking through the portal.
2. **Secrets and secretless authentication** — store credentials in Key Vault and, better still, eliminate stored credentials with federated identity.
3. **Security and compliance scanning** — automate detection of vulnerable dependencies, leaked secrets, and unsafe code throughout the pipeline.
4. **Instrumentation and monitoring** — make the platform observable with Application Insights, distributed tracing, and KQL.

## Prerequisites

You should be able to design a branching and pull-request workflow (do-c01) and author multi-stage YAML pipelines with templates, gates, and progressive deployment (do-c02). You will need an Azure subscription where you can create resource groups, a Key Vault, and an Application Insights resource, plus a GitHub or Azure DevOps organization where you can configure repository settings and service connections. Familiarity with Microsoft Entra ID concepts — tenants, app registrations, service principals, and managed identities — will make the second and third modules land faster.

## How this fits the bigger picture

DevOps and platform engineering is not only about delivery speed; it is about shipping *safely and observably* at speed. The first two courses in this vertical taught you to move code from a developer's branch into production reliably. This course hardens that path: it ensures the environments are defined, the credentials are protected, the artifacts are scanned, and the result is watchable. These are the practices that let a small platform team operate a large estate without the estate operating them. The patterns here — declarative infrastructure, secretless authentication, shift-left scanning, and unified telemetry — recur across every cloud and every compliance regime, so what you learn translates well beyond any single Azure service. By the end you will be able to hand a fellow engineer an environment that is reproducible by file, secured by identity, scanned by default, and observable by design.
