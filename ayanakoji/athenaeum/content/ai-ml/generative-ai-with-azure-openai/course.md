---
kind: course
id: ai-c01
vertical: ai-ml
course_id: ai-c01
title: Generative AI Solutions with Azure OpenAI
level: foundational
grounded_on: "AI-102 skills outline (2025-12-23), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/ai-102
synthetic: true
prereqs: []
objectives: []
---

# Generative AI Solutions with Azure OpenAI

Wiring a large language model into a real application is deceptively easy to start
and surprisingly hard to do well. A two-line prototype that calls a chat model looks
like progress, but production demands more: you have to choose the right model and
deployment shape, make the model answer with *your* facts instead of plausible
fiction, keep latency and cost predictable, and stop the system from emitting unsafe
or off-policy content. This course builds the capability to take a generative feature
from a notebook demo to a service you would put your name on.

You will work the full arc using Azure OpenAI models hosted in Microsoft Foundry: you
provision the resource and deploy a model, shape its behavior with prompts and
parameters, ground it in private knowledge with retrieval-augmented generation, and
finally instrument it with evaluation, content safety, and monitoring. The through-line
is a single fictional product — a customer-support assistant for "Northwind Outfitters,"
an outdoor-gear retailer — so each module adds a layer to one believable system rather
than teaching four disconnected toys.

## Who this is for

This course is for application developers and ML-adjacent engineers who can already read
and write Python and have basic familiarity with calling a REST or SDK-based service. You
do not need prior machine-learning experience or a data-science background — generative AI
engineering is mostly software engineering with a probabilistic dependency. This is the
entry point for the AI & Machine Learning Engineering vertical, so no prior courses in this
track are assumed.

## What you'll be able to do

- Provision an Azure OpenAI resource in Foundry and deploy a model with a deployment name your code can call.
- Choose between deployment options and model families based on the workload's latency, cost, and capability needs.
- Engineer prompts and tune generation parameters to get reliable, well-formatted, on-task output.
- Build a retrieval-augmented generation pipeline that grounds answers in your own documents and cites its sources.
- Evaluate generation quality with repeatable metrics and configure content filters, prompt shields, and monitoring.
- Reason about the failure modes of generative systems — hallucination, prompt injection, drift — and design controls for them.

## Module path

This course is four sequential modules; each builds on the last.

1. **Provisioning and deploying models in Microsoft Foundry** — create the resource, deploy a model, and make your first authenticated SDK call.
2. **Prompt engineering and templates** — control behavior with system prompts, few-shot examples, parameters, and reusable templates.
3. **Retrieval-augmented generation (RAG)** — ground the model in private data with chunking, retrieval, and source citation.
4. **Evaluation, monitoring, and responsible AI** — measure quality, apply content safety and prompt shields, and watch the system in production.

## Prerequisites

None — this is an entry point for the vertical. You should be comfortable writing Python,
installing packages with `pip`, and using environment variables for configuration. An Azure
subscription with access to Azure OpenAI is needed to run the walkthroughs; access is
gated, so confirm your subscription is enabled for the service before you start. Familiarity
with REST and JSON will help but is not required.

## How this fits the bigger picture

Generative AI is rarely a standalone feature; it sits on top of the same cloud foundations
the rest of the Athenaeum tracks teach. The retrieval layer you build here often reads from
the storage and search services covered in the Cloud & Backend and Data Engineering
verticals, and the production concerns — identity, secrets, monitoring, scaling — are the
same disciplines those tracks drill. The two follow-on courses in this vertical, *Language &
Document Intelligence* and *Computer Vision & Knowledge Mining*, broaden from text generation
to the full Azure AI portfolio. Treat this course as the spine: once you can deploy, prompt,
ground, and govern a generative model, the rest of Azure AI is variations on a theme you
already understand.
