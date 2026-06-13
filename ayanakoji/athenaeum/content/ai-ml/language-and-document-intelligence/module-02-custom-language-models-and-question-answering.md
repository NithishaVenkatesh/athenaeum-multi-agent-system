---
kind: module
id: ai-c02-m02
vertical: ai-ml
course_id: ai-c02
title: Custom language models and question answering
level: intermediate
grounded_on: "AI-102 skills outline (2025-12-23), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/ai-102
synthetic: true
order: 2
prereqs: [ai-c02-m01]
objectives:
  - Design intents, entities, and utterances for a conversational understanding model
  - Train, evaluate, deploy, and test a language understanding model
  - Build a custom question answering knowledge base from your own sources
---

# Custom language models and question answering

The prebuilt skills from *Analyzing and translating text* are powerful, but they only know the world's general categories. Larkspur Outfitters' new voice assistant needs to understand *Larkspur's* world: a customer saying "where's my stuff" and "track package 88231" both mean the same thing, `CheckOrderStatus`, and the assistant must pull the order number out as a typed slot. No prebuilt model knows that intent exists. And when a customer asks "how long do I have to return a tent?", the assistant should answer from Larkspur's actual return policy, not guess. Those are two different custom-modeling jobs — conversational language understanding and custom question answering — and this module builds both.

## Learning objectives

By the end of this module you will be able to:

- Model a domain as intents, entities, and labeled utterances for a conversational language understanding (CLU) project.
- Train a CLU model, read its evaluation metrics, and deploy it to a named deployment slot for runtime prediction.
- Build a custom question answering project by importing sources and adding question-and-answer pairs.
- Choose correctly between intent classification and question answering for a given problem.

## Concepts

### The shape of a CLU project: intents, entities, utterances

Conversational Language Understanding (CLU) is a feature of Azure AI Language for building models that map a user's sentence to a structured meaning. Three things define a project. An **intent** is what the user wants to do — `CheckOrderStatus`, `StartReturn`, `Greeting`. An **entity** is a piece of information to extract — an `OrderNumber`, a `ProductName`, a `DateRange`. An **utterance** is an example sentence a real user might say, labeled with its intent and with the entity spans marked inside it.

The model learns from your labeled utterances, so coverage and variety are everything. Ten near-identical phrasings of one intent teach the model less than ten genuinely different ones. You want utterances that span the slang, typos, and word orders your real users produce. Entities can be learned from labeled examples, defined by a fixed list of values and synonyms, matched by a regular expression, or built from prebuilt types — and you can combine these so an `OrderNumber` is recognized both by pattern and by where it appears in a sentence.

### Train, evaluate, deploy — the lifecycle that keeps you honest

You do not ship a model because training succeeded; you ship it because evaluation says it generalizes. CLU splits your utterances into a training set and a testing set and, after training, reports per-intent and per-entity metrics — precision, recall, and F1 — plus a confusion matrix showing which intents the model mixes up. If `StartReturn` and `CheckOrderStatus` are being confused, the fix is almost always more and clearer utterances at the boundary, not more training.

Critically, training and deployment are separate steps. A trained model lives inside the project; it does not serve traffic until you **deploy** it to a named deployment (for example `production`). The runtime prediction call targets a project *and* a deployment name, which lets you train a v2 model, evaluate it, and swap it into the `production` deployment only when its metrics beat v1 — a clean, reversible release.

### Custom question answering is retrieval, not classification

Custom question answering solves a different problem: given a user question, return the best matching answer from a curated knowledge base. You build the knowledge base by **importing sources** — a published FAQ URL, a policy document, or a structured file — which the service parses into question-and-answer pairs, and by **adding pairs manually** for things no document covers. You can attach alternate phrasings to a pair so "what's your return window?" and "how many days to send something back?" both hit the same answer, and you can add follow-up prompts to build multi-turn flows.

The distinction that trips people up: CLU decides *what the user wants to do* and extracts slots; question answering *retrieves a stored answer*. "Track my order" is an intent for CLU to classify and route to your order API. "What is the return policy?" is a question for QnA to answer from your sources. Many assistants use both — CLU as the router, question answering as one of the things it can route to.

### Grounded answers and confidence

Like the prebuilt skills, question answering returns a confidence score with each candidate answer. You set a threshold below which the assistant says "I'm not sure, let me connect you to an agent" rather than returning a weak match. This is how you keep a knowledge-base bot from confidently answering questions it has no real source for — the same discipline of thresholding on confidence you learned for sentiment and PII.

## Walkthrough: routing and answering at Larkspur

Assume you have already authored a CLU project named `larkspur-clu` in the portal — intents `CheckOrderStatus`, `StartReturn`, and `Greeting`, an `OrderNumber` entity, and a few dozen labeled utterances — and trained and deployed it to a deployment called `production`. Now you call it at runtime to classify an inbound sentence and read back the predicted intent and extracted entities.

```python
import os
from azure.core.credentials import AzureKeyCredential
from azure.ai.language.conversations import ConversationAnalysisClient

endpoint = os.environ["LANGUAGE_ENDPOINT"]
client = ConversationAnalysisClient(endpoint, AzureKeyCredential(os.environ["LANGUAGE_KEY"]))

result = client.analyze_conversation(
    task={
        "kind": "Conversation",
        "analysisInput": {
            "conversationItem": {
                "id": "1",
                "participantId": "user",
                "text": "track package 88231 please",
            }
        },
        "parameters": {
            "projectName": "larkspur-clu",
            "deploymentName": "production",
        },
    }
)

prediction = result["result"]["prediction"]
print("Top intent:", prediction["topIntent"])
for entity in prediction["entities"]:
    print("Entity:", entity["category"], "->", entity["text"], round(entity["confidenceScore"], 2))
```

The call targets the project *and* the `production` deployment, which is why you could retrain without disturbing live traffic. The response gives `topIntent` — here `CheckOrderStatus` — and an entities list containing the `OrderNumber` `88231` with its confidence. Your application code then branches on the intent: `CheckOrderStatus` calls the order API with the extracted number, while a question like "what's your return window?" would instead be sent to your custom question answering deployment, whose response carries the best-matching answer and a confidence score you threshold on before showing it.

## Common pitfalls

- **Too few or too similar utterances.** A model trained on narrow examples overfits to phrasings it has seen. Collect varied, realistic utterances — including the awkward ones — for every intent, especially near intents that get confused.
- **Forgetting that training is not deployment.** A freshly trained model serves no traffic until you deploy it to a named slot, and your runtime call must pass that deployment name. Skipping deployment yields confusing "model not found" errors.
- **Using CLU where you need question answering (or vice versa).** Classifying "what is the return policy?" as an intent forces you to hand-write the answer in code; storing "track my order" as a QnA pair gives you no slot extraction. Match the tool to whether you need an action or a stored answer.
- **Shipping without reading the evaluation metrics.** Confusion between two intents is visible in the evaluation results before it ever reaches a user. Inspect precision/recall and the confusion matrix; fix the data, then retrain.
- **No low-confidence fallback.** Both CLU and question answering return scores. Without a threshold and a graceful "I'm not sure" path, the assistant will act on or answer with weak predictions.

## Knowledge check

1. Your assistant must handle "where is order 88231" by calling your shipping API with the number extracted, and "how do refunds work?" by stating your policy. Which feature handles each, and why?
2. You retrain your CLU model and its evaluation looks strong, but you want zero risk to live users during rollout. What deployment strategy makes the switch safe and reversible?
3. Evaluation shows `StartReturn` and `CheckOrderStatus` are frequently confused. What is the most effective fix, and why is "train for more epochs" usually not it?

<details>
<summary>Answers</summary>

1. CLU handles "where is order 88231" — it classifies the `CheckOrderStatus` intent and extracts the `OrderNumber` slot to pass to the API; custom question answering handles "how do refunds work?" by retrieving the stored policy answer. — One needs an action plus slot extraction; the other needs a curated answer.
2. Train and evaluate the new model, then deploy it to a *separate or staged* deployment slot and only point the `production` deployment name at it once metrics beat the current version — you can revert by repointing. — Deployments are named and decoupled from training, enabling reversible release.
3. Add more varied, clearly distinguished utterances at the boundary between the two intents and retrain. — Confusion comes from ambiguous or sparse training data, not from undertraining; more epochs on bad data just memorizes the ambiguity.

</details>

## Summary

CLU and custom question answering are the two ways to teach Azure AI Language *your* domain: CLU classifies intent and extracts entities so your app can act, while question answering retrieves curated answers from your sources. Both follow the same disciplined lifecycle — label well, evaluate honestly, deploy to a named slot, and threshold on confidence with a graceful fallback. With text understood and your custom models in place, the next module, *Document Intelligence*, moves from sentences to scanned and structured documents, where layout and fields matter as much as words.

## Further learning

- [What is conversational language understanding (CLU)?](https://learn.microsoft.com/en-us/azure/ai-services/language-service/conversational-language-understanding/overview)
- [What is custom question answering?](https://learn.microsoft.com/en-us/azure/ai-services/language-service/question-answering/overview)
- [Train and evaluate a CLU model](https://learn.microsoft.com/en-us/azure/ai-services/language-service/conversational-language-understanding/how-to/train-model)
- [Create a knowledge base and add sources](https://learn.microsoft.com/en-us/azure/ai-services/language-service/question-answering/how-to/create-test-deploy)
