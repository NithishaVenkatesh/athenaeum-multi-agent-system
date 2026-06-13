---
kind: module
id: de-c02-m02
vertical: data-engineering
course_id: de-c02
title: Transforming with T-SQL and Synapse
level: intermediate
grounded_on: "DP-203 skills outline (2024-10-24), paraphrased — original synthetic content; current path Fabric DP-700"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/dp-203
synthetic: true
order: 2
prereqs: [de-c02-m01]
objectives:
  - Express transformations as set-based T-SQL in a Synapse dedicated SQL pool
  - Load data efficiently into a SQL pool using external tables and CTAS
  - Shred JSON and handle encoding so semi-structured data becomes relational
---

# Transforming with T-SQL and Synapse

Greenfork's analysts live in a Synapse dedicated SQL pool, not in notebooks. Once you cleaned the nightly sales feed with Spark (in the previous module, **Ingest and transform with Apache Spark**), the data still has to land in the warehouse where the dashboards query it — and a lot of the remaining transformation is cheaper to do *in* the warehouse, set-based, than to round-trip through Spark. The supplier feed is worse: it arrives as JSON, one document per delivery, with nested line items, and someone wrote half the product names in Latin-1 so they show up garbled. You need to load this efficiently, shred the JSON into rows, and fix the encoding — all in T-SQL, on a distributed SQL engine that punishes row-by-row thinking.

## Learning objectives

By the end of this module you will be able to:

- Write set-based T-SQL transformations and avoid row-by-row anti-patterns
- Load data into a dedicated SQL pool efficiently using external tables and CTAS
- Shred JSON documents into relational rows with `OPENJSON`
- Diagnose and correct encoding problems when ingesting text data

## Concepts

### Set-based thinking on a distributed engine

A Synapse dedicated SQL pool is a *massively parallel processing* (MPP) engine. Your table is split across distributions, and a query runs as many parallel tasks, one per distribution. This makes set-based operations — `INSERT ... SELECT`, `UPDATE ... FROM`, `MERGE` — fast, because each distribution works its slice in parallel. It makes anything iterative slow, because cursors and row-by-row loops serialize what the engine wants to parallelize.

The corollary that surprises people coming from SQL Server is *data movement*. When a join or aggregation needs rows that live on different distributions, the engine shuffles them across the network — a `SHUFFLE_MOVE` you can see in the query plan. The biggest lever you have over performance is the table's distribution: hash-distribute large fact tables on the column you join and group by most, so matching rows already sit together and the shuffle disappears. Replicate small dimensions so they exist on every distribution. Get distribution wrong and a correct query still crawls.

### Loading: external tables and CTAS, not INSERT-per-row

The efficient way to get files into a dedicated SQL pool is to *not* stream rows through the client at all. You define an **external table** that points at the files in the lake (via the PolyBase-style external table mechanism, or the newer `COPY INTO` statement), then read from it with SQL as if it were a table. The engine reads the files in parallel directly from storage.

To materialize the result you use **CTAS** — `CREATE TABLE ... AS SELECT`. CTAS is the workhorse load pattern in a SQL pool: it creates a new physical table and populates it in one parallel, minimally-logged operation, and crucially it lets you *set the distribution and index at creation time*. The idiom is: external table → `SELECT` with your transforms → `CTAS` into the target with the right distribution. Avoid the temptation to `INSERT` millions of rows one statement at a time; CTAS and `COPY INTO` are built for bulk.

### Shredding JSON with OPENJSON

Semi-structured JSON has to become rows before relational tools can use it. T-SQL gives you `OPENJSON`, which takes a JSON string and a path and returns a rowset. With an explicit `WITH` clause you map JSON properties to typed columns; using `CROSS APPLY` you can descend into a nested array (like line items inside a delivery) and explode it into one row per element. The mechanism: `OPENJSON` parses the document, the `WITH` schema casts each extracted value, and `CROSS APPLY` runs the shred once per parent row. The result is an ordinary rowset you can `CTAS` into a table.

### Encoding: bytes are not text until you say so

A file is bytes; turning bytes into characters requires the right *code page*. When a UTF-8 file is read as Latin-1 (or vice versa), accented characters turn into mojibake — `café` becomes `cafÃ©`. The fix lives at load time: tell the loader the source encoding so it decodes correctly. `COPY INTO` and external file formats accept an encoding setting; when the source is genuinely mixed, the durable answer is to standardize on UTF-8 upstream rather than patching strings after the fact. Patching with `REPLACE` chains is brittle and never covers every character — fix the decode, not the symptom.

## Walkthrough: loading Greenfork's supplier deliveries

A vendor drops JSON delivery documents into the lake. Each document has a header and a nested `items` array. You will read them via an external table, shred the array with `OPENJSON`, and CTAS the result into a hash-distributed fact table.

```sql
-- 1. Point an external table at the JSON files in the lake.
--    (Assumes the external data source and a JSON-friendly file format
--    already exist; create them once per environment.)
CREATE EXTERNAL TABLE ext.deliveries_raw (
    doc NVARCHAR(MAX)
)
WITH (
    LOCATION   = '/supplier/deliveries/2026-06-12/',
    DATA_SOURCE = lake_src,
    FILE_FORMAT = json_lines_format
);

-- 2. Shred the JSON: one row per line item, typed columns via WITH,
--    nested array exploded with CROSS APPLY.
CREATE TABLE staging.delivery_items
WITH (
    DISTRIBUTION = HASH(product_id),
    HEAP
)
AS
SELECT
    h.delivery_id,
    h.supplier_id,
    CAST(h.delivered_at AS datetime2) AS delivered_at,
    i.product_id,
    i.quantity,
    i.unit_cost
FROM ext.deliveries_raw AS r
CROSS APPLY OPENJSON(r.doc)
    WITH (
        delivery_id  INT            '$.deliveryId',
        supplier_id  INT            '$.supplierId',
        delivered_at VARCHAR(30)    '$.deliveredAt',
        items        NVARCHAR(MAX)  '$.items' AS JSON
    ) AS h
CROSS APPLY OPENJSON(h.items)
    WITH (
        product_id INT            '$.productId',
        quantity   INT            '$.quantity',
        unit_cost  DECIMAL(10,2)  '$.unitCost'
    ) AS i;

-- 3. Load the curated fact table with CTAS, distributed on the join key.
CREATE TABLE gold.fact_delivery
WITH (
    DISTRIBUTION = HASH(product_id),
    CLUSTERED COLUMNSTORE INDEX
)
AS
SELECT
    di.delivery_id,
    di.supplier_id,
    di.product_id,
    di.delivered_at,
    di.quantity,
    di.unit_cost,
    di.quantity * di.unit_cost AS line_total
FROM staging.delivery_items AS di;
```

The outer `OPENJSON` extracts the header and pulls `items` out as a JSON blob (`AS JSON`); the second `OPENJSON` over `CROSS APPLY` explodes that array into one row per line item. Both staging and gold tables hash-distribute on `product_id` — the column you join to the product dimension — so later joins avoid a shuffle. The columnstore index on the gold table makes the analytical scans the dashboards run fast.

## Common pitfalls

- **Row-by-row cursors in an MPP pool.** A cursor serializes work the engine wants to parallelize and can be orders of magnitude slower. Rewrite as a single set-based statement (`MERGE`, `UPDATE ... FROM`, CTAS).
- **Ignoring distribution.** A query that joins two large tables distributed on different keys triggers a costly shuffle on every run. Hash-distribute fact tables on the common join/group key; replicate small dimensions.
- **`INSERT`-looping a bulk load.** Loading millions of rows with repeated `INSERT` statements is slow and heavily logged. Use external tables + CTAS or `COPY INTO`, which load in parallel and minimally logged.
- **Forgetting `AS JSON` on a nested array.** Without it, `OPENJSON`'s `WITH` clause cannot hand the inner array to a second `OPENJSON`, and the shred of nested items fails or returns nulls.
- **Patching mojibake with `REPLACE`.** String-replacing garbled characters is whack-a-mole. Set the correct encoding at load time, or standardize the source to UTF-8 — fix the decode, not each symptom.

## Knowledge check

1. A nightly job loads 50 million rows into a SQL pool with a loop of `INSERT` statements and takes hours. What load pattern should you use and why is it faster?
2. Two large fact tables are joined every morning and the plan shows a large `SHUFFLE_MOVE`. What physical design change removes the shuffle?
3. A JSON document has a top-level `orderId` and a nested `lines` array. Outline how you shred it into one row per line with `OPENJSON`.

<details>
<summary>Answers</summary>

1. Use an external table over the files plus `CREATE TABLE AS SELECT` (CTAS), or `COPY INTO`. These read files in parallel directly from storage and load minimally-logged, whereas per-row `INSERT` serializes and fully logs. — Bulk load mechanisms exploit MPP parallelism; row-at-a-time defeats it.
2. Hash-distribute both tables on the column they join on, so matching rows already live on the same distribution and no cross-distribution data movement is needed. — The shuffle exists only because joined rows sit on different distributions.
3. Use `OPENJSON(doc) WITH (orderId INT '$.orderId', lines NVARCHAR(MAX) '$.lines' AS JSON)` to get the header and the array blob, then `CROSS APPLY OPENJSON(lines) WITH (...)` to explode the array into one row per element. — `AS JSON` passes the nested array to a second `OPENJSON` for shredding.

</details>

## Summary

In a dedicated SQL pool you think in sets, not rows, and you let distribution decide your performance. You learned to load efficiently with external tables and CTAS rather than per-row inserts, to control distribution so joins avoid shuffles, to shred nested JSON into relational rows with `OPENJSON` and `CROSS APPLY`, and to fix encoding at decode time rather than patching mojibake. Both Spark (module 1) and T-SQL are now in your toolkit; the next module, **Orchestrating pipelines with Data Factory**, wraps these transforms in scheduled, versioned pipelines so they run on their own.

## Further learning

- [What is dedicated SQL pool in Azure Synapse Analytics](https://learn.microsoft.com/en-us/azure/synapse-analytics/sql-data-warehouse/sql-data-warehouse-overview-what-is)
- [CREATE TABLE AS SELECT (CTAS) in Azure Synapse Analytics](https://learn.microsoft.com/en-us/azure/synapse-analytics/sql-data-warehouse/sql-data-warehouse-develop-ctas)
- [OPENJSON (Transact-SQL)](https://learn.microsoft.com/en-us/sql/t-sql/functions/openjson-transact-sql)
- [Distributed tables design guidance for dedicated SQL pool](https://learn.microsoft.com/en-us/azure/synapse-analytics/sql-data-warehouse/sql-data-warehouse-tables-distribute)
