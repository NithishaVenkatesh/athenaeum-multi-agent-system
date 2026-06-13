---
kind: course
id: de-c03
vertical: data-engineering
course_id: de-c03
title: Real-Time Analytics & Streaming
level: advanced
grounded_on: "DP-203 skills outline (2024-10-24), paraphrased — original synthetic content; current path Fabric DP-700"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/dp-203
synthetic: true
prereqs: [de-c01, de-c02]
objectives: []
---

# Real-Time Analytics & Streaming

Most data work assumes the data is already at rest: a table, a file, a lake. Streaming inverts that assumption. The data is in motion, it never ends, and the question is no longer "what happened" but "what is happening right now, and what does it mean for the next decision in the next few seconds." This course teaches you to build pipelines that ingest events the moment they are produced, transform them in flight, aggregate them over time correctly, and land trustworthy results in a sink — without losing data when a node dies or a producer floods you. You will work across the three tools that carry most real-time workloads on Azure: Azure Event Hubs for ingestion, Azure Stream Analytics for SQL-style stream processing, and Apache Spark Structured Streaming for code-first processing into a lakehouse.

## Who this is for

You are a data engineer who is comfortable with batch pipelines and the lakehouse pattern, and you now need to handle data that arrives continuously. This course assumes you have completed **Data Ingestion & Transformation** (de-c01) and **Data Storage & the Lakehouse** (de-c02), so you already know how to move data with pipelines, work with partitioned storage, and read and write Delta tables. What you have not yet done is reason about *unbounded* data, event time versus processing time, and the failure modes that only appear when a job runs forever.

## What you'll be able to do

- Stand up an end-to-end ingestion-and-processing path with Event Hubs and Stream Analytics.
- Reason about throughput, partitions, and ordering so a pipeline scales without reshuffling correctness.
- Process unbounded data with Spark Structured Streaming and write the results to Delta exactly once.
- Handle schema drift in a stream without breaking the running job.
- Aggregate over time using tumbling, hopping, and session windows, and decide when each fits.
- Configure watermarking and checkpoints so late data is handled and a restarted job resumes cleanly.
- Monitor a streaming job's health, diagnose backlog and lag, and scale resources to clear it.

## Module path

This course is four sequential modules; each builds on the last.

1. **Stream processing with Stream Analytics and Event Hubs** — ingest events, process them, and deliver to a sink reliably.
2. **Spark structured streaming** — process unbounded data as code, handle schema drift, and write to Delta.
3. **Windowing, watermarking, and time** — aggregate over time correctly and tame late-arriving data.
4. **Monitoring, scaling, and optimization** — keep a long-running pipeline healthy and cost-effective.

## Prerequisites

You should have completed **Data Ingestion & Transformation** (de-c01) and **Data Storage & the Lakehouse** (de-c02), or have equivalent experience: building data pipelines, working with partitioned object storage, and reading and writing Delta Lake tables. You should be comfortable reading Python and SQL. No prior streaming experience is assumed — the first module introduces the mental model from the ground up — but a working knowledge of Spark DataFrames will make the second module faster.

## How this fits the bigger picture

Real-time analytics is rarely a standalone system; it sits beside the batch lakehouse you built in earlier courses. A common shape is the streaming layer landing fresh events into the same Delta tables your batch jobs curate, so dashboards see recent data within seconds while history stays consistent. The skills here — partitioned ingestion, event-time correctness, watermarking, and operational monitoring — are the load-bearing parts of that architecture. Note that the certification landscape is shifting: the DP-203 concepts this course is grounded on now live largely inside Microsoft Fabric and the DP-700 path, but the underlying engines (Event Hubs, Stream Analytics, and Spark) and the reasoning about time and throughput carry over directly. Verify current product names and limits in the docs, but the way you think about a moving dataset does not change.
