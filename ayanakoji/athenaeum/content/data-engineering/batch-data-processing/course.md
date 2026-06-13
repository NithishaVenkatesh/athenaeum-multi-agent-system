---
kind: course
id: de-c02
vertical: data-engineering
course_id: de-c02
title: Batch Data Processing & Pipelines
level: intermediate
grounded_on: "DP-203 skills outline (2024-10-24), paraphrased — original synthetic content; current path Fabric DP-700"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/dp-203
synthetic: true
prereqs: [de-c01]
objectives: []
---

# Batch Data Processing & Pipelines

Most of the data an organization actually reports on does not arrive clean, and it does not arrive once. It lands in files and tables on a schedule — nightly exports, hourly drops, a vendor feed that shows up whenever the vendor feels like it — and someone has to turn that raw arrival into trustworthy, query-ready tables. This course teaches you to be that someone. You will learn to transform data at scale with Apache Spark, express set-based transformations in T-SQL inside a Synapse SQL pool, orchestrate the whole thing as scheduled pipelines, and make those pipelines reliable enough to run unattended.

## Who this is for

You are a data engineer or analytics engineer who can already navigate a data lake and a relational warehouse, and now needs to own the *processing* layer between them. The course assumes you have completed **Data Storage & Lakehouse Design** (de-c01) — you should be comfortable with the difference between a lake and a warehouse, with file formats like Parquet and Delta, and with the medallion (bronze/silver/gold) idea. You write SQL daily and can read Python without flinching. If you have ever been paged because a report was wrong and the cause turned out to be a duplicated batch or a silent type coercion upstream, this course is aimed squarely at you.

## What you'll be able to do

- Cleanse, deduplicate, and reshape large datasets with Spark DataFrame transformations
- Choose between Spark and T-SQL for a given transformation and justify the choice
- Write efficient set-based T-SQL and load data into a dedicated SQL pool the right way
- Shred JSON and handle encoding so semi-structured data becomes relational
- Build, schedule, version, and trigger pipelines in Azure Data Factory or Synapse Pipelines
- Design incremental loads and upserts that are restartable, validated, and safe to re-run

## Module path

This course is four sequential modules; each builds on the last.

1. **Ingest and transform with Apache Spark** — cleanse, dedupe, and reshape raw data into a tidy table.
2. **Transforming with T-SQL and Synapse** — express the same intent as set-based SQL and load it efficiently.
3. **Orchestrating pipelines with Data Factory** — wrap your transforms in scheduled, versioned, triggerable pipelines.
4. **Incremental loads, upserts, and error handling** — make the whole thing incremental, idempotent, and robust to failure.

## Prerequisites

You need **Data Storage & Lakehouse Design** (de-c01) or equivalent experience: a working mental model of lakes versus warehouses, of columnar file formats, and of layered (medallion) storage. You should be able to read and write intermediate SQL and follow Python. No prior Spark or Data Factory experience is required — both are introduced from first principles here, but at a pace that assumes engineering maturity. You will get the most out of the walkthroughs if you have access to a Synapse or Fabric workspace where you can run a Spark notebook and a dedicated SQL pool, though you can also read the code and reason about it without an environment.

## How this fits the bigger picture

Storage (de-c01) gives you somewhere to put data; this course gives you the machinery to *move and refine* it. Spark and SQL pools are the two engines you will reach for again and again — Spark when the work is row-by-row or schema is messy, set-based T-SQL when the data is already relational and the warehouse is closer. Data Factory and Synapse Pipelines are the conductor that runs both on a schedule and recovers when a run fails. The skills here are grounded in the DP-203 data-processing domain; the same patterns carry forward almost unchanged into Microsoft Fabric, where the engines are rebadged but the engineering judgement is identical. Master batch first: it is forgiving, observable, and the foundation that streaming and orchestration both rest on.
