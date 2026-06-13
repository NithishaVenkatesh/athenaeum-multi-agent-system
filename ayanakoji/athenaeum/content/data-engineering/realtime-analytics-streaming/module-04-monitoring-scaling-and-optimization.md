---
kind: module
id: de-c03-m04
vertical: data-engineering
course_id: de-c03
title: Monitoring, scaling, and optimization
level: advanced
grounded_on: "DP-203 skills outline (2024-10-24), paraphrased — original synthetic content; current path Fabric DP-700"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/dp-203
synthetic: true
order: 4
prereqs: [de-c03-m03]
objectives:
  - Monitor a streaming pipeline's health using the right signals — backlog, lag, throughput, and utilization
  - Scale ingestion and processing resources to clear a backlog without breaking correctness
  - Diagnose interruptions and tune long-running jobs for throughput and cost
---

# Monitoring, scaling, and optimization

The Tidewater Ferries streaming pipeline works in the demo and falls over in production at exactly the wrong moment. During the summer festival, all 40 ferries run at peak frequency, the transponders emit more often, and the live board goes stale — alerts that should appear in seconds now lag by minutes. Nobody changed the code. The pipeline simply met more load than it was provisioned for, and there was no dashboard to see it coming. A streaming job is not a thing you deploy and forget; it is a long-running service with a backlog that can grow, resources that can saturate, and failures that must be recovered without losing data. This module is about operating one: knowing which signals mean trouble, scaling the right knob, and tuning so the system stays both fast and affordable.

## Learning objectives

By the end of this module you will be able to:

- Identify the health signals that matter for streaming — input backlog, watermark/processing lag, throughput, and resource utilization.
- Decide what to scale — ingestion partitions/throughput versus processing parallelism — when a backlog grows.
- Recover from interruptions cleanly using checkpoints and replayable sources.
- Tune a job for throughput and cost, and recognize when a pipeline is mis-sized in either direction.

## Concepts

### The signals that actually tell you the pipeline is healthy

A streaming pipeline's health is not "is it running" — a job can be running and falling further behind every second. The signals that matter are about whether processing is keeping up with arrival. The most direct is **backlog**: how much unprocessed data is sitting in the source. For Event Hubs this surfaces as the gap between the latest offset and your consumer's committed offset; for Stream Analytics, the input-events-backlogged metric. A backlog that is flat or near zero means you are keeping up; a backlog that climbs steadily means arrival rate exceeds processing rate and the system is degrading even if nothing has errored.

Two related signals refine the picture. **Lag** — how far behind real time your output is, often visible as the gap between event time and processing time, or in Spark as the watermark falling behind wall-clock — tells you how stale results are. **Resource utilization** — the streaming-unit utilization percentage in Stream Analytics, or executor CPU/memory in Spark — tells you whether you are near a ceiling. The diagnostic move is to read these together: rising backlog plus high utilization means you need more resources; rising backlog with *low* utilization usually means a parallelism or skew problem, not a capacity problem.

### Scaling the right thing

When a backlog grows, the instinct is "add resources," but you have to add the *right* resources, and scaling one stage without the others just moves the bottleneck. There are two independent dimensions. **Ingestion** capacity is governed by the source — Event Hubs partition count caps read parallelism, and provisioned throughput caps ingress/egress rate. **Processing** capacity is the engine — streaming units in Stream Analytics, or executor count and cores in Spark.

The rule that ties the lessons together: processing parallelism cannot exceed source parallelism. If your event hub has 8 partitions, no more than 8 readers can pull from it concurrently per consumer group, so throwing 32 Spark cores at it will not help past that ceiling — the extra cores sit idle while 8 do the work. Conversely, adding partitions does nothing if your processing tier is already starved of compute. Scale them in proportion, and remember the partitioning lesson from module 1: the job only parallelizes cleanly if keys line up end to end. Skew — one hot partition (one extremely chatty ferry) — defeats scaling because one reader is overwhelmed while the rest idle; the fix is a better key, not more cores.

### Interruptions, recovery, and tuning

Long-running jobs *will* be interrupted — node failures, deployments, transient source outages. Recovery rests on the two properties built in earlier modules: a **replayable source** (Event Hubs retains events, so a restarted consumer resumes from its offset) and a **durable checkpoint** (Spark resumes processing and window state exactly where it left off). The operational discipline is to ensure those are intact: retention long enough to cover your worst restart window, and checkpoints that are never shared or deleted. If a job is down longer than retention, it loses data — so retention is a recovery-time budget, not a storage afterthought.

Tuning is the steady-state work: matching resources to load so you are neither dropping behind nor paying for idle capacity. Over-provisioning is a real cost in streaming because the job runs continuously, twenty-four hours a day. Right-sizing means watching utilization at peak and trough and adjusting — and treating any specific autoscale behavior or per-unit limit as something to confirm in the current docs, since these change across tiers and product generations.

## Walkthrough: diagnosing the festival slowdown

During the festival the live board lagged. You will query the health signals to find the cause, then scale. First, read the Stream Analytics job metrics with the Azure CLI to see backlog and SU utilization together — the pair that distinguishes a capacity problem from a parallelism problem.

```bash
# Read streaming-unit utilization and input backlog over the festival window.
RESOURCE_ID=$(az stream-analytics job show \
  --resource-group tidewater-rt \
  --name tidewater-speedwatch \
  --query id -o tsv)

az monitor metrics list \
  --resource "$RESOURCE_ID" \
  --metric "SUStreamingUnits1MinPercentUtilization" "InputEventsBackloggedTotal" \
  --interval PT1M \
  --start-time 2026-06-13T18:00:00Z \
  --end-time 2026-06-13T22:00:00Z \
  --output table
```

The output shows SU utilization pinned near 100% while the backlog climbs steadily — a clear capacity-bound signal, not skew. The fix is more processing parallelism, but only if the job is parallelizable and the source can feed it. Because the input is partitioned by vessel and the query is partition-aligned (from module 1), raising streaming units helps. Scale the job up, then re-check that the backlog drains.

```bash
# Increase processing capacity, then confirm the backlog clears.
az stream-analytics job update \
  --resource-group tidewater-rt \
  --name tidewater-speedwatch \
  --streaming-units 12

# After a few minutes, backlog should trend back toward zero.
az monitor metrics list \
  --resource "$RESOURCE_ID" \
  --metric "InputEventsBackloggedTotal" \
  --interval PT1M \
  --output table
```

If the backlog had been climbing while utilization stayed *low*, scaling SUs would have been wrong — that pattern points to a partition ceiling or a hot key, where the right move is more partitions or a better partition key, not more compute. Reading the two signals together is what tells you which lever to pull.

## Common pitfalls

- **Treating "the job is running" as healthy** — A job can run while its backlog grows every minute and results go stale. Watch backlog and lag, not just the up/down status, or you will discover the degradation only when users complain.
- **Adding compute when the source is the bottleneck** — Processing parallelism cannot exceed source parallelism. More Spark cores or SUs do nothing past the partition ceiling; check whether ingestion, not processing, is the limit before scaling compute.
- **Ignoring partition skew** — One hot key (a single chatty producer) overwhelms one reader while others idle, so the job will not scale no matter how many resources you add. Fix the key distribution; capacity is not the problem.
- **Retention shorter than your worst restart window** — If a job is down longer than the source's retention, the unread events expire and are lost permanently. Size retention as a recovery-time budget that covers deployments and outages.
- **Leaving a job over-provisioned around the clock** — A streaming job runs continuously, so idle headroom is paid for every hour. Right-size to peak-and-trough load and revisit it, rather than provisioning once for the worst case and forgetting.

## Knowledge check

1. A Stream Analytics job shows backlog climbing steadily while SU utilization sits at about 35%. Is adding streaming units the right fix? What is the likely cause?
2. A Spark streaming job recovers cleanly from a five-minute node failure but loses data after a four-hour outage. The checkpoint was intact the whole time. What setting most likely caused the loss?
3. The live board lags during peak hours but the team does not want to pay for that capacity overnight when traffic is light. What two health signals should drive the sizing decision, and what is the risk of just provisioning for peak permanently?

<details>
<summary>Answers</summary>

1. No. Low utilization with rising backlog points to a parallelism problem — likely a source partition ceiling or a hot/skewed partition — not a capacity shortage. Adding SUs will not help if readers are limited by partition count or one key dominates; investigate partitioning and key distribution first.
2. Source retention. The checkpoint lets the job resume from its last offset, but if the outage exceeds Event Hubs retention, the unread events expire before the job comes back and are lost. Retention must cover the worst expected restart window.
3. Resource utilization and backlog/lag, read together at peak and trough. Provisioning permanently for peak means paying for idle capacity every off-peak hour, since the job runs continuously — the cost of over-provisioning a 24/7 service is significant, so size to actual load and adjust.

</details>

## Summary

A streaming pipeline is a service you operate, not a script you run once. You now know to judge health by backlog, lag, and utilization read together — and that the combination tells you whether to scale capacity, add partitions, or fix a skewed key. Recovery rests on the replayable source and durable checkpoint from earlier modules, with retention sized as a recovery budget. With these four modules you can stand up an end-to-end streaming path, process unbounded data into a lakehouse, aggregate correctly over event time, and keep the whole thing healthy and cost-effective under real load.

## Further learning

- [Monitor Stream Analytics jobs with metrics](https://learn.microsoft.com/en-us/azure/stream-analytics/stream-analytics-monitoring)
- [Understand and adjust streaming units in Stream Analytics](https://learn.microsoft.com/en-us/azure/stream-analytics/stream-analytics-streaming-unit-consumption)
- [Scale an Azure Stream Analytics job to increase throughput](https://learn.microsoft.com/en-us/azure/stream-analytics/stream-analytics-scale-jobs)
- [Production considerations for Structured Streaming](https://learn.microsoft.com/en-us/azure/databricks/structured-streaming/production)
