---
kind: module
id: de-c02-m01
vertical: data-engineering
course_id: de-c02
title: Ingest and transform with Apache Spark
level: intermediate
grounded_on: "DP-203 skills outline (2024-10-24), paraphrased — original synthetic content; current path Fabric DP-700"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/dp-203
synthetic: true
order: 1
prereqs: [de-c01]
objectives:
  - Transform large datasets using Apache Spark DataFrame operations
  - Cleanse data and resolve duplicate and missing values deliberately
  - Normalize and denormalize data to match the target model
---

# Ingest and transform with Apache Spark

Greenfork Grocers, a fictional regional chain, drops a daily CSV of point-of-sale transactions into their lake. The file is a mess: the same sale sometimes appears twice because the till retries on a flaky network, customer IDs are blank for cash purchases, prices arrive as strings with currency symbols, and one store's export uses a different timezone. A row-by-row Python script worked when there were ten stores; at four hundred stores and eighty million rows a night, it does not finish before the morning reports run. You need an engine that can spread that work across a cluster and a programming model that lets you say *what* you want, not *how* to loop. That engine is Apache Spark.

## Learning objectives

By the end of this module you will be able to:

- Read raw files into a Spark DataFrame and apply column-level transformations at scale
- Remove true duplicates while preserving the record you actually want to keep
- Decide between dropping, filling, and flagging missing values, and implement each
- Reshape data between normalized and denormalized forms to fit the downstream model

## Concepts

### The DataFrame and lazy evaluation

A Spark DataFrame is a distributed table: conceptually rows and columns, physically partitioned across the worker nodes of a cluster. You manipulate it with *transformations* — `select`, `filter`, `withColumn`, `groupBy`, `join` — each of which returns a new DataFrame rather than mutating the old one. This immutability is not just style; it lets Spark build a plan.

The key mental shift is *lazy evaluation*. Transformations do not run when you write them. Spark records them as a logical plan and does nothing until you call an *action* — `write`, `count`, `collect`, `show`. At that moment the Catalyst optimizer rewrites your whole chain into an efficient physical plan (pushing filters down, pruning columns, combining steps) and only then executes. The practical consequence: chaining ten transformations costs nothing until the action, so you can write clear, step-by-step code without paying for intermediate materializations. The trap, which we will return to, is calling an action — or the same DataFrame — repeatedly and unknowingly recomputing the entire chain each time.

### Cleansing is a sequence of explicit decisions

"Cleanse the data" is not one operation; it is a series of judgement calls you make explicit in code. Trimming whitespace, normalizing case, stripping a currency symbol and casting to a decimal, parsing a timestamp with the correct timezone, rejecting rows that fail a business rule — each is a transformation you choose deliberately. The discipline is to *never silently coerce*. If `"$3.50"` becomes `NULL` because the cast failed, you want to know that happened, not discover it three layers downstream. Cast into a new column, count the nulls the cast produced, and decide what they mean before you overwrite the original.

### Duplicates and missing values: keep the right one, fill with intent

Two records are rarely byte-identical duplicates. More often a "duplicate" is two rows with the same business key (same transaction ID) but different arrival times or partial data. `dropDuplicates()` on the full row will not catch those. The correct pattern is to define the *key* that makes a row unique, then choose which of the colliding rows survives — usually the latest by an event timestamp. A window function ranked within each key lets you keep exactly the row you mean.

Missing values are a decision, not a default. You have three honest options: **drop** the row (acceptable only when the field is mandatory and the row is useless without it), **fill** with a defined sentinel or computed value (`0`, `"UNKNOWN"`, a group median), or **flag** it by adding a boolean column so downstream consumers can choose. The wrong move is to let nulls flow through unexamined and propagate into broken aggregates.

### Normalize and denormalize for the target

Your raw feed and your target model rarely share a shape. *Normalizing* splits a wide, redundant row into related tables so each fact lives once — good for write-heavy operational stores. *Denormalizing* does the opposite: it pre-joins reference data into one wide table so reads are fast and join-free — good for analytics and the gold layer. In a batch pipeline you usually denormalize for serving: enrich the transaction row with the product name and category from a small lookup so the BI tool never has to join at query time. Spark's `broadcast` join makes that enrichment cheap when the lookup is small.

## Walkthrough: cleaning Greenfork's nightly POS feed

You will read the raw CSV, clean the price and timestamp, deduplicate by transaction key keeping the latest, handle missing customer IDs by flagging, and enrich with a product lookup. The code is idiomatic PySpark and runs in a Synapse or Fabric Spark notebook.

```python
from pyspark.sql import functions as F
from pyspark.sql.window import Window

# 1. Read the raw nightly drop. inferSchema is fine for exploration;
#    in production you would supply an explicit schema for stability.
raw = (
    spark.read
    .option("header", True)
    .csv("abfss://bronze@greenfork.dfs.core.windows.net/pos/2026-06-12/*.csv")
)

# 2. Cleanse: strip the currency symbol, cast price, parse the timestamp.
cleaned = (
    raw
    .withColumn("price", F.regexp_replace("price", r"[$,]", "").cast("decimal(10,2)"))
    .withColumn("sold_at", F.to_timestamp("sold_at", "yyyy-MM-dd HH:mm:ss"))
    .withColumn("store_id", F.trim(F.col("store_id")))
)

# 3. Surface what the casts cost us before trusting the data.
bad_prices = cleaned.filter(F.col("price").isNull()).count()
print(f"Rows with unparseable price: {bad_prices}")

# 4. Deduplicate by transaction_id, keeping the latest arrival.
w = Window.partitionBy("transaction_id").orderBy(F.col("sold_at").desc())
deduped = (
    cleaned
    .withColumn("rn", F.row_number().over(w))
    .filter(F.col("rn") == 1)
    .drop("rn")
)

# 5. Missing customer IDs are expected for cash sales — flag, don't drop.
flagged = (
    deduped
    .withColumn("is_anonymous", F.col("customer_id").isNull())
    .fillna({"customer_id": "ANON"})
)

# 6. Denormalize: broadcast-join the small product lookup for fast reads.
products = spark.read.format("delta").load(
    "abfss://silver@greenfork.dfs.core.windows.net/dim_product"
)
enriched = flagged.join(
    F.broadcast(products.select("product_id", "product_name", "category")),
    on="product_id",
    how="left",
)

# 7. The single action that triggers the whole plan.
(
    enriched.write
    .format("delta")
    .mode("overwrite")
    .save("abfss://silver@greenfork.dfs.core.windows.net/fact_sales")
)
```

Notice that steps 1–6 build a plan and cost nothing; step 7 is the only action, so Spark optimizes the entire chain once. The `print` in step 3 is itself an action — useful during development, but in a tight production job you would compute that count differently or drop it, because it forces an extra pass over the data.

## Common pitfalls

- **Calling actions in a loop and recomputing everything.** Each `count()`, `show()`, or write re-executes the whole lazy chain from the source. If you reuse a DataFrame several times, `cache()` (or `persist()`) it after the expensive steps, and `unpersist()` when done.
- **`dropDuplicates()` on the whole row.** Near-duplicates differing only by timestamp survive. Define the business key and use a ranked window to keep the row you actually want.
- **Silent cast failures.** `cast("decimal")` turns junk into `NULL` with no error. Always measure how many nulls a cast produced before overwriting the source column.
- **Broadcasting a table that is not small.** `broadcast()` ships the table to every executor. Do it to a multi-gigabyte table and you exhaust executor memory. Broadcast only genuinely small dimensions; let Spark choose the join strategy otherwise.
- **Trusting `inferSchema` in production.** Inference samples the file and can guess wrong when an early partition lacks a value. Supply an explicit schema for scheduled jobs so a stray file cannot silently change your column types.

## Knowledge check

1. Your job reads a DataFrame, then calls `.count()` three times and `.write` once. Performance is terrible. What is happening and what is the fix?
2. A feed has duplicate `order_id` rows that differ only in a `received_at` timestamp. Why is `dropDuplicates(["order_id"])` risky here, and what should you do instead?
3. Customer email is missing on 8% of rows. Marketing needs to know which records lacked an email, but the records are still valid sales. Drop, fill, or flag — and why?

<details>
<summary>Answers</summary>

1. Each action re-executes the entire lazy plan from the source, so the source is read four times. Cache the DataFrame after the costly transformations (`df.cache()`), reuse the cached version, and `unpersist()` when finished. — Lazy evaluation means transformations are free but each action triggers full recomputation unless results are persisted.
2. `dropDuplicates(["order_id"])` keeps an *arbitrary* one of the colliding rows, so you may keep stale data. Use a window partitioned by `order_id` ordered by `received_at` descending and keep `row_number() == 1`. — You must control *which* duplicate survives, not just that one does.
3. Flag it: add an `is_email_missing` boolean (or fill with a sentinel and flag). Dropping discards valid sales and biases revenue; blindly filling hides the gap from marketing. — Missing-data handling should preserve valid records while making the gap explicit to downstream consumers.

</details>

## Summary

Spark turns large-scale cleansing into a sequence of explicit, immutable transformations that an optimizer executes lazily in one pass. You learned to read raw files, cleanse columns while surfacing cast losses, deduplicate by business key with a ranked window, handle missing values by deciding (drop, fill, or flag) rather than defaulting, and denormalize with a broadcast join for fast reads. The next module, **Transforming with T-SQL and Synapse**, takes the same intentions — dedupe, reshape, enrich — and expresses them as set-based SQL inside a warehouse, where the data is already relational and the engine sits closer to the gold tables.

## Further learning

- [What is Apache Spark in Azure Synapse Analytics](https://learn.microsoft.com/en-us/azure/synapse-analytics/spark/apache-spark-overview)
- [Apache Spark DataFrames in Microsoft Fabric / Azure](https://learn.microsoft.com/en-us/azure/databricks/getting-started/dataframes)
- [Window functions and the PySpark functions API reference](https://learn.microsoft.com/en-us/azure/synapse-analytics/spark/apache-spark-data-frame-tutorial)
