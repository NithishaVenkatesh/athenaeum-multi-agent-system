---
kind: module
id: cb-c01-m04
vertical: cloud-backend
course_id: cb-c01
title: "Scaling, configuration, and diagnostics"
level: foundational
grounded_on: "AZ-204 skills outline (2026-01-14), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/az-204
synthetic: true
order: 4
prereqs: [cb-c01-m03]
objectives:
  - Implement autoscaling rules for variable load
  - Configure diagnostics and logging for running services
  - Choose the right compute service for a workload
---

# Scaling, configuration, and diagnostics

Northwind Parcel's services now run on App Service, Functions, and Container Apps — and on the morning of a holiday-shipping promotion, the orders API buckled under ten times its usual traffic while an idle reporting app sat fully provisioned, burning money. Two of the team's services were misconfigured in opposite directions: one could not grow, the other could not shrink. Worse, when latency spiked, nobody could say *why*, because the running services were nearly silent. This module is about closing both gaps: making compute follow demand, and making it observable enough to diagnose under pressure.

## Learning objectives

By the end of this module you will be able to:

- Implement autoscaling rules that grow and shrink compute in response to load.
- Configure diagnostics and logging so a running service emits the signals you need to debug it.
- Choose the appropriate compute service for a workload from its shape, lifecycle, and operational needs.

## Concepts

### Scaling up versus scaling out, and autoscale

There are two distinct ways to give a service more capacity. **Scaling up** (vertical) moves to a larger instance — more CPU and memory per instance. **Scaling out** (horizontal) adds more instances of the same size and spreads load across them. For stateless web APIs and most cloud services, scaling out is the workhorse because it adds capacity without a ceiling per box and improves availability. **Autoscale** is a rule engine that adds or removes instances automatically based on a signal — CPU percentage, a queue length, request count, or a schedule. A well-designed rule is *symmetric*: it scales out when a metric crosses a high threshold and scales back in when the metric falls, returning you to a cheap baseline. Different platforms expose this differently — App Service uses autoscale rules on its plan; Container Apps and Functions scale on triggers including HTTP and event-source depth, and can scale to zero.

### Diagnostics and structured logging

A service you cannot observe is a service you cannot operate. Azure compute platforms can stream **platform logs** (HTTP, container, and console output) and **application telemetry** to a destination. The recommended destination for application insight is **Application Insights**, which collects requests, dependencies, exceptions, and custom metrics, and correlates them so you can trace one slow request across its downstream calls. The key practice is to emit *structured* signals — log levels, request IDs, and meaningful events — rather than unlabeled print statements, so that you can later query them. (The DevOps & Platform vertical goes deep on querying these logs with KQL; here the goal is to make sure the data is being collected at all.)

### Choosing the right compute service

The through-line of this whole course is a decision, not a default. Ask: Is the work *request/response* and long-lived? App Service or Container Apps. Is it *event-triggered and intermittent*? Functions. Is it a *one-off or batch* task that runs and exits? Container Instances. Does it need *custom OS-level dependencies* or strict portability? Containers (ACR plus Container Apps or ACI). Does it need *gradual rollout and traffic-splitting* between versions? Container Apps revisions or App Service slots. There is rarely one correct answer, but matching the workload's *shape and lifecycle* to the service's strengths is what keeps cost, latency, and operational burden low.

## Walkthrough: surviving the holiday promotion

Northwind Parcel hardens the orders web app (on a Standard App Service plan) before the next promotion. First, autoscale so the plan grows on CPU pressure and shrinks afterward:

```bash
RG="northwind-parcel-rg"
PLAN="orders-plan"

# 1. Enable autoscale on the plan, with sane floor and ceiling
az monitor autoscale create \
  --resource-group "$RG" \
  --resource "$PLAN" \
  --resource-type Microsoft.Web/serverfarms \
  --name orders-autoscale \
  --min-count 2 --max-count 10 --count 2

# 2. Scale OUT by 2 instances when average CPU exceeds 70%
az monitor autoscale rule create \
  --resource-group "$RG" --autoscale-name orders-autoscale \
  --condition "CpuPercentage > 70 avg 5m" \
  --scale out 2

# 3. Scale IN by 1 instance when average CPU drops below 30%
az monitor autoscale rule create \
  --resource-group "$RG" --autoscale-name orders-autoscale \
  --condition "CpuPercentage < 30 avg 10m" \
  --scale in 1
```

The rules are deliberately asymmetric in *timing*: scale out fast (5-minute window) so users do not feel the spike, scale in slowly (10-minute window) so a brief dip does not cause thrashing. The floor of two instances preserves availability; the ceiling of ten caps the blast radius on cost. Next, wire diagnostics so the team can see what happens during the surge — connect the app to Application Insights and turn on platform logging:

```bash
APP="northwind-orders-api"

# Enable application logging (filesystem) and HTTP logs
az webapp log config \
  --name "$APP" --resource-group "$RG" \
  --application-logging filesystem \
  --web-server-logging filesystem \
  --level information

# Stream live logs while load-testing the promotion
az webapp log tail --name "$APP" --resource-group "$RG"
```

What to observe during a load test: as synthetic traffic drives CPU past 70%, autoscale adds instances within the scale-out window and request latency stabilizes; when the test ends and CPU falls, instances are removed gradually back toward the floor of two. Meanwhile `log tail` shows live HTTP and application logs, and Application Insights records the request rate, failures, and dependency timings so a post-incident review can pinpoint *which* downstream call slowed down — turning "the site was slow" into "the tariff dependency's p95 tripled at 09:14."

## Common pitfalls

- **Scale-out rule with no matching scale-in rule.** You grow under load and then stay large forever, paying peak cost indefinitely. Always pair an out rule with an in rule so capacity returns to baseline.
- **Symmetric, twitchy thresholds causing flapping.** Identical thresholds and windows for out and in make the service oscillate, adding and removing instances repeatedly. Use a gap between thresholds and a longer window for scale-in.
- **A minimum of one (or zero) instance for a critical service.** A single instance has no headroom and no redundancy. For availability-sensitive workloads, keep the floor at two or more so one unhealthy instance does not take you down.
- **Logging configured but never routed anywhere durable.** Filesystem logs are fine for a live tail but are not a lasting store. Send telemetry to Application Insights (or a Log Analytics workspace) so you still have the data after the incident.
- **Picking compute by habit instead of by workload.** Running a bursty event job on an always-on plan, or a latency-critical API on scale-to-zero, are both mismatches. Decide from the workload's shape and lifecycle every time.

## Knowledge check

1. After your first promotion, the bill stays high for days even though traffic returned to normal. What is the most likely autoscale misconfiguration?
2. Why is it good practice to use a shorter metric window for scale-out than for scale-in?
3. A teammate proposes running an intermittent, event-triggered image-processing job on an always-on Container App with a fixed two-replica minimum. What is the mismatch, and what fits better?

<details>
<summary>Answers</summary>

1. There is a scale-out rule but no scale-in rule (or its threshold is never met), so instances added during the spike are never removed. Add a symmetric scale-in rule. — Autoscale must shrink as well as grow, or you pay peak cost permanently.
2. Scaling out quickly protects users from a real load spike, while scaling in slowly avoids reacting to brief dips and prevents flapping. — Asymmetric timing biases toward availability while still reclaiming idle capacity.
3. An intermittent, event-triggered job pays for idle replicas with a fixed minimum; it suits an event-driven, scale-to-zero model such as Azure Functions (or a Container App scaling to zero on a queue trigger). — Match intermittent work to scale-to-zero compute, not always-on capacity.

</details>

## Summary

Resilient compute follows demand and tells you what it is doing. Scale out (add instances) for stateless services and pair every scale-out rule with a scale-in rule so you return to a cheap, available baseline; tune thresholds and windows to avoid flapping. Make every service observable by streaming platform logs and application telemetry to Application Insights, emitting structured signals you can later query. Above all, choose the compute service deliberately from the workload's shape and lifecycle — the single judgment that ties App Service, Functions, and the container services together. With this foundation, you are ready for the Cloud Data & Storage course, where these running services gain durable state.

## Further learning

- [Get started with autoscale in Azure](https://learn.microsoft.com/en-us/azure/azure-monitor/autoscale/autoscale-get-started)
- [Enable diagnostics logging for apps in Azure App Service](https://learn.microsoft.com/en-us/azure/app-service/troubleshoot-diagnostic-logs)
- [Application Insights overview](https://learn.microsoft.com/en-us/azure/azure-monitor/app/app-insights-overview)
- [Scaling in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/scale-app)
