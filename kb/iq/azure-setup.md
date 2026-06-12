---
title: Azure / Foundry infra setup for Foundry IQ
tags: [azure, infra, howto, foundry-iq]
status: stable
sources:
  - microsoft/iq-series infra/README.md + cookbook READMEs
  - Reasoning Agents starter kit env setup
updated: 2026-06-12
related: [foundry-iq, foundry-iq-code]
---

# Azure setup (Foundry IQ stack)

## One-click deploy (fastest)

https://aka.ms/iq-series/deploytoazure — deploys in 5–10 min:

| Resource | Purpose |
|----------|---------|
| Azure AI Search (**Standard** tier) | vector + semantic + agentic retrieval |
| Azure OpenAI | `text-embedding-3-large` + `gpt-4o-mini` deployments |
| Azure AI Services + Foundry Project | project for agents |
| AI Search connection | links Foundry project ↔ Search |
| Blob Storage | blob knowledge source |
| RBAC role assignments | user + service-to-service |

Inputs: resource group (e.g. `iq-series-rg`), **User Object ID** (`az ad signed-in-user show --query id -o tsv`), region supporting **agentic retrieval** (default `eastus2`).

CLI alternative: `cd infra && ./deploy.sh -g "iq-series-rg" -l "eastus2"` (in the iq-series repo; generates `.env` in repo root).

Known failure: tenant policies blocking key-based storage access break the **data-seeding deployment script** only — core resources still deploy; seed manually by running the ep1 cookbook or via Foundry IQ portal UI.

## .env template (superset across cookbooks)

```env
SEARCH_ENDPOINT=https://<search-service>.search.windows.net
AOAI_ENDPOINT=https://<openai-resource>.openai.azure.com
AOAI_EMBEDDING_MODEL=text-embedding-3-large
AOAI_EMBEDDING_DEPLOYMENT=text-embedding-3-large
AOAI_GPT_MODEL=gpt-4o-mini
AOAI_GPT_DEPLOYMENT=gpt-4o-mini
FOUNDRY_PROJECT_ENDPOINT=https://<ai-services>.services.ai.azure.com/api/projects/<project>
FOUNDRY_MODEL_DEPLOYMENT_NAME=gpt-4o-mini
AZURE_AI_SEARCH_CONNECTION_NAME=iq-series-search-connection
FOUNDRY_PROJECT_RESOURCE_ID=/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.MachineLearningServices/workspaces/<ws>/projects/<project>
BLOB_CONNECTION_STRING=<from outputs>     # only for blob knowledge source
BLOB_CONTAINER_NAME=<container>
```

`FOUNDRY_PROJECT_RESOURCE_ID`: ai.azure.com → project → Overview → Properties (full ARM ID). Everything else: deployment **Outputs** tab.

Starter-kit minimal alternative: `AZURE_AI_PROJECT_ENDPOINT` + `AZURE_AI_MODEL_DEPLOYMENT=gpt-4o`.

## Gotchas

- **Free tier**: limited model access by region/quota, tight rate limits; some orchestration/eval features need pay-as-you-go. Azure for Students is an option.
- `az login` before running anything (`DefaultAzureCredential`).
- AI Search **Standard** tier is not free — delete when done: `az group delete --name iq-series-rg --yes --no-wait`.
- `azure-search-documents==12.1.0b1` is a preview SDK; pin it.
- Keep `.env` out of git; never bake secrets into container images (hosted agents use Entra agent identity).
