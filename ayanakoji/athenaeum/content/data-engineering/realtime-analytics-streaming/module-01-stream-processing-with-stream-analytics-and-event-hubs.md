---
kind: module
id: de-c03-m01
vertical: data-engineering
course_id: de-c03
title: Stream processing with Stream Analytics and Event Hubs
level: advanced
grounded_on: "DP-203 skills outline (2024-10-24), paraphrased — original synthetic content; current path Fabric DP-700"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/dp-203
synthetic: true
order: 1
prereqs: [de-c01, de-c02]
objectives:
  - Create an end-to-end stream processing solution with Event Hubs as the source and Stream Analytics as the engine
  - Reason about ingestion throughput, partition count, and how partition key choice affects ordering and scale
  - Deliver query results to a sink reliably, accounting for at-least-once delivery and duplicates
---

# Stream processing with Stream Analytics and Event Hubs

Tidewater Ferries, a fictional regional ferry operator, has bolted a GPS transponder onto each of its 40 vessels. Every transponder emits a position-and-speed reading every two seconds. The operations team wants a live board that flags any ferry exceeding the harbour speed limit within the no-wake zone — and they want the flag to appear within a few seconds, not in tomorrow's report. The current "solution" dumps readings into blob storage and runs a nightly batch job, which is useless for stopping a ferry that is speeding right now. You cannot solve this by making the batch job faster. You need a path that processes each reading as it arrives, holds just enough state to compare a position against the zone, and emits an alert the moment a threshold is crossed. This module builds that path.

## Learning objectives

By the end of this module you will be able to:

- Wire Event Hubs as an ingestion buffer in front of a Stream Analytics job.
- Predict how many throughput units and partitions a workload needs, and how partition key choice affects ordering.
- Write a Stream Analytics query that filters and projects a live stream into a sink.
- Explain at-least-once delivery and design a sink that tolerates duplicates.

## Concepts

### Event Hubs as a partitioned, replayable buffer

Event Hubs is not a queue in the "one consumer pops one message" sense. It is an append-only log, conceptually closer to a commit log than a mailbox. Producers append events; the hub assigns each event an offset within a **partition** and retains it for a configured time, regardless of whether anyone has read it. Consumers track their own position by offset and can replay from any point still in retention. This is the property that makes streaming robust: if your processor crashes, it resumes from the last committed offset rather than losing the events that arrived while it was down.

Partitions are the unit of parallelism and the unit of ordering. Events are ordered *within* a partition but not *across* partitions. Which partition an event lands in is decided by its partition key: events with the same key always go to the same partition, so they stay in order relative to each other. For Tidewater, using the vessel id as the partition key means every reading from one ferry arrives in order, which is exactly what you need to detect "this ferry just crossed into the zone." If you instead let events round-robin across partitions, two readings from the same ferry could be processed out of order, and your zone-entry logic would misfire.

The number of partitions is fixed at creation for a given hub and caps your read parallelism — you cannot have more concurrent readers per consumer group than partitions. Choose it for the throughput and parallelism you expect to need, because changing it later is disruptive. Throughput itself is provisioned separately (historically as throughput units; newer tiers use processing units or a capacity model). Treat the specific ingress and egress limits per unit as something to verify in the current pricing and quota docs rather than memorize, because they change between tiers.

### Stream Analytics: SQL over a moving table

Azure Stream Analytics lets you treat a stream as if it were a table you query with SQL. A job has one or more **inputs** (here, the event hub), a **query**, and one or more **outputs** (the sink). The mental shift from batch SQL is that the query runs *continuously* over data that never stops arriving, so a plain `SELECT ... WHERE` emits a result row for every matching event as it flows through, rather than once over a finished table.

A job's parallelism is expressed in **streaming units (SUs)**, the compute-and-memory allocation the job runs on. To use SUs effectively the job must be *parallelizable*: the input partition key, the partitioning of your query, and the output should line up so each partition's data can be processed independently. When they line up, the job is "embarrassingly parallel" and scales by adding SUs; when they don't — for example, an aggregation that has to see all partitions at once — the job has to shuffle and cannot scale as cleanly. This is the streaming echo of the partitioning lessons from the lakehouse course: align your keys end to end and the system parallelizes for free.

### Delivery guarantees and the duplicate problem

Distributed streaming systems generally promise **at-least-once** delivery, not exactly-once, on the wire. If a processor emits a result to a sink and then crashes before recording that it succeeded, on restart it will reprocess the same input and emit the result again. The consequence for you is concrete: your sink will occasionally see duplicate rows, and your design must not break when it does. The usual defenses are an idempotent sink (writing by a natural key so a re-write is a no-op) or downstream deduplication on an event id. Assume duplicates will happen and you will not be surprised at 3 a.m.

## Walkthrough: the Tidewater speed-watch board

You will create an event hub, send it a few synthetic ferry readings from Python, and write the Stream Analytics query that flags speeding in the no-wake zone. First, provision the hub with the Azure CLI. The vessel count is small, so a modest partition count is fine; partitioning by vessel preserves per-ferry order.

```bash
# Resource group + Event Hubs namespace + hub, partitioned for per-vessel ordering.
az group create --name tidewater-rt --location eastus

az eventhubs namespace create \
  --resource-group tidewater-rt \
  --name tidewater-ns-demo \
  --sku Standard

az eventhubs eventhub create \
  --resource-group tidewater-rt \
  --namespace-name tidewater-ns-demo \
  --name vessel-readings \
  --partition-count 8 \
  --message-retention 1
```

Now send readings. Each event carries the vessel id, a timestamp, speed in knots, and whether the vessel is currently inside the no-wake zone (in a real system that flag would come from a geofence; here it is part of the synthetic payload). Passing `partition_key=vessel_id` keeps one ferry's readings in order.

```python
import asyncio
import json
from datetime import datetime, timezone
from azure.eventhub.aio import EventHubProducerClient
from azure.eventhub import EventData
from azure.identity.aio import DefaultAzureCredential

NAMESPACE = "tidewater-ns-demo.servicebus.windows.net"
HUB = "vessel-readings"

async def send_readings() -> None:
    credential = DefaultAzureCredential()
    producer = EventHubProducerClient(
        fully_qualified_namespace=NAMESPACE,
        eventhub_name=HUB,
        credential=credential,
    )
    readings = [
        {"vessel_id": "FERRY-07", "knots": 11.4, "in_no_wake_zone": True},
        {"vessel_id": "FERRY-07", "knots": 12.9, "in_no_wake_zone": True},
        {"vessel_id": "FERRY-02", "knots": 4.1, "in_no_wake_zone": True},
    ]
    async with producer, credential:
        # One batch per vessel so partition_key keeps each ferry ordered.
        for r in readings:
            r["event_time"] = datetime.now(timezone.utc).isoformat()
            batch = await producer.create_batch(partition_key=r["vessel_id"])
            batch.add(EventData(json.dumps(r)))
            await producer.send_batch(batch)
    print("sent", len(readings), "readings")

asyncio.run(send_readings())
```

With events flowing, the Stream Analytics job reads the hub as input `vessel_input` and emits an alert row only when a vessel exceeds 8 knots inside the zone. The harbour limit is a named threshold, not a magic number buried in the predicate.

```sql
-- Stream Analytics query: emit one alert per offending reading.
WITH NoWakeViolations AS (
    SELECT
        vessel_id,
        knots,
        event_time
    FROM vessel_input TIMESTAMP BY event_time
    WHERE in_no_wake_zone = 1 AND knots > 8.0   -- 8 knots = no-wake limit
)
SELECT
    vessel_id,
    knots,
    event_time,
    System.Timestamp() AS detected_at
INTO alert_output
FROM NoWakeViolations
```

The `TIMESTAMP BY event_time` clause tells the engine to use the reading's own timestamp as event time rather than arrival time — a distinction the windowing module makes central. Each FERRY-07 reading above (11.4 and 12.9 knots) produces an alert row; FERRY-02 at 4.1 knots produces none. Wire `alert_output` to a sink such as a SQL table or a Power BI dataset for the live board.

## Common pitfalls

- **Round-robin partitioning when order matters** — If you do not set a partition key, events spread across partitions and per-entity ordering is lost. For per-vessel logic, key by vessel id so each ferry's readings stay in sequence.
- **Provisioning too few partitions and trying to fix it later** — Partition count is effectively fixed at hub creation and caps read parallelism. Size it for your expected fan-out up front rather than discovering the ceiling under load.
- **A query that cannot parallelize across partitions** — A global aggregation forces the job to shuffle all partitions together, so adding streaming units stops helping. Partition the query consistently with the input where you can, and verify the job shows as parallel.
- **Assuming exactly-once into the sink** — At-least-once delivery means duplicates after a restart. Make the sink idempotent (write by natural key) or dedupe downstream; do not assume each result lands exactly once.
- **Confusing arrival time with event time** — Without `TIMESTAMP BY`, the engine uses arrival time, so a delayed batch looks "current." Set the event-time column explicitly when the event's own timestamp is what your logic depends on.

## Knowledge check

1. Tidewater needs every reading from a single ferry processed strictly in order, but readings from different ferries can interleave freely. What partition key should the producer use, and why?
2. A teammate proposes raising the partition count from 8 to 32 on the live hub to "go faster," then notices ordering bugs appear afterward. What two things are wrong with this plan?
3. The alert sink occasionally shows the same violation twice. Is this a bug in the query, and what is the right fix?

<details>
<summary>Answers</summary>

1. Use the vessel id as the partition key. Events with the same key land in the same partition, and ordering is guaranteed within a partition, so each ferry stays ordered while different ferries (different keys) can spread across partitions and process in parallel.
2. First, partition count is fixed at creation and cannot simply be raised on a running hub without disruption. Second, "more partitions = faster" ignores ordering: increasing partitions only helps if the query parallelizes, and reshuffling keys across more partitions can break per-vessel order that the logic depends on. Throughput is provisioned separately from partition count.
3. Not a query bug. At-least-once delivery means a restart can reprocess events and re-emit results. The fix is an idempotent sink (write keyed by vessel id + event time so a duplicate write is a no-op) or downstream deduplication, not changing the query.

</details>

## Summary

You now have the core streaming loop: Event Hubs buffers and replays a partitioned, ordered log; Stream Analytics runs continuous SQL over it and emits results to a sink; and partition keys decide both ordering and how far the job can scale. You also know that delivery is at-least-once, so sinks must tolerate duplicates. The next module, *Spark structured streaming*, swaps the SQL engine for code-first processing into a Delta lakehouse, where you control the transformation in Python and write exactly-once to a table.

## Further learning

- [Azure Event Hubs — features and terminology](https://learn.microsoft.com/en-us/azure/event-hubs/event-hubs-features)
- [Welcome to Azure Stream Analytics](https://learn.microsoft.com/en-us/azure/stream-analytics/stream-analytics-introduction)
- [Understand and adjust streaming units in Stream Analytics](https://learn.microsoft.com/en-us/azure/stream-analytics/stream-analytics-streaming-unit-consumption)
- [Leverage query parallelization in Stream Analytics](https://learn.microsoft.com/en-us/azure/stream-analytics/stream-analytics-parallelization)
