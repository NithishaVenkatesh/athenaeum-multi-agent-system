# Athenaeum

> A grounded course-content synthesis & validation framework.
> Lives beside `backend/` and `frontend/` and is fully decoupled. It needs no cloud
> credentials.

Athenaeum turns the *public, license-clean* structure of real Microsoft certification
outlines into a catalog of **original, professionally-authored synthetic course content**.
The backend then serves it with grounded, cited retrieval.

## The pipeline: ground → author → index

1. **Ground**: read the *public* "skills measured" outline for each vertical's
   certification (via the Microsoft Learn MCP / the public exam study guides). Only the
   factual skeleton (domains, sub-skills, weights) is used; **no Microsoft prose is copied
   or stored**. Captured in `grounding/` and distilled into `content/_catalog.json`.
2. **Author**: deep, modular, professional markdown is authored against the grounded
   skeleton following the **`course-author` skill** (the quality bar). Every file carries
   provenance frontmatter and is original prose.
3. **Index**: done by the backend, not here.
   `ayanakoji/backend/scripts/reindex_vectors.py` embeds every catalog module with
   **Cohere `embed-v4.0`** and uploads the vectors to **Qdrant Cloud** (free tier). The
   vectors are committed to `backend/app/data/course_vectors.json`, so rebuilding a deleted
   cluster costs no embedding calls.

## Verticals (5 × 3 courses × 4 modules)

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
athenaeum validate            # check catalog/content/schema/provenance integrity (offline)
```

## Design notes

- **Typed contracts.** Pydantic models at every boundary, fail-fast config.
- **License-clean.** `athenaeum validate` diffs authored content against the grounding
  source to assert no verbatim Microsoft strings are present.

See [content/_catalog.json](content/_catalog.json) for the full grounded course map and
`.claude/skills/course-author/SKILL.md` for the authoring quality standard.
