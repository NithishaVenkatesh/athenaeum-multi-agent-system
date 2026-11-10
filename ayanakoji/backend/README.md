# Ayanakoji Backend

FastAPI service for the Enterprise Learning Agent. Provides the liveness +
connectivity contract and the synthetic **Work IQ** read service.

## Stack
- Python 3.12, managed with [uv](https://docs.astral.sh/uv/)
- FastAPI + Uvicorn
- pytest / ruff / mypy

## Setup
```bash
cd ayanakoji/backend
uv sync                      # creates .venv and installs deps + dev group
cp .env.example .env         # then fill real values (never commit .env)
```

## Run
```bash
uv run uvicorn app.main:app --reload --port 8000
# http://localhost:8000/health   http://localhost:8000/api/ping   /docs
```

## Work IQ service (synthetic, GET-only)

A Work-IQ-pattern read layer over a **fabricated** engineering org (Helix
Dynamics / Team "Atlas"): a senior + junior developer in each of the five
Athenaeum verticals plus one engineering manager (11 personas), each with a
realistic Mon–Fri work week at 30-minute resolution, learning preferences
(study hours, cadence, modality), work context (focus windows, on-call, PTO,
after-hours load), a synthetic profile (tenure, level, languages), and team
delivery context (sprint, OKRs, cert targets, capacity policy).

> **Synthetic, demo-only.** Fabricated identifiers (`EMP-001`, `L-1001`,
> `TEAM-A`); star codenames are fictional personas — no real people, PII, emails,
> or customer data. Work-signal aggregates are *derived* from the calendar
> (Response Fidelity), so the schedule and signals can never disagree.

**Scope & fidelity.** Real Microsoft Work IQ derives from M365 activity (calendar,
meetings, mail, files). The **Work-IQ-pattern** surfaces here are `work_signals`,
`schedule`, `work_context`, and `availability`. `profile` (HRIS-style) and team
`sprint`/`okrs`/`cert-targets` (Azure Boards / Viva Goals-style) are **adjacent
workforce context** included for demo realism — not claimed to come from Work IQ.
This is stated in the service descriptor's `scope` field.

**Trust model (no auth by design).** A persona switcher with no tenancy or
passwords, so there is no auth layer. Compartmentalization is by API shape, not
login: the manager surface (`teams/{id}/capacity`) is **aggregate-only** and
never exposes per-learner detail; per-persona endpoints represent that persona
reading their own data.

Data source: [`app/data/work_iq.json`](app/data/work_iq.json), produced
deterministically by the offline synthesizer and committed as the source of
truth. CI regenerates it and fails on any drift.

```bash
uv run python scripts/generate_work_iq.py   # regenerate the data source
```

Routes (all read-only, under `/api/workiq`):

| Method · Path | Returns |
|---|---|
| `GET /api/workiq` | service descriptor (principles, week, disclaimer) |
| `GET /api/workiq/org` | organization + teams |
| `GET /api/workiq/verticals` | the five engineering verticals |
| `GET /api/workiq/personas` | roster (filters: `vertical`, `seniority`, `team_id`) |
| `GET /api/workiq/personas/{id}` | full persona (profile, prefs, context, signals, learner profile, schedule) |
| `GET /api/workiq/personas/{id}/profile` | synthetic profile/identity |
| `GET /api/workiq/personas/{id}/learning` | learner profile (Dataset 1) |
| `GET /api/workiq/personas/{id}/learning/preferences` | learning preferences & cadence |
| `GET /api/workiq/personas/{id}/work-context` | work mode, focus windows, on-call, PTO |
| `GET /api/workiq/personas/{id}/availability` | derived availability + weekly free capacity |
| `GET /api/workiq/personas/{id}/schedule` | full week schedule (each day carries a summary) |
| `GET /api/workiq/personas/{id}/schedule/{day}` | one day's timed blocks (`mon`..`fri`) + summary |
| `GET /api/workiq/personas/{id}/signals` | work signals (Work IQ Dataset 2) |
| `GET /api/workiq/work-signals` | org-wide work signals |
| `GET /api/workiq/teams/{id}` | team roster + delivery context |
| `GET /api/workiq/teams/{id}/sprint` | active sprint |
| `GET /api/workiq/teams/{id}/okrs` | team OKRs |
| `GET /api/workiq/teams/{id}/cert-targets` | per-vertical certification targets |
| `GET /api/workiq/teams/{id}/capacity` | aggregate-only team capacity (manager view) |

## Quality gates
```bash
uv run ruff check .          # lint
uv run ruff format --check . # format
uv run mypy app              # types
uv run pytest                # tests + coverage (>=80%)
```

## Live providers (all free tier, no credit card)

| Role | Provider | Notes |
|---|---|---|
| LLM tiers 1-2 | **Groq** `openai/gpt-oss-120b` / `gpt-oss-20b` | `reasoning_effort=low` keeps small budgets from emptying |
| LLM tiers 3-4 | **Google Gemini** `gemini-2.5-flash` / `gemini-3.5-flash-lite` | via AI Studio's OpenAI-compatible endpoint |
| Injection classifier | **Groq** Llama Prompt Guard 2 (86M) | alongside the regex + heuristic + LLM layers |
| Embeddings | **Cohere** `embed-v4.0` (1024-d) | trial key: 1,000 calls/month, so the corpus is pre-embedded and queries are LRU-cached |
| Vector search | **Qdrant Cloud** free cluster | hybrid: fused with the lexical retriever (RRF); any failure → lexical-only, labelled in the trace |
| Answer evaluation | LLM-as-judge through the same chain | one JSON call scores groundedness / relevance / retrieval (1-5) |

With no keys at all, everything runs on the deterministic offline path (CI does this).
The OpenAI SDK lives in the optional `llm` dependency group; Cohere and Qdrant are
plain `httpx` calls. Secrets live in Infisical (project `athenaeum-multi-agent-system`).
`app/config.py` fails loud via `require_groq()` / `require_gemini()` /
`require_vector_search()` when values are missing or placeholders.

```bash
uv sync --group dev --group llm
infisical run --env dev -- .venv/bin/uvicorn app.main:app --reload --port 8000

# (Re)build the vector index: embeds only changed modules (1 Cohere call for the whole
# catalog), then recreates the Qdrant collection from app/data/course_vectors.json.
infisical run --env dev -- uv run python scripts/reindex_vectors.py
# Restore a deleted/suspended cluster without spending any Cohere calls:
infisical run --env dev -- uv run python scripts/reindex_vectors.py --upload-only
```

### Keeping the free Qdrant cluster alive
Free Qdrant clusters are suspended after a week with no traffic and deleted after four.
A cron-job.org job sends one 1-result search every 2 days with a **read-only** key,
which is negligible load. If the cluster is lost anyway, run `--upload-only` above.
