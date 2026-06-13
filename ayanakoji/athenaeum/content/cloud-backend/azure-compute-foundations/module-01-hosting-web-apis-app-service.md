---
kind: module
id: cb-c01-m01
vertical: cloud-backend
course_id: cb-c01
title: Hosting web APIs with Azure App Service
level: foundational
grounded_on: "AZ-204 skills outline (2026-01-14), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/az-204
synthetic: true
order: 1
prereqs: []
objectives:
  - Create and configure an App Service web app for a backend API
  - Use deployment slots for zero-downtime releases and slot swaps
  - Configure TLS, app settings, and service connections securely
---

# Hosting web APIs with Azure App Service

The fictional team at Northwind Parcel has a working orders API written in Python. It runs fine on a developer's laptop, but the moment they need it reachable, patched, TLS-terminated, and able to survive a deploy without dropping requests, the laptop stops being a plan. They do not want to babysit virtual machines or operating-system updates. What they want is a managed place to put HTTP code that handles the undifferentiated heavy lifting. That place is Azure App Service, and learning to operate it well is the difference between "it's deployed" and "it's deployed safely."

## Learning objectives

By the end of this module you will be able to:

- Create and configure an App Service web app sized for a backend API workload.
- Deploy new versions through deployment slots and swap them with no downtime.
- Configure TLS, application settings, and connection strings so secrets never live in your code.

## Concepts

### What App Service actually manages for you

App Service is a Platform-as-a-Service host for web applications and APIs. You hand it your code (or a container) and it runs that code on infrastructure it patches, load-balances, and keeps available. The unit you actually pay for is the **App Service Plan** — a set of compute resources (a tier and a number of instances) that one or more web apps share. This separation matters: the *plan* defines how much horsepower and which features you get (custom domains, scaling, slots), while the *app* is the deployed workload. Several small apps can share one plan to save money, or a demanding app can have a plan to itself.

Tiers range from Free and Basic up through Standard, Premium, and Isolated. The practical rule: features like deployment slots and autoscaling appear at Standard and above. When you choose a tier you are choosing a feature set and a scaling ceiling, not just a price. Treat the exact instance sizes and per-tier limits as something to confirm in the current docs, because Microsoft revises them.

### App settings and connection strings as configuration

App Service injects **application settings** into your process as environment variables at startup. This is the idiomatic way to configure a cloud app: your code reads `os.environ["DATABASE_URL"]` and never contains the value. Settings configured in the platform override any matching values baked into your deployment, which lets the same image behave differently per environment. Connection strings are a closely related slot in the configuration UI that App Service can surface with a documented prefix; for most modern apps, plain app settings plus a secret store are the cleaner path. The principle that carries forward to every later course: configuration and secrets are *operational data*, not source code.

### Deployment slots and the swap

A **deployment slot** is a fully functioning copy of your app with its own hostname, running inside the same plan. You deploy your new version to a staging slot, let it warm up, smoke-test it against its own URL, and then perform a **swap** with production. The swap is the clever part: App Service warms up the staging instances, then redirects production traffic to them by exchanging the routing, so users never hit a cold or half-deployed app. If the new version misbehaves, you swap back. Some settings (those marked as deployment-slot settings, often called "sticky") stay pinned to their slot during a swap — useful for keeping a staging connection string out of production. Slots are the single most valuable feature for releasing without an outage window.

## Walkthrough: shipping the Northwind Parcel orders API

Northwind Parcel wants their `orders-api` running on App Service with a staging slot for safe releases. Here is the path using the Azure CLI. Each command is one deliberate step.

```bash
# Variables for clarity
RG="northwind-parcel-rg"
PLAN="orders-plan"
APP="northwind-orders-api"   # must be globally unique

# 1. Resource group to hold everything
az group create --name "$RG" --location eastus

# 2. A Standard plan (S1) — Standard tier is required for slots
az appservice plan create \
  --name "$PLAN" --resource-group "$RG" \
  --sku S1 --is-linux

# 3. The web app itself, on a Python runtime
az webapp create \
  --name "$APP" --resource-group "$RG" \
  --plan "$PLAN" --runtime "PYTHON:3.12"

# 4. Configuration as environment variables (no secrets in code)
az webapp config appsettings set \
  --name "$APP" --resource-group "$RG" \
  --settings ORDERS_REGION=eastus LOG_LEVEL=info

# 5. Enforce HTTPS so plaintext requests are redirected
az webapp update \
  --name "$APP" --resource-group "$RG" \
  --https-only true

# 6. A staging slot for zero-downtime releases
az webapp deployment slot create \
  --name "$APP" --resource-group "$RG" \
  --slot staging
```

After deploying a new build to the `staging` slot and confirming it is healthy on its own URL (`https://northwind-orders-api-staging.azurewebsites.net`), the team promotes it:

```bash
# Swap staging into production with no downtime
az webapp deployment slot swap \
  --name "$APP" --resource-group "$RG" \
  --slot staging --target-slot production
```

What you should observe: the production hostname now serves the new build, the old version is now sitting in `staging` (so a swap back is instant), and at no point did production return errors to users because App Service warmed the staging instances before redirecting traffic. The `--https-only true` setting means any `http://` request gets a redirect, which together with the platform-managed TLS certificate gives you encrypted transport without handling certificate files yourself.

## Common pitfalls

- **Treating the plan tier as a price knob only.** Picking Basic to save money silently removes slots and autoscaling. Choose the tier by the *features* the workload needs, then optimize cost within that tier.
- **Putting secrets in app settings as plaintext and calling it secure.** App settings keep secrets out of source control, which is good, but they are still readable by anyone with portal access. For real secrets, reference Key Vault (covered in the Securing & Integrating course) rather than storing raw values.
- **Forgetting that some settings are sticky and some are not.** If a connection string follows the code across a swap when you wanted it pinned to staging, you can point production at the wrong database. Mark slot-specific settings as deployment-slot settings deliberately.
- **Swapping without warming up.** If your app does heavy initialization, an un-warmed slot can serve slow first requests right after a swap. Hit the staging slot's health endpoint before swapping so instances are ready.
- **Reusing a non-unique app name.** The default `*.azurewebsites.net` hostname is global; a generic name like `orders-api` will already be taken. Use an org prefix.

## Knowledge check

1. Your team is on a Basic-tier plan and asks why the "Add slot" button is missing. What do you tell them, and what is the fix?
2. After a swap, production suddenly connects to the staging database. What configuration mistake most likely caused this?
3. Why is reading database credentials from `os.environ` preferable to hard-coding them, even before you introduce a dedicated secret store?

<details>
<summary>Answers</summary>

1. Deployment slots are a Standard-and-above feature; Basic does not include them. Scale the plan up to at least Standard (S1) to enable slots. — Slots are gated by tier, so the capability follows the plan, not the app.
2. The database connection setting was not marked as a deployment-slot (sticky) setting, so it followed the code from staging into production during the swap. — Non-sticky settings move with the code on a swap; environment-specific values must be pinned to their slot.
3. Environment variables keep credentials out of source control and let the same build run against different environments by changing platform configuration, not code. — Configuration is operational data; decoupling it from the artifact is the foundation that secret stores later build on.

</details>

## Summary

App Service gives you a managed home for HTTP workloads: you supply code, it supplies patched, load-balanced, TLS-terminated infrastructure billed through an App Service Plan. The two operational superpowers are configuration-as-environment-variables, which keeps secrets and environment differences out of your artifact, and deployment slots, which let you release new versions and roll them back with no downtime via a swap. With a managed place to run synchronous request/response code established, the next module turns to code that should run *only when something happens* — event-driven serverless logic in Azure Functions.

## Further learning

- [Azure App Service overview](https://learn.microsoft.com/en-us/azure/app-service/overview)
- [Set up staging environments in Azure App Service](https://learn.microsoft.com/en-us/azure/app-service/deploy-staging-slots)
- [Configure an App Service app](https://learn.microsoft.com/en-us/azure/app-service/configure-common)
- [Add and manage TLS/SSL certificates in Azure App Service](https://learn.microsoft.com/en-us/azure/app-service/configure-ssl-certificate)
