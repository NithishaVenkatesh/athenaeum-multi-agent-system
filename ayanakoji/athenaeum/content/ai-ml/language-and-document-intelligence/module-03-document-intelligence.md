---
kind: module
id: ai-c02-m03
vertical: ai-ml
course_id: ai-c02
title: Document Intelligence
level: intermediate
grounded_on: "AI-102 skills outline (2025-12-23), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/ai-102
synthetic: true
order: 3
prereqs: [ai-c02-m01]
objectives:
  - Use prebuilt models to extract structured data from common document types
  - Train, test, and publish a custom document model on your own layouts
  - Compose multiple custom models to classify and route mixed document types
---

# Document Intelligence

Larkspur Outfitters' accounts-payable team drowns in paper. Every week, supplier invoices, shipping receipts, and warranty claim forms arrive as scans and PDFs, and someone keys the totals, dates, and line items into the finance system by hand. The text-analysis skills you have so far operate on clean strings; they cannot find the "Total Due" box on a crumpled invoice or read a table that wraps across a page. That is the job of Azure AI Document Intelligence: it understands a document's *layout* — where text sits, what is a table, which value pairs with which label — and returns it as structured, typed fields you can write straight into a database.

## Learning objectives

By the end of this module you will be able to:

- Provision a Document Intelligence resource and call prebuilt models to extract fields from invoices, receipts, and IDs.
- Decide when a prebuilt model suffices and when you must train a custom model on your own document layout.
- Label, train, test, and publish a custom extraction model, then call it at runtime.
- Compose several custom models behind one endpoint so a classifier routes each incoming document to the right extractor.

## Concepts

### Layout is the foundation; prebuilt models are the shortcut

Under every Document Intelligence model is layout analysis: optical character recognition plus structural understanding that locates words, lines, selection marks (checkboxes), and tables, each with a bounding region and a confidence score. The **prebuilt models** sit on top of that and add a trained schema for a common document class — invoices, receipts, identity documents, business cards, tax forms, and a general document model. When your document is one of those standard types, you get named fields like `InvoiceTotal`, `VendorName`, and a typed `Items` array for free, with no training at all.

Prebuilt models return more than a flat value: each field carries its extracted content, a normalized typed value where applicable (a date as a date, currency as a number plus code), and a confidence score. Confidence is your quality gate — a `0.98` total can post automatically; a `0.62` total routes to a human. This is the same thresholding discipline that runs through the whole course.

### When prebuilt isn't enough: custom extraction models

Larkspur's own warranty claim form is not a standard invoice — it has fields no prebuilt model knows, like `ClaimReason` and `PurchaseStore`. For documents specific to your organization, you train a **custom extraction model**. You upload a handful of example documents to storage, label the fields you care about by drawing on the document in Document Intelligence Studio, and train. The service learns the field positions and patterns from your labels.

There are two flavors worth knowing conceptually. A **template** custom model learns from consistent layouts and needs only a few examples; it is fast and precise when every form looks the same. A **neural** custom model handles varied layouts and structured-plus-unstructured content at the cost of needing more training data and time. Choose template for rigid forms, neural when the same logical document arrives in many visual shapes. Exact minimum sample counts and supported field types shift over time — verify the current requirements in the docs before you size a labeling effort.

### Train, test, publish — and version with model IDs

A custom model's lifecycle mirrors the CLU lifecycle from the previous module, but the unit of versioning is the **model ID**. You train a model and give it an ID, test it against documents it has never seen, and only then treat it as published for runtime use. Because every model has its own ID, you can train an improved `warranty-claim-v2`, validate it, and switch your application to call it without touching `warranty-claim-v1` — a clean rollback path if the new one underperforms.

### Composed models route mixed mailbags

Larkspur's intake folder mixes invoices, receipts, and warranty claims in one stream, and you do not know which is which until you open it. A **composed model** solves this: it bundles several custom models behind a single model ID and puts a classifier in front. At runtime you call the one composed model; it identifies the document type, then runs the matching sub-model and returns that model's fields. This turns "open it, figure out what it is, pick the right extractor" into a single call — the document equivalent of the CLU router you built for text.

## Walkthrough: extracting an invoice at Larkspur AP

Start with the prebuilt invoice model so the AP team gets value on day one, before any custom training. You provision a Document Intelligence resource, assign your identity a reader role (or use a key locally), and point the client at a supplier invoice reachable by URL.

```python
import os
from azure.identity import DefaultAzureCredential
from azure.ai.documentintelligence import DocumentIntelligenceClient

endpoint = os.environ["DOCINTEL_ENDPOINT"]
client = DocumentIntelligenceClient(endpoint, DefaultAzureCredential())

invoice_url = "https://larkspur-intake.example.com/invoices/sup-4471.pdf"
poller = client.begin_analyze_document(
    "prebuilt-invoice",
    {"urlSource": invoice_url},
)
result = poller.result()

for doc in result.documents:
    fields = doc.fields
    vendor = fields.get("VendorName")
    total = fields.get("InvoiceTotal")
    if vendor:
        print("Vendor:", vendor.get("valueString"), "conf", round(vendor.get("confidence", 0), 2))
    if total:
        amount = total.get("valueCurrency", {})
        print("Total:", amount.get("amount"), amount.get("currencyCode"),
              "conf", round(total.get("confidence", 0), 2))
```

`begin_analyze_document` is a long-running operation — analysis is asynchronous, so you get a poller and call `.result()` to wait for completion. You pass the model ID `prebuilt-invoice`; for your own form you would pass your custom model's ID, and for the mailbag you would pass the composed model's ID instead. Each returned field exposes a typed value (`valueString`, `valueCurrency`, `valueDate`) and a `confidence` score. The AP automation reads `InvoiceTotal`: above your threshold it posts to finance automatically; below it, the invoice lands in a review queue with the low-confidence field highlighted. Once the prebuilt model is paying off, you repeat the lifecycle for the warranty form — label, train, test, publish a custom model ID — and finally compose invoice, receipt, and warranty models so the single intake call self-routes.

## Common pitfalls

- **Reaching for a custom model when a prebuilt one fits.** If your documents are standard invoices or receipts, training your own is wasted effort and worse accuracy. Try the prebuilt model first; only go custom for organization-specific layouts.
- **Treating analysis as synchronous.** `begin_analyze_document` returns a poller, not the answer. Forgetting to call `.result()` (or not awaiting it) leaves you reading an unfinished operation.
- **Labeling too few or too uniform samples.** A custom model generalizes only as well as its labeled examples represent reality. One pristine sample teaches little; include the skewed scans and edge cases. Confirm current minimum sample counts in the docs.
- **Ignoring per-field confidence.** A document can return overall, while one critical field — the total — is low confidence. Gate on the *fields you act on*, not just the document, and route those to review.
- **Choosing template vs neural blindly.** Template models excel on fixed layouts with few samples; neural models handle layout variation but need more data. Picking the wrong one wastes a labeling cycle — match the model type to how much your documents vary.

## Knowledge check

1. Larkspur receives standard supplier invoices and its own bespoke warranty forms. Which model type fits each, and why not use one approach for both?
2. Your code calls `begin_analyze_document` and immediately inspects the response object, but the fields are empty. What did you forget, and why does it matter for this service?
3. The intake folder contains a random mix of invoices, receipts, and warranty claims with no labels telling you which is which. How do you process them with a single runtime call?

<details>
<summary>Answers</summary>

1. Use the prebuilt invoice model for standard invoices (no training, named fields out of the box) and a custom extraction model for the bespoke warranty form (fields no prebuilt model knows). — Prebuilt covers common types; custom is for org-specific layouts, and forcing one approach onto both costs accuracy or wasted training.
2. You forgot to wait on the long-running operation — call `.result()` on the poller. — Document analysis is asynchronous; the poller is not the finished result, so reading it early yields nothing.
3. Build a composed model that bundles the three custom/prebuilt models behind one model ID; its classifier identifies each document and runs the matching extractor. — Composition turns "detect type, then extract" into a single call over a mixed stream.

</details>

## Summary

Document Intelligence reads structure, not just text: layout analysis underpins prebuilt models for common documents, custom extraction models for your own forms, and composed models that classify and route mixed streams. The working pattern is to start with a prebuilt model, train custom models only where your layouts demand it, version by model ID for safe rollouts, and always gate on per-field confidence. With text and documents both structured, the final module, *Speech and translation solutions*, extends the same intelligence to spoken audio.

## Further learning

- [What is Azure AI Document Intelligence?](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/overview)
- [Prebuilt models](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/concept-model-overview)
- [Build and train a custom extraction model](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/train/custom-model)
- [Compose custom models](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/train/composed-models)
