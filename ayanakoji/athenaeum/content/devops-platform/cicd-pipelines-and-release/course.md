---
kind: course
id: do-c02
vertical: devops-platform
course_id: do-c02
title: CI/CD Pipelines & Release Engineering
level: intermediate
grounded_on: "AZ-400 skills outline (2026-04-24), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/az-400
synthetic: true
prereqs: [do-c01]
objectives: []
---

# CI/CD Pipelines & Release Engineering

The gap between "the code is merged" and "the change is safely running in production" is where most engineering teams quietly lose time, sleep, and trust. This course teaches you to close that gap deliberately. You will build multi-stage delivery pipelines that compile, test, package, and ship software with the same rigor you apply to the code itself — and you will learn to release changes so that a bad deploy degrades gracefully instead of paging the whole team at 2 a.m.

## Who this is for

This course is for engineers and platform specialists who already commit to shared repositories, open pull requests, and understand the basics of Git branching and build tooling — the ground covered in **Source Control & Collaboration Foundations** (do-c01). You do not need prior pipeline experience, but you should be comfortable reading YAML, running shell commands, and reasoning about how a build turns source into a deployable artifact. If you have ever clicked "deploy" and held your breath, you are in the right place.

The examples lean on Azure Pipelines and Azure services because the concepts behind the AZ-400 outline are expressed most concretely there, but the skills transfer. A stage that gates on a coverage threshold, an artifact that carries a SemVer string, a canary that watches its own telemetry — these patterns look almost identical whether your team runs Azure Pipelines, GitHub Actions, or another platform entirely. Treat the specific tasks as illustrations of durable ideas.

## What you'll be able to do

- Author multi-stage YAML pipelines with reusable templates, variables, and trigger rules that control exactly when and how work runs.
- Design package feeds and a dependency-versioning strategy so that builds are reproducible and consumers can upgrade on their own schedule.
- Build a layered testing strategy and wire quality and release gates that block bad changes before they reach users.
- Integrate code-coverage analysis and read it without being misled by the headline number.
- Design progressive deployment strategies — blue-green, canary, rings, and feature flags — that shrink the blast radius of every release.

## Module path

This course is four sequential modules; each builds on the last.

1. **Building pipelines with YAML** — Express your whole delivery process as version-controlled YAML, with stages, jobs, templates, and triggers.
2. **Package management and artifact versioning** — Publish and consume dependencies through feeds, and give every artifact a meaningful, reproducible version.
3. **Testing strategy and quality gates** — Layer fast and slow tests, measure coverage, and gate promotion on objective signals.
4. **Progressive deployment strategies** — Release changes gradually with slots, canaries, rings, and feature flags so failures stay small.

## Prerequisites

You should have completed **Source Control & Collaboration Foundations** (do-c01) or hold equivalent experience: working comfortably with Git, branches, pull requests, and a build tool for at least one language stack. Familiarity with reading YAML and using a command line is assumed throughout. No prior Azure Pipelines or GitHub Actions experience is required — module one starts from the structure of a pipeline and builds up. The code examples use .NET and Node tooling, but you do not need to be an expert in either; the steps are explained in plain terms so the lesson lands regardless of your primary language.

## How this fits the bigger picture

Release engineering is the connective tissue of the devops-platform vertical: it is where source control, infrastructure, observability, and security all meet a running system. The patterns here — pipelines as code, immutable versioned artifacts, automated gates, and progressive exposure — are grounded in the concepts behind the AZ-400 outline, but they generalize well beyond any single tool. Whether your team runs Azure Pipelines, GitHub Actions, or something else, the durable skill is the same: turning the messy, manual ritual of "shipping" into a repeatable, observable, and reversible system you can trust. Later courses in this vertical assume you can deliver software this way, and treat your pipeline as the place where security scanning, infrastructure provisioning, and runtime telemetry are enforced rather than hoped for.
