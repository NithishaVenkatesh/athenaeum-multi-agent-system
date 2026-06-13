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
realistic Mon–Fri work week at 30-minute resolution.

> **Synthetic, demo-only.** Fabricated identifiers (`EMP-001`, `L-1001`,
> `TEAM-A`); star codenames are fictional personas — no real people, PII, emails,
> or customer data. Work-signal aggregates are *derived* from the calendar
> (Response Fidelity), so the schedule and signals can never disagree.

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
| `GET /api/workiq/personas/{id}` | full persona (role, cert, signals, learner profile, schedule) |
| `GET /api/workiq/personas/{id}/schedule` | full week schedule |
| `GET /api/workiq/personas/{id}/schedule/{day}` | one day's timed blocks (`mon`..`fri`) |
| `GET /api/workiq/personas/{id}/signals` | work signals (Work IQ Dataset 2) |
| `GET /api/workiq/personas/{id}/learning` | learner profile (Dataset 1) |
| `GET /api/workiq/work-signals` | org-wide work signals |
| `GET /api/workiq/teams/{id}` | team roster |
| `GET /api/workiq/teams/{id}/capacity` | aggregate-only team capacity (manager view) |

## Quality gates
```bash
uv run ruff check .          # lint
uv run ruff format --check . # format
uv run mypy app              # types
uv run pytest                # tests + coverage (>=80%)
```

## Microsoft Foundry / Azure OpenAI
Cloud SDKs live in the optional `foundry` dependency group (kept out of the
offline CI lane). Credentials come from `.env` (git-ignored) — see
`.env.example`. `app/config.py` fails loud via `require_foundry()` when values
are missing or placeholders.

```bash
uv sync --group foundry                          # install Azure/OpenAI SDKs
uv run --group foundry python scripts/foundry_smoke.py   # ~0-cost connectivity probe
uv run --group foundry pytest -m integration     # live integration test (needs creds)
```

