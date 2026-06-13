---
kind: module
id: do-c03-m04
vertical: devops-platform
course_id: do-c03
title: Instrumentation and monitoring
level: advanced
grounded_on: "AZ-400 skills outline (2026-04-24), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/az-400
synthetic: true
order: 4
prereqs: [do-c03-m03]
objectives:
  - Configure telemetry collection with Application Insights for application and infrastructure
  - Inspect distributed traces to follow a request across service boundaries
  - Interrogate logs and metrics with basic Kusto Query Language (KQL)
---

# Instrumentation and monitoring

At 02:14 the rate-quote service starts returning 500s. Meridian Freight's on-call engineer opens the dashboard and sees... that requests are failing. Nothing more. Is it the database? A downstream pricing call? A bad deploy? Without telemetry, the next hour is guesswork and log-grepping across machines. A platform that is observable answers those questions in minutes: a single request can be followed end to end, the slow dependency is named, the error's stack trace is attached, and a KQL query turns "something is wrong" into "the pricing API's p95 latency tripled at 02:11, right after the 02:09 deploy." This module builds that capability.

## Learning objectives

By the end of this module you will be able to:

- Configure telemetry collection with Application Insights for applications and the infrastructure they run on.
- Inspect distributed traces to follow a single request across multiple services.
- Distinguish metrics, logs, and traces and choose the right one for a question.
- Interrogate telemetry with basic Kusto Query Language (KQL).

## Concepts

### The three telemetry signals

Observability rests on three kinds of signal, and confusing them wastes time. *Metrics* are numeric measurements aggregated over time — request rate, p95 latency, CPU — cheap to store and ideal for dashboards and alerts that answer "is something wrong and how much." *Logs* are discrete, timestamped events with structured properties — ideal for "what exactly happened to this request." *Traces* connect the events of a single operation across service boundaries — ideal for "where did the time go and which hop failed." A healthy platform emits all three, and you reach for the one that matches the question.

Application Insights, part of Azure Monitor, collects all three. Its data lands in a Log Analytics workspace, where every signal is queryable with the same language (KQL) in the same place — so you can pivot from a latency spike on a metric chart to the exact failing requests in the logs without changing tools.

### Distributed tracing and correlation

A modern request rarely lives in one process. The rate-quote call hits the API, which calls a pricing service, which queries a database. Distributed tracing stitches these into one *trace* by propagating a correlation identifier across each hop. Application Insights does this largely automatically through *auto-instrumentation* and the W3C Trace Context standard: each operation gets an operation ID, and child calls carry the parent's context so the backend can reassemble the tree.

The payoff is the *end-to-end transaction* view: one request shown as a waterfall of dependencies, each with its own duration and success flag. When the 02:14 errors hit, this view shows at a glance that the API itself is fast but its call to the pricing service is timing out — the failure is located in seconds, not after an hour of correlating logs by hand.

### KQL: querying telemetry

Kusto Query Language is how you interrogate everything Azure Monitor stores. A query starts from a table — `requests`, `dependencies`, `exceptions`, `traces` — and pipes it through operators with the `|` symbol: `where` to filter, `summarize` to aggregate, `project` to choose columns, `order by` to sort. The model is a pipeline, like Unix pipes for telemetry. Learning even a handful of operators lets you go from a vague symptom to a precise, time-bounded answer, and the same queries become the basis for dashboards and alert rules. KQL reads top-to-bottom: each line transforms the rows produced by the line above.

## Walkthrough: finding the 02:14 failure

Meridian's rate-quote API is an ASP.NET Core service. The team adds Application Insights, then uses KQL to diagnose the incident. Instrumentation is a few lines at startup — auto-collection then captures requests, dependencies, and exceptions without per-call code:

```csharp
// Program.cs
var builder = WebApplication.CreateBuilder(args);

// Connection string supplied via configuration / Key Vault (module 2),
// never hardcoded.
builder.Services.AddApplicationInsightsTelemetry();

var app = builder.Build();
app.MapControllers();
app.Run();
```

With telemetry flowing, the on-call engineer opens Logs and asks which dependency calls are failing in the incident window. KQL makes the question precise:

```kusto
// Failing dependency calls in the incident window, by target,
// with count and p95 duration
dependencies
| where timestamp between (datetime(2026-06-13 02:00) .. datetime(2026-06-13 02:30))
| where success == false
| summarize
    failures = count(),
    p95_ms = percentile(duration, 95)
  by target, type
| order by failures desc
```

The result names the culprit: the `pricing-api` HTTP dependency, hundreds of failures, p95 climbing. To confirm the trigger, the engineer correlates request failures against deploy time by binning over the hour:

```kusto
// Server-side failure rate per minute around the incident
requests
| where timestamp between (datetime(2026-06-13 01:50) .. datetime(2026-06-13 02:30))
| summarize total = count(), failed = countif(success == false) by bin(timestamp, 1m)
| extend failureRate = round(100.0 * failed / total, 1)
| order by timestamp asc
```

The failure rate is flat near zero until 02:11, then spikes — two minutes after a 02:09 deploy of the pricing service. From here the end-to-end transaction view for one failing request shows the exact timed-out call and its exception, and the fix (roll back the pricing deploy) is obvious and evidenced. The whole diagnosis took minutes because the request told its own story. Specific table and column names are stable, but always confirm the current schema in the docs if a query returns nothing.

## Common pitfalls

- **Logging everything at full volume.** Unsampled, verbose telemetry is expensive and slow to query, and it buries signal. Use adaptive sampling and log at appropriate levels; capture rich detail on errors, not on every healthy request.
- **Breaking trace correlation with hand-rolled HTTP calls.** Bypassing the instrumented client or stripping headers loses the trace-context propagation, so the dependency appears disconnected. Use the framework's instrumented clients so correlation headers flow automatically.
- **Putting secrets in telemetry.** Logging full request bodies or connection strings turns your observability store into a secret leak — exactly the surface module 2 worked to close. Scrub or exclude sensitive fields before they are recorded.
- **Confusing metrics with logs.** Trying to reconstruct a single request's path from aggregated metrics, or trending latency by scanning raw logs, is the wrong tool each way. Match the signal to the question: metrics for trends and alerts, logs for events, traces for paths.
- **No alerting on the metrics you collect.** Telemetry only watched on a dashboard nobody is looking at delivers no value at 02:14. Define alert rules on the key metrics so the platform tells you, rather than waiting to be asked.

## Knowledge check

1. The API's own server-side duration looks healthy, yet users report slow responses. Which telemetry signal and view locate the delay, and why?
2. You want an alert when the rate-quote service's failure rate exceeds a threshold over five minutes. Which signal underpins that alert, and why not use logs directly?
3. A custom HTTP client your team wrote makes downstream calls, but those calls never appear linked to their parent request in the transaction view. What most likely broke, and how do you fix it?

<details>
<summary>Answers</summary>

1. A distributed trace shown in the end-to-end transaction view — it breaks the request into per-dependency durations across services, revealing that a downstream call (not the API itself) is consuming the time. — Traces answer "where did the time go across hops," which a single service's metrics cannot.
2. Metrics — aggregated numeric measurements over time are cheap to evaluate continuously and are what alert rules are designed to threshold; querying raw logs for every evaluation is expensive and slower. — Use metrics for trends and alerting, logs for investigating specific events.
3. The custom client is not propagating W3C trace-context headers, so the downstream call has no parent correlation and appears disconnected; fix it by using the framework's instrumented HTTP client (or forwarding the trace-context headers) so correlation flows automatically. — Distributed tracing depends on context propagation across each hop.

</details>

## Summary

Observability stands on three signals — metrics for trends and alerts, logs for discrete events, traces for following a request across services — all collected by Application Insights into a Log Analytics workspace and queried with KQL. Distributed tracing and the end-to-end transaction view locate failures across service boundaries in seconds, and a few KQL operators turn a vague symptom into an evidenced root cause. Together with the previous three modules, you now have a platform that is declared as code, secured by identity, scanned by default, and observable by design — the full secure-DevOps lifecycle this course set out to teach.

## Further learning

- [Application Insights overview](https://learn.microsoft.com/en-us/azure/azure-monitor/app/app-insights-overview)
- [Application Insights distributed tracing and the transaction diagnostics experience](https://learn.microsoft.com/en-us/azure/azure-monitor/app/distributed-trace-data)
- [Kusto Query Language (KQL) overview](https://learn.microsoft.com/en-us/kusto/query/)
- [Log queries in Azure Monitor](https://learn.microsoft.com/en-us/azure/azure-monitor/logs/log-query-overview)
