---
kind: module
id: do-c01-m04
vertical: devops-platform
course_id: do-c01
title: Traceability and flow of work
level: foundational
grounded_on: "AZ-400 skills outline (2026-04-24), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/az-400
synthetic: true
order: 4
prereqs: [do-c01-m03]
objectives:
  - Design traceability from work item to deployment
  - Integrate Azure Boards with GitHub repositories
  - Build flow metrics like cycle time and lead time
---

# Traceability and flow of work

It is 2 a.m. and Meridian Tea Co.'s checkout is throwing errors after last night's deploy. The on-call engineer asks the only question that matters — "what changed?" — and cannot answer it. They have the commits, but no thread connecting them to *why* each change was made or which feature it belonged to. The reverse is just as broken: a product manager asks "did the loyalty-points feature actually ship?" and nobody can say without spelunking through merge messages. Both are the same gap: there is no traceable thread from a unit of planned work, through the commits and pull request that implemented it, to the deployment that released it. This module is about weaving that thread and measuring how work flows along it.

## Learning objectives

By the end of this module you will be able to:

- Design end-to-end traceability so any deployment can be traced back to the work items and pull requests that produced it.
- Integrate Azure Boards with GitHub repositories so commits and pull requests automatically link to work items.
- Build flow metrics — cycle time and lead time among them — and surface them on a dashboard the team actually uses.

## Concepts

### Traceability is a chain, and it must be built into the workflow

Traceability means that for any change you can move in either direction along a chain: **work item → branch/commit → pull request → deployment**, and back. The "deployment" anchor is the tag from the previous module — it marks exactly what shipped, and from that commit you can find the merged pull requests and from those the work items. Teams lack traceability not because the data is impossible to capture but because capturing it was left to human diligence, and humans under deadline write `fix stuff` and move on.

The fix is to make linking part of the workflow rather than an act of virtue. The lightest technique is a *linking convention*: reference the work item by ID in the branch name and the pull request. When the workflow records the link — a commit message that mentions a work item the tracking system recognizes — the chain assembles itself. Design it backwards from the question you'll answer at 2 a.m.: "given a deployed commit, can I list every work item in it?"

### Integrating Azure Boards with GitHub

A common, powerful arrangement is to plan work in **Azure Boards** while the code lives in **GitHub** — rich work-item tracking and the GitHub developer experience together. The integration connects the two so that mentioning a Boards work item from a GitHub commit or pull request creates a live, two-way link: the work item shows the commits and PR that implemented it, and the PR shows the work item it satisfies. After connecting the Boards app to the repository, developers create links by referencing the work item ID with the recognized syntax (commonly `AB#123`) in commit messages, PR titles, or descriptions. The exact syntax and setup steps evolve, so confirm them in the current Boards–GitHub integration docs before standardizing your convention.

This closes the chain without extra work: a developer already writing a commit message simply includes `AB#1042`, and the planning-to-code link exists forever. Combined with deployment tags, the on-call engineer can go from "the commit that broke checkout" to "the pull request" to "work item AB#1042, the loyalty-points change" in under a minute.

### Flow metrics: measuring the system, not the people

Once work is traceable, you can measure how it *flows* — and flow metrics describe the system, not individual productivity, which is the only honest way to use them. Two are foundational. **Lead time** runs from when a request is made (the work item is created) until it is delivered to the customer — the customer's view of "how long until I get what I asked for." **Cycle time** is the narrower span from when work *actively starts* ("in progress") until done — the team's view of "how long does the work itself take." Lead time minus cycle time is roughly your queue and wait time, often where the real delay hides.

Two more round out the picture: **deployment frequency** (how often you successfully release) and **time to recovery** (how long from a production failure until service is restored). Together these tell you whether the team is fast *and* stable. A dashboard's point is not to wave green numbers at management; it is to expose where flow stalls — a wide lead-minus-cycle gap says work queues; a rising recovery time says incidents are getting harder to fix — so you can act on causes.

## Walkthrough: Meridian links work to deployments and reads the flow

Meridian plans in Azure Boards and codes in GitHub. After an admin connects the Boards app to `storefront`, the convention is simple: every branch and commit references its work item, and releases are tagged. An engineer implementing loyalty points (work item 1042) works like this.

```bash
# Branch name carries the work item id for human readability
git switch -c feature/AB1042-loyalty-points main

# The commit message mentions the work item so Boards links it automatically
git commit -am "checkout: accrue loyalty points on order complete

Implements points accrual per the loyalty rules.
AB#1042"

git push -u origin feature/AB1042-loyalty-points
```

The pull request title also includes `AB#1042`. Once it merges to `main` and the release ships, the team tags the deployed commit so it is a permanent anchor.

```bash
git switch main
git pull --rebase origin main
git tag -a v2.5.0 -m "Release 2.5.0 — loyalty points (AB#1042)"
git push origin v2.5.0
```

Now the chain is whole: work item 1042 shows the commits and PR; the PR shows the work item; tag `v2.5.0` marks exactly what was deployed. At 2 a.m., the on-call engineer finds the failing commit, sees it belongs to the PR for `AB#1042`, and knows the loyalty change is the suspect. For flow, the team uses Azure DevOps **Analytics** as the dashboard data source — cycle time and lead time have built-in widgets, and deployment frequency derives from release tags. An analyst can also query Analytics with OData, sketching average lead time by iteration:

```text
# OData (Azure DevOps Analytics) — average lead time per iteration, conceptually
GET https://analytics.dev.azure.com/meridian/storefront/_odata/v3.0/WorkItems
  ?$filter=State eq 'Closed' and CompletedDate ge 2026-01-01Z
  &$apply=groupby((IterationPath),
      aggregate(LeadTimeDays with average as AvgLeadTimeDays))
```

Pin the cycle-time and lead-time widgets and a deployment-frequency tile to a shared dashboard. The team now watches the *gap* between lead and cycle time — when it widens, work is queuing somewhere, a process problem to fix, not a person to push. Treat exact OData paths and widget names as version-dependent and confirm them in the current Analytics docs.

## Common pitfalls

- **Leaving linking to human diligence.** "Remember to reference the work item" fails under deadline. Bake the link into the branch, commit, and PR convention so the chain assembles automatically.
- **Tagging nothing, so deployments aren't anchored.** Without a tag on the deployed commit, "what shipped" is guesswork. Tag every release as the permanent anchor.
- **Confusing lead time and cycle time.** Lead time is the customer's request-to-delivery span; cycle time is active-work-to-done. Reporting one as the other hides the queue time you most need to see.
- **Weaponizing flow metrics against individuals.** Flow metrics describe the system; using them to rank people corrupts the data as everyone games their numbers. Measure the flow, fix the system.
- **Building a dashboard nobody reads.** A wall of green tiles with no owner is decoration. Tie each metric to a question the team asks and a response when it moves.

## Knowledge check

1. After a bad deploy, the on-call engineer can see the commits but cannot tell which feature or planned work each belonged to. Which two practices, used together, would have given them the answer fast?
2. A team's cycle time is short but its lead time is long. What does the gap most likely indicate, and where should they look?
3. Why is it a mistake to use cycle time to compare individual engineers' productivity?

<details>
<summary>Answers</summary>

1. Referencing the work item in commits/PRs (e.g. `AB#1042`) so Boards links code to planning, plus tagging the deployed commit so "what shipped" is anchored — together they let you trace a deployed commit back to its work items. — The chain only works when both the planning link and the deployment anchor are captured automatically.
2. The gap (lead time minus cycle time) is queue and wait time, so the delay is happening before work actively starts — likely in backlog prioritization, waiting for review, or waiting to be picked up. — Short cycle time means the work itself is fast; long lead time means it waits.
3. Because flow metrics measure the system, not people; using cycle time to rank individuals invites gaming (splitting tickets, avoiding hard work) that corrupts the metric and the team. — The metric's value is diagnosing system flow, which individual comparison destroys.

</details>

## Summary

Traceability is a chain from work item to commit to pull request to deployment, and it survives only when each link is captured by the workflow — branch and commit conventions, an Azure Boards–GitHub integration that auto-links `AB#` mentions, and release tags that anchor what shipped. Once the chain exists, flow metrics like lead time, cycle time, deployment frequency, and time to recovery turn it into insight: read the gap between lead and cycle time to find where work waits, and always measure the system, not the people. With this module you complete the foundation of healthy collaboration — branching, enforced review, a fast governable repository, and a traceable, measurable flow of work — that the rest of the DevOps & Platform vertical builds upon.

## Further learning

- [Azure Boards–GitHub integration](https://learn.microsoft.com/en-us/azure/devops/boards/github/)
- [Cumulative flow, lead time, and cycle time analytics](https://learn.microsoft.com/en-us/azure/devops/report/dashboards/cycle-time-and-lead-time)
- [Link GitHub commits and pull requests to work items](https://learn.microsoft.com/en-us/azure/devops/boards/github/link-to-from-github)
- [What is GitHub flow?](https://learn.microsoft.com/en-us/azure/devops/repos/git/git-branching-guidance)
