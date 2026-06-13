# Ayanakoji Backend

FastAPI service for the Enterprise Learning Agent. Skeleton stage — liveness +
connectivity contract only, no agent logic yet.

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

