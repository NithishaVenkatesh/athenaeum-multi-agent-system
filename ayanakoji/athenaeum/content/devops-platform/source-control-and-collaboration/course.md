---
kind: course
id: do-c01
vertical: devops-platform
course_id: do-c01
title: Source Control & Collaboration Strategy
level: foundational
grounded_on: "AZ-400 skills outline (2026-04-24), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/az-400
synthetic: true
prereqs: []
objectives: []
---

# Source Control & Collaboration Strategy

Most delivery problems that look like "engineering is slow" are really collaboration problems wearing an engineering costume: branches that live for weeks and merge in pain, pull requests that rubber-stamp through with no real review, repositories that have quietly grown a two-gigabyte history nobody can clone over hotel Wi-Fi, and a release manager who cannot answer the simplest question — "which work item shipped in last night's deploy?" This course teaches you to design the source-control and collaboration practices that make a team fast *and* safe, using Git, Azure Repos, GitHub, and Azure Boards as the concrete tooling.

## Who this is for

You are an engineer, tech lead, or aspiring platform owner who already uses Git day to day — you can branch, commit, and open a pull request — but you have never had to *design* how a whole team should work. You want to make deliberate choices about branching, review policy, repository scale, and traceability rather than inheriting whatever the last person set up. No prior courses are required; this is the entry point for the DevOps & Platform vertical, and later courses on pipelines, releases, and security build directly on the habits you form here.

## What you'll be able to do

- Choose a branching strategy (trunk-based, feature-branch, or release-branch) that fits a team's size, release cadence, and risk tolerance, and defend the choice.
- Design a pull-request workflow with branch policies and protection rules that enforce quality without grinding delivery to a halt.
- Apply merge restrictions and required reviews that scale with the risk of the code being changed.
- Manage large binary files with Git LFS and keep a repository fast to clone as it grows.
- Configure repository permissions and tags so the right people have the right access and history is navigable.
- Build end-to-end traceability from a work item, through commits and pull requests, to a deployment, and surface flow metrics like cycle time and lead time on a dashboard.

## Module path

This course is four sequential modules; each builds on the last.

1. **Choosing a branching strategy** — compare trunk-based, feature, and release branching and match a model to a team's reality.
2. **Pull requests, policies, and protection** — turn review from theater into an enforced quality gate with branch policies.
3. **Managing and scaling repositories** — keep repos fast with Git LFS, sane permissions, and a scaling strategy as history grows.
4. **Traceability and flow of work** — wire work items, commits, and pull requests together and measure how work actually flows.

## Prerequisites

Working comfort with Git fundamentals: cloning, branching, committing, pushing, and opening pull requests from the command line or an IDE. You should understand what a merge and a rebase are at a conceptual level, even if you do not yet know when to prefer one. Familiarity with either Azure Repos or GitHub is helpful but not assumed — the course introduces both. None of the later courses are required first; this is an entry point for the vertical.

## How this fits the bigger picture

Source control is the foundation that every other DevOps practice sits on. A continuous-integration pipeline can only be as reliable as the branching model that feeds it; a release strategy can only be as safe as the review gate that admits code to the main branch; an incident retrospective can only be as honest as the traceability that connects a deployment back to its changes. The decisions you make here — how branches flow, who can merge what, how you measure the work — set the ceiling for everything the platform vertical builds on top. Get these right and the rest of DevOps becomes a series of refinements rather than a series of rescues. Get them wrong and you spend the next two years firefighting symptoms. This course is where you build the foundation deliberately, so the teams that depend on it inherit speed and safety by default rather than by luck.
