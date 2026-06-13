---
kind: module
id: ai-c01-m02
vertical: ai-ml
course_id: ai-c01
title: Prompt engineering and templates
level: foundational
grounded_on: "AI-102 skills outline (2025-12-23), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/ai-102
synthetic: true
order: 2
prereqs: [ai-c01-m01]
objectives:
  - Apply prompt engineering techniques — clear instructions, role framing, and few-shot examples — to make responses reliable
  - Configure generation parameters such as temperature, max tokens, and stop sequences to control output behavior
  - Build reusable prompt templates that separate fixed instructions from per-request input
---

# Prompt engineering and templates

Northwind's `support-chat` deployment answers questions now, but the answers are
inconsistent. Ask it the return policy three times and you get three different tones,
two different lengths, and one answer that helpfully invents a "platinum member exception"
that does not exist. The model is not broken — it is doing exactly what an underspecified
prompt asks it to do, which is to produce *something plausible*. The skill that turns a
chat model into a dependable component is prompt engineering: giving the model enough
structure that its output is consistent, correctly scoped, and shaped the way your code
downstream expects. This assumes you can already call the deployment from *Provisioning and
deploying models in Microsoft Foundry*; here you make that call behave.

## Learning objectives

By the end of this module you will be able to:

- Write system and user messages that constrain scope, set tone, and reduce hallucination through explicit instruction.
- Use few-shot examples to teach output format and edge-case handling without fine-tuning.
- Configure `temperature`, `top_p`, `max_tokens`, and stop sequences, and predict their effect on output.
- Factor prompts into reusable templates that keep fixed instructions separate from variable per-request data.

## Concepts

### The message roles and why the system prompt does the heavy lifting

A chat request is a list of messages, each with a role. The **system** message sets durable
behavior — who the assistant is, what it may and may not do, the tone and format. The **user**
message carries the specific request. The model also produces **assistant** messages, and you
can include prior assistant turns to give it conversational memory.

The system message is your strongest lever and the most underused. "You are a support
assistant" is nearly useless. A system prompt that says *who* the assistant is, *what it is
allowed to answer*, *what to do when it does not know*, and *how to format the answer* removes
most of the variance that frustrated the Northwind team. The decisive instruction is usually
the refusal clause: telling the model to say it does not know rather than guess is what stops
the invented "platinum exception." Models are eager to be helpful; absent a boundary, eagerness
becomes fabrication.

### Few-shot examples teach format and judgment

When you need a specific output *shape* — a JSON object, a fixed set of fields, a particular
escalation rule — describing it in prose is less reliable than *showing* it. Few-shot prompting
includes a handful of example input/output pairs in the prompt. The model infers the pattern
and follows it. Two or three well-chosen examples that cover the normal case and an edge case
(a question the assistant should decline, a malformed request) often outperform a long
paragraph of instructions, because the model generalizes from demonstrations more reliably than
from description. The cost is tokens: examples sit in every request, so keep them tight.

### Parameters: shaping the probability distribution

The model generates one token at a time by sampling from a probability distribution over
possible next tokens. The generation parameters reshape that sampling.

- **`temperature`** scales how much randomness you allow. Near `0`, the model almost always
  picks the most probable token — output is focused and repeatable, which is what you want for
  factual support answers. Higher values flatten the distribution, producing more varied and
  creative (and less predictable) output.
- **`top_p`** (nucleus sampling) restricts choices to the smallest set of tokens whose combined
  probability reaches `p`. It is an alternative knob for the same diversity dial; the common
  guidance is to tune one of `temperature` or `top_p`, not both at once.
- **`max_tokens`** caps the length of the *completion*. Set it deliberately — too low truncates
  answers mid-sentence; unset, a verbose answer can balloon cost and latency.
- **Stop sequences** tell the model to halt when it emits a given string, useful for keeping it
  from running past a structured boundary.

For Northwind's support answers, low temperature plus a sensible `max_tokens` is the right
default: you want correctness and consistency, not creativity.

### Templates separate the stable from the variable

Once a prompt works, you do not want it retyped and quietly mutated across the codebase. A
prompt **template** is a parameterized string: the fixed instruction text lives in one place,
and per-request values (the customer's question, retrieved context, the order ID) are slotted
in at call time. This keeps prompts versionable, testable, and consistent, and it is the seam
where the next module's retrieved context will be injected. Treat your prompts as code: one
source of truth, reviewed and changed deliberately.

## Walkthrough: making Northwind's assistant consistent

You will take the inconsistent assistant and pin it down with a structured system prompt, one
few-shot example, deterministic parameters, and a reusable template.

```python
import os
from string import Template
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

# A reusable template: fixed instructions, with a slot for the live question.
SYSTEM_PROMPT = (
    "You are Northwind Outfitters' support assistant. "
    "Answer only questions about orders, returns, shipping, and gear care. "
    "If a question is outside that scope or you are not certain of the answer, "
    "say you don't know and offer to connect the customer to a human agent. "
    "Never invent policies, exceptions, or membership tiers. "
    "Answer in at most three sentences, in a warm, plain tone."
)

USER_TEMPLATE = Template("Customer question: $question")

def answer(question: str) -> str:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        # One few-shot example showing the desired refusal behavior:
        {"role": "user", "content": "Customer question: Can you recommend a stock to invest in?"},
        {"role": "assistant", "content": "I can only help with Northwind orders, returns, shipping, and gear care. I'd be happy to connect you with a human agent for anything else."},
        {"role": "user", "content": USER_TEMPLATE.substitute(question=question)},
    ]
    resp = client.chat.completions.create(
        model="support-chat",
        messages=messages,
        temperature=0.2,   # low: consistent, factual answers
        max_tokens=200,    # cap length to control cost and truncation
    )
    return resp.choices[0].message.content

print(answer("What is your return window for unused gear?"))
print(answer("Do you have a platinum members' exception?"))
```

Run it and ask the return-policy question several times: the answers are now consistent in
tone and length. Ask the "platinum exception" question and the assistant declines instead of
inventing one, because the system prompt forbade fabricated tiers and the few-shot example
demonstrated the refusal. The variable part — the customer's question — flows through one
template, so there is a single place to evolve the prompt.

## Common pitfalls

- **A vague system prompt.** "You are a helpful assistant" delegates every decision to the model. Specify scope, refusal behavior, and format explicitly; that is where consistency comes from.
- **No "I don't know" instruction.** Without permission to decline, the model fills gaps with confident fabrication. An explicit refusal clause is the single highest-leverage line against hallucination.
- **Cranking temperature for "better" answers.** High temperature adds variety, not accuracy. For factual tasks, low temperature is correct; reserve higher values for genuinely creative generation.
- **Tuning `temperature` and `top_p` together.** They control overlapping behavior. Adjust one and leave the other at its default, or you will chase confusing interactions.
- **Scattering prompt strings across the codebase.** Inline, duplicated prompts drift apart and become untestable. Centralize them in templates so a prompt change is one reviewed edit.

## Knowledge check

1. A support assistant keeps inventing plausible-but-false policies when asked about edge cases. Which prompt change attacks this most directly, and why is it more effective than lowering temperature?
2. You need the assistant to return answers as a JSON object with fixed fields. Would you more reliably get this by describing the format in prose or by including few-shot examples, and why?
3. For Northwind's factual support answers, you set `temperature=0.2` and `max_tokens=200`. Explain what each setting buys you and what would go wrong if you set `temperature=1.2` instead.

<details>
<summary>Answers</summary>

1. Add an explicit instruction to **say "I don't know" and not invent policies** (a refusal clause in the system prompt). Lowering temperature only makes the model more *consistent*; it does not stop fabrication, because a confidently wrong answer can be the highest-probability token. The boundary instruction removes the behavior itself.
2. **Few-shot examples.** Showing the model two or three input/output pairs in the exact JSON shape teaches the format more reliably than prose, because models follow demonstrated patterns more faithfully than described ones.
3. `temperature=0.2` keeps answers focused and repeatable (the model nearly always picks high-probability tokens), which is what factual support needs; `max_tokens=200` caps length to prevent truncation surprises and runaway cost. At `temperature=1.2` the distribution flattens, so answers become inconsistent and more prone to drifting off-task or fabricating.

</details>

## Summary

Prompt engineering is how you convert a probabilistic model into a predictable component:
a precise system prompt sets scope and refusal behavior, few-shot examples teach format and
judgment, parameters like temperature and `max_tokens` control variability and length, and
templates keep all of it as versioned, single-source code. The refusal clause is your strongest
defense against hallucination — but only against questions the model could never answer. To make
it answer *your* facts correctly, you need to give it those facts at request time. That is
retrieval-augmented generation, the subject of the next module, *Retrieval-augmented generation
(RAG)*.

## Further learning

- [Prompt engineering techniques with Azure OpenAI](https://learn.microsoft.com/en-us/azure/ai-services/openai/concepts/prompt-engineering)
- [How to work with chat completions and the Chat Completions API](https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to/chatgpt)
- [Azure OpenAI request parameters reference](https://learn.microsoft.com/en-us/azure/ai-services/openai/reference)
- [System message design and safety guidance](https://learn.microsoft.com/en-us/azure/ai-services/openai/concepts/system-message)
