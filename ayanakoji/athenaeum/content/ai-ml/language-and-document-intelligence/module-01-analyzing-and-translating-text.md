---
kind: module
id: ai-c02-m01
vertical: ai-ml
course_id: ai-c02
title: Analyzing and translating text
level: intermediate
grounded_on: "AI-102 skills outline (2025-12-23), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/ai-102
synthetic: true
order: 1
prereqs: [ai-c01]
objectives:
  - Extract key phrases and named entities from raw text
  - Determine sentiment and detect the language of text
  - Detect personally identifiable information and translate text and documents
---

# Analyzing and translating text

The support desk at Larkspur Outfitters, a fictional outdoor-gear retailer, receives a few thousand messages a day across email, chat, and a web form. They arrive in a dozen languages, some are furious and some are routine, many mention order numbers and the occasional credit card, and a human triages every one. That triage step is the bottleneck. Before you can route a message, redact what shouldn't be stored, or auto-reply in the customer's language, you have to make a machine understand a paragraph of free text. Azure AI Language gives you that understanding as a set of focused, deterministic operations — and Azure AI Translator handles the language barrier.

## Learning objectives

By the end of this module you will be able to:

- Extract key phrases and named entities from unstructured text and interpret the linked, categorized results.
- Determine document-level and aspect-level sentiment, and detect the dominant language of a passage.
- Detect and redact personally identifiable information so downstream systems never store it.
- Translate text between languages, including transliteration and language auto-detection, with Azure AI Translator.

## Concepts

### One resource, many skills

Azure AI Language is a single Azure resource that exposes a family of prebuilt skills over the same endpoint: language detection, key phrase extraction, named entity recognition (NER), entity linking, PII detection, and sentiment analysis. You authenticate once and choose the skill per call. Each skill takes a batch of *documents* — short objects with an `id`, the `text`, and an optional `language` hint — and returns a per-document result keyed by that same `id`. Batching matters: the service accepts multiple documents in one request, which cuts round-trips and cost, but each document has a character limit, so very long text must be chunked before you send it.

The mental model that keeps you out of trouble: these are *prebuilt classifiers and extractors*, not a chat model. They do not reason, follow instructions, or improvise. They return categories from a fixed taxonomy with confidence scores. That constraint is the feature — results are stable, fast, and cheap, which is exactly what you want for a triage step that runs millions of times.

### Entities, key phrases, and the difference between them

Key phrase extraction answers "what is this text *about*?" It returns the salient noun phrases — for a return request you might get `damaged tent pole`, `order number`, `refund`. It is unsupervised and needs no schema; it is ideal for tagging, search, and getting a quick sense of a corpus.

Named entity recognition answers "what specific *things* are named here, and what type is each?" It returns spans classified into categories such as Person, Location, Organization, DateTime, and Quantity, each with a confidence score and the character offset where it appears. Entity linking goes further and ties a recognized entity to a knowledge-base identifier so that "Surface" the device is disambiguated from "surface" the noun. Use NER when you need typed, positioned facts you can act on programmatically; use key phrases when you need a loose topical summary.

### Sentiment, PII, and why confidence scores are the point

Sentiment analysis classifies text as positive, neutral, negative, or mixed, and returns confidence scores for each class at both the document and sentence level. Opinion mining (aspect-based sentiment) goes deeper, attaching sentiment to specific targets — so "the tent was great but shipping was a disaster" yields positive sentiment toward *tent* and negative toward *shipping*. The scores are what make this usable: instead of trusting a single label, you set a threshold appropriate to the cost of being wrong. Auto-closing a ticket needs a higher bar than flagging one for review.

PII detection finds and categorizes sensitive spans — names, phone numbers, email addresses, and financial identifiers — and can return a redacted version of the text with those spans masked. The redaction is done by the service, so you can store the masked text and discard the original, which is the safe default when you are not certain you are allowed to retain raw customer data. As always, the categories come with confidence scores; treat low-confidence detections as candidates, not facts.

### Translation is a separate service

Language *detection* lives in Azure AI Language, but *translation* is Azure AI Translator, a distinct resource with its own endpoint and key. Translator can auto-detect the source language, translate into multiple target languages in one call, transliterate between scripts, and translate whole documents while preserving formatting. Because detection and translation are separate services, a real pipeline often calls Language to understand and route a message, then calls Translator to render a reply in the customer's language.

## Walkthrough: triaging a Larkspur Outfitters support message

Larkspur wants a triage function that, given one inbound message, returns its language, its sentiment, the entities it mentions, and a PII-redacted copy safe for logging. You provision an Azure AI Language resource, grant your identity the **Cognitive Services Language Reader** role (or use a key for local testing), and set the endpoint as an environment variable. Authenticating with `DefaultAzureCredential` means no secret lives in code.

```python
import os
from azure.identity import DefaultAzureCredential
from azure.ai.textanalytics import TextAnalyticsClient

endpoint = os.environ["LANGUAGE_ENDPOINT"]  # e.g. https://larkspur-lang.cognitiveservices.azure.com/
client = TextAnalyticsClient(endpoint=endpoint, credential=DefaultAzureCredential())

message = (
    "Hi, this is Dana Okafor. My order 88231 arrived with a snapped tent pole "
    "and I am furious. Call me at 555-0117 or dana.okafor@example.com."
)
docs = [{"id": "1", "text": message}]

language = client.detect_language(documents=docs)[0]
sentiment = client.analyze_sentiment(documents=docs)[0]
entities = client.recognize_entities(documents=docs)[0]
pii = client.recognize_pii_entities(documents=docs)[0]

print("Language:", language.primary_language.iso6391_name)
print("Sentiment:", sentiment.sentiment, sentiment.confidence_scores)
print("Entities:", [(e.text, e.category, round(e.confidence_score, 2)) for e in entities.entities])
print("Redacted:", pii.redacted_text)
```

Each call sends the same one-document batch and returns a per-document result. `detect_language` reports the dominant language (here English). `analyze_sentiment` returns a `negative` label with class confidences you can threshold on. `recognize_entities` surfaces typed spans like the person *Dana Okafor* and the quantity *88231*. `recognize_pii_entities` returns `redacted_text` with the name, phone, and email masked — that masked string is what you persist to your ticket log, while the raw message is dropped. To answer the customer in their own language, you would hand the original text to a Translator client; that crosses into the second half of this module's skill set and the next module's deployment patterns.

## Common pitfalls

- **Treating confidence scores as binary truth.** The services return probabilities, not verdicts. Auto-acting on a 0.55 sentiment score will misfire constantly. Pick thresholds tied to the cost of an error and route low-confidence results to a human.
- **Ignoring the per-document size limit.** Each document in a batch has a character cap. Sending a 50-page transcript as one document silently truncates or errors. Chunk long text and reconcile results yourself.
- **Logging raw text before redaction.** If you write the inbound message to logs *then* call PII detection, the sensitive data is already on disk. Redact first, persist the masked version, and never log the original.
- **Confusing language detection with translation.** Detection (in Language) tells you what language something is; it does not translate it. Translation is a separate Translator resource with its own key and endpoint — provision both if you need both.
- **Forgetting the `language` hint on mixed corpora.** When you know a document's language, pass it. Letting the service guess on short or code-switched text adds avoidable error to every downstream skill.

## Knowledge check

1. A teammate wants typed, positioned facts — names, dates, and order quantities — that the app will act on automatically. Should they use key phrase extraction or named entity recognition, and why?
2. Your pipeline must guarantee that customer phone numbers never reach your log store, even when detection is imperfect. Where in the flow do you call PII detection, and what do you persist?
3. A customer writes "the boots fit perfectly but the laces broke on day one." Plain document sentiment returns "mixed." How would you get sentiment attached to *boots* versus *laces* specifically?

<details>
<summary>Answers</summary>

1. Named entity recognition — it returns spans classified into types (Person, DateTime, Quantity) with offsets and confidence, which is what you need to act programmatically. Key phrases only tell you the loose topic, not typed, positioned facts. — NER is supervised and typed; key phrase extraction is unsupervised and topical.
2. Call PII detection *before* any logging, then persist only the `redacted_text` and discard the raw message. — Redacting after logging means the sensitive data already touched disk; redacting first makes the masked copy the only stored form.
3. Use opinion mining (aspect-based sentiment), which attaches sentiment to specific target terms rather than the whole document. — Document-level sentiment collapses opposing opinions into "mixed"; aspect-based analysis separates them per target.

</details>

## Summary

Azure AI Language is a set of fast, deterministic prebuilt skills — detection, key phrases, NER, PII, and sentiment — that turn free text into structured signal, while Azure AI Translator handles cross-language rendering as a separate service. The craft is in batching efficiently, thresholding on confidence rather than trusting labels, and redacting before you persist. With raw text now understandable, the next module, *Custom language models and question answering*, teaches you to train models on your own intents and sources when the prebuilt taxonomy isn't enough.

## Further learning

- [What is Azure AI Language?](https://learn.microsoft.com/en-us/azure/ai-services/language-service/overview)
- [Personally identifiable information (PII) detection](https://learn.microsoft.com/en-us/azure/ai-services/language-service/personally-identifiable-information/overview)
- [Sentiment analysis and opinion mining](https://learn.microsoft.com/en-us/azure/ai-services/language-service/sentiment-opinion-mining/overview)
- [What is Azure AI Translator?](https://learn.microsoft.com/en-us/azure/ai-services/translator/translator-overview)
