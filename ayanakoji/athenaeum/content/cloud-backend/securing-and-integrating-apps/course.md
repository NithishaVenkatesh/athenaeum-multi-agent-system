---
kind: course
id: cb-c03
vertical: cloud-backend
course_id: cb-c03
title: Securing & Integrating Cloud Applications
level: advanced
grounded_on: "AZ-204 skills outline (2026-01-14), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/az-204
synthetic: true
prereqs: [cb-c01, cb-c02]
objectives: []
---

# Securing & Integrating Cloud Applications

Once an application has compute and data, the hard problems shift. Now you must prove *who* is calling, keep credentials out of source control, expose your APIs to partners without handing them the keys to the kingdom, and connect a growing fleet of services without coupling them into a brittle monolith. This course builds the identity, secrets, gateway, and messaging skills that turn a working backend into one you can safely run in production for a real organization.

## Who this is for

You are a backend or cloud developer who can already deploy compute and persist data on Azure, and you now own the security and integration story for a service. This course assumes you have completed *Azure Compute & Serverless Foundations* (cb-c01) and *Cloud Data & Storage for Developers* (cb-c02), so you are comfortable with App Service, Functions, the Azure SDKs, and `DefaultAzureCredential`. You do not need to be a security specialist — that is what we are here to teach.

## What you'll be able to do

- Authenticate users and apps with the Microsoft identity platform and call Microsoft Graph on their behalf.
- Eliminate stored credentials by combining Azure Key Vault with managed identities.
- Publish, document, and govern APIs behind Azure API Management with subscription keys and policies.
- Decouple services using Event Grid, Event Hubs, Service Bus, and Queue Storage.
- Choose correctly between an *event* and a *message* for a given integration scenario.
- Reason about the security trade-offs of shared access signatures, tokens, and rate limits.

## Module path

This course is four sequential modules; each builds on the last.

1. **Authentication with the Microsoft identity platform** — sign users in, authorize apps, and call Graph with delegated permissions.
2. **Secrets, keys, and managed identities** — store secrets in Key Vault and access them with an identity instead of a password.
3. **Publishing APIs with Azure API Management** — front your backend with a gateway that handles keys, docs, and policies.
4. **Event- and message-based integration** — connect services asynchronously and pick the right broker for the job.

## Prerequisites

You should be comfortable building and deploying an Azure web API or Function, calling Azure services with the official SDKs, and working at the command line with the `az` CLI. The named prerequisite courses are *Azure Compute & Serverless Foundations* (cb-c01) and *Cloud Data & Storage for Developers* (cb-c02). A working knowledge of OAuth 2.0 and HTTP is helpful but not required; we introduce the identity concepts from first principles in module one. You will get the most from the course if you have an Azure subscription where you can create resources, since every module ends in a hands-on walkthrough you are encouraged to run yourself rather than read passively.

A consistent fictional organization — Northwind Logistics, a freight company — runs through all four modules. You will secure its internal expense portal, harden the secret it depends on, publish its shipment-tracking API to partners, and finally wire its delivery, scanning, and fulfillment systems together asynchronously. Carrying one scenario across the course lets each module build on a concrete, familiar system instead of a fresh toy example.

## How this fits the bigger picture

Security and integration are where most cloud incidents are born: a leaked connection string, an over-permissioned token, an unthrottled public endpoint, a tightly coupled synchronous call that takes down three services when one is slow. This course is the third pillar of the Cloud & Backend vertical, sitting on top of compute and data. The patterns here — federated identity, secretless access, gateway-mediated APIs, and asynchronous messaging — recur across every Azure workload and map directly to the design and architecture skills you will meet later in the *Cloud Solution Architecture & Security* vertical. Master them once and you carry them everywhere.
