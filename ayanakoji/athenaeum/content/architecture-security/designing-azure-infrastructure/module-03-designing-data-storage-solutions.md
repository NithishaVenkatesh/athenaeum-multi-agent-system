---
kind: module
id: as-c01-m03
vertical: architecture-security
course_id: as-c01
title: Designing data storage solutions
level: foundational
grounded_on: "AZ-305 skills outline (2026-04-17), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/az-305
synthetic: true
order: 3
prereqs: [as-c01-m01]
objectives:
  - Recommend a store for relational, semi-structured, and unstructured data
  - Recommend a database service tier and compute tier for a workload
  - Balance features, performance, and cost across access tiers and redundancy options
---

# Designing data storage solutions

Solstice Tickets is now generating three very different kinds of data, and the team wants to put all of it in one database "to keep things simple." That instinct is a trap. There are normalized financial records that demand transactions and joins; a stream of clickstream events with a loose, evolving shape and global readers; and millions of uploaded venue photos and ticket PDFs that are just bytes. Forcing all three into a single relational engine means overpaying for the photos, fighting the schema for the clickstream, and still not getting global low-latency reads. This module teaches you to match each data shape to the store built for it — and to choose the tier and redundancy that keep the bill honest.

## Learning objectives

By the end of this module you will be able to:

- Recommend a store for relational, semi-structured, and unstructured data based on access pattern.
- Choose a database service tier and compute model appropriate to the load.
- Select blob access tiers and redundancy options to balance durability, performance, and cost.
- Express a storage recommendation as a decision matrix tied to requirements.

## Concepts

### Match the store to the data shape and access pattern

Storage selection is driven by two things: the *shape* of the data and how it is *accessed*.

**Relational data** has a fixed schema, relationships, and a need for multi-row transactions and joins — think orders, invoices, and ledger entries where correctness is non-negotiable. **Azure SQL Database** (or SQL Managed Instance for closer SQL Server parity) is the default, with PostgreSQL and MySQL flavors available when the app or team prefers them. The signal is: you need ACID transactions and you query by relationships.

**Semi-structured data** has a shape that varies between records or evolves over time — JSON documents, event payloads, user profiles with optional fields. **Azure Cosmos DB** is the document/NoSQL choice, and its distinguishing feature is **turnkey global distribution** with single-digit-millisecond reads and a tunable consistency model. The signal is: schema flexibility, high write throughput, or geographically distributed low-latency access.

**Unstructured data** is opaque bytes — images, video, PDFs, backups, logs. **Azure Blob Storage** stores these cheaply and serves them at scale; it is emphatically *not* where you put a row you need to query relationally. The signal is: you store and retrieve whole objects by key and rarely query their internals.

The Solstice mapping falls out immediately: financial records → Azure SQL Database; clickstream and profiles → Cosmos DB; photos and PDFs → Blob Storage. One workload, three stores, each cheaper and better at its job than a single forced choice.

### Tiers: pay for the performance and freshness you need, not more

Within a store, *tiers* let you trade cost against performance and access frequency.

For **Azure SQL Database**, the headline choice is the purchasing model and compute tier. The **vCore** model with **provisioned** compute suits steady, predictable load; **serverless** compute autoscales and can pause during inactivity, which fits intermittent or dev/test databases that would otherwise pay for idle capacity. The architectural move mirrors the compute module: predictable load favors provisioned, bursty or idle-prone load favors serverless. (Specific vCore ranges and auto-pause delays change — verify current values in the docs.)

For **Blob Storage**, the **access tier** trades retrieval cost and latency against storage cost. **Hot** is cheapest to read and most expensive to store — for actively served content like recent venue photos. **Cool** lowers storage cost for data accessed infrequently. **Cold** and **Archive** push storage cost lower still for rarely or almost-never accessed data, with Archive requiring a rehydration step (and delay) before you can read an object. Old ticket PDFs from concluded events belong in Cool or Archive; this week's photos belong in Hot.

### Redundancy is a durability-and-availability decision, not a default

Every storage account has a **redundancy** setting that determines how many copies exist and where. **Locally redundant storage (LRS)** keeps copies within one datacenter — cheapest, but a regional disaster loses the data. **Zone-redundant storage (ZRS)** spreads copies across availability zones in one region, surviving a datacenter failure. **Geo-redundant storage (GRS)** also replicates to a paired secondary region, surviving a regional outage. Each step up costs more and buys more resilience. The discipline is to set redundancy from the data's *value and recovery requirements*, not to accept a default: Solstice's irreplaceable financial backups warrant geo-redundancy; easily regenerated thumbnails may be fine on LRS.

## Walkthrough: provisioning tiered, redundant storage for Solstice

Two storage requirements are concrete. First, ticket PDFs are served hot for two weeks and then almost never read — they should land in Hot and age into Cool to cut cost. Second, the account holding them must survive a regional outage, so it needs geo-redundancy. Capture this as a decision matrix, then make it real.

```text
Data                  Store              Tier / model        Redundancy  Why
--------------------  -----------------  ------------------  ----------  --------------------------------
Financial records     Azure SQL DB       vCore, provisioned  (HA in DB)  ACID, joins, steady load
Clickstream/profiles  Cosmos DB          autoscale RU/s      multi-region flexible schema, global reads
Recent ticket PDFs    Blob (Hot)         Hot                 GRS         actively served, must survive region loss
Aged ticket PDFs      Blob (Cool)        Cool                GRS         rarely read; cheaper storage
```

Now provision the geo-redundant blob account and set a default access tier with `az`:

```bash
# Geo-redundant storage account, default access tier Hot.
az storage account create \
  --name solsticeticketpdfs \
  --resource-group solstice-prod-rg \
  --location eastus \
  --sku Standard_GRS \
  --kind StorageV2 \
  --access-tier Hot

# Move a concluded event's PDFs to Cool to cut storage cost.
az storage blob set-tier \
  --account-name solsticeticketpdfs \
  --container-name event-2025-spring \
  --name finals/ticket-88231.pdf \
  --tier Cool
```

`--sku Standard_GRS` encodes the "survive a regional outage" requirement directly into the account, and `--access-tier Hot` sets the default for newly written blobs that are being actively served. The `set-tier` call demonstrates the lifecycle move by hand — in production you would automate this with a lifecycle management policy that ages blobs from Hot to Cool to Archive on a schedule rather than touching each blob, but the tier transition is the same decision made declaratively.

## Common pitfalls

- **Forcing every data shape into one engine.** A relational database is a poor and costly home for opaque media or schema-fluid event payloads. Match each shape to its store; "one database to keep it simple" is rarely simpler or cheaper at scale.
- **Storing query-able data in Blob Storage.** Blobs are retrieved by key, not queried by attribute. If you need to filter or join, you need a database, not a container of JSON files.
- **Accepting the default redundancy.** LRS will not survive a regional disaster. Set redundancy from the data's recovery requirements; do not discover the gap during an outage.
- **Leaving cold data in the Hot tier.** Storing rarely read PDFs in Hot wastes money every month. Conversely, putting actively served content in Archive incurs rehydration delays on every read. Tier follows access frequency.
- **Over-provisioning a database that sits idle.** A dev or intermittent database on always-on provisioned compute pays for capacity it does not use; serverless compute that auto-pauses fits that pattern better.

## Knowledge check

1. An app stores user profiles whose fields vary by account type, needs very high write throughput, and serves readers on three continents with low latency. Which store fits, and what single capability makes it the right choice?
2. A finance team's audit backups are irreplaceable and must survive the loss of an entire Azure region. Which redundancy option meets that requirement, and why is LRS insufficient?
3. Ticket PDFs are read heavily for two weeks, then almost never. What blob lifecycle approach minimizes cost while keeping recent ones fast, and what is the catch with the very cheapest tier?

<details>
<summary>Answers</summary>

1. Azure Cosmos DB; its turnkey global distribution with low-latency, multi-region reads (plus schema flexibility for the varying fields) is the capability a single-region relational database cannot match.
2. Geo-redundant storage (GRS), which replicates to a paired secondary region; LRS keeps all copies in one datacenter and would lose the data in a regional disaster.
3. Serve them from Hot, then age them to Cool (and eventually Archive) via a lifecycle policy; the catch is that Archive requires rehydration before an object can be read, adding latency, so it suits truly cold data only.

</details>

## Summary

Storage design is pattern-matching: relational data with transactions goes to Azure SQL, schema-fluid or globally distributed data goes to Cosmos DB, and opaque bytes go to Blob Storage — and within each, tiers and redundancy let you pay only for the performance and durability the data actually requires. Setting those knobs from requirements rather than defaults is what keeps a design both resilient and affordable. With compute placed, the network designed, and data homed correctly, the final module, *Designing application architecture*, connects these pieces with messaging, events, caching, and API integration into one coherent system.

## Further learning

- [Choose a data store for your Azure application](https://learn.microsoft.com/en-us/azure/architecture/guide/technology-choices/data-store-decision-tree)
- [Azure Storage redundancy](https://learn.microsoft.com/en-us/azure/storage/common/storage-redundancy)
- [Hot, cool, cold, and archive access tiers for blob data](https://learn.microsoft.com/en-us/azure/storage/blobs/access-tiers-overview)
- [Azure SQL Database purchasing models](https://learn.microsoft.com/en-us/azure/azure-sql/database/purchasing-models)
