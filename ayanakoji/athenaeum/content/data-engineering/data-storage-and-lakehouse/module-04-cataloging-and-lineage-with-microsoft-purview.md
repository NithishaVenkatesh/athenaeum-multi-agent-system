---
kind: module
id: de-c01-m04
vertical: data-engineering
course_id: de-c01
title: Cataloging and lineage with Microsoft Purview
level: foundational
grounded_on: "DP-203 skills outline (2024-10-24), paraphrased — original synthetic content; current path Fabric DP-700"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/dp-203
synthetic: true
order: 4
prereqs: [de-c01-m03]
objectives:
  - Browse and search metadata in a data catalog to discover datasets
  - Push data lineage to Microsoft Purview from a pipeline
  - Use cataloging and lineage to support governance and trust
---

# Cataloging and lineage with Microsoft Purview

Northwind Telemetry now has a well-partitioned, zoned, transactional lakehouse — and a new problem of success. There are hundreds of tables across bronze, silver, and gold. A finance analyst spends a morning asking three engineers "is there a table with daily moisture by region, and can I trust it?" Worse, when a regulator asks "where did the number in this compliance report come from?", nobody can answer with confidence — the report reads a gold table that derives from a silver table that derives from a bronze drop, and that chain lives only in people's heads. A data estate you can't *discover* or *trace* is a liability. Microsoft Purview is the governance layer that turns the lake into a searchable, traceable, trustworthy asset.

## Learning objectives

By the end of this module you will be able to:

- Register and scan data sources so their metadata is searchable in the data catalog.
- Browse and search the catalog to discover datasets and understand them before querying.
- Push data lineage to Purview so transformations are traceable end to end.
- Explain how cataloging and lineage underpin governance, trust, and compliance.

## Concepts

### What a data catalog is, and why metadata is the product

A data catalog is a searchable inventory of your data assets and everything *about* them — names, schemas, owners, descriptions, classifications, and where each fits in the data flow. The key insight is that the catalog stores **metadata, not data**. Purview never copies your sensor readings; it records that a dataset called `gold/daily_moisture_by_region` exists at a given path, has these columns and types, is owned by the analytics team, and contains no sensitive fields. That metadata is the product, because the expensive problem in a large estate is not storing data — it's *finding the right data and knowing whether to trust it*.

Purview populates this inventory by **scanning** registered sources. You register a source (a Data Lake Storage Gen2 account, a SQL database, a Power BI tenant), point a scan at it, and Purview reads the structure — files, folders, tables, columns — and writes the metadata into the catalog. Scans run on a schedule, so the catalog stays current as the lake grows. Scanning can also run automatic **classification**, tagging columns that look like email addresses, government IDs, or other sensitive patterns, which is the foundation of governance and compliance reporting.

### Discovery: search and browse

Once scanned, assets are discoverable two ways. **Search** is keyword-driven: the finance analyst types "moisture daily region," and Purview returns matching tables ranked by relevance, each with its schema, owner, and description. **Browse** is structure-driven: you navigate the catalog by source and hierarchy, the way you'd browse a file tree, to see everything in the gold zone of the Northwind account. Good discovery depends on good metadata — a glossary of business terms, owner assignments, and human-written descriptions turn a list of cryptic table names into something a non-engineer can self-serve from. The catalog only repays the effort you put into curating it; an unannotated catalog is a directory listing, while a curated one answers "what should I use, and can I trust it?" without a human in the loop.

### Lineage: the chain of custody for data

**Lineage** is the recorded map of how data flows: which sources feed which transformations, which produce which outputs. In Purview, lineage appears as a graph — `bronze/sensor_drop` → (Spark transform) → `silver/sensor_readings_delta` → (aggregation) → `gold/daily_moisture_by_region` → (Power BI) → the compliance report. This is the regulator's answer made visual and auditable.

Lineage matters for three concrete jobs. **Impact analysis:** before you change or drop a table, lineage shows everything downstream that would break. **Root-cause analysis:** when a gold number looks wrong, you trace upstream to find which source or transform introduced the error. **Compliance and trust:** you can prove, not assert, where a reported figure originated. Some lineage is captured automatically when you run transformations through systems Purview integrates with (such as Data Factory or Synapse pipelines); for custom processing, you push lineage explicitly via the Purview APIs, registering the process and its input and output assets. The principle to internalize: lineage is only complete if *every* transformation reports it — one un-instrumented script creates a blind spot in the chain.

### How cataloging supports governance

Cataloging, classification, and lineage together form the governance backbone. Classification tells you *where* sensitive data lives; ownership and glossary terms tell you *who is accountable* and *what things mean*; lineage tells you *how data moves and what depends on it*. Governance is not a separate product bolted on at the end — it is what these metadata capabilities enable. A governed estate is one where any analyst can find a trustworthy dataset, any engineer can assess the blast radius of a change, and any auditor can trace a number to its source.

## Walkthrough: cataloging and tracing Northwind's lakehouse

You will register the Gen2 account as a source, then push lineage for the custom Spark job that builds the gold aggregate, so the regulator's "where did this come from?" has a recorded answer. Source registration and scanning are typically done in the Purview governance portal; the lineage push below uses the Purview Data Map (Atlas) REST API from Python for a custom transform that isn't captured automatically.

```python
import requests
from azure.identity import DefaultAzureCredential

# DefaultAzureCredential resolves a managed identity in Azure or your
# az-login locally — no secrets in code.
credential = DefaultAzureCredential()
token = credential.get_token("https://purview.azure.net/.default").token
ATLAS = "https://nw-purview.purview.azure.com/datamap/api/atlas/v2"
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# Register a "Process" entity linking the silver input to the gold output.
# Purview draws the lineage edge from inputs -> outputs for this process.
process = {
    "entities": [{
        "typeName": "Process",
        "attributes": {
            "qualifiedName": "nw://jobs/build_daily_moisture_by_region",
            "name": "build_daily_moisture_by_region",
            "inputs": [{
                "typeName": "azure_datalake_gen2_path",
                "uniqueAttributes": {
                    "qualifiedName": "https://nwtelemetry.dfs.core.windows.net/silver/sensor_readings_delta"
                }
            }],
            "outputs": [{
                "typeName": "azure_datalake_gen2_path",
                "uniqueAttributes": {
                    "qualifiedName": "https://nwtelemetry.dfs.core.windows.net/gold/daily_moisture_by_region"
                }
            }],
        },
    }]
}

resp = requests.post(f"{ATLAS}/entity/bulk", headers=headers, json=process, timeout=30)
resp.raise_for_status()
print("lineage process registered:", resp.json().get("guidAssignments"))
```

After this call, opening `daily_moisture_by_region` in the Purview portal shows a lineage graph with an edge back to `sensor_readings_delta` via the named process. (Endpoint paths and entity type names evolve across Purview API versions — confirm the current API version and `typeName` values in the docs before relying on them.) The regulator's question is now answered by a click, not a meeting: the gold figure traces to silver, which the catalog already links back to the bronze drop. Run this push as a step in the same job that builds the table, so lineage is recorded every time the data moves.

## Common pitfalls

- **Treating the catalog as auto-magic.** Scanning populates schemas and names, but discoverability depends on humans adding descriptions, owners, and glossary terms. An unannotated catalog is just a directory listing.
- **Incomplete lineage from un-instrumented jobs.** Pipelines run through integrated services may report lineage automatically, but custom scripts won't unless you push it. One un-instrumented step breaks the chain and creates a blind spot exactly where auditors look.
- **Stale catalog from one-off scans.** A lake grows daily; a catalog scanned once is wrong within a week. Schedule recurring scans so metadata tracks reality.
- **Over-scanning sensitive sources without controls.** Scans can read structure and sample data for classification; point them at sources you're authorized to inspect and scope credentials with least privilege.
- **Confusing classification with protection.** Purview *finds and labels* sensitive data; it doesn't by itself encrypt or restrict it. Classification informs the controls you must still apply at the storage and access layers.

## Knowledge check

1. A finance analyst can't find a table they're sure exists, even though Purview scanned the account. The schema and name are correct in the catalog. What is the most likely reason discovery is failing, and how do you fix it?
2. An automated Data Factory pipeline shows full lineage, but a gold table built by a custom Spark script shows no upstream connection. Why, and what's the remedy?
3. Before dropping a silver table, you want to know what would break. Which Purview capability answers this, and what is it called?

<details>
<summary>Answers</summary>

1. Discovery likely fails because the asset lacks descriptions, glossary terms, or business-friendly metadata, so keyword search doesn't surface it for the analyst's terms. Curate the asset with an owner, a clear description, and glossary terms. — *The catalog only repays the metadata you curate; scanning alone gives names, not findability.*
2. The custom script doesn't run through a Purview-integrated service, so lineage isn't captured automatically. Push lineage explicitly via the Purview Data Map API as a step in the job, registering the process with its input and output assets. — *Lineage is complete only if every transformation reports it.*
3. Lineage, used for impact analysis — tracing downstream from the table to see every dataset, report, and process that depends on it. — *Lineage is the chain of custody that reveals the blast radius of a change.*

</details>

## Summary

Microsoft Purview turns a sprawling lakehouse into a governed asset by managing metadata: scanning registered sources into a searchable catalog, classifying sensitive data, and recording lineage that traces every number to its origin. Discovery depends on curation, and lineage depends on every transformation reporting itself — including the custom jobs you must instrument by hand. With cataloging and lineage in place, Northwind's estate is now discoverable, traceable, and trustworthy, completing the storage foundation: partitioned for speed, zoned for clarity, transactional for reliability, and governed for trust. From here, the Batch Data Processing & Pipelines course builds the transformations that move data through this foundation at scale.

## Further learning

- [What is Microsoft Purview?](https://learn.microsoft.com/en-us/purview/purview)
- [Data lineage in the Microsoft Purview Data Catalog](https://learn.microsoft.com/en-us/purview/concept-data-lineage)
- [Connect to and manage Azure Data Lake Storage Gen2 in Microsoft Purview](https://learn.microsoft.com/en-us/purview/register-scan-adls-gen2)
- [Microsoft Purview Data Map REST API reference](https://learn.microsoft.com/en-us/rest/api/purview/datamapdataplane/entity)
