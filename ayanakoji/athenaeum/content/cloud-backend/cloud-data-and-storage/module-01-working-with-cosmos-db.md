---
kind: module
id: cb-c02-m01
vertical: cloud-backend
course_id: cb-c02
title: Working with Azure Cosmos DB
level: intermediate
grounded_on: "AZ-204 skills outline (2026-01-14), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/az-204
synthetic: true
order: 1
prereqs: [cb-c01]
objectives:
  - Perform CRUD operations on Cosmos DB containers and items via the SDK
  - Select an appropriate consistency level for a workload
  - Reason about request units and partitioning when designing a container
---

# Working with Azure Cosmos DB

The team at Meridian Parcel, a fictional same-day courier startup, just moved their delivery-tracking service to Azure and picked Cosmos DB for the NoSQL API because the docs promised single-digit-millisecond reads. A week later the on-call engineer is paged: reads are fine, but a nightly bulk import is throwing `429 Too Many Requests`, and a dashboard that "was working yesterday" sometimes shows a delivery as both *in transit* and *delivered*. Neither symptom is a bug in their code in the usual sense. They are the predictable result of not understanding three things: how Cosmos charges for work, how it spreads data across partitions, and what consistency level they silently accepted. This module gives you that model.

## Learning objectives

By the end of this module you will be able to:

- Perform create, read, replace, upsert, and delete operations on items in a Cosmos DB container using the SDK.
- Explain request units (RUs) and predict why an operation throttles.
- Choose a partition key that distributes load and keeps related reads cheap.
- Select a consistency level that matches a workload's tolerance for stale reads.

## Concepts

### Containers, items, and the partition key

A Cosmos DB database holds **containers**, and a container holds **items** — schemaless JSON documents. The single most consequential decision you make is the container's **partition key**: a property on every item (for example `/customerId`) whose value Cosmos hashes to assign the item to a *logical partition*. All items sharing a partition-key value live together and are co-located on the same *physical partition* behind the scenes.

Think of it like a coat check with many numbered racks. The partition key is the rule that decides which rack a coat goes on. A good rule spreads coats evenly across racks and lets the attendant grab all of one guest's coats from a single rack. A bad rule — say, "all coats from today on rack 1" — creates a hot rack everyone queues behind while the others sit empty. That "hot partition" is exactly what a poorly chosen key produces: throughput is provisioned per physical partition, so a key that funnels writes to one value throttles even when the account has plenty of total capacity. Choose a key with high cardinality and access patterns that mostly stay within one value.

### Request units: the currency of throughput

Every operation costs **request units**. A point read of a 1 KB item costs about 1 RU; writes, queries, and large items cost more. You provision throughput as RUs per second — either manually or with autoscale — at the container or database level. When your consumption exceeds the provisioned RU/s for a partition, Cosmos returns HTTP 429 with a `x-ms-retry-after-ms` header telling you how long to wait.

This reframes "is it fast enough?" into "did I provision enough RU/s, and is my load spread across partitions?" Meridian's nightly import throttled because it fired thousands of writes into one logical partition faster than that partition's share of RU/s allowed. The SDK retries 429s automatically up to a limit, but the durable fixes are to spread writes across partition-key values, raise throughput (autoscale handles spikes), or pace the import.

### Consistency levels and the staleness you accept

Cosmos offers five consistency levels along a spectrum from **strong** to **eventual**, with **bounded staleness**, **session**, and **consistent prefix** in between. Strong guarantees a read always sees the latest committed write but costs more RUs and adds latency, especially across regions. Eventual is cheapest and lowest-latency but a read may return an older value for a while. **Session** — the default — guarantees that *within a single client session* you read your own writes, which is what most request-scoped applications actually need.

Meridian's "in transit and delivered at once" glitch came from a dashboard reading at eventual consistency across two regions during a write. Nothing was corrupt; one replica simply hadn't caught up. Picking session (or bounded staleness with a defined lag) would have made the read-your-writes behavior they assumed they already had explicit.

## Walkthrough: Meridian Parcel's delivery store

You will create a `deliveries` container partitioned by `/customerId`, write a delivery, read it back as a cheap point read, and update its status. The Python SDK (`azure-cosmos`) uses `DefaultAzureCredential`, so no keys live in code — the same credential habit you will carry into cb-c03.

```python
import os
from azure.cosmos import CosmosClient, PartitionKey, exceptions
from azure.identity import DefaultAzureCredential

endpoint = os.environ["COSMOS_ENDPOINT"]  # e.g. https://meridian.documents.azure.com:443/
client = CosmosClient(endpoint, credential=DefaultAzureCredential())

db = client.create_database_if_not_exists("logistics")
container = db.create_container_if_not_exists(
    id="deliveries",
    partition_key=PartitionKey(path="/customerId"),
    offer_throughput=400,  # 400 RU/s minimum for a manual-throughput container
)

# Create an item. The partition-key property must be present on the document.
delivery = {
    "id": "dlv-90187",
    "customerId": "cust-4521",
    "status": "in_transit",
    "destination": "14 Harbour Lane",
}
container.create_item(body=delivery)

# Point read: cheapest possible operation (~1 RU). Needs id AND partition key.
item = container.read_item(item="dlv-90187", partition_key="cust-4521")
print(item["status"])  # in_transit

# Update status with a full replace, then confirm the RU charge.
item["status"] = "delivered"
container.replace_item(item="dlv-90187", body=item)
charge = container.client_connection.last_response_headers["x-ms-request-charge"]
print(f"replace cost {charge} RU")
```

The key thing to observe is that `read_item` requires both the `id` *and* the partition key. Supplying the partition key turns a potentially fan-out query into a single-partition point read — the operation Cosmos is fastest and cheapest at. Reading the `x-ms-request-charge` header after a call is how you measure real cost rather than guessing; build that into your load tests.

## Common pitfalls

- **Choosing a low-cardinality or time-based partition key.** Keys like `/region` (few values) or `/date` (all today's writes on one value) create hot partitions and 429s under load. Prefer a high-cardinality key aligned with your most common query filter.
- **Querying without the partition key.** Omitting the partition key forces a cross-partition query that fans out and costs far more RUs. If you know the value, always pass it.
- **Assuming strong consistency by default.** The account default is session. If two clients in different sessions must see identical data instantly, you need a stronger level — and must budget the extra RUs and latency.
- **Ignoring 429 retry headers.** Treating throttling as a hard failure instead of honoring `retry-after` turns a transient backpressure signal into an outage. Let the SDK retry, and fix the root cause (spread or throughput).
- **Storing huge items.** Items have a maximum size (commonly cited around 2 MB — verify the current limit in the docs). Large blobs belong in Blob Storage with a pointer in Cosmos, which you will build in module 3.

## Knowledge check

1. A container partitioned by `/orderDate` throttles every night at midnight even though total RU/s is barely used. What is the most likely cause and fix?
2. Your service reads an item it wrote one millisecond earlier and sometimes sees the old value. The account uses eventual consistency. Which level fixes this most cheaply?
3. Two point reads of the same 1 KB item report different `x-ms-request-charge` values — one ~1 RU, one ~3 RU. What likely differs between the calls?

<details>
<summary>Answers</summary>

1. The key is time-based, so every write at a given moment lands on one logical partition — a hot partition — exhausting that partition's RU share while others idle. Repartition on a high-cardinality key (e.g. `/customerId`) or spread writes. — RU/s is enforced per partition, not just per account.
2. Session consistency. It guarantees read-your-own-writes within a session at much lower cost than strong. — It targets exactly the monotonic read-your-writes guarantee the workload needs.
3. The cheaper call was a point read (id + partition key); the costlier one likely omitted the partition key and ran a cross-partition query. — Point reads are the cheapest operation; fan-out queries cost more.

</details>

## Summary

Cosmos DB rewards a clear mental model: items live in partitions chosen by your partition key, every operation costs request units, and reads return data at the consistency level you select. Pick a high-cardinality key, pass it on reads, watch the RU charge, and choose session consistency unless you can justify stronger. With CRUD and these trade-offs in hand, the next module turns the writes you just made into an event stream using the **change feed**.

## Further learning

- [Azure Cosmos DB for NoSQL overview](https://learn.microsoft.com/en-us/azure/cosmos-db/nosql/)
- [Partitioning and horizontal scaling in Azure Cosmos DB](https://learn.microsoft.com/en-us/azure/cosmos-db/partitioning-overview)
- [Request units in Azure Cosmos DB](https://learn.microsoft.com/en-us/azure/cosmos-db/request-units)
- [Consistency levels in Azure Cosmos DB](https://learn.microsoft.com/en-us/azure/cosmos-db/consistency-levels)
