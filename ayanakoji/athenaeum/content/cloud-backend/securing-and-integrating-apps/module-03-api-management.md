---
kind: module
id: cb-c03-m03
vertical: cloud-backend
course_id: cb-c03
title: Publishing APIs with Azure API Management
level: advanced
grounded_on: "AZ-204 skills outline (2026-01-14), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/az-204
synthetic: true
order: 3
prereqs: [cb-c03-m01]
objectives:
  - Create an API Management instance and import a backend API
  - Configure access to APIs with subscription keys and products
  - Apply policies for transformation, caching, and rate limiting
---

# Publishing APIs with Azure API Management

Northwind Logistics has just signed three freight partners who want to call its shipment-tracking API directly. Suddenly your tidy internal service faces the open internet. Each partner needs their own credential so you can revoke one without breaking the others. You need to throttle a partner who accidentally loops a polling script, hide the fact that "the API" is really four microservices behind it, return cached responses for the read-heavy lookups, and hand each partner clean documentation. Bolting all of that into your application code would be a maintenance nightmare and would couple business logic to gateway concerns. **Azure API Management (APIM)** is the gateway that handles every one of those cross-cutting jobs in front of your backend, so your services stay focused on their actual work.

## Learning objectives

By the end of this module you will be able to:

- Provision an API Management instance and import a backend API from an OpenAPI definition.
- Organize APIs into products and control access with subscription keys.
- Author and apply policies at the inbound, backend, and outbound stages of a request.
- Implement rate limiting, response caching, and request/response transformation with policies.

## Concepts

### What the gateway is, and the three planes

API Management is a **facade**: clients call APIM, and APIM forwards to your real backends. This indirection is the whole value, because it gives you one place to enforce authentication, throttling, caching, transformation, and logging without touching the services behind it. An APIM instance has three logical parts. The **gateway** is the runtime data plane that proxies and processes every request. The **management plane** is where you configure APIs, products, and policies (via portal, CLI, or ARM/Bicep). The **developer portal** is an auto-generated, customizable site where consumers discover APIs, read docs, and obtain keys.

APIM comes in tiers (Consumption, Developer, Basic, Standard, Premium, and newer variants) that trade off price, scale, isolation, and features like VNet integration. Choose the tier from real requirements — the Developer tier is for non-production because it carries no SLA. Verify the current tier matrix in the docs, since the lineup evolves.

### Products, subscriptions, and keys: how access is granted

Consumers do not get raw access to an API. Instead you group one or more APIs into a **product** (for example a "Partner Tracking" product), and a consumer takes out a **subscription** to that product. The subscription issues a **subscription key** that the caller sends in the `Ocp-Apim-Subscription-Key` header. Because each partner has a distinct key, you can throttle, monitor, or revoke them independently — revoking Northwind's loose-cannon partner is a single action that does not touch the others.

Subscription keys identify the *calling application*, but they are not strong end-user authentication. For real security you layer **OAuth 2.0 / JWT validation** on top using a policy that checks the bearer token issued by the Microsoft identity platform (module one). Think of the subscription key as "which partner is this and what product did they buy," and the validated JWT as "and is the actual caller authorized." Production partner APIs typically use both.

### Policies: the programmable request pipeline

Policies are the heart of APIM. A **policy** is an XML statement that runs at a defined stage of the request lifecycle: **inbound** (before the request reaches the backend), **backend** (around the call to your service), **outbound** (before the response returns to the client), and **on-error**. Policies can be set globally, per product, per API, or per operation, and they inherit and compose via `<base />`. With policies you enforce `rate-limit-by-key` to cap a partner's call volume, `cache-lookup`/`cache-store` to serve repeated reads without hitting the backend, `validate-jwt` to enforce identity, and `set-header`/`set-body` to transform requests and responses. This is how you implement cross-cutting behavior declaratively instead of scattering it through application code.

## Walkthrough: fronting the Northwind tracking API for partners

You will create an APIM instance, import the shipment-tracking API, and apply a policy that rate-limits each partner and caches lookups. Start by provisioning the instance and importing from an OpenAPI URL:

```bash
# Create the APIM instance (Developer tier for this non-prod example)
az apim create \
  --name nw-apim \
  --resource-group rg-northwind-expense \
  --publisher-name "Northwind Logistics" \
  --publisher-email "apis@northwind.example" \
  --sku-name Developer

# Import the backend tracking API from its OpenAPI definition
az apim api import \
  --resource-group rg-northwind-expense \
  --service-name nw-apim \
  --api-id tracking-api \
  --path "tracking" \
  --specification-format OpenApi \
  --specification-url "https://nw-tracking-func.azurewebsites.net/openapi.json"
```

Now apply an inbound policy on the tracking API that throttles per subscription key and caches GET responses. APIM policies are XML:

```xml
<policies>
  <inbound>
    <base />
    <!-- Cap each partner (identified by their subscription key) to 600 calls / 60s -->
    <rate-limit-by-key calls="600" renewal-period="60"
        counter-key="@(context.Subscription.Id)" />
    <!-- Serve cached responses for repeat lookups; vary by the tracking id -->
    <cache-lookup vary-by-developer="false" vary-by-developer-groups="false">
      <vary-by-query-parameter>trackingId</vary-by-query-parameter>
    </cache-lookup>
  </inbound>
  <backend>
    <base />
  </backend>
  <outbound>
    <base />
    <!-- Store successful responses for 30s so identical lookups skip the backend -->
    <cache-store duration="30" />
    <!-- Strip an internal header so partners never see backend details -->
    <set-header name="X-Internal-Node" exists-action="delete" />
  </outbound>
  <on-error>
    <base />
  </on-error>
</policies>
```

Reading the pipeline top to bottom: on the way *in*, `rate-limit-by-key` counts calls against each partner's subscription ID and returns `429 Too Many Requests` if they exceed 600 per minute, and `cache-lookup` checks for a cached response keyed by `trackingId`. On the way *out*, `cache-store` saves successful responses for 30 seconds and `set-header` deletes an internal diagnostic header so the backend's topology never leaks to partners. None of this logic lives in the tracking service — it is pure gateway configuration, and it applies identically to every partner the moment you add a new subscription.

## Common pitfalls

- **Treating subscription keys as authentication.** A subscription key tells you *which app/product*, not *which authorized user*. For sensitive operations, add a `validate-jwt` policy checking an Entra-issued token. Keys alone are an access *organizing* tool, not an identity guarantee.
- **Forgetting `<base />` in a scoped policy.** Policies inherit from broader scopes via `<base />`. Omitting it in an API-level policy silently drops global policies (like CORS or logging) for that API. Always include `<base />` unless you intend to override.
- **Rate-limiting on the wrong counter key.** `rate-limit` (per APIM instance) versus `rate-limit-by-key` with a per-subscription counter behave very differently. If you want fairness *per partner*, key on `context.Subscription.Id`; otherwise one noisy partner consumes everyone's budget.
- **Caching responses that vary by caller without varying the cache key.** If a response depends on the partner or a query parameter and you do not `vary-by`, partners can receive each other's cached data. Always vary the cache key by every input that changes the response.
- **Using the Developer tier in production.** It is cost-effective for testing but has no SLA. Match the tier to availability and scale needs; verify the current tier capabilities in the docs before committing.

## Knowledge check

1. A partner complains they intermittently receive shipment data for a *different* tracking number. Your team recently added response caching. What is the most likely misconfiguration?
2. You need each of three partners to be throttled independently so one runaway script cannot starve the others. Which policy and counter key do you choose?
3. Why is requiring only a subscription key insufficient for an operation that updates shipment status, and what do you add?

<details>
<summary>Answers</summary>

1. **The cache key does not vary by `trackingId`** (or another distinguishing input), so different lookups collide on one cached entry. Rationale: a cache must vary by every parameter that changes the response, or callers receive stale/wrong cached data.
2. **`rate-limit-by-key` with `counter-key` set to `context.Subscription.Id`.** Rationale: keying the counter on each subscription enforces a separate quota per partner, so one partner's overuse cannot consume another's allowance.
3. **A subscription key identifies the calling app/product, not an authorized user, and can be replayed.** Add a `validate-jwt` inbound policy to verify an Entra-issued bearer token. Rationale: state-changing operations need real, verifiable end-user/app authorization, not just a shared key.

</details>

## Summary

API Management is the facade that lets you secure, throttle, cache, transform, and document APIs in one place, decoupled from your backend services. Products and subscription keys organize and gate access per consumer, while policies — running across the inbound, backend, and outbound stages — implement the cross-cutting behavior declaratively. Pair subscription keys with JWT validation for genuine security, and always scope rate limits and cache keys correctly. With your synchronous APIs published safely, the final module turns to *asynchronous* integration, where services communicate through events and messages rather than direct calls.

## Further learning

- [About Azure API Management](https://learn.microsoft.com/en-us/azure/api-management/api-management-key-concepts)
- [API Management policies overview](https://learn.microsoft.com/en-us/azure/api-management/api-management-howto-policies)
- [Subscriptions in Azure API Management](https://learn.microsoft.com/en-us/azure/api-management/api-management-subscriptions)
- [Protect APIs with rate limiting and quotas](https://learn.microsoft.com/en-us/azure/api-management/api-management-sample-flexible-throttling)
