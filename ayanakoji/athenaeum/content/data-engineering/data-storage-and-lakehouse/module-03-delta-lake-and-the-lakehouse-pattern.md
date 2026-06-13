---
kind: module
id: de-c01-m03
vertical: data-engineering
course_id: de-c01
title: Delta Lake and the lakehouse pattern
level: foundational
grounded_on: "DP-203 skills outline (2024-10-24), paraphrased — original synthetic content; current path Fabric DP-700"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/dp-203
synthetic: true
order: 3
prereqs: [de-c01-m02]
objectives:
  - Explain the lakehouse architecture and what Delta Lake adds over plain Parquet
  - Read from and write to a Delta Lake, including updates and merges
  - Use versioning and time travel to inspect and revert data
---

# Delta Lake and the lakehouse pattern

Northwind Telemetry's silver zone holds clean, partitioned Parquet — and last Tuesday it nearly took down the morning dashboards. A nightly job failed halfway through overwriting the `sensor_readings` table; it had deleted the old files and written only a third of the new ones before crashing. For four hours, every query returned partial data with no error to warn anyone. Plain Parquet has no notion of a transaction: a multi-file write is not atomic, there is no schema enforcement, and there is no way to ask "what did this table look like before the bad job?" The lakehouse pattern, built on Delta Lake, closes exactly these gaps — you keep cheap object storage but gain the reliability guarantees of a database.

## Learning objectives

By the end of this module you will be able to:

- Explain the lakehouse architecture and the role Delta Lake's transaction log plays.
- Read from and write to Delta tables, including appends, overwrites, and upserts via `MERGE`.
- Inspect a table's version history and query past versions with time travel.
- Revert a table to a previous state after a bad load.

## Concepts

### The lakehouse: one storage layer, two sets of guarantees

For years teams ran two systems: a data lake (cheap, scalable, schemaless object storage, good for raw and ML data) and a data warehouse (transactional, governed, fast SQL, expensive and rigid). Data was copied between them, doubling storage and drifting out of sync. The **lakehouse** collapses these into one: you keep data in open files on object storage *and* get warehouse-grade reliability — ACID transactions, schema enforcement, consistent reads — by adding a transactional table format on top. Delta Lake is that format on Azure Databricks, Synapse Spark, and Microsoft Fabric.

The trick is that a Delta table is just Parquet data files plus a **transaction log** (a directory named `_delta_log`). The log is an ordered series of JSON commit files, each recording exactly which Parquet files were added or removed in that transaction. Readers never list the data folder and guess; they read the log to learn the *current valid set of files*. That indirection is the whole magic.

### How the transaction log delivers ACID

Consider Northwind's failed overwrite. With plain Parquet, the writer deleted files and wrote new ones directly, so a crash left the folder in a broken in-between state. With Delta, the writer never touches the reader's view until it is done: it writes the new Parquet files, then **atomically** appends a single commit to the log that says "remove old files A, B, C; add new files X, Y, Z." Until that commit lands, readers continue to see the old, complete version. If the job crashes before committing, the half-written files are simply never referenced by any log entry — they are orphans, ignored by every reader. The table is *always* in a consistent state. That single atomic log append is what turns a multi-file write into an all-or-nothing transaction.

The log also enables **schema enforcement**: each commit records the schema, and a write that doesn't match the table's schema is rejected rather than silently corrupting the data (you can opt into controlled schema evolution when you genuinely want to add columns). And because each commit is a numbered version, the log is simultaneously a complete, queryable history of the table.

### Time travel and reverting

Because the log records every version, you can read the table *as of* any past version or timestamp — this is **time travel**. `VERSION AS OF 41` reads the exact file set that was valid at commit 41. This is not a backup you restore from; it is the live table, viewed at a past point, with no copy made. It is invaluable for debugging ("the numbers were right yesterday — what changed?"), for reproducible reports ("run this against the data as of month-end"), and for auditing.

Reverting builds on the same mechanism. If a bad job corrupts the table at version 42, you don't dig through backups — you `RESTORE` the table to version 41, which writes a new commit (version 43) whose valid file set equals version 41's. The fix is fast because no data is rewritten; only the log changes. Note that old versions are retained only as long as their underlying files exist — a maintenance operation (often called `VACUUM`) eventually removes files no longer referenced beyond a retention window, so time travel is bounded by that window. Verify the default retention in the docs, as it has changed across versions.

### Upserts with MERGE

Real tables aren't only appended to; rows get corrected, late data arrives, and the same record may be re-ingested. Plain Parquet has no update-in-place. Delta provides `MERGE` — a single atomic statement that inserts new rows and updates existing ones based on a match condition (an *upsert*). This is the backbone of incremental loading, which you'll use heavily in the next course's pipelines. `MERGE` reads the matching files, computes the changed rows, and commits the result as one transaction, so concurrent readers see either the full before or the full after.

## Walkthrough: making Northwind's silver table reliable

You will convert the curated sensor readings into a Delta table, run a safe upsert of corrected records, then simulate a bad load and revert it — all without restoring from a backup. This runs in PySpark on a Spark cluster that supports Delta.

```python
from delta.tables import DeltaTable
from pyspark.sql import functions as F

silver_path = "abfss://silver@nwtelemetry.dfs.core.windows.net/sensor_readings_delta"

# 1. Write the curated readings as a Delta table, partitioned as before.
#    The "delta" format creates the _delta_log alongside the Parquet files.
(
    spark.read.parquet("abfss://silver@nwtelemetry.dfs.core.windows.net/sensor_readings/")
    .write.format("delta")
    .partitionBy("event_date")
    .mode("overwrite")
    .save(silver_path)
)

# 2. A batch of corrected readings arrives (some new devices, some fixes).
corrections = spark.read.parquet(
    "abfss://bronze@nwtelemetry.dfs.core.windows.net/corrections/2026-06-12/"
)

# 3. Upsert atomically: update moisture where the device+date already exists,
#    insert otherwise. Readers see either the full old or full new state.
target = DeltaTable.forPath(spark, silver_path)
(
    target.alias("t")
    .merge(
        corrections.alias("s"),
        "t.device_id = s.device_id AND t.event_date = s.event_date",
    )
    .whenMatchedUpdate(set={"moisture": "s.moisture"})
    .whenNotMatchedInsertAll()
    .execute()
)
```

Now inspect history and recover from a hypothetical bad load:

```python
# View the version history: each write/merge is a numbered commit.
target.history().select("version", "timestamp", "operation").show(truncate=False)

# Suppose a later job corrupted the table at the newest version. Read the
# table as it was at an earlier good version (time travel) to verify the data...
good = spark.read.format("delta").option("versionAsOf", 1).load(silver_path)
print("good row count:", good.count())

# ...then restore the live table to that version. This writes a NEW commit
# whose file set equals version 1; no Parquet is rewritten, so it is fast.
spark.sql(f"RESTORE TABLE delta.`{silver_path}` TO VERSION AS OF 1")
```

What to observe: the `MERGE` updated and inserted in a single atomic commit, so no query ever saw a partial result. `history()` shows the audit trail. `RESTORE` recovered from corruption in seconds by rewriting only the log — the exact failure that hurt Northwind under plain Parquet is now a one-line fix.

## Common pitfalls

- **Expecting time travel forever.** Old versions survive only while their files do; a `VACUUM` past the retention window deletes them and breaks time travel to those versions. Don't treat time travel as long-term backup — verify retention and back up deliberately for compliance needs.
- **Bypassing the transaction log.** Editing or deleting Parquet files in a Delta directory directly (with raw file tools) corrupts the table, because the log no longer matches reality. Only ever write through the Delta API/SQL.
- **Accidental schema changes.** Relying on automatic schema merge in production can let a malformed upstream change silently widen your table. Keep schema enforcement on and evolve schemas intentionally.
- **Tiny commits from streaming or frequent writes.** Many small Delta commits create many small files and a long log, slowly degrading reads. Schedule compaction/optimize and log checkpointing for high-write tables.
- **Confusing time travel with replication.** Reading `VERSION AS OF` does not protect against an account deletion or region outage. Time travel is in-table history, not disaster recovery.

## Knowledge check

1. A nightly Delta overwrite job crashes after writing some but not all of its Parquet files. What do concurrent dashboard queries see, and why?
2. A teammate wants to "restore last week's data" and plans to copy old Parquet files back into the folder by hand. Why is this dangerous in a Delta table, and what should they do instead?
3. You restored a 5 TB table to a prior version and it completed in seconds. Explain why a restore can be so fast.

<details>
<summary>Answers</summary>

1. They see the previous complete version of the table. The new files aren't referenced by any commit until the writer atomically appends the commit to the log, so a crash before commit leaves the new files as ignored orphans. — *The transaction log makes a multi-file write atomic and keeps readers on a consistent version.*
2. Copying files in directly bypasses the transaction log, so the log no longer matches the files on disk and the table is corrupted. They should use time travel / `RESTORE TABLE ... TO VERSION AS OF` (or a timestamp) so the recovery goes through the log. — *All changes must go through the Delta API so the log stays authoritative.*
3. `RESTORE` only writes a new commit whose valid file set equals the target version's; it doesn't rewrite the 5 TB of Parquet, since those files still exist. The work is a metadata operation on the log. — *Versioning is logical (which files are valid), so reverting is a log change, not a data rewrite.*

</details>

## Summary

A Delta Lake table is Parquet plus a transaction log, and that log is what turns cheap object storage into a lakehouse: atomic multi-file writes, schema enforcement, full version history, time travel, and fast reverts. `MERGE` gives you database-style upserts for incremental loads, and `RESTORE` recovers from bad loads without backups. Northwind's silver tables are now reliable as well as organized. The final module, **Cataloging and lineage with Microsoft Purview**, makes the whole estate discoverable and traceable so people across the organization can trust and find these tables.

## Further learning

- [What is Delta Lake? (Azure Databricks)](https://learn.microsoft.com/en-us/azure/databricks/delta/)
- [Work with Delta Lake table history and time travel](https://learn.microsoft.com/en-us/azure/databricks/delta/history)
- [Upsert into a Delta Lake table using MERGE](https://learn.microsoft.com/en-us/azure/databricks/delta/merge)
- [What is a lakehouse? (Microsoft Fabric)](https://learn.microsoft.com/en-us/fabric/data-engineering/lakehouse-overview)
