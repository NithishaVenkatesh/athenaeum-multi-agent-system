---
kind: module
id: de-c01-m01
vertical: data-engineering
course_id: de-c01
title: Partition strategies for analytical data
level: foundational
grounded_on: "DP-203 skills outline (2024-10-24), paraphrased — original synthetic content; current path Fabric DP-700"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/dp-203
synthetic: true
order: 1
prereqs: []
objectives:
  - Design a partition strategy for files and analytical workloads
  - Recognize when partitioning helps and when it hurts in Data Lake Storage Gen2
  - Avoid common small-file and data-skew problems
---

# Partition strategies for analytical data

Northwind Telemetry runs a fleet of soil sensors for farms across three regions. Every night a job lands a year of readings — about 2 billion rows — as Parquet in their lake, all in one folder. The first analyst query, "average moisture for the Riverbend region last week," takes eleven minutes and scans the entire dataset. Nobody changed the data; they changed nothing at all. The problem is purely physical: the engine has no way to skip the 99% of files that cannot possibly contain Riverbend's last week. Partitioning is how you fix that, and it is the single highest-leverage storage decision you will make.

## Learning objectives

By the end of this module you will be able to:

- Design a partition strategy for files and analytical tables driven by real query predicates.
- Explain how partition pruning lets a query engine skip irrelevant data.
- Recognize the small-file problem and the over-partitioning that causes it.
- Detect and mitigate data skew across partitions.

## Concepts

### What partitioning actually does

Partitioning splits a dataset into separate physical groups of files based on the values of one or more columns, and encodes those values into the directory path. A table partitioned by `region` and `event_date` produces a tree like `.../region=riverbend/event_date=2026-06-07/part-0001.parquet`. The column values live in the *path*, not inside the files.

This layout enables **partition pruning**. When a query includes `WHERE region = 'riverbend' AND event_date = '2026-06-07'`, the engine reads the directory names, discards every path whose values cannot match, and opens only the surviving files. Northwind's eleven-minute scan becomes a sub-second read of a handful of files. Crucially, pruning happens *before* any file is opened — it is a cheap metadata operation on paths, which is why it scales so well.

The implication is the rule that governs everything else: **partition on the columns your queries filter on, not on the columns that seem natural.** A partition column that never appears in a `WHERE` clause buys you nothing and costs you on every write. Look at the predicates analysts actually use. For Northwind, almost every query filters by date and often by region, so `event_date` (and possibly `region`) are the candidates.

### Granularity, and the small-file trap

Once you pick partition columns, you pick granularity. Date is the classic case: partition by day, by month, or by year? The instinct is "finer is better, the engine skips more." That instinct is wrong, and the reason is the **small-file problem**.

Analytical engines and object storage are built for large, columnar files. Each file carries overhead — metadata to parse, a network round trip to open, a task to schedule. The widely cited sweet spot for a single Parquet file is roughly **128 MB to 1 GB**; treat that as a rule of thumb and verify current guidance for your engine. Partition 50 GB by `region`, `device_id`, and `hour` and you can shatter it into hundreds of thousands of 10 KB files. Now every query spends its time on file-open overhead and scheduling, not reading data — and listing that many paths becomes its own bottleneck. Over-partitioning is the most common way teams make queries *slower* while believing they are tuning them.

A simple discipline: estimate `total_size / number_of_partitions`. If the average partition is well under ~100 MB, your partitioning is too fine. Northwind's 2 billion rows over one year is fine partitioned by day (365 partitions, hundreds of MB each); partitioning additionally by `device_id` (tens of thousands of values) would be a disaster.

### Skew: when partitions are wildly unequal

Even a sensible partition column can hurt if its values are unevenly distributed. Suppose 80% of Northwind's sensors are in Riverbend. Partitioning by `region` gives you one enormous partition and two tiny ones. A distributed query that filters on Riverbend can only parallelize across the files *within* that partition, and any aggregation over all regions waits on the one slow, oversized task. This is **data skew**, and it shows up as a job where most workers finish quickly and one runs for ages.

Mitigations: combine the skewed column with an evenly distributed one (partition by `event_date` so each region's data spreads across day partitions); or, for in-engine processing, repartition or salt the skewed key across more tasks. The instinct to build: when one stage of a job is slow, check whether work is distributed evenly before you reach for more compute.

### Partitioning is workload-specific

The right strategy differs by workload. For **files and batch analytics**, partition by the common filter columns at a granularity that keeps files large. For **streaming sinks**, time-based partitioning (by ingest date or hour) lets each micro-batch append to the current partition without rewriting old data — but a too-fine time grain reproduces the small-file problem in real time, so streaming jobs pair partitioning with periodic compaction. The unifying idea: partitioning trades how much data a read can skip against how much overhead each write and read pays.

## Walkthrough: repartitioning Northwind's sensor lake

Northwind's nightly job currently writes everything to one folder. You will rewrite it to partition by `event_date`, sized for healthy file counts. The job runs in PySpark on an Azure Databricks or Synapse Spark cluster reading from and writing to Data Lake Storage Gen2.

```python
from pyspark.sql import functions as F

# Read the unpartitioned raw drop (one giant folder of Parquet).
raw = spark.read.parquet("abfss://raw@nwtelemetry.dfs.core.windows.net/sensor_readings/")

# Derive the partition column from the event timestamp. Partitioning on a
# coarse date keeps the number of partitions bounded (~365/year) and the
# files large, instead of partitioning on the high-cardinality device_id.
readings = raw.withColumn("event_date", F.to_date("event_ts"))

# Coalesce within each date partition to control file count. Without this,
# Spark may emit one small file per input task per partition. Targeting a
# modest number of output files per day keeps each file in the hundreds of MB.
(
    readings
    .repartition("event_date")          # shuffle so each date lands together
    .sortWithinPartitions("region")     # cluster region for better file skipping
    .write
    .mode("overwrite")
    .partitionBy("event_date")          # encodes event_date into the path
    .parquet("abfss://curated@nwtelemetry.dfs.core.windows.net/sensor_readings/")
)
```

After this runs, the lake holds paths like `.../sensor_readings/event_date=2026-06-07/part-*.parquet`. Now rerun the analyst query:

```python
result = (
    spark.read.parquet("abfss://curated@nwtelemetry.dfs.core.windows.net/sensor_readings/")
    .where((F.col("event_date") >= "2026-06-01") & (F.col("region") == "riverbend"))
    .groupBy("region").agg(F.avg("moisture").alias("avg_moisture"))
)
result.explain()  # confirm "PartitionFilters" appear in the physical plan
```

Call `.explain()` and look for `PartitionFilters: [event_date >= ...]` in the scan node. Its presence proves the engine will prune to seven day-partitions instead of scanning the year. The eleven-minute query collapses to seconds — not because you added compute, but because you stopped reading data that could not match.

## Common pitfalls

- **Partitioning on a high-cardinality column.** `device_id` or a full timestamp creates millions of tiny partitions and the small-file problem. Partition on low-to-moderate cardinality columns that appear in filters; push fine-grained skipping to file-level statistics instead.
- **Partitioning on a column queries never filter.** It adds write cost and directory clutter with zero pruning benefit. Validate every partition column against real query predicates.
- **Ignoring file size.** Tens of thousands of 1 MB files will be slower than a few hundred 256 MB files, regardless of how clever the partition scheme is. Coalesce or compact on write, and schedule periodic compaction for append-heavy tables.
- **Filtering with a function on the partition column.** Writing `WHERE year(event_ts) = 2026` instead of `WHERE event_date >= '2026-01-01'` can defeat pruning, because the engine may not match the expression to the partition path. Filter directly on the partition column.
- **Ignoring skew.** A single dominant key (one huge region, one busy customer) creates a straggler partition that no amount of extra workers fixes. Spread skewed keys across an evenly distributed second column or salt them.

## Knowledge check

1. An analyst's queries almost always filter by `customer_id` (50,000 distinct values) and `order_date`. A teammate proposes partitioning by `customer_id`. Why is this likely a mistake, and what would you suggest instead?
2. A team partitioned 200 GB by `region`, `device_id`, and `minute`, and queries got slower. Name the most likely cause and the metric you would check to confirm it.
3. You partitioned by `event_date` but a query that filters `WHERE event_date = '2026-06-07'` still scans the whole table. What is the first thing you would inspect?

<details>
<summary>Answers</summary>

1. Partitioning by `customer_id` creates 50,000 partitions, most tiny — the small-file problem — and a single-customer query still can't skip much within its own partition. Partition by `order_date` (bounded count, large files) which most queries also filter on, and rely on file-level statistics or clustering for `customer_id` skipping. — *Granularity should keep partitions large; high-cardinality keys belong in clustering, not partitioning.*
2. Over-partitioning into millions of tiny files; query time is dominated by file-open and listing overhead, not data reads. Confirm by checking the average partition/file size (`total_size / file_count`) — it will be far below ~100 MB. — *The small-file problem makes finer partitioning slower, not faster.*
3. Inspect the query's physical plan (`.explain()`) for `PartitionFilters`. If absent, the predicate isn't being matched to the partition path — often because a function wraps the column or a type mismatch prevents pruning. — *Pruning only happens when the engine can map the filter to partition paths.*

</details>

## Summary

Partitioning lays data on disk so a query engine can skip what it doesn't need, and that skipping — pruning — is where the speedup comes from. The art is choosing columns that match real query filters at a granularity that keeps files large, while watching for skew that creates straggler partitions. Get this right and every downstream query and pipeline inherits the benefit; get it wrong and no amount of compute rescues you. With a sound physical layout in hand, the next module organizes the whole account — **Data Lake Storage Gen2 and the exploration layer** — so people, not just engines, can find and query the data.

## Further learning

- [Best practices for using Azure Data Lake Storage Gen2](https://learn.microsoft.com/en-us/azure/storage/blobs/data-lake-storage-best-practices)
- [Introduction to Azure Data Lake Storage Gen2](https://learn.microsoft.com/en-us/azure/storage/blobs/data-lake-storage-introduction)
- [Partition discovery and data layout (Apache Spark on Azure Synapse)](https://learn.microsoft.com/en-us/azure/synapse-analytics/spark/apache-spark-performance)
