---
kind: module
id: cb-c03-m04
vertical: cloud-backend
course_id: cb-c03
title: Event- and message-based integration
level: advanced
grounded_on: "AZ-204 skills outline (2026-01-14), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/az-204
synthetic: true
order: 4
prereqs: [cb-c03-m03]
objectives:
  - Implement event-based solutions with Azure Event Grid and Event Hubs
  - Implement message-based solutions with Azure Service Bus and Queue Storage
  - Choose between events and messages for a given integration scenario
---

# Event- and message-based integration

Northwind Logistics now has a tracking API behind a gateway, but the business keeps asking for things that do not fit a request/response model. When a shipment is delivered, three downstream systems — billing, customer notifications, and analytics — all need to know, and none of them should make the delivery API wait. The warehouse's IoT scanners emit millions of scan events an hour that an analytics pipeline must ingest in order. And the order-fulfillment workflow must process each order *exactly once*, survive a consumer crash mid-process, and never lose an order even if the fulfillment service is down for an hour. Solving these synchronously couples the services and makes one slow component everyone's problem. The answer is **asynchronous integration**: services communicate through a broker, and the producer is decoupled from the consumer in time and availability. Azure gives you four such brokers, and choosing the right one is the core skill of this module.

## Learning objectives

By the end of this module you will be able to:

- Publish and react to discrete events with Azure Event Grid.
- Ingest high-throughput event streams with Azure Event Hubs.
- Process reliable, ordered, transactional messages with Azure Service Bus.
- Decide between Event Grid, Event Hubs, Service Bus, and Queue Storage for a scenario.

## Concepts

### Events versus messages: the distinction that drives every choice

The single most important idea here is the difference between an *event* and a *message*. An **event** is a lightweight notification that *something happened* — "shipment 4471 was delivered." The publisher does not know or care who consumes it, and typically does not expect a reply. A **message** is data with an *intent* that some consumer is expected to act on and usually own — "fulfill order 9920." Messages often carry the actual payload and demand reliable, sometimes ordered, sometimes transactional handling.

This distinction maps cleanly onto the services. **Event Grid** and **Event Hubs** are event services; **Service Bus** and **Queue Storage** are message services. Get the producer's *intent* right — notification versus instruction — and the service choice usually follows.

### The event services: Event Grid and Event Hubs

**Azure Event Grid** is a serverless event-routing service for discrete, reactive events. A publisher sends events to a topic; subscribers register with filters and Event Grid pushes matching events to their handlers (a Function, a webhook, a queue) with built-in retry. It is the right tool for "react to this thing that happened" at modest per-event volumes — the delivery-completed fan-out to billing, notifications, and analytics is a textbook Event Grid case.

**Azure Event Hubs** is a high-throughput streaming ingestion service built for *telemetry and event streams* — millions of events, partitioned for parallelism, retained for a window so multiple independent consumers can read at their own pace. Consumers track their position with an offset/checkpoint rather than removing events. The warehouse scanner firehose belongs here: Event Grid would buckle and Service Bus is the wrong model for ordered, replayable streams.

### The message services: Service Bus and Queue Storage

**Azure Service Bus** is an enterprise message broker for reliable, decoupled business workflows. It offers **queues** (point-to-point) and **topics/subscriptions** (publish/subscribe), plus the features serious workflows need: FIFO ordering with **sessions**, **dead-lettering** for messages that cannot be processed, **duplicate detection**, transactions, and scheduled delivery. The exactly-once-ish, never-lose-an-order fulfillment workflow wants Service Bus.

**Azure Queue Storage** is a simpler, massively scalable queue built on a storage account. It gives you basic, durable, at-least-once delivery without Service Bus's richer semantics. Reach for it when you need a straightforward backlog of work items and do not need ordering, sessions, topics, or transactions. A useful rule of thumb: if you find yourself wanting dead-lettering, sessions, or pub/sub, you have outgrown Queue Storage and want Service Bus. Note both have message-size limits (Queue Storage messages cap at 64 KB; Service Bus limits vary by tier) — verify current limits in the docs and keep large payloads in Blob Storage with a pointer in the message (the claim-check pattern).

## Walkthrough: routing the Northwind delivery-completed event

You will publish a `ShipmentDelivered` event when a delivery is confirmed and fan it out to billing, notifications, and analytics using Event Grid — the discrete-event, fan-out scenario. First, create the custom topic and capture its endpoint and key:

```bash
# Create an Event Grid custom topic for shipment events
az eventgrid topic create \
  --name nw-shipment-events \
  --resource-group rg-northwind-expense \
  --location eastus

# Capture the publish endpoint and an access key (store the key in Key Vault)
az eventgrid topic show --name nw-shipment-events \
  --resource-group rg-northwind-expense --query endpoint -o tsv
az eventgrid topic key list --name nw-shipment-events \
  --resource-group rg-northwind-expense --query key1 -o tsv
```

Now publish the event from the delivery service using the Event Grid SDK with `DefaultAzureCredential` (the topic's managed-identity RBAC role, from module two, grants publish rights):

```python
from azure.identity import DefaultAzureCredential
from azure.eventgrid import EventGridPublisherClient, EventGridEvent

TOPIC_ENDPOINT = "https://nw-shipment-events.eastus-1.eventgrid.azure.net/api/events"

client = EventGridPublisherClient(TOPIC_ENDPOINT, DefaultAzureCredential())

def publish_delivered(shipment_id: str, delivered_to: str) -> None:
    event = EventGridEvent(
        subject=f"shipments/{shipment_id}",
        event_type="Northwind.Shipment.Delivered",
        data={"shipmentId": shipment_id, "deliveredTo": delivered_to},
        data_version="1.0",
    )
    client.send(event)  # fire-and-forget; Event Grid handles fan-out + retry
```

The delivery service publishes *one* event and returns immediately — it does not call billing, notifications, or analytics, and is not blocked if any of them is slow. Each downstream system creates its own **event subscription** to this topic, optionally filtered by `event_type`, and Event Grid pushes the event to each handler with automatic retry. Adding a fourth consumer later is purely a new subscription; the producer code never changes. That is the decoupling payoff: the producer knows nothing about its consumers.

## Common pitfalls

- **Using Event Hubs for discrete reactive events (or Event Grid for high-volume streams).** Event Hubs is a partitioned stream for telemetry; Event Grid is a router for discrete events. Swapping them leads to either needless complexity or throughput collapse. Match the service to event *shape* and *volume*.
- **Assuming exactly-once and strict order by default.** Most of these services are at-least-once; consumers must be **idempotent**. Strict FIFO in Service Bus requires **sessions**; Event Hubs preserves order only *within a partition*. Design for redelivery and design your partition/session keys deliberately.
- **Ignoring the dead-letter queue.** Service Bus dead-letters messages that repeatedly fail or expire. If you never read the DLQ, failures vanish silently and orders are lost. Monitor and drain dead-letter queues as a first-class operational task.
- **Putting large payloads in messages.** Queue Storage caps messages at 64 KB and Service Bus has tier-dependent limits. Storing a big document inline fails or wastes the broker; use the claim-check pattern — store the blob and pass a reference. Verify current size limits in the docs.
- **Reaching for Queue Storage when you need richer semantics.** If the scenario needs ordering, pub/sub, duplicate detection, or transactions, Queue Storage will force you to reinvent them poorly. That is the signal to use Service Bus instead.

## Knowledge check

1. A warehouse emits roughly two million scan events per hour that an analytics job must process in order and that a second team also wants to replay later. Which service, and why?
2. The order-fulfillment workflow must never lose an order, must process each exactly once in practice, and must quarantine orders it cannot process. Which service and which two features do you rely on?
3. A "shipment delivered" notification must fan out to billing, customer notifications, and analytics without the delivery service waiting on any of them. Which service fits best and why?

<details>
<summary>Answers</summary>

1. **Azure Event Hubs.** Rationale: it is built for high-throughput, partitioned event *streams* with retention, so multiple independent consumers can read and replay at their own offsets, and ordering is preserved within a partition.
2. **Azure Service Bus**, relying on **dead-lettering** (to quarantine unprocessable orders) and **sessions/duplicate detection** (for ordering and to support exactly-once-style processing). Rationale: only Service Bus provides these enterprise messaging guarantees among the four brokers.
3. **Azure Event Grid.** Rationale: a delivery is a discrete event, and Event Grid pushes it to multiple independent subscribers with retry, fully decoupling the producer from consumers so it never blocks on them.

</details>

## Summary

Asynchronous integration decouples services in time and availability by routing communication through a broker, and the right broker follows from whether the producer is emitting a *notification* (event) or an *instruction* (message). Event Grid routes discrete events with fan-out and retry; Event Hubs ingests high-volume, replayable streams; Service Bus delivers reliable, ordered, transactional messages with dead-lettering; and Queue Storage offers simple, scalable work queues. Build consumers to be idempotent, watch your dead-letter queues, and keep large payloads out of messages. This module completes the *Securing & Integrating Cloud Applications* course: you can now authenticate, protect secrets, publish APIs, and connect services into a resilient, loosely coupled system.

## Further learning

- [Choose between Azure messaging services](https://learn.microsoft.com/en-us/azure/event-grid/compare-messaging-services)
- [What is Azure Event Grid?](https://learn.microsoft.com/en-us/azure/event-grid/overview)
- [Azure Service Bus messaging overview](https://learn.microsoft.com/en-us/azure/service-bus-messaging/service-bus-messaging-overview)
- [Azure Queue Storage introduction](https://learn.microsoft.com/en-us/azure/storage/queues/storage-queues-introduction)
