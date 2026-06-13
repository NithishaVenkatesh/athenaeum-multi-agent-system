---
kind: module
id: de-c02-m04
vertical: data-engineering
course_id: de-c02
title: Incremental loads, upserts, and error handling
level: intermediate
grounded_on: "DP-203 skills outline (2024-10-24), paraphrased — original synthetic content; current path Fabric DP-700"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/dp-203
synthetic: true
order: 4
prereqs: [de-c02-m03]
objectives:
  - Design incremental loads using a watermark so each run processes only new data
  - Implement idempotent upserts with MERGE so re-runs are safe
  - Handle failed loads, validate results, and configure exception handling in pipelines
---

# Incremental loads, upserts, and error handling

Greenfork's nightly pipeline works — but it reloads the *entire* sales history every night, and as the table grows the run is creeping past the 02:00–06:00 window. Worse, last Tuesday the SQL load failed halfway, someone re-ran it, and a batch of sales got double-counted because the load just appended. The business now distrusts the numbers. You need three things you have not yet built: a way to process only what is *new* since the last run, a way to apply changes so that re-running is harmless, and a way to fail loudly, validate the result, and recover without corrupting data. This is what separates a demo pipeline from one that runs unattended for a year.

## Learning objectives

By the end of this module you will be able to:

- Design a watermark-based incremental load that processes only new or changed rows
- Write an idempotent `MERGE` upsert so re-running a batch never duplicates data
- Validate a load against expected row counts and known invariants before publishing it
- Configure exception handling and recovery so failures are visible and non-destructive

## Concepts

### Incremental loads and the watermark

A full reload is simple and wrong at scale: it grows linearly with history and reprocesses data that has not changed. An **incremental load** processes only rows that are new or changed since the last successful run. The mechanism is a **watermark** — a stored high-water mark, usually the maximum value of a monotonically increasing column (an `updated_at` timestamp or an ever-rising surrogate key) from the last load. Each run reads rows *greater than* the stored watermark, processes them, and on success advances the watermark to the new maximum.

The subtlety is *what column makes a sound watermark*. It must increase whenever a row is inserted or updated and never go backwards. An `updated_at` set by the source on every write is ideal; a `created_at` misses updates to existing rows. Store the watermark in a tiny control table in the warehouse, read it at the start of the run, and write the new value only after the load succeeds — so a failed run leaves the watermark untouched and the next run simply retries the same slice.

### Upserts with MERGE: make re-runs harmless

Appending is dangerous because a re-run appends again. An **upsert** instead reconciles incoming rows against the target by key: update the row if the key already exists, insert it if it does not. T-SQL expresses this with `MERGE`, matching a source set against the target `ON` the business key, with `WHEN MATCHED THEN UPDATE` and `WHEN NOT MATCHED THEN INSERT` branches. The payoff is **idempotency**: running the same batch twice produces the same result as running it once, because the second run matches the existing rows and updates them in place rather than duplicating them. Idempotency is the property that lets you re-run a failed pipeline without fear — and you *will* re-run pipelines.

### Validation: trust, but verify the load

A load that "completed" is not the same as a load that is *correct*. Before you advance the watermark and expose the data, validate it. Cheap, high-value checks: did the row count land within an expected range (zero rows on a normal business day is suspicious; ten times normal is suspicious the other way)? Are there nulls in columns that must never be null? Do the keys you upserted actually exist now? Encode these as queries that fail the pipeline when an invariant is violated, so bad data never silently becomes "the numbers."

### Exception handling and non-destructive recovery

Things fail: a source file is malformed, a transient network blip kills a connection, a constraint rejects a row. Robust pipelines handle this on two fronts. *Activity-level* retries (from the previous module) absorb transient failures automatically. *Structural* handling routes the failure: a failure path that logs the error and alerts, a quarantine location where rejected rows are written instead of crashing the whole batch (reject thresholds on bulk loads do exactly this), and — critically — making each step safe to repeat. The guiding principle is **non-destructive failure**: a half-run pipeline must leave the system in a state the next run can recover from. Watermark-after-success plus upsert gives you exactly that.

## Walkthrough: Greenfork's restartable incremental load

You will read the stored watermark, stage only newer rows, upsert them into the fact table with `MERGE`, validate, then advance the watermark — all so the load is incremental, idempotent, and safe to re-run.

```sql
-- 1. Read the last successful watermark from the control table.
DECLARE @last_watermark datetime2;
SELECT @last_watermark = last_loaded_at
FROM   meta.load_control
WHERE  table_name = 'fact_sales';

-- 2. Stage only rows changed since the watermark.
CREATE TABLE staging.fact_sales_delta
WITH (DISTRIBUTION = HASH(transaction_id), HEAP)
AS
SELECT *
FROM   silver.fact_sales
WHERE  updated_at > @last_watermark;

-- 3. Upsert: update existing keys, insert new ones. Idempotent by design.
MERGE gold.fact_sales AS target
USING staging.fact_sales_delta AS source
    ON target.transaction_id = source.transaction_id
WHEN MATCHED THEN
    UPDATE SET
        target.price        = source.price,
        target.product_id   = source.product_id,
        target.is_anonymous = source.is_anonymous,
        target.updated_at   = source.updated_at
WHEN NOT MATCHED BY TARGET THEN
    INSERT (transaction_id, product_id, price, is_anonymous, sold_at, updated_at)
    VALUES (source.transaction_id, source.product_id, source.price,
            source.is_anonymous, source.sold_at, source.updated_at);

-- 4. Validate before trusting the load. Fail loudly if an invariant breaks.
DECLARE @null_prices int =
    (SELECT COUNT(*) FROM gold.fact_sales WHERE price IS NULL);
IF @null_prices > 0
    THROW 50001, 'Validation failed: NULL prices present after load.', 1;

-- 5. Advance the watermark ONLY after success, so a failure replays cleanly.
UPDATE meta.load_control
SET    last_loaded_at = (SELECT MAX(updated_at) FROM staging.fact_sales_delta)
WHERE  table_name = 'fact_sales'
  AND  EXISTS (SELECT 1 FROM staging.fact_sales_delta);
```

Trace the safety: if step 3 or 4 throws, step 5 never runs, so the watermark stays put and the next run re-stages the same delta and re-`MERGE`s it — and because `MERGE` is keyed, that re-run updates the same rows instead of duplicating them. The pipeline is now both incremental (step 2 limits the work) and idempotent (steps 3 and 5 make re-runs harmless). Wrap step 4's `THROW` so the pipeline's failure path catches it and alerts.

## Common pitfalls

- **Appending instead of upserting.** A re-run of an append-only load double-counts. Use `MERGE` keyed on the business key so re-runs reconcile rather than duplicate.
- **Advancing the watermark before the load succeeds.** If you bump the watermark first and the load then fails, the failed slice is skipped forever. Always update the watermark *after* validation passes.
- **Choosing `created_at` as the watermark.** It misses updates to existing rows, so changed records never reload. Use a column the source bumps on every insert *and* update, such as `updated_at`.
- **Treating "completed" as "correct".** A load can finish and still be wrong. Add row-count and null/invariant checks that fail the pipeline before the data is exposed.
- **Letting one bad row crash the whole batch.** A single malformed record should not sink millions of good ones. Use reject thresholds / a quarantine path so bad rows are isolated and the batch proceeds, then triage the rejects.

## Knowledge check

1. A pipeline updates the watermark first, then runs the load. The load fails. What goes wrong on the *next* run, and how do you fix the ordering?
2. Why does using `MERGE` keyed on the business key make a pipeline safe to re-run, where an `INSERT` does not?
3. Your watermark column is `created_at`. Rows that were *edited* (not newly created) since the last run are not being picked up. Why, and what column should the watermark use instead?

<details>
<summary>Answers</summary>

1. The next run reads the already-advanced watermark and skips the slice that failed, so that data is never loaded. Advance the watermark only *after* the load and validation succeed, so a failure leaves it untouched and the slice replays. — Watermark-after-success guarantees non-destructive recovery.
2. `MERGE` matches incoming rows against existing ones by key and updates in place when matched, so a second run of the same batch reconciles to the same state. `INSERT` blindly adds rows, so a re-run duplicates them. — Keyed reconciliation is what makes the operation idempotent.
3. `created_at` only changes when a row is first inserted, so updates to existing rows keep their old timestamp and fall below the watermark. Use an `updated_at` column that the source sets on every insert and update. — A sound watermark must increase on any change, not just on creation.

</details>

## Summary

Reliable batch processing rests on three habits: load incrementally using a watermark so each run touches only new data, upsert with a keyed `MERGE` so re-runs are idempotent, and validate then advance the watermark only on success so failures recover non-destructively. Combined with the activity retries and failure paths from **Orchestrating pipelines with Data Factory**, these turn a fragile nightly job into one that runs unattended and earns the business's trust. You have now traveled the full batch path — cleanse with Spark, transform and load with T-SQL, orchestrate with Data Factory, and harden with incremental, idempotent, validated loads — and you are ready to apply the same engineering judgement in Microsoft Fabric, where the engines change names but these patterns do not.

## Further learning

- [Copy data incrementally using Change Tracking / watermark in Azure Data Factory](https://learn.microsoft.com/en-us/azure/data-factory/tutorial-incremental-copy-overview)
- [MERGE (Transact-SQL)](https://learn.microsoft.com/en-us/sql/t-sql/statements/merge-transact-sql)
- [Error handling and recovery in mapping data flows / pipelines](https://learn.microsoft.com/en-us/azure/data-factory/concepts-pipelines-activities)
- [Use TRY...CATCH and THROW for T-SQL error handling](https://learn.microsoft.com/en-us/sql/t-sql/language-elements/try-catch-transact-sql)
