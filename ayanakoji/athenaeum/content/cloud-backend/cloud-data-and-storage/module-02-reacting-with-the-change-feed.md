---
kind: module
id: cb-c02-m02
vertical: cloud-backend
course_id: cb-c02
title: Reacting to data with the change feed
level: intermediate
grounded_on: "AZ-204 skills outline (2026-01-14), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/az-204
synthetic: true
order: 2
prereqs: [cb-c02-m01]
objectives:
  - Implement change feed notifications that react to item writes
  - Design idempotent, restartable change-feed consumers
  - Compare the change feed with polling for freshness and cost
---

# Reacting to data with the change feed

Meridian Parcel now stores every delivery in the `deliveries` container you built in **Working with Azure Cosmos DB**. Marketing wants a text message sent the moment a parcel flips to `delivered`, and analytics wants each status change copied into a reporting store. The first instinct is a cron job that queries the container every minute for recently changed rows. That approach is expensive (it burns RUs scanning for changes that mostly aren't there), laggy (up to a minute behind), and fragile (it misses changes if two happen within a poll window and it has to track "what did I already see?" by hand). Cosmos DB already records every write in order; you just need to read that log. That log is the **change feed**, and learning to consume it correctly is what this module is about.

## Learning objectives

By the end of this module you will be able to:

- Explain what the change feed captures and the order it guarantees.
- Implement a change-feed consumer using the change feed processor model.
- Design consumers that are idempotent and survive restarts without losing or double-processing changes.
- Decide when the change feed beats polling and what it does not do.

## Concepts

### What the change feed is, and what it is not

The change feed is a persistent, ordered record of creates and updates to items in a container, exposed per logical partition in the order the writes happened. When you process it, you receive each changed item; you do not have to scan the whole container or compare timestamps yourself. Crucially, in its standard mode it surfaces only the **latest version** of each changed item — if an item is updated three times before you read, you see the final state once, not three intermediate versions. It also does **not** emit deletes in that mode. The common workaround is a *soft delete*: set a `deleted: true` flag (often with a short time-to-live), so the deletion shows up as an update you can react to.

Think of it as the database's outbox. Every committed write drops a copy in the outbox; your consumer empties the outbox in order and never has to ask "anything new?" by polling.

### The change feed processor and leases

You rarely read the raw feed yourself. The SDK provides a **change feed processor** that does the hard parts: it distributes the container's partitions across however many consumer instances you run, tracks how far each has read, and rebalances when instances come and go. It records that progress in a separate **lease container** — a small Cosmos container holding one lease document per partition range, each storing a continuation token (a bookmark).

This is why restarts are safe. If a consumer crashes, the lease still holds the last acknowledged position; a new instance picks up the lease and resumes from the bookmark rather than from the beginning or from "now." It is also how you scale: run more instances and the processor spreads leases across them. Run one and it holds them all. The lease container is the durable memory that makes the whole pattern reliable, so it must not be deleted or shared between unrelated processors.

### Idempotency and at-least-once delivery

The change feed gives **at-least-once** delivery. After a crash or rebalance, the processor may redeliver a change it had started but not finished acknowledging. Therefore every consumer must be **idempotent**: processing the same change twice must produce the same result as processing it once. Sending two identical SMS messages, or double-incrementing a counter, is a real failure mode here.

The fix is to make the effect safe to repeat. Use the item's `id` plus a version (Cosmos exposes an `_etag` and a per-item `_ts`) as a deduplication key, record "already processed change X" in your sink, and skip duplicates. For external side effects like sending a message, write a "notified" marker before or atomically with the send so a redelivery is a no-op. Design for redelivery and the at-least-once guarantee becomes a non-issue.

## Walkthrough: notifying on delivered parcels

Meridian wants to react when a delivery's status becomes `delivered`. You will register a change feed processor against the `deliveries` container, using a `leases` container for progress, and process each batch idempotently.

```python
import os
from azure.cosmos import CosmosClient, PartitionKey
from azure.identity import DefaultAzureCredential

client = CosmosClient(os.environ["COSMOS_ENDPOINT"], credential=DefaultAzureCredential())
db = client.create_database_if_not_exists("logistics")
monitored = db.get_container_client("deliveries")

# A dedicated lease container stores per-partition continuation bookmarks.
leases = db.create_container_if_not_exists(
    id="leases", partition_key=PartitionKey(path="/id")
)

# Stand-in for a durable sink that remembers what we've already acted on.
already_notified = set()

def handle_changes(changes):
    for item in changes:
        if item.get("status") != "delivered":
            continue
        # Idempotency key: item id + version. Skip if seen before.
        dedupe_key = (item["id"], item["_etag"])
        if dedupe_key in already_notified:
            continue
        send_sms(item["customerId"], f"Parcel {item['id']} delivered.")
        already_notified.add(dedupe_key)

def send_sms(customer_id, message):
    print(f"-> SMS to {customer_id}: {message}")

# Read changes from the start; the processor advances the lease as it goes.
for item in monitored.query_items_change_feed(start_time="Beginning"):
    handle_changes([item])
```

This sample uses the SDK's pull-model `query_items_change_feed` to keep the example self-contained and runnable; in a hosted service you would typically wire the same `handle_changes` logic into a Cosmos DB trigger on an Azure Function (the binding you met in cb-c01) and let the platform host the processor and lease container for you. Either way, the contract is identical: you receive changed items in order, you filter for `delivered`, and you guard the side effect with a dedup key so a redelivered change cannot send a second SMS.

## Common pitfalls

- **Assuming you see every intermediate update.** Standard mode coalesces to the latest version per item. If you need every revision, you need all-versions-and-deletes mode (verify availability and configuration in the docs) or an append-only write pattern.
- **Expecting delete events.** Deletes are not surfaced in standard mode. Use soft deletes (a `deleted` flag, optionally with TTL) so a deletion appears as an update.
- **Non-idempotent consumers.** Because delivery is at-least-once, a consumer that isn't safe to re-run will double-send or double-count after any restart. Always dedupe on a stable key.
- **Sharing or deleting the lease container.** It is the processor's durable memory. Point two unrelated processors at one lease container and they corrupt each other's bookmarks; delete it and you replay from the beginning.
- **Treating the change feed as a queue with deletes.** It is an ordered log of current item state, not a message queue. For competing-consumer messaging with explicit acks and dead-lettering, use Service Bus or Queue Storage (covered in cb-c03).

## Knowledge check

1. An item is updated five times in quick succession before your consumer reads the feed in standard mode. How many change events do you process for it, and what state do they carry?
2. After a consumer pod restarts, marketing reports a few customers got two identical SMS messages. What is the root cause and the fix?
3. A teammate wants the change feed to fire when a delivery row is deleted. Why won't that work directly, and what is the standard pattern?

<details>
<summary>Answers</summary>

1. One event, carrying the latest (fifth) state. — Standard change feed surfaces the most recent version per item, not each intermediate update.
2. At-least-once delivery redelivered an in-flight change after the restart, and the consumer wasn't idempotent. Dedupe on a stable key (id + `_etag`) or record a "notified" marker before sending. — The guarantee is at-least-once, so consumers must tolerate redelivery.
3. Standard mode does not emit delete events. Use a soft delete — set a `deleted` flag (optionally with TTL) — so the deletion arrives as an update the consumer can act on. — Deletes aren't part of the standard feed.

</details>

## Summary

The change feed turns your Cosmos container into an ordered event source: the processor distributes partitions, the lease container remembers progress so restarts are safe, and at-least-once delivery means your consumers must be idempotent. Reach for it instead of polling whenever you need to react to writes cheaply and in order, and remember its boundaries — latest-version-only and no deletes by default. Next, in **Azure Blob Storage with the SDK**, you move from structured items to unstructured objects and the storage service that holds the large payloads Cosmos should only point at.

## Further learning

- [Change feed in Azure Cosmos DB](https://learn.microsoft.com/en-us/azure/cosmos-db/change-feed)
- [Change feed processor in Azure Cosmos DB](https://learn.microsoft.com/en-us/azure/cosmos-db/nosql/change-feed-processor)
- [Azure Functions trigger for Azure Cosmos DB](https://learn.microsoft.com/en-us/azure/azure-functions/functions-bindings-cosmosdb-v2-trigger)
- [Time to Live (TTL) in Azure Cosmos DB](https://learn.microsoft.com/en-us/azure/cosmos-db/nosql/time-to-live)
