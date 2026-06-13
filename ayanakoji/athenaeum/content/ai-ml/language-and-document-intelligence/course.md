---
kind: course
id: ai-c02
vertical: ai-ml
course_id: ai-c02
title: Language & Document Intelligence
level: intermediate
grounded_on: "AI-102 skills outline (2025-12-23), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/ai-102
synthetic: true
prereqs: [ai-c01]
objectives: []
---

# Language & Document Intelligence

Most of the data a business actually runs on is unstructured: support tickets, contracts, scanned invoices, recorded calls, and free-text forms. Humans read it slowly and inconsistently, and traditional code cannot parse it at all. This course teaches you to turn that raw text and those documents into structured, queryable signal using three Azure AI services — Azure AI Language, Azure AI Document Intelligence, and Azure AI Speech — so the systems you build can read, understand, and respond like a capable analyst working at machine speed.

The through-line across all four modules is the same engineering discipline applied to four input shapes. Every service returns typed results with confidence scores, every custom capability follows a label-train-evaluate-deploy lifecycle, and every production decision comes down to thresholding on confidence and routing the uncertain cases to a human. Learn that pattern once and it transfers from a sentence to a scanned invoice to a phone call.

## Who this is for

You are a developer or applied-AI engineer who can already call an Azure AI service with an SDK, authenticate with a credential, and reason about a REST response. You have completed **Generative AI Solutions with Azure OpenAI** (ai-c01) or have equivalent experience provisioning Azure AI resources and handling keys and endpoints. You do not need a linguistics or machine-learning background — you need to understand what each service is good at, where it breaks, and how to wire it into a production workflow.

## What you'll be able to do

- Extract entities, key phrases, sentiment, language, and personally identifiable information from raw text, and translate it across languages.
- Design and train a conversational language understanding model that maps messy user phrasing to intents and entities your app can act on.
- Stand up a custom question answering project that serves grounded answers from your own sources.
- Extract structured fields and tables from invoices, receipts, IDs, and your own document layouts using prebuilt and custom Document Intelligence models.
- Compose multiple custom models so one endpoint can classify and then route mixed document types.
- Add speech-to-text, expressive text-to-speech, and real-time speech translation to an application.

## Module path

This course is four sequential modules; each builds on the last.

1. **Analyzing and translating text** — Pull entities, sentiment, key phrases, and PII out of text, and translate it with Azure AI Translator.
2. **Custom language models and question answering** — Train a conversational understanding model and a custom Q&A knowledge base on your own data.
3. **Document Intelligence** — Extract fields and tables from documents with prebuilt models, then train, publish, and compose custom models.
4. **Speech and translation solutions** — Convert between speech and text, shape pronunciation with SSML, and translate speech in real time.

## Prerequisites

Completion of **Generative AI Solutions with Azure OpenAI** (ai-c01), or equivalent fluency provisioning Azure AI resources, managing endpoints and keys, and calling a service with the Python SDK and `DefaultAzureCredential`. Comfort reading JSON responses and basic familiarity with REST are assumed.

## How this fits the bigger picture

In the AI & Machine Learning vertical, the Azure OpenAI course taught you to generate and reason over language with large models. This course teaches the complementary half: deterministic, structured extraction and recognition services that are cheaper, faster, and auditable for the narrow jobs they do well. Real systems combine both — a Document Intelligence model lifts the line items off an invoice, a Language model classifies the accompanying email, and a generative model drafts the reply. By the end you will know which tool to reach for, how to ground it in your own data, and how to keep the whole pipeline accurate and cost-aware.
