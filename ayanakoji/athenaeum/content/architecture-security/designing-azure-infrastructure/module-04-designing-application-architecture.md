---
kind: module
id: as-c01-m04
vertical: architecture-security
course_id: as-c01
title: Designing application architecture
level: foundational
grounded_on: "AZ-305 skills outline (2026-04-17), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/az-305
synthetic: true
order: 4
prereqs: [as-c01-m03]
objectives:
  - Recommend messaging and event-driven architectures for decoupling
  - Recommend caching and API integration solutions
  - Recommend an automated deployment solution for application infrastructure
---

# Designing application architecture

Solstice Tickets' services now run on the right compute, reach each other over the right network, and persist to the right stores. But they are still wired together badly. The checkout service calls the email service directly and synchronously, so when email is slow, checkout stalls and customers abandon carts. The same product catalog is read thousands of times a second from the database. And every release is a hand-edited portal click that nobody can reproduce. These are integration problems, and they are where good infrastructure either becomes a resilient system or stays a fragile one. This module teaches you to decouple with messaging and events, absorb read load with caching, govern access with API integration, and make the whole thing reproducible with automated deployment.

## Learning objectives

By the end of this module you will be able to:

- Recommend a messaging architecture and distinguish it from an event-driven one.
- Choose between Service Bus, Event Grid, and Event Hubs for a given integration.
- Recommend a caching solution to absorb read load and reduce latency.
- Recommend an API integration layer and an automated, repeatable deployment solution.

## Concepts

### Messages versus events: command versus notification

The most consequential integration decision is whether a piece of communication is a **message** or an **event**, because they have opposite semantics.

A **message** is a command with intent: "process this payment," "send this receipt." The sender expects it to be handled, exactly once if possible, and cares about delivery guarantees, ordering, and retries. **Azure Service Bus** is built for this — durable queues and topics, sessions for ordering, dead-letter queues for poison messages, and at-least-once delivery. When Solstice's checkout drops a "send receipt" message onto a Service Bus queue, checkout returns instantly and the email service consumes the message on its own schedule; email being slow no longer stalls checkout.

An **event** is a notification that something happened: "a blob was created," "an order was placed." The publisher does not know or care who is listening and expects nothing back. **Azure Event Grid** is the lightweight publish/subscribe router for these discrete reactive events, fanning a single event out to many subscribers. **Azure Event Hubs** is different again: it is built for *high-volume telemetry streams* — millions of events per second from clickstreams or IoT — where consumers read from a partitioned log. The rule of thumb: command that must be handled → Service Bus; discrete "react to this" notification → Event Grid; firehose of telemetry → Event Hubs.

### Caching: stop asking the database the same question

When the same data is read far more often than it changes, every read hitting the database is wasted work and added latency. A **cache** stores the answer close to the consumer so most reads never touch the origin. **Azure Cache for Redis** is the managed in-memory cache for this: the catalog service writes the rendered product list into Redis with a time-to-live, and thousands of reads per second are served from memory in sub-millisecond time while the database handles only the occasional miss and refresh. The two design questions are *what to cache* (read-heavy, change-tolerant data) and *how to invalidate* (a TTL, or explicit eviction on write). Caching also absorbs traffic spikes — a flash sale that would overwhelm the database becomes a flood of cache hits. The caution: a cache introduces a second copy of the truth, so you must decide how stale a read may be.

### API integration: one governed front door

As services multiply, exposing each one directly to clients spreads authentication, rate limiting, and versioning logic everywhere. **Azure API Management (APIM)** consolidates that into one façade: it presents a unified API surface, enforces subscription keys and auth, applies policies for throttling and transformation, and lets you version and document APIs in one place. For Solstice's partner integrations, APIM is where you enforce "this partner gets 100 calls a minute" without touching the pricing service's code.

### Automated deployment: if it is not codified, it is not reproducible

A design that can only be deployed by hand is not finished. **Infrastructure as code** — Bicep or ARM templates — captures the resources so an environment can be recreated identically, reviewed in a pull request, and rolled back. This is the bridge into the rest of the vertical: every governance, resilience, and security control you add later assumes the infrastructure is defined declaratively rather than clicked into existence.

## Walkthrough: decoupling Solstice checkout from email

The fix for the stalling checkout is to put a Service Bus queue between the checkout service (producer) and the email service (consumer). Checkout enqueues a "send receipt" message and returns immediately; the email service drains the queue at its own pace, and a slow or briefly down email service no longer blocks a sale. First, declare the queue as code so the change is reviewable:

```bicep
param location string = resourceGroup().location

resource sbNamespace 'Microsoft.ServiceBus/namespaces@2022-10-01-preview' = {
  name: 'solstice-checkout-sb'
  location: location
  sku: { name: 'Standard', tier: 'Standard' }
}

resource receiptQueue 'Microsoft.ServiceBus/namespaces/queues@2022-10-01-preview' = {
  parent: sbNamespace
  name: 'receipt-emails'
  properties: {
    maxDeliveryCount: 5          // after 5 failed tries, dead-letter it
    lockDuration: 'PT30S'        // consumer has 30s to process before redelivery
    deadLetteringOnMessageExpiration: true
  }
}
```

`maxDeliveryCount: 5` is the resilience decision made explicit: a message that repeatedly fails to process is moved to the dead-letter queue after five attempts instead of poisoning the consumer forever, where an operator can inspect it. `lockDuration` gives the consumer a window to finish before the message becomes visible to another receiver, preventing duplicate sends under normal operation. Now the producer side, using the modern credential-free pattern from earlier courses:

```python
from azure.servicebus import ServiceBusClient, ServiceBusMessage
from azure.identity import DefaultAzureCredential

FQDN = "solstice-checkout-sb.servicebus.windows.net"
credential = DefaultAzureCredential()  # managed identity in prod; no secrets in code

with ServiceBusClient(FQDN, credential) as client:
    sender = client.get_queue_sender(queue_name="receipt-emails")
    with sender:
        sender.send_messages(ServiceBusMessage('{"orderId": "SOL-90422"}'))
        # checkout returns now; email is handled asynchronously downstream
```

`DefaultAzureCredential` means production runs on a managed identity with no connection string in code — the credential discipline the security course builds on. The moment `send_messages` returns, checkout is free; the email service, scaled independently, processes the receipt whenever it is ready. The synchronous coupling that abandoned carts is gone.

## Common pitfalls

- **Using an event router where you needed guaranteed delivery.** Event Grid is fire-and-forget pub/sub; if the communication is a command that *must* be processed (a payment, a receipt), use Service Bus, whose queues, retries, and dead-lettering give the delivery guarantees events do not.
- **Reaching for Event Hubs when you meant Service Bus (or vice versa).** Event Hubs is a high-throughput telemetry stream consumed from a partitioned log; Service Bus is transactional command messaging. Picking the wrong one means fighting the service's model.
- **Caching without an invalidation plan.** A cache with no TTL or eviction strategy serves stale data indefinitely. Decide up front how fresh reads must be and how writes evict the entry.
- **Exposing every microservice directly to clients.** Without an API gateway, auth, throttling, and versioning logic scatters across services and drifts. APIM centralizes the cross-cutting concerns.
- **Deploying by hand.** Portal clicks are not reproducible, reviewable, or rollback-able. Codify infrastructure in Bicep/ARM so environments are identical and changes go through review.

## Knowledge check

1. A checkout service must trigger a receipt email but should never block on it, and the email must not be lost if the email service is briefly down. Which integration service fits, and which two of its features deliver that guarantee?
2. A product catalog is read thousands of times per second and changes a few times a day. What pattern reduces database load and latency, and what is the one design risk it introduces?
3. Five partner APIs each need their own rate limit, key-based auth, and versioning. Rather than coding that into each service, what should the architecture include, and why?

<details>
<summary>Answers</summary>

1. Azure Service Bus; durable queuing decouples checkout (it enqueues and returns) and at-least-once delivery with retries plus dead-lettering ensures the message survives a brief outage and is not silently lost.
2. Caching with Azure Cache for Redis serves the read-heavy, change-tolerant catalog from memory and absorbs spikes; the risk is staleness — a second copy of the truth — which you manage with a TTL or eviction-on-write.
3. An API Management layer, because it centralizes auth, rate limiting, and versioning as policy in one governed façade instead of duplicating and drifting that logic across every service.

</details>

## Summary

Application architecture is about how the pieces *talk*: commands that must be handled go through Service Bus, discrete notifications through Event Grid, telemetry firehoses through Event Hubs; read-heavy data is absorbed by a cache with a deliberate invalidation plan; client access is governed through an API Management façade; and the whole topology is codified so it is reproducible. Decoupling with messaging is the single highest-leverage move — it turns a chain of synchronous failures into independent, resilient services. You have now designed a complete Azure infrastructure end to end; the next course in this vertical, *Identity, Governance & Resilience*, takes this foundation and adds the identity, policy, and continuity controls that make it production-grade.

## Further learning

- [Asynchronous messaging options in Azure](https://learn.microsoft.com/en-us/azure/architecture/guide/technology-choices/messaging)
- [Choose between Azure messaging services — Event Grid, Event Hubs, Service Bus](https://learn.microsoft.com/en-us/azure/event-grid/compare-messaging-services)
- [Caching guidance](https://learn.microsoft.com/en-us/azure/architecture/best-practices/caching)
- [What is Azure API Management?](https://learn.microsoft.com/en-us/azure/api-management/api-management-key-concepts)
