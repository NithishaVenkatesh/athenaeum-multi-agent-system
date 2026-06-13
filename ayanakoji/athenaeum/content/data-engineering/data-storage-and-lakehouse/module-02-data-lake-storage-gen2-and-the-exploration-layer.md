---
kind: module
id: de-c01-m02
vertical: data-engineering
course_id: de-c01
title: Data Lake Storage Gen2 and the exploration layer
level: foundational
grounded_on: "DP-203 skills outline (2024-10-24), paraphrased — original synthetic content; current path Fabric DP-700"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/dp-203
synthetic: true
order: 2
prereqs: [de-c01-m01]
objectives:
  - Structure a Data Lake Storage Gen2 account into purposeful zones
  - Query lake data with serverless SQL and Spark, choosing the right engine
  - Build an exploration layer analysts can use without moving data
---

# Data Lake Storage Gen2 and the exploration layer

Northwind Telemetry's lake now has well-partitioned sensor data (you fixed that in the previous module), but the account itself is a swamp. There are folders named `final`, `final_v2`, `test_DONT_DELETE`, and `jons_export`. A new analyst can't tell which path is the trustworthy one, an engineer accidentally reads half-cleaned data into a report, and a query that should hit one zone instead crawls a mix of raw and curated files. A lake without structure is just a more expensive file share. This module gives the account a deliberate shape and shows you how to query it in place — with serverless SQL and Spark — so analysts get value without anyone copying data into yet another silo.

## Learning objectives

By the end of this module you will be able to:

- Organize a Data Lake Storage Gen2 account into containers and a zoned medallion layout.
- Query files directly with serverless SQL using `OPENROWSET`.
- Query and transform the same files with Spark, and decide which engine fits a task.
- Build an exploration layer that analysts can use against governed data.

## Concepts

### What Data Lake Storage Gen2 really is

Data Lake Storage Gen2 is not a separate product bolted on to Blob Storage — it *is* Blob Storage with the **hierarchical namespace** enabled. That one flag changes the storage from a flat key-value bucket into a real directory tree. The practical consequence matters: with a hierarchical namespace, renaming or deleting a "folder" is a single atomic metadata operation rather than a copy-and-delete of every object underneath it. For analytics, where jobs constantly write to temporary directories and then promote them, that atomic rename is what makes commit operations fast and safe. It also enables POSIX-style access control lists on directories, so you can grant a team read access to one zone without exposing the rest.

The addressing scheme reflects the hierarchy. You reference data with the `abfss://` driver: `abfss://<container>@<account>.dfs.core.windows.net/<path>`. The container (Gen2 calls it a *filesystem*) is the top-level grouping; below it are directories and files.

### Zoning the lake: the medallion idea

The cure for the `final_v2` swamp is to give every byte a known stage in its life. A widely used convention is the **medallion** layout — three zones, mapped to containers or top-level directories:

- **Bronze (raw):** data exactly as it arrived, append-only, never edited. This is your replay-and-audit source of truth. If a downstream transform has a bug, you reprocess from bronze.
- **Silver (cleansed/curated):** data that has been validated, deduplicated, conformed to consistent types and schemas, and partitioned sensibly. This is what most engineering reads from.
- **Gold (serving):** business-level aggregates and curated marts shaped for specific consumers — the tables a dashboard or an analyst hits directly.

The value isn't the medal names; it's the contract. Everyone knows bronze is untouched, gold is trustworthy, and you never point a production report at a path under bronze. Combine zoning with the partition discipline from the previous module so `silver/sensor_readings/event_date=.../` is both *findable* (clear zone) and *fast* (pruned).

### Two query engines over the same files

A defining feature of the lakehouse is that you query data **in place** — the files stay in the lake, and you bring compute to them. On Azure you have two complementary serverless-friendly engines, and choosing well is a real skill.

**Serverless SQL** lets you run T-SQL directly over files using `OPENROWSET`, paying per terabyte of data scanned rather than for a running cluster. It is ideal for analysts who think in SQL, for ad-hoc exploration, and for building logical views over the lake without provisioning anything. It excels at "let me look at this Parquet folder right now." It is not built for heavy iterative transformation or machine-learning workloads.

**Spark** (Azure Databricks or Synapse Spark) gives you a full distributed compute engine with Python, Scala, SQL, and rich libraries. Reach for it when you need to *transform* at scale, run multi-step pipelines, apply complex logic, or write back partitioned outputs (exactly what you did in the previous module). It costs more to keep a cluster warm, so you don't want it for a one-line `SELECT`.

The mental model: **serverless SQL for reading and exploring, Spark for transforming and writing.** Both read the same files in the same zones, which is the whole point — no data movement, one source of truth, two lenses.

### The exploration layer

An exploration layer is a thin, query-friendly surface over the governed zones so analysts self-serve without engineers in the loop and without copying data. In practice it is a set of **views** (in serverless SQL or a Spark metastore) that point at silver and gold paths, name columns sensibly, and hide the physical folder structure. Analysts query `vw_sensor_readings`, not an `abfss://` path with partition folders. When you later repartition or move files, you update the view definition and queries keep working — the layer is an abstraction boundary, like an API in front of a database.

## Walkthrough: standing up Northwind's exploration layer

You will define the zoned containers, then expose the curated sensor data through a serverless SQL view so analysts can query it without touching paths. First, create the account with the hierarchical namespace and the three zone containers using the Azure CLI.

```bash
# Create a Gen2 account: Blob Storage + hierarchical namespace (--hns true).
az storage account create \
  --name nwtelemetry \
  --resource-group rg-nwtelemetry \
  --location eastus \
  --sku Standard_LRS \
  --kind StorageV2 \
  --hns true

# One container per medallion zone.
for zone in bronze silver gold; do
  az storage container create \
    --account-name nwtelemetry \
    --name "$zone" \
    --auth-mode login
done
```

Setting `--hns true` is the switch that makes this a Data Lake Storage Gen2 account rather than plain Blob Storage; you cannot toggle it casually after the fact, so decide up front. Now expose the curated data through serverless SQL. This view reads the partitioned Parquet you wrote into `silver` and gives analysts a clean name.

```sql
-- Run in a serverless SQL pool. OPENROWSET reads files in place; the engine
-- prunes partitions from the WHERE clause, so analysts pay only for data scanned.
CREATE VIEW vw_sensor_readings AS
SELECT
    r.region,
    r.device_id,
    r.moisture,
    r.event_date
FROM OPENROWSET(
    BULK 'https://nwtelemetry.dfs.core.windows.net/silver/sensor_readings/',
    FORMAT = 'PARQUET'
) AS r;

-- An analyst now writes plain SQL with no knowledge of folders or partitions:
SELECT region, AVG(moisture) AS avg_moisture
FROM vw_sensor_readings
WHERE event_date >= '2026-06-01' AND region = 'riverbend'
GROUP BY region;
```

The analyst's query filters on `event_date` and `region`; because the silver data is partitioned by `event_date`, serverless SQL prunes to a week of files and bills only for that scan. Observe two things: the analyst never saw an `abfss://` path, and no data was copied — the view is a lens over files that already exist.

## Common pitfalls

- **Forgetting the hierarchical namespace.** Creating a plain Blob account (or `--hns false`) means no atomic directory rename and no directory ACLs, which quietly breaks analytics commit performance and fine-grained security. Set `--hns true` at creation.
- **Letting the lake sprawl without zones.** `final_v2` folders are how lakes rot. Enforce bronze/silver/gold (or your equivalent) from day one; ad-hoc top-level folders are a smell.
- **Using the wrong engine for the job.** Running heavy multi-stage transforms in serverless SQL, or spinning up a Spark cluster for a one-line `SELECT`, wastes money and time. Match engine to task: SQL to explore, Spark to transform.
- **Exposing raw paths to analysts.** If consumers hardcode `abfss://` paths, every storage reorganization breaks their queries. Put a view layer in between so paths stay an implementation detail.
- **Granting blanket access to the whole account.** Use container- and directory-level access control so a team that needs gold cannot accidentally read or write bronze.

## Knowledge check

1. An analyst needs to run an ad-hoc count over a 2 GB Parquet folder once, today. A colleague suggests spinning up a Spark cluster. What would you recommend and why?
2. Why does enabling the hierarchical namespace matter for a pipeline that writes to a staging directory and then promotes it to the final location?
3. You move the curated sensor files to a new path for better organization. Analysts who queried `vw_sensor_readings` report no breakage, while one analyst who hardcoded the old `abfss://` path is broken. What design principle explains the difference?

<details>
<summary>Answers</summary>

1. Use serverless SQL with `OPENROWSET` — it queries the file in place, costs only for the ~2 GB scanned, and needs no cluster to provision or pay to keep warm. Spark is overkill for a one-off read. — *Match the engine to the task: SQL for ad-hoc reads, Spark for heavy transforms.*
2. With the hierarchical namespace, promoting the staging directory is an atomic metadata rename rather than a copy-and-delete of every file, so the commit is fast and there is no window where consumers see half-moved data. — *Atomic directory rename is the key Gen2 feature enabling safe, fast commits.*
3. The view is an abstraction boundary that hides the physical path; updating its definition keeps consumers working. The hardcoded path coupled the analyst directly to the physical layout, so reorganizing storage broke them. — *An exploration/view layer decouples consumers from physical storage, like an API over a database.*

</details>

## Summary

Data Lake Storage Gen2 is Blob Storage with a hierarchical namespace, and that namespace is what makes atomic commits and directory-level security possible. Give the account a deliberate medallion shape so every byte has a known trust level, then query it in place — serverless SQL to explore, Spark to transform — and wrap a view layer around the governed zones so analysts self-serve without touching paths. You now have a structured, queryable lake; the next module, **Delta Lake and the lakehouse pattern**, adds transactions and time travel so those silver and gold tables become reliable, not just organized.

## Further learning

- [Introduction to Azure Data Lake Storage Gen2](https://learn.microsoft.com/en-us/azure/storage/blobs/data-lake-storage-introduction)
- [Query files using a serverless SQL pool (Azure Synapse Analytics)](https://learn.microsoft.com/en-us/azure/synapse-analytics/sql/query-data-storage)
- [Use OPENROWSET with serverless SQL pool](https://learn.microsoft.com/en-us/azure/synapse-analytics/sql/develop-openrowset)
- [What is Azure Data Lake Storage Gen2 best practices](https://learn.microsoft.com/en-us/azure/storage/blobs/data-lake-storage-best-practices)
