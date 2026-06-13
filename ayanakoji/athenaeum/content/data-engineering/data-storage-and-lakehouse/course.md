---
kind: course
id: de-c01
vertical: data-engineering
course_id: de-c01
title: Data Storage & Lakehouse Design
level: foundational
grounded_on: "DP-203 skills outline (2024-10-24), paraphrased — original synthetic content; current path Fabric DP-700"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/dp-203
synthetic: true
prereqs: []
objectives: []
---

# Data Storage & Lakehouse Design

Before a single transformation runs or a dashboard loads, someone decides where the data lives and how it is laid out on disk. That decision quietly governs every query cost and pipeline runtime that follows, and it is the part of a platform that is most painful to change once data has accumulated. This course teaches you to design the storage foundation of an analytics platform on Azure — how to partition data so scans stay cheap, how to organize Azure Data Lake Storage Gen2 so analysts and engineers can find what they need, how to get reliable ACID tables on top of cheap object storage with Delta Lake, and how to make the whole estate discoverable and trustworthy with a data catalog. You will finish able to make these decisions deliberately rather than discovering their consequences months later in a slow query or an untraceable report.

## Who this is for

You are an early-career data engineer, an analytics engineer, or a backend developer moving into data work. You can read and write SQL, you are comfortable on a command line, and you have seen Python before — but you have not yet owned the storage layout of a production data platform. No prior Azure data experience is assumed; this is the entry point for the Data Engineering & Analytics vertical, and later courses (Batch Data Processing & Pipelines, Real-Time Analytics & Streaming) build directly on the lakehouse you learn to design here.

## What you'll be able to do

- Design a partition strategy for files, analytical tables, and streaming sinks that avoids small-file and skew problems.
- Lay out a Data Lake Storage Gen2 account into zones that serve both ad-hoc exploration and governed production reads.
- Query lake data with serverless SQL and Spark, and decide which engine fits which question.
- Build Delta Lake tables that give you ACID transactions, schema enforcement, time travel, and the ability to revert a bad load.
- Register data in Microsoft Purview so colleagues can discover datasets and trace lineage from source to report.

## Module path

This course is four sequential modules; each builds on the last.

1. **Partition strategies for analytical data** — choose a layout that keeps scans cheap and avoids the small-file trap.
2. **Data Lake Storage Gen2 and the exploration layer** — structure a lake and query it with serverless SQL and Spark.
3. **Delta Lake and the lakehouse pattern** — add ACID tables, schema enforcement, and time travel over object storage.
4. **Cataloging and lineage with Microsoft Purview** — make the lake discoverable, governable, and trustworthy.

## Prerequisites

None — this is an entry point for the vertical. You should be comfortable reading SQL, navigating a shell, and reading short Python or PySpark snippets. An Azure subscription with permission to create a storage account and a Spark or serverless SQL compute resource will let you follow the walkthroughs hands-on, but the concepts stand on their own.

## How this fits the bigger picture

Storage design is the part of data engineering that is hardest to change later: once terabytes are written in a bad layout, reorganizing them is a project, not a tweak. Getting the foundation right — partitioning, zoning, transactional tables, and a catalog — is what lets the batch pipelines and streaming jobs in the rest of this vertical run fast and stay correct. The lakehouse pattern you learn here, cheap object storage plus a transactional table format plus a governance layer, is the architecture that underpins Azure Databricks, Azure Synapse Analytics, and Microsoft Fabric alike. Master it once and the same mental model carries across every modern Azure analytics service you will touch.
