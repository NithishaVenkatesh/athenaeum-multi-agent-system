---
kind: module
id: ai-c01-m03
vertical: ai-ml
course_id: ai-c01
title: Retrieval-augmented generation (RAG)
level: foundational
grounded_on: "AI-102 skills outline (2025-12-23), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/ai-102
synthetic: true
order: 3
prereqs: [ai-c01-m02]
objectives:
  - Implement a retrieval-augmented generation pattern that grounds a model in your own data
  - Design a chunking and retrieval strategy that returns relevant, citable context
  - Construct grounded prompts that instruct the model to answer only from retrieved context and cite sources
---

# Retrieval-augmented generation (RAG)

Northwind's assistant now declines questions it cannot answer — which is honest, but not
useful when a customer asks "Is the Summit 40L pack covered by your repair warranty?" and the
answer is sitting in a PDF in the support team's shared drive. The base model has never seen
Northwind's actual policies, product catalog, or warranty terms; those are private and were not
in its training data. You cannot prompt your way to facts the model does not have. The pattern
that fixes this is retrieval-augmented generation: at request time you *retrieve* the relevant
private text and *insert* it into the prompt, so the model answers from your data instead of
from memory. This builds directly on the templating from *Prompt engineering and templates* —
RAG is, mechanically, a template with a context slot you fill from a search.

## Learning objectives

By the end of this module you will be able to:

- Explain the retrieve-then-generate flow and why it reduces hallucination compared with prompting alone.
- Chunk source documents and embed them so that relevant passages can be retrieved by meaning, not just keyword.
- Retrieve top-matching chunks for a query and assemble them into a grounded prompt.
- Instruct the model to answer only from the supplied context and to cite which source it used.

## Concepts

### Why grounding beats memorization

A language model's knowledge is frozen at training time and is general, not yours. Two problems
follow: it does not know your private or current facts, and when asked anyway it tends to
generate fluent guesses. RAG addresses both by changing where the facts come from. Instead of
hoping the answer is latent in the weights, you fetch authoritative text for *this* question and
hand it to the model with an instruction to answer from it. The model's job narrows from
"recall the answer" to "read this passage and summarize the relevant part" — a task it does well
and a task you can verify, because you know which source it was given.

### Embeddings and retrieval by meaning

The retrieval step needs to find passages that are *relevant* to a question, and relevance is
about meaning, not shared keywords — "return window" should match a paragraph about "how long
you have to send items back." This is what embeddings provide. An embedding model converts a
piece of text into a vector of numbers that positions it in a high-dimensional space where
semantically similar text lands nearby. You embed every chunk of your documents once and store
the vectors. At query time you embed the question and find the chunks whose vectors are closest,
typically by cosine similarity. In production you would store these vectors in a vector index —
Azure AI Search and Azure Cosmos DB both offer vector search, and you will meet AI Search
properly in *Computer Vision & Knowledge Mining*. The concept is independent of the store:
embed, index, and retrieve nearest neighbors.

### Chunking: the decision that quietly determines quality

You cannot embed an entire 40-page warranty PDF as one vector and expect precise retrieval, and
you cannot fit it all into one prompt. You split documents into **chunks**. Chunk size is a
trade-off that most teams underweight. Chunks that are too large dilute relevance — the matching
vector represents a paragraph buried in unrelated text, and you waste prompt tokens on noise.
Chunks that are too small fragment ideas, so the retrieved piece lacks the surrounding context
needed to answer. A common, sensible starting point is a few hundred tokens per chunk with a
small overlap between consecutive chunks so a sentence split across a boundary is not lost. Keep
metadata with each chunk — the source document and section — because that is what lets the model
cite where an answer came from.

### Assembling the grounded prompt

The final step reuses your templating skill. You build a prompt that contains: the retrieved
chunks (clearly delimited, each tagged with its source), the user's question, and a system
instruction that is the heart of RAG — *answer only using the provided context; if the context
does not contain the answer, say so; cite the source you used.* Without that instruction the
model will happily blend retrieved facts with its own guesses, which defeats the purpose.
Grounding is the retrieval plus the instruction to stay within it.

## Walkthrough: grounding the Northwind assistant in policy docs

You will build a minimal end-to-end RAG flow over Northwind's support documents. To keep the
example self-contained and runnable, retrieval is done in-memory with cosine similarity; in
production you would swap the in-memory store for a vector index, leaving the rest unchanged.

```python
import os
import numpy as np
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import AzureOpenAI

token_provider = get_bearer_token_provider(
    DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default"
)
client = AzureOpenAI(
    azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
    azure_ad_token_provider=token_provider,
    api_version="2024-10-21",  # verify current API version in the docs
)

# Each chunk carries its source so answers can be cited.
CHUNKS = [
    {"source": "returns-policy.md", "text": "Unused gear may be returned within 30 days of delivery for a full refund."},
    {"source": "warranty.md", "text": "The Summit 40L pack carries a 2-year repair warranty covering stitching and zipper defects."},
    {"source": "shipping.md", "text": "Standard shipping is free on orders over $75 and takes 3-5 business days."},
]

def embed(text: str) -> np.ndarray:
    # Use a deployed EMBEDDING model (a separate deployment from the chat model).
    resp = client.embeddings.create(model="support-embed", input=text)
    return np.array(resp.data[0].embedding)

# Embed chunks once (in production: store these vectors in a vector index).
CHUNK_VECTORS = [(c, embed(c["text"])) for c in CHUNKS]

def retrieve(question: str, k: int = 2):
    q = embed(question)
    scored = [
        (c, float(np.dot(q, v) / (np.linalg.norm(q) * np.linalg.norm(v))))
        for c, v in CHUNK_VECTORS
    ]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [c for c, _ in scored[:k]]

def grounded_answer(question: str) -> str:
    context = "\n".join(f"[{c['source']}] {c['text']}" for c in retrieve(question))
    messages = [
        {"role": "system", "content": (
            "Answer the customer's question using ONLY the context below. "
            "If the context does not contain the answer, say you don't know. "
            "Cite the source in brackets, e.g. [warranty.md].\n\n"
            f"Context:\n{context}"
        )},
        {"role": "user", "content": question},
    ]
    resp = client.chat.completions.create(
        model="support-chat", messages=messages, temperature=0.1, max_tokens=200
    )
    return resp.choices[0].message.content

print(grounded_answer("Is the Summit 40L pack covered by a repair warranty?"))
```

Run it. The question embeds, the warranty chunk scores highest, and the model answers from that
passage with a `[warranty.md]` citation. Ask something the chunks do not cover — "Do you sell
gift cards?" — and the assistant says it does not know, because the instruction forbids answering
beyond the retrieved context. Notice the embedding model uses its own deployment (`support-embed`),
deployed separately as discussed in the first module.

## Common pitfalls

- **Skipping the "answer only from context" instruction.** Retrieving the right text but not constraining the model lets it mix retrieved facts with hallucinated ones. The instruction is what makes it grounding rather than decoration.
- **One-size chunking.** Giant chunks dilute relevance and burn tokens; tiny chunks lose context. Tune chunk size and overlap to your documents and test retrieval quality directly.
- **Forgetting source metadata.** If chunks do not carry their origin, the model cannot cite and you cannot audit answers. Attach source and section to every chunk from the start.
- **Mixing up the model families.** Embeddings and chat are different deployments. Calling the chat deployment for `embeddings.create` (or vice versa) fails; deploy and reference each correctly.
- **Retrieving too many or too few chunks.** Too few and the answer may not be present; too many and you bury the relevant passage in noise and overflow the context. Tune `k` and measure.

## Knowledge check

1. The base model refuses a question whose answer lives in a private PDF. Why does adding retrieval solve this when better prompting alone cannot?
2. Your RAG system retrieves the correct passage but the model still occasionally adds invented details. Which part of the pipeline is at fault and how do you fix it?
3. Why is chunk size described as a quality decision rather than a formatting detail? Give one failure mode for chunks that are too large and one for chunks that are too small.

<details>
<summary>Answers</summary>

1. The fact is not in the model's training data, so no prompt can extract it — there is nothing to extract. Retrieval *injects* the authoritative text into the prompt at request time, changing the task from "recall" to "read and summarize," which the model can do and you can verify.
2. The **grounding instruction** in the prompt. Retrieval is working, but without a strict "answer only from the provided context, otherwise say you don't know" instruction the model blends context with its own guesses. Tighten the instruction (and keep temperature low).
3. Because chunk size directly controls retrieval relevance and answer completeness. Too-large chunks dilute the embedding so matches are imprecise and waste prompt tokens on irrelevant text; too-small chunks fragment an idea so the retrieved piece lacks the context needed to answer.

</details>

## Summary

RAG grounds a model in facts it never learned by retrieving relevant private text and inserting
it into the prompt, with a strict instruction to answer only from that context and cite the
source. The quality of a RAG system is set less by the model than by the retrieval design —
chunking, embeddings, and how many passages you pull — and by the grounding instruction that
keeps the model inside the evidence. With grounding in place, the assistant is genuinely useful
and auditable. What remains is proving it stays correct and safe over time: the next module,
*Evaluation, monitoring, and responsible AI*, covers measuring quality and applying safety
controls in production.

## Further learning

- [Retrieval Augmented Generation (RAG) in Azure AI Foundry](https://learn.microsoft.com/en-us/azure/ai-foundry/concepts/retrieval-augmented-generation)
- [Azure OpenAI On Your Data](https://learn.microsoft.com/en-us/azure/ai-services/openai/concepts/use-your-data)
- [Understand embeddings in Azure OpenAI](https://learn.microsoft.com/en-us/azure/ai-services/openai/concepts/understand-embeddings)
- [Vector search in Azure AI Search](https://learn.microsoft.com/en-us/azure/search/vector-search-overview)
