---
kind: module
id: as-c02-m03
vertical: architecture-security
course_id: as-c02
title: Designing logging and monitoring
level: intermediate
grounded_on: "AZ-305 skills outline (2026-04-17), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/az-305
synthetic: true
order: 3
prereqs: [as-c02-m02]
objectives:
  - Recommend a logging solution centered on Azure Monitor and Log Analytics workspaces
  - Recommend a solution for routing platform, resource, and security logs to the right destinations
  - Recommend a monitoring solution using metrics, alerts, and workbooks tied to operational needs
---

# Designing logging and monitoring

It is 3 a.m. and the checkout service at Lumen Mart, a fictional grocery chain, is returning errors. The on-call engineer logs in and finds — nothing. Diagnostic logs were never enabled on half the resources, the logs that exist are scattered across five subscriptions with no central place to query them, and there is no alert that fired before customers started complaining. The infrastructure was designed well; the *observability* was not. An architecture that you cannot see into is one you cannot operate. This module teaches you to design logging and monitoring so that telemetry is collected by default, lands somewhere you can actually query, and turns into alerts and views that answer real operational questions before customers ask them.

## Learning objectives

By the end of this module you will be able to:

- Recommend a logging solution built on Azure Monitor and Log Analytics workspaces.
- Recommend a strategy for routing platform, resource, and security logs to appropriate destinations.
- Recommend a monitoring solution using metrics, alert rules, action groups, and workbooks.
- Decide what telemetry to collect and how long to retain it, balancing visibility against cost.

## Concepts

### The two shapes of telemetry: metrics and logs

Azure Monitor is the umbrella, and underneath it telemetry comes in two fundamentally different shapes. **Metrics** are numeric, time-stamped values sampled at regular intervals — CPU percentage, request count, queue depth. They are cheap to store, fast to query, and ideal for "is it healthy right now and how is the trend." **Logs** are structured event records — a request with its status code and duration, an audit entry, an exception with a stack trace. They are richer and queryable with the Kusto Query Language but cost more to ingest and store.

The design implication: use metrics for fast, high-frequency health signals and alerting on thresholds, and use logs for investigation, correlation, and anything you need to slice by arbitrary dimensions. You will almost always design both, and the mistake is treating them as interchangeable.

### Log Analytics workspaces: where logs live, and how many

Logs land in a **Log Analytics workspace**, a container that stores log data and is the thing KQL queries run against. The central design question is *workspace topology*: one workspace for the whole organization, or many. A single workspace makes cross-resource correlation trivial — one query spans everything — and simplifies access if everyone may see everything. Multiple workspaces give you data-residency boundaries (a workspace per region for sovereignty requirements), access isolation (a security team's workspace separate from app teams), and independent retention and cost ownership.

A common, defensible pattern is a *small number* of workspaces: one per data-sovereignty region, perhaps split by sensitivity, rather than one-per-team sprawl. Retention is set per workspace (and increasingly per table), so you can keep security logs for a long compliance window while expiring verbose application logs sooner — this is a major cost lever. Verify current retention limits and archive-tier behavior in the docs, since these change.

### Routing telemetry: diagnostic settings and the destinations

Resources do not send their logs anywhere by default. A **diagnostic setting** on each resource declares *which* log categories and metrics to emit and *where* to send them. There are three destination types, and good designs use them for different purposes. A **Log Analytics workspace** is the destination for interactive querying, alerting, and dashboards. **Azure Storage** is the destination for cheap, long-term archival — you would not query it interactively, but it satisfies "keep audit logs for seven years." **Event Hubs** is the destination for streaming telemetry to an external SIEM or a third-party analytics platform in near-real-time.

Because nothing emits diagnostics until a setting exists, you should not configure these by hand on hundreds of resources — you enforce them with the `deployIfNotExists` Azure Policy effect from the previous module, so every new resource automatically gets the right diagnostic setting. This is where governance and observability meet. Separately, *Activity Log* (subscription-level control-plane events) and *Microsoft Entra audit and sign-in logs* are routed the same way and are essential for security investigation.

### Turning telemetry into action: alerts, action groups, workbooks

Collection is necessary but not sufficient — Lumen Mart had some logs and still flew blind. **Alert rules** evaluate a metric threshold or a log query on a schedule and fire when a condition is met. An alert points at an **action group**, a reusable bundle of notifications and automated responses (email and SMS, a webhook to an incident tool, an Azure Function or Logic App for automated remediation). Designing action groups as reusable units keeps notification logic out of individual alerts. Finally, **workbooks** are interactive, parameterized reports that combine metrics, logs, and text into a view tailored to an audience — an on-call dashboard, an executive summary, a capacity-planning view.

## Walkthrough: investigating Lumen Mart's checkout errors

Lumen Mart has now centralized its application logs into a Log Analytics workspace via diagnostic settings enforced by policy. As the architect, you write the KQL that the on-call workbook and an alert will both use: surface the rate of HTTP 5xx responses from the checkout service over the last hour, bucketed so a spike is obvious.

```kql
// Checkout 5xx error rate over the last hour, in 5-minute buckets.
AppRequests
| where TimeGenerated > ago(1h)
| where AppRoleName == "checkout-service"
| summarize
    total = count(),
    failures = countif(ResultCode >= 500)
    by bin(TimeGenerated, 5m)
| extend failureRatePct = round(100.0 * failures / total, 2)
| project TimeGenerated, total, failures, failureRatePct
| order by TimeGenerated asc
```

The query reads from the `AppRequests` table (Application Insights request telemetry), filters to the checkout role, and uses `summarize ... by bin(TimeGenerated, 5m)` to roll events into five-minute buckets — the bucketing is what turns a flat list of requests into a trend you can see. `countif(ResultCode >= 500)` counts only server errors, and `failureRatePct` expresses them as a percentage so the signal is comparable regardless of traffic volume. You would base a *log alert rule* on this query (fire when `failureRatePct` exceeds, say, 5 over two consecutive evaluations) wired to an action group that pages on-call and posts to the incident channel. The same query backs a workbook tile, so the engineer who gets paged lands on a view that already shows the spike. Now the system tells you before the customers do.

## Common pitfalls

- **No diagnostic settings, so resources emit nothing.** This is Lumen Mart's original failure. Resources are silent by default; enforce diagnostic settings with `deployIfNotExists` policy so collection is automatic, not manual.
- **Ingesting everything into one expensive tier.** Logs cost money to ingest and retain. Route verbose, low-value telemetry to cheaper storage or a basic table, reserve interactive workspace ingestion for what you query, and set retention per data type.
- **Alerting on symptoms with no actionable signal.** An alert that fires constantly gets muted, and one with no clear owner gets ignored. Alert on conditions a human can act on, route them through well-scoped action groups, and tune thresholds to reduce noise.
- **Workspace sprawl.** One workspace per team makes cross-service correlation a nightmare during an incident. Prefer a small number of workspaces aligned to sovereignty and sensitivity boundaries.
- **Forgetting control-plane and identity logs.** Application metrics won't tell you that someone changed a firewall rule or that sign-ins from an unusual location spiked. Route Activity Log and Entra sign-in/audit logs alongside resource logs.

## Knowledge check

1. Lumen Mart must keep audit logs for seven years for compliance but only queries the last 30 days interactively. How do you design the routing to satisfy both cost and compliance?
2. A new microservice is deployed weekly and the team keeps forgetting to turn on its logs. What is the durable architectural fix, and which earlier governance tool does it rely on?
3. You want a single alert definition to notify on-call by SMS, open an incident ticket, and trigger an automated restart. How do you structure this in Azure Monitor?

<details>
<summary>Answers</summary>

1. Use two destinations in the diagnostic setting: a Log Analytics workspace with ~30-day retention for interactive querying, plus an Azure Storage account (or a long archive tier) for cheap seven-year retention — query the workspace, archive to storage.
2. Enforce a diagnostic setting with a `deployIfNotExists` Azure Policy assigned at a management group, so every new resource automatically gets logging configured — it relies on the Azure Policy governance from Module 2.
3. Define one alert rule and point it at a single action group that bundles the SMS notification, the webhook to the ticketing tool, and the automation (Function/Logic App) for the restart — action groups are reusable response bundles.

</details>

## Summary

You cannot operate what you cannot see, so design observability deliberately: collect both metrics and logs, route them with diagnostic settings (enforced by policy, not by hand) to the right destination for the job — workspace for querying, storage for archive, Event Hubs for streaming — and turn telemetry into action with tuned alerts, reusable action groups, and audience-specific workbooks. Keep workspace topology lean and retention cost-aware. With the platform visible, the final module asks the hardest reliability question of all: when something fails completely, does the business recover? That is **Designing business continuity**.

## Further learning

- [Azure Monitor overview](https://learn.microsoft.com/en-us/azure/azure-monitor/overview)
- [Log Analytics workspace overview](https://learn.microsoft.com/en-us/azure/azure-monitor/logs/log-analytics-workspace-overview)
- [Diagnostic settings in Azure Monitor](https://learn.microsoft.com/en-us/azure/azure-monitor/essentials/diagnostic-settings)
- [Create and manage action groups in the Azure portal](https://learn.microsoft.com/en-us/azure/azure-monitor/alerts/action-groups)
