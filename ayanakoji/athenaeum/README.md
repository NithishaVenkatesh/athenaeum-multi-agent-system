# Athenaeum

> A grounded course-content synthesis & **Foundry IQ** ingestion framework.
> Lives beside `backend/` and `frontend/` but is fully decoupled — it only consumes the
> shared Azure environment.

Athenaeum turns the *public, license-clean* structure of real Microsoft certification
outlines into a catalog of **original, professionally-authored synthetic course content**,
then publishes it to a **Foundry IQ knowledge base** (Azure AI Search) for grounded,
cited retrieval.

## The pipeline: ground → author → ingest

1. **Ground** — read the *public* "skills measured" outline for each vertical's
   certification (via the Microsoft Learn MCP / the public exam study guides). Only the
   factual skeleton (domains, sub-skills, weights) is used; **no Microsoft prose is copied
   or stored**. Captured in `grounding/` and distilled into `content/_catalog.json`.
2. **Author** — deep, modular, professional markdown is authored against the grounded
   skeleton following the **`course-author` skill** (the quality bar). Every file carries
   provenance frontmatter and is original prose.
3. **Ingest** — provision Azure AI Search (Basic), build a vector + semantic index with a
   `text-embedding-3-large` vectorizer, upload the chunked documents, and create a Foundry
   IQ `KnowledgeBase` exposing the `knowledge_base_retrieve` MCP endpoint.

## Verticals (5 × 3 courses × 4 modules = 75 documents)

| Vertical | Grounded on |
|----------|-------------|
| Cloud & Backend Development | AZ-204 |
| DevOps & Platform Engineering | AZ-400 |
| Data Engineering & Analytics | DP-203 (current path: Fabric DP-700) |
| AI & Machine Learning Engineering | AI-102 |
| Cloud Solution Architecture & Security | AZ-305 + SC-100 |

## Usage

```bash
uv sync                       # install deps
athenaeum validate            # check catalog/content/schema/provenance integrity
athenaeum provision           # az: create AI Search Basic + deploy embeddings, write .env
athenaeum ingest              # build index + upload docs + create Foundry IQ KnowledgeBase
athenaeum status              # show index/KB document counts
athenaeum teardown            # delete the search resource group (credit hygiene)
```

## Design notes

- **Production-grade, no tracing.** Typed Pydantic contracts at every boundary, idempotent
  `create_or_update` operations, retries on transient Azure errors, fail-fast config. No
  OpenTelemetry / App Insights / log shipping by design.
- **Credit-safe.** Azure AI Search is a first-party `Microsoft.Search` resource billed to
  the Azure sponsorship credit, not a card; the subscription's `deny-real-money` policy
  blocks only marketplace/SaaS/reservation purchases. `athenaeum teardown` removes it.
- **License-clean.** `athenaeum validate` diffs authored content against the grounding
  source to assert no verbatim Microsoft strings are present.

See [content/_catalog.json](content/_catalog.json) for the full grounded course map and
`.claude/skills/course-author/SKILL.md` for the authoring quality standard.
