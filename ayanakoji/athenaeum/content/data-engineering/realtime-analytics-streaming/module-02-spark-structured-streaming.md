---
kind: module
id: de-c03-m02
vertical: data-engineering
course_id: de-c03
title: Spark structured streaming
level: advanced
grounded_on: "DP-203 skills outline (2024-10-24), paraphrased — original synthetic content; current path Fabric DP-700"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/dp-203
synthetic: true
order: 2
prereqs: [de-c03-m01]
objectives:
  - Process unbounded data with Spark Structured Streaming using the readStream/writeStream model
  - Handle schema drift in an incoming stream without crashing the running job
  - Write streaming output to a Delta table with exactly-once semantics via checkpointing
---

# Spark structured streaming

The Tidewater Ferries pipeline from the previous module flags speeding in real time, but the operations team now wants something the SQL job is awkward at: every reading, enriched and cleaned, landing continuously into the same Delta lakehouse the batch analysts already use, so the next morning's reports and the live board read from one source of truth. They also keep changing the transponder firmware — last month a new field `engine_temp_c` started appearing in some payloads, and the ingestion job that did not expect it threw a parse error and stopped, dropping readings until someone noticed. You need code-first stream processing: a job that reads the unbounded stream, transforms it in Python, absorbs new fields without dying, and writes to Delta exactly once. Spark Structured Streaming is that tool.

## Learning objectives

By the end of this module you will be able to:

- Define a streaming source and sink with `readStream` and `writeStream`, and explain the micro-batch execution model.
- Apply transformations to a streaming DataFrame the same way you would to a batch one.
- Detect and absorb schema drift so new fields do not crash the job.
- Write to a Delta table with a checkpoint location that gives you exactly-once output and clean restarts.

## Concepts

### The unbounded table and micro-batch execution

Structured Streaming's central idea is that a stream is an *unbounded table* that grows forever, and the query you write against it is the same query you would write against a static table. You declare it once; the engine runs it repeatedly as new data arrives, and each run appends to a conceptually infinite result table. You almost never reason about individual events — you reason about a DataFrame, and the engine handles the incremental mechanics.

Under the hood the default execution is **micro-batch**: the engine periodically checks the source for new data, processes whatever has arrived as a small batch, commits it, and waits for the next trigger. This is why a structured streaming job feels like batch code that runs on a loop — because that is essentially what it is. The trigger interval controls latency versus efficiency: a short interval gives lower latency but more, smaller batches; the default fires a new batch as soon as the previous one finishes. The key mental model is that *the same transformation logic works on batch and stream*, which is what lets you share code between your nightly job and your live job.

### Checkpointing, offsets, and exactly-once

A streaming job that runs forever must survive restarts without losing or double-counting data. Spark achieves this with a **checkpoint location** — a directory where the engine durably records which source offsets it has processed and the state of any aggregations. On restart, the job reads the checkpoint, sees exactly where it left off, and resumes. This is what lets Spark offer **exactly-once** output to a Delta sink even though the source delivers at-least-once: the combination of checkpointed offsets and Delta's transactional commit means a re-attempted micro-batch writes the same data under the same transaction and does not duplicate it.

The non-negotiable rule is that every streaming query needs its own dedicated, stable checkpoint location, and you must not delete it or point two different queries at the same one. The checkpoint *is* the job's memory. Lose it and the job either reprocesses everything from the start of retention or, worse, cannot reconcile its state. Treat the checkpoint directory as a first-class part of the pipeline, not a temp folder.

### Schema drift: planning for fields you have not seen yet

Schema drift is when the shape of incoming data changes over time — a producer adds a field, renames one, or changes a type. A job with a rigid hard-coded schema treats an unexpected field as an error and may stop. The robust approach depends on the source. When reading files with the cloud-file source, the engine can infer and *evolve* a schema, storing the tracked schema in a location you specify and adding new columns as they appear (with a mode that controls whether the stream restarts to pick them up). When reading JSON payloads from Event Hubs, a common pattern is to land the raw body and parse defensively — selecting known fields explicitly while keeping the unparsed remainder — so a new field is captured rather than fatal. Either way, the principle is the same: decide in advance what happens when a new column shows up, instead of letting an exception decide for you.

## Walkthrough: enriched ferry readings into Delta

You will read the `vessel-readings` event hub as a structured stream, parse the JSON body, tolerate the new `engine_temp_c` field, and write the result to a Delta table with a checkpoint. The example uses the Spark JSON-parsing pattern: read the binary body, cast to string, and parse against a schema that includes the *known* fields, while `mode("PERMISSIVE")` keeps malformed or partial records instead of dropping the batch.

```python
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, from_json, current_timestamp
from pyspark.sql.types import StructType, StructField, StringType, DoubleType, BooleanType

spark = SparkSession.builder.getOrCreate()

# Known fields. engine_temp_c is declared so the new field is captured, not fatal.
reading_schema = StructType([
    StructField("vessel_id", StringType()),
    StructField("knots", DoubleType()),
    StructField("in_no_wake_zone", BooleanType()),
    StructField("event_time", StringType()),
    StructField("engine_temp_c", DoubleType()),   # added by new firmware; null for old payloads
])

raw = (
    spark.readStream
    .format("eventhubs")
    .options(**eventhubs_conf)            # connection config provided by the platform
    .load()
)

parsed = (
    raw.select(from_json(col("body").cast("string"), reading_schema).alias("r"))
       .select("r.*")
       .withColumn("ingested_at", current_timestamp())
)

# Exactly-once write to Delta. The checkpoint is dedicated and stable.
query = (
    parsed.writeStream
    .format("delta")
    .outputMode("append")
    .option("checkpointLocation", "/lakehouse/tidewater/_checkpoints/vessel_readings")
    .option("mergeSchema", "true")        # absorb new columns into the Delta table
    .toTable("tidewater.vessel_readings")
)

query.awaitTermination()
```

Two things make this drift-tolerant. First, `engine_temp_c` is declared in the schema, so payloads that include it are parsed and old payloads simply get `null`. Second, `mergeSchema=true` lets the Delta sink add a genuinely new column to the table rather than rejecting the write. When the firmware adds yet another field, you add it to `reading_schema`, redeploy, and the job continues from its checkpoint without losing data. To confirm exactly-once behavior, stop the job mid-stream and restart it: the checkpoint resumes from the last committed offset, and the Delta table shows no duplicate rows for the events that were in flight.

## Common pitfalls

- **Sharing or deleting the checkpoint location** — The checkpoint is the query's durable memory of processed offsets and state. Two queries sharing one, or a deleted checkpoint, causes reprocessing or unrecoverable state. Give every query its own stable directory and never treat it as disposable.
- **A rigid schema that crashes on new fields** — Parsing strictly against a fixed schema turns a harmless new field into a fatal error that halts ingestion. Declare known fields, parse permissively, and enable schema merge on the sink so drift is absorbed.
- **Forgetting `mergeSchema` on the Delta write** — Even if you parse a new column, the Delta sink rejects it by default. Enable `mergeSchema` (or evolve the table deliberately) so the new column lands instead of failing the batch.
- **Expecting sub-second latency from default micro-batch** — Micro-batch processing has inherent per-batch overhead; the default trigger is not the same as event-by-event streaming. If you need lower latency, tune the trigger and resources, and verify the engine's continuous or low-latency options in the docs rather than assuming.
- **Treating exactly-once as automatic for any sink** — Exactly-once relies on checkpointed offsets *plus* a transactional sink like Delta. Writing to a non-transactional sink does not get the same guarantee; know what your sink supports.

## Knowledge check

1. A job runs fine for a week, then the team deletes its checkpoint directory during a "cleanup." On the next start the job either reprocesses a huge backlog or fails. Why, and what is the rule?
2. The transponder firmware adds a field `heading_deg`. The current job parses against a fixed schema and writes to Delta without `mergeSchema`. Which two changes keep the job alive and capture the new field?
3. How does Spark deliver exactly-once output to Delta when the Event Hubs source only guarantees at-least-once?

<details>
<summary>Answers</summary>

1. The checkpoint stores the source offsets and state the job has committed; it is the job's memory of where it left off. Deleting it removes that memory, so on restart the job has no record of progress and must start over (or cannot reconcile state). The rule: each query gets its own stable checkpoint location that you never share or delete.
2. Add `heading_deg` to the parsing schema so the field is captured (old payloads get null), and enable `mergeSchema` on the Delta write so the sink adds the new column instead of rejecting the batch. Permissive parsing prevents a malformed payload from killing the batch.
3. Spark records processed source offsets in the checkpoint and writes each micro-batch to Delta inside a transaction. If a batch is retried after a failure, it commits the same data under the same transactional boundary, so duplicates from the at-least-once source are reconciled and the table reflects each event once.

</details>

## Summary

You can now process an unbounded stream as ordinary DataFrame code: `readStream` defines the source, transformations look just like batch, and `writeStream` to Delta with a dedicated checkpoint gives you exactly-once output and clean restarts. You also know how to keep the job alive through schema drift by parsing known fields permissively and merging new columns into the sink. The next module, *Windowing, watermarking, and time*, tackles the hardest part of streaming — aggregating correctly over time when events arrive late or out of order.

## Further learning

- [Structured Streaming Programming Guide (Apache Spark)](https://learn.microsoft.com/en-us/azure/databricks/structured-streaming/)
- [Configure schema inference and evolution in Auto Loader](https://learn.microsoft.com/en-us/azure/databricks/ingestion/cloud-object-storage/auto-loader/schema)
- [Use Delta Lake change data feed and streaming reads/writes](https://learn.microsoft.com/en-us/azure/databricks/structured-streaming/delta-lake)
- [Streaming with Apache Spark in Microsoft Fabric](https://learn.microsoft.com/en-us/fabric/data-engineering/spark-structured-streaming)
