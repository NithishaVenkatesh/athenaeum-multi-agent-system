---
kind: course
id: cb-c01
vertical: cloud-backend
course_id: cb-c01
title: Azure Compute & Serverless Foundations
level: foundational
grounded_on: "AZ-204 skills outline (2026-01-14), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/az-204
synthetic: true
prereqs: []
objectives: []
---

# Azure Compute & Serverless Foundations

Every cloud application you ship eventually answers the same question: *where does my code actually run?* This course builds the answer from the ground up. You will learn to host a backend API on managed web infrastructure, react to events without standing up a server, package your code into portable containers, and keep all of it healthy when traffic swings from a trickle to a flood. By the end you will be able to look at a workload and confidently pick — and operate — the right Azure compute service for it.

## Who this is for

You are a software developer who can write and deploy an application but has not yet owned the compute layer in Azure. You are comfortable with HTTP, a programming language like Python or C#, and the basics of a command line. You do not need prior Azure experience — this is the entry point for the Cloud & Backend Development vertical, and later courses (Cloud Data & Storage for Developers, Securing & Integrating Cloud Applications) assume the foundations you build here.

## What you'll be able to do

- Create, configure, and deploy a backend web API on Azure App Service with zero-downtime releases.
- Build event-driven serverless functions that respond to timers, HTTP requests, and data changes.
- Package an application as a container image, publish it to a private registry, and run it on Azure's container services.
- Choose between App Service, Functions, Container Instances, and Container Apps based on workload shape.
- Configure autoscaling so compute follows demand instead of paying for peak capacity around the clock.
- Instrument running services with diagnostics and logs so you can diagnose problems in production.

## Module path

This course is four sequential modules; each builds on the last.

1. **Hosting web APIs with Azure App Service** — stand up a managed web app, deploy safely with slots, and lock down TLS and settings.
2. **Event-driven code with Azure Functions** — run code on triggers and bindings without managing servers.
3. **Containerized solutions: ACR, ACI, and Container Apps** — package, publish, and run containers across Azure's container platforms.
4. **Scaling, configuration, and diagnostics** — make compute elastic, observable, and resilient under real load.

## Prerequisites

None — this is an entry point for the vertical. You should be able to write a small web application in a language with an Azure SDK (Python, C#, JavaScript, or Java) and run shell commands. Familiarity with HTTP request/response semantics and environment-variable-based configuration will make the material click faster. An Azure subscription (a free trial is sufficient) lets you follow the walkthroughs hands-on, which is strongly recommended over reading alone.

## How this fits the bigger picture

Compute is the load-bearing wall of any cloud system: storage, identity, and integration all attach to something that runs your code. The four services you learn here — App Service, Functions, Container Registry/Instances/Container Apps — cover the overwhelming majority of backend workloads a development team ships, from a steady REST API to bursty background processing to a containerized microservice. The mental model you develop, *match the service to the workload's shape and lifecycle*, is the same model architects apply at scale in the Cloud Solution Architecture vertical. Get the compute layer right and the rest of the platform has somewhere solid to stand; get it wrong and you will fight cost, latency, and operational pain in every later course. This foundation also feeds directly into the data and security courses, where your running compute becomes the thing that connects to Cosmos DB, reads secrets from Key Vault, and is fronted by API Management. Treat this course as the place you learn the vocabulary and the instincts that the rest of the vertical depends on.
