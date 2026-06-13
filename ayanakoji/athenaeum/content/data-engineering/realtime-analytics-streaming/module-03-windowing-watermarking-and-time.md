---
kind: module
id: de-c03-m03
vertical: data-engineering
course_id: de-c03
title: Windowing, watermarking, and time
level: advanced
grounded_on: "DP-203 skills outline (2024-10-24), paraphrased — original synthetic content; current path Fabric DP-700"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/dp-203
synthetic: true
order: 3
prereqs: [de-c03-m02]
objectives:
  - Build windowed aggregates using tumbling, hopping, and session windows and choose the right one
  - Distinguish event time from processing time and configure watermarking to bound state and late data
  - Process time-series and late-arriving data correctly without unbounded memory growth
---

# Windowing, watermarking, and time

Tidewater Ferries now lands enriched readings into Delta, but the operations team wants a metric the per-event jobs cannot give them: the average speed of each ferry over rolling one-minute windows, to spot a vessel that is consistently running hot through the harbour. The first attempt seems easy — group by vessel and a one-minute window — until reality intrudes. A transponder on FERRY-07 buffers readings while it passes under a bridge and dead-spots, then dumps thirty seconds of data all at once, ninety seconds late. Do those readings belong to the window they *happened* in, or the window they *arrived* in? And if the job waits forever for stragglers, its memory grows without bound. This module is about answering those questions correctly. Getting time wrong is the most common way streaming aggregates silently lie.

## Learning objectives

By the end of this module you will be able to:

- Aggregate a stream over tumbling, hopping, and session windows, and pick the one that matches the question.
- Explain event time versus processing time and why aggregates must use event time.
- Configure a watermark to handle late data and bound the state the engine must keep.
- Reason about the trade-off between waiting for late data and emitting results promptly.

## Concepts

### Event time versus processing time

Every event has (at least) two clocks. **Event time** is when the thing actually happened — the timestamp the ferry's transponder stamped on the reading. **Processing time** is when your engine got around to handling it. In a perfect network these are nearly identical, but in reality they diverge: buffering, retries, network delays, and back-pressure all push processing time later than event time, sometimes by a lot.

For any time-based aggregate, event time is almost always the correct clock. If you bucket FERRY-07's delayed dump by processing time, thirty seconds of harbour-crossing data gets credited to the wrong minute, and your "average speed per minute" is wrong in exactly the windows you care about. Both Stream Analytics (`TIMESTAMP BY`) and Spark (`withWatermark` on an event-time column) let you tell the engine which column is event time. The cost of using event time is that the engine must hold a window open long enough to receive late events — which is precisely what watermarking governs.

### Windows: tumbling, hopping, and session

A window groups events into finite buckets so you can aggregate over a stream that never ends. Three shapes cover most needs:

- **Tumbling** windows are fixed-size and non-overlapping: one-minute buckets, back to back. Each event belongs to exactly one window. Use them for "the average per minute" — the Tidewater requirement.
- **Hopping** (sliding) windows are fixed-size but overlap by advancing a smaller hop: a five-minute window that emits every one minute. Each event can fall into several windows. Use them for smoothed rolling metrics, like a five-minute moving average updated each minute.
- **Session** windows have no fixed size; they group events separated by gaps shorter than a timeout and close after a period of inactivity. Use them for activity bursts — for example, grouping a vessel's continuous movement into "trips" separated by idle time at a dock.

Choosing the wrong window shape produces results that are technically correct but answer a different question than the one asked. Match the window to the metric's meaning.

### Watermarks: bounding lateness and state

A **watermark** is the engine's moving estimate of "event time has progressed at least this far; I will not wait indefinitely for events older than this." You configure it as a threshold of allowed lateness — say, two minutes. The engine tracks the maximum event time it has seen and subtracts the threshold; windows whose end is older than that watermark are considered complete, their results are finalized, and the state they held is dropped. Events that arrive *after* their window has passed the watermark are too late and are dropped (or routed aside, depending on the engine).

Watermarking solves two problems at once. It lets late-but-not-too-late events still land in their correct window, and — crucially — it lets the engine *forget* old windows so state does not grow forever. Without a watermark, an event-time aggregation must keep every window open indefinitely in case a straggler arrives, and a forever-running job will eventually exhaust memory. The threshold is a deliberate trade-off: a longer watermark tolerates later data but delays final results and holds more state; a shorter one emits sooner and uses less memory but discards more stragglers. Pick it from how late your real data actually arrives, and verify the engine's exact late-data behavior in the docs because the handling of very-late events differs between output modes.

## Walkthrough: per-minute average speed with late data

You will extend the Spark job from the previous module to compute each ferry's average speed over tumbling one-minute event-time windows, tolerating up to two minutes of lateness. The `withWatermark` call names the event-time column and the allowed lateness; the `window` function defines the tumbling bucket. Note that `event_time` arrives as a string from the JSON payload, so it is cast to a timestamp first.

```python
from pyspark.sql.functions import col, to_timestamp, window, avg, max as smax

# parsed = the streaming DataFrame from module 2 (vessel_id, knots, event_time, ...)
typed = parsed.withColumn("event_ts", to_timestamp(col("event_time")))

windowed = (
    typed
    .withWatermark("event_ts", "2 minutes")          # tolerate up to 2 min of lateness
    .groupBy(
        col("vessel_id"),
        window(col("event_ts"), "1 minute")          # tumbling 1-minute buckets
    )
    .agg(
        avg("knots").alias("avg_knots"),
        smax("knots").alias("peak_knots"),
    )
)

query = (
    windowed.writeStream
    .format("delta")
    .outputMode("append")                            # finalized windows only, after watermark passes
    .option("checkpointLocation", "/lakehouse/tidewater/_checkpoints/speed_by_minute")
    .toTable("tidewater.speed_by_minute")
)

query.awaitTermination()
```

With `outputMode("append")`, a window's row is written only once its end has fallen behind the watermark — i.e., once the engine is confident no more in-time events will arrive for it. So FERRY-07's ninety-seconds-late dump still lands in the correct minute as long as it arrives within the two-minute watermark; a reading that shows up three minutes late is dropped, and the window's average is finalized without it. To see the trade-off, widen the watermark to five minutes and observe that finalized rows appear later but tolerate later stragglers; narrow it to thirty seconds and rows appear quickly but more late readings are discarded.

## Common pitfalls

- **Aggregating by processing time instead of event time** — Bucketing by arrival time credits late data to the wrong window, so a per-minute average is wrong precisely when data is delayed. Always declare the event-time column and aggregate on it.
- **Event-time aggregation with no watermark** — Without a watermark the engine must keep every window open forever in case a straggler arrives, and state grows without bound until the job runs out of memory. A watermark is what lets old state be released.
- **A watermark too short for real lateness** — If your data routinely arrives a minute late but the watermark is thirty seconds, you silently drop a chunk of valid events and undercount. Set the threshold from observed lateness, not a guess.
- **Picking the wrong window shape** — Tumbling, hopping, and session windows answer different questions. Using a tumbling window for a smoothed rolling metric, or a hopping window for non-overlapping per-minute totals, yields a correct-looking but wrong answer.
- **Expecting `append` output mode to emit results immediately** — In append mode a windowed result is emitted only after the watermark passes the window's end, so there is an inherent delay. If you need running, updatable results sooner, use the update output mode and understand its semantics.

## Knowledge check

1. FERRY-07's transponder dumps ninety seconds of readings all at once, well after they were recorded. The team wants those readings counted in the minutes they actually occurred. Which clock must the windowed aggregate use, and what mechanism lets the late dump still land correctly?
2. A streaming aggregation has run for three days and is slowly running out of memory even though throughput is steady. The query groups by an event-time window but has no watermark. What is happening and what fixes it?
3. The team wants a five-minute moving average of speed, refreshed every minute. Which window shape fits, and how does it differ from the per-minute average?

<details>
<summary>Answers</summary>

1. The aggregate must use event time (the transponder's timestamp), not processing time. A watermark with an allowed-lateness threshold (e.g., two minutes) keeps each window's state alive long enough to receive late-but-not-too-late events, so the ninety-seconds-late dump still falls into its correct minute as long as it arrives within the threshold.
2. With an event-time window and no watermark, the engine cannot know when a window is "done," so it keeps every window's state indefinitely in case a late event arrives — state grows without bound and memory is exhausted. Adding a watermark lets the engine finalize and drop windows older than the threshold, bounding state.
3. A hopping (sliding) window of size five minutes with a one-minute hop. Unlike a tumbling one-minute window where each event belongs to exactly one bucket, the hopping window overlaps so each event contributes to several windows, producing a smoothed rolling average refreshed every minute.

</details>

## Summary

Time is the part of streaming that punishes carelessness. You now distinguish event time from processing time, know to aggregate on event time, and can choose tumbling, hopping, or session windows to match the question being asked. Watermarking is the linchpin: it lets late data land in the right window while bounding the state the engine must hold, trading promptness against tolerance for stragglers. The final module, *Monitoring, scaling, and optimization*, turns to keeping these long-running jobs healthy — spotting backlog and lag, scaling to clear it, and recovering from interruptions.

## Further learning

- [Window functions in Azure Stream Analytics](https://learn.microsoft.com/en-us/azure/stream-analytics/stream-analytics-window-functions)
- [Watermarks in Azure Stream Analytics event delivery](https://learn.microsoft.com/en-us/azure/stream-analytics/stream-analytics-time-handling)
- [Apply watermarks to control data processing thresholds (Structured Streaming)](https://learn.microsoft.com/en-us/azure/databricks/structured-streaming/watermarks)
- [Windowed aggregations on streaming data](https://learn.microsoft.com/en-us/azure/databricks/structured-streaming/aggregation)
