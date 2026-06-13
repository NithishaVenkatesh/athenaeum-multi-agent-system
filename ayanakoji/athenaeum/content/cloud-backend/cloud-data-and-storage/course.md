---
kind: course
id: cb-c02
vertical: cloud-backend
course_id: cb-c02
title: Cloud Data & Storage for Developers
level: intermediate
grounded_on: "AZ-204 skills outline (2026-01-14), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/az-204
synthetic: true
prereqs: [cb-c01]
objectives: []
---

# Cloud Data & Storage for Developers

A cloud application is only as good as the data layer underneath it. Compute scales, requests come and go, but state has to live somewhere durable, queryable, and affordable. This course teaches you to make the two storage choices that sit behind most Azure backends — a globally distributed document database in Azure Cosmos DB and an object store in Azure Blob Storage — and to use their SDKs the way a production engineer does, not the way a "hello world" tutorial does. You will learn how request units, partitioning, consistency, change feeds, access tiers, and lifecycle policies actually behave, so that your design survives both a traffic spike and an invoice review. The throughline is deliberate: structured records belong in Cosmos DB, large opaque payloads belong in Blob Storage, and a thin pointer connects the two — a separation that keeps reads cheap and the data layer easy to reason about.

## Who this is for

You are a backend developer who can already stand up compute on Azure and now needs to wire durable state behind it. We assume you have completed **Azure Compute & Serverless Foundations** (cb-c01) — you can deploy a web API to App Service, write an Azure Function, and reason about scaling and configuration. You are comfortable in Python or C# and have used a REST API and an SDK before. You do not need prior Cosmos DB or Blob Storage experience; we build that here.

## What you'll be able to do

- Perform create, read, update, and delete operations on Cosmos DB containers and items through the SDK, with correct partition-key handling.
- Choose a consistency level that matches a workload's tolerance for staleness, and explain the cost trade-off.
- Build event-driven flows that react to data changes using the Cosmos DB change feed, with idempotent consumers.
- Store, retrieve, and tag unstructured data in Blob Storage, and select access tiers for the right cost-versus-latency balance.
- Automate retention, tiering, and expiry with lifecycle management policies instead of hand-written cleanup jobs.

## Module path

This course is four sequential modules; each builds on the last.

1. **Working with Azure Cosmos DB** — Container and item operations through the SDK, request units, partitioning, and choosing a consistency level.
2. **Reacting to data with the change feed** — Turning writes into an event stream and building idempotent, restartable consumers.
3. **Azure Blob Storage with the SDK** — Object operations, properties, and metadata for unstructured data, plus access-tier selection.
4. **Data lifecycle and storage policies** — Automating tiering, expiry, and protection so storage stays cheap and compliant.

## Prerequisites

Completion of **Azure Compute & Serverless Foundations** (cb-c01), or equivalent experience deploying and operating Azure compute. You should be able to read Python or C#, authenticate to Azure with a credential, and use the Azure CLI. No prior NoSQL or object-storage background is required; the course introduces both Cosmos DB and Blob Storage from first principles and builds up to production patterns.

## How this fits the bigger picture

Compute and storage are the two halves of a cloud backend; cb-c01 gave you the first half and this course gives you the second. The patterns here — partition-aware writes, consistency trade-offs, change-driven processing, and policy-based lifecycle — recur in nearly every Azure system you will build. The next course in this vertical, **Securing & Integrating Cloud Applications** (cb-c03), layers identity, secrets, and messaging on top of the data layer you build here, so the credential and connection habits you form now carry forward directly. By the end of this course you will reason about data on Azure the way an experienced engineer does: in terms of throughput you pay for, boundaries you partition along, and policies you let the platform enforce.
