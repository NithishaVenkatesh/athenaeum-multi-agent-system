---
kind: module
id: ai-c01-m01
vertical: ai-ml
course_id: ai-c01
title: Provisioning and deploying models in Microsoft Foundry
level: foundational
grounded_on: "AI-102 skills outline (2025-12-23), paraphrased — original synthetic content"
source_url: https://learn.microsoft.com/en-us/credentials/certifications/resources/study-guides/ai-102
synthetic: true
order: 1
prereqs: []
objectives:
  - Provision an Azure OpenAI resource in Microsoft Foundry and understand what it does and does not give you
  - Select and deploy a model under a deployment name your application code can target
  - Call the deployed model from Python using a managed-identity-friendly credential and the SDK
---

# Provisioning and deploying models in Microsoft Foundry

The team at Northwind Outfitters has decided to build a support assistant that can answer
customer questions about orders, returns, and gear. Someone pasted a model API key into a
script over the weekend and got a chatbot talking, and now everyone assumes the hard part is
done. It is not. That script will not survive contact with production: there is no clean way
to swap models, no identity story, no cost ceiling, and the endpoint it talks to is not the
one your security team will approve. Before you write a single prompt, you need to stand up
the resource correctly and understand the one concept that trips up almost everyone: in Azure
OpenAI, the model you call is not the model you picked — it is a *deployment* of that model
that you named yourself.

## Learning objectives

By the end of this module you will be able to:

- Provision an Azure OpenAI resource in Microsoft Foundry and explain the role of the endpoint and the deployment.
- Select a model family and deploy it under a deployment name, and explain why deployment names — not model names — are what your code targets.
- Choose between deployment types (such as standard versus provisioned throughput) based on a workload's latency and cost profile.
- Make an authenticated chat-completion call from Python using `DefaultAzureCredential` rather than a hard-coded key.

## Concepts

### The resource, the endpoint, and the deployment

Three things sit between your code and a generated token, and confusing them is the source of
most "it works on my machine" failures.

The **resource** is the Azure object you create — an Azure OpenAI resource, managed within
Microsoft Foundry. It is the billing and security boundary. It has a region, a pricing tier,
network rules, and an authentication surface. Creating the resource does *not* give you a
usable model; it gives you an empty container and a base **endpoint** URL of the form
`https://<your-resource-name>.openai.azure.com/`.

A **deployment** is a named instance of a specific model version that you create *inside* the
resource. This is the part newcomers miss. When you deploy a model you give the deployment a
name — say `support-chat` — and that name is what your application code references, not the
underlying model identifier. The indirection is deliberate and valuable: you can later point
`support-chat` at a newer model version, or move it to a different capacity tier, without
touching application code. Think of the deployment name as a stable alias and the model behind
it as swappable plumbing. Your code says "call `support-chat`"; operations decides what
`support-chat` actually is today.

### Choosing a model and a deployment type

Model selection is a capability-versus-cost trade. Larger, more capable chat models reason
better over messy instructions and longer context but cost more per token and respond more
slowly. Smaller models are cheaper and faster and are often entirely sufficient for narrow,
well-prompted tasks. A common mistake is to default to the largest available model for
everything; for a support assistant answering bounded questions, a mid-tier model with good
prompting usually wins on cost and latency. You will also deploy embedding models separately
when you reach the retrieval module — embeddings and chat are different model families with
different deployments.

Beyond *which* model, you choose *how* it is served. The common path is a standard,
consumption-style deployment where you pay per token and share capacity. For workloads that
need predictable latency and reserved capacity, a provisioned-throughput deployment reserves
dedicated units. The exact tier names and quota mechanics change over time, so treat specific
quota numbers as something to verify in the docs for your region rather than memorize. The
durable idea: standard for spiky or early-stage workloads, provisioned for steady high-volume
production where you need guaranteed throughput.

### Authentication: keys versus identity

Every Azure OpenAI resource exposes API keys, and they are the fastest way to make a call —
which is exactly why they leak. A key in source control or a notebook is a credential anyone
can replay. The production-grade approach is Microsoft Entra ID authentication: you assign your
application or developer a role (such as a Cognitive Services OpenAI user role) on the resource,
and the SDK fetches a token at runtime. The `DefaultAzureCredential` class in the Azure Identity
library tries a chain of credential sources — your signed-in developer CLI session locally, a
managed identity when deployed to Azure — so the *same code* authenticates correctly in both
places with no key in sight. Prefer this from day one; retrofitting identity after you have
keys scattered across environments is painful.

## Walkthrough: standing up the Northwind support model

You are the engineer setting up Northwind's assistant properly. You will create the resource,
deploy a chat model named `support-chat`, and verify it with a Python call that uses identity,
not a key.

First, provision and deploy from the Azure CLI. Replace placeholder values with your own.

```bash
# Create the Azure OpenAI resource (kind=OpenAI) in a resource group
az cognitiveservices account create \
  --name northwind-aoai \
  --resource-group northwind-ai-rg \
  --kind OpenAI \
  --sku S0 \
  --location eastus \
  --yes

# Deploy a chat model UNDER the deployment name your code will call.
# The model name/version below is illustrative — list current models
# with `az cognitiveservices account list-models` and verify availability.
az cognitiveservices account deployment create \
  --name northwind-aoai \
  --resource-group northwind-ai-rg \
  --deployment-name support-chat \
  --model-name gpt-4o-mini \
  --model-version "2024-07-18" \
  --model-format OpenAI \
  --sku-name Standard \
  --sku-capacity 10
```

The first command creates the resource and gives you the endpoint; the second creates the
`support-chat` deployment. Note that `--deployment-name` and `--model-name` are different on
purpose — your code will only ever use `support-chat`.

Now call it from Python with identity-based auth. Sign in locally first with `az login` so
`DefaultAzureCredential` has a token source.

```python
import os
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import AzureOpenAI

# DefaultAzureCredential uses your `az login` session locally and a
# managed identity in Azure — no API key in code or config.
token_provider = get_bearer_token_provider(
    DefaultAzureCredential(),
    "https://cognitiveservices.azure.com/.default",
)

client = AzureOpenAI(
    azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],  # e.g. https://northwind-aoai.openai.azure.com/
    azure_ad_token_provider=token_provider,
    api_version="2024-10-21",  # pin an API version; verify the current value in the docs
)

response = client.chat.completions.create(
    model="support-chat",  # the DEPLOYMENT name, not the model name
    messages=[
        {"role": "system", "content": "You are Northwind Outfitters' support assistant."},
        {"role": "user", "content": "What is your return window for unused gear?"},
    ],
)

print(response.choices[0].message.content)
```

Run it. You should see a generated answer. The two things to observe: `model="support-chat"`
targets your deployment alias, and there is no key anywhere — the token provider produced a
bearer token from your Entra identity. If you later create a `support-chat-v2` deployment on a
newer model, you change one string, not your auth.

## Common pitfalls

- **Passing the model name where the deployment name belongs.** The SDK's `model` parameter wants your *deployment* name. Passing the raw model identifier yields a "deployment not found" error that looks like a model problem but is a naming problem.
- **Hard-coding API keys "just for now."** Temporary keys become permanent leaks. Wire `DefaultAzureCredential` from the first commit so local and deployed code share one auth path.
- **Pinning nothing, or pinning everything blindly.** Not setting an `api_version` lets behavior shift under you; copying a stale version from an old sample breaks against current features. Set it explicitly and verify the current value in the docs.
- **Assuming model availability is global.** Models and capacity vary by region and change over time. List available models for your region rather than assuming a model you read about is deployable where you provisioned.
- **Defaulting to the biggest model.** Reaching for the largest model for a bounded task burns cost and latency. Start smaller and size up only when prompting and evaluation show you need to.

## Knowledge check

1. Your application code calls `client.chat.completions.create(model="...")`. What string belongs in `model`, and why does this design make model upgrades safer?
2. A teammate proposes shipping the app with the resource's API key in an environment variable to "keep it simple." What is the production-grade alternative and what concrete advantage does it give you across environments?
3. You have a low-traffic internal tool with unpredictable, bursty usage and a separate high-volume production assistant that must hold steady latency. Which deployment type fits each, and why?

<details>
<summary>Answers</summary>

1. The **deployment name** (the alias you chose, e.g. `support-chat`) — not the model name. Because the deployment is an indirection layer, you can repoint it to a newer model version or capacity tier without changing a line of application code.
2. Use **Microsoft Entra ID authentication via `DefaultAzureCredential`** with an appropriate role on the resource. The advantage: the same code authenticates with your developer login locally and a managed identity in Azure, so there is no key to leak, rotate manually, or accidentally commit.
3. **Standard (consumption) deployment** for the bursty internal tool — you pay per token and tolerate shared capacity; **provisioned throughput** for the steady high-volume assistant — reserved capacity gives the predictable latency that variable shared capacity cannot guarantee.

</details>

## Summary

A working generative feature starts with a correctly provisioned resource, a model deployed
under a stable deployment name, and identity-based authentication wired in from the start. The
deployment-name indirection is the mental model to keep: your code targets an alias, operations
controls what it points to. With the `support-chat` deployment answering calls, you have the
substrate the rest of the course builds on. The next module, *Prompt engineering and templates*,
turns that raw model call into reliable, controllable behavior.

## Further learning

- [What is Azure OpenAI in Azure AI Foundry Models?](https://learn.microsoft.com/en-us/azure/ai-services/openai/overview)
- [Deploy a model in Azure OpenAI](https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to/create-resource)
- [Authenticate requests to Azure AI services](https://learn.microsoft.com/en-us/azure/ai-services/authentication)
- [Azure OpenAI client library for Python (azure-identity + openai)](https://learn.microsoft.com/en-us/azure/ai-services/openai/supported-languages)
