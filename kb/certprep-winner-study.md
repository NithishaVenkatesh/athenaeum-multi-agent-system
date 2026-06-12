# What Made the Last Reasoning Agents Track Winner Win — A Complete Study

*Research report — generated 2026-06-12 | Sources: 8 primary | Confidence: High (all claims verified against the winning repo's actual code)*

## The Event and the Winner

The most recent completed "reasoning agent track" competition in the Microsoft Skill Fest ecosystem was the **Microsoft Agents League** — a 2-week hackathon (Feb 16 – Mar 1, 2026) with three tracks: Creative Apps (GitHub Copilot), **Reasoning Agents (Microsoft Foundry)**, and Enterprise Agents (M365 Agents Toolkit). It drew **100+ submissions** ([Meet the Winners](https://techcommunity.microsoft.com/blog/azuredevcommunityblog/agents-league-meet-the-winners/4507503)). A new edition is running right now as part of AI Skills Fest 2026 (June 4–14, 2026) with a $55K student prize pool and the same three tracks.

**Reasoning Agents track winner:** **CertPrep Multi-Agent System — Personalised Microsoft Exam Preparation** by **Athiq Ahmed** (India, individual submission).

- Submission: [microsoft/agentsleague#76](https://github.com/microsoft/agentsleague/issues/76)
- Repo: [athiq-ahmed/agentsleague](https://github.com/athiq-ahmed/agentsleague)
- Official spotlight: [Agents League Winner Spotlight – Reasoning Agents Track](https://techcommunity.microsoft.com/blog/azuredevcommunityblog/%F0%9F%8F%86-agents-league-winner-spotlight-%E2%80%93-reasoning-agents-track/4511211) (Apr 2026)
- Demo video: [youtube.com/watch?v=okWcFnQoBsE](https://www.youtube.com/watch?v=okWcFnQoBsE) · Live app (mock mode): [agentsleague.streamlit.app](https://agentsleague.streamlit.app/)
- Confirmed by Lee Stott (Microsoft): "What stands out isn't just the innovation, it's the engineering discipline behind these projects."

## The Judging Rubric (what he was scored against)

From the [official rules](https://github.com/microsoft/agentsleague):

| Criterion | Weight |
|---|---|
| Accuracy & Relevance (meets challenge requirements) | 20% |
| Reasoning & Multi-step Thinking | 20% |
| Reliability & Safety (solid patterns, avoids pitfalls) | 20% |
| Creativity & Originality | 15% |
| User Experience & Presentation (clear, polished, demoable) | 15% |
| Community vote (Discord) | 10% |

The track challenge was prescriptive: build a multi-agent system that helps students prepare for Microsoft certification exams — understand the syllabus, generate study plans, assess readiness, adapt, with human-in-the-loop validation. Microsoft even published a reference architecture in the [starter kit](https://github.com/microsoft/agentsleague/tree/main/starter-kits/2-reasoning-agents).

**Key insight:** he didn't invent a novel problem — he took Microsoft's own suggested scenario and executed it to a production standard, generalized it (9 exam families instead of 1), and maximized every rubric line simultaneously.

## What He Built

A pipeline of **8 specialized reasoning agents** on Azure AI Foundry, orchestrated through a Streamlit 7-tab UI + Admin Dashboard:

1. **LearnerProfilingAgent** — free-text → structured `LearnerProfile` (the only LLM-calling agent)
2. **StudyPlanAgent** — week-by-week Gantt schedule via the parliamentary **Largest Remainder Method** (day-level allocation, exact budget, every domain ≥ 1 day)
3. **LearningPathCuratorAgent** — exam domains → curated MS Learn modules with trusted URLs
4. **ProgressAgent** — exam-weighted readiness: `0.55 × domain ratings + 0.25 × hours utilisation + 0.20 × practice score`
5. **AssessmentAgent** — 10-question domain-proportional mock quiz, 60% pass threshold
6. **CertificationRecommendationAgent** — GO / CONDITIONAL GO / NOT YET verdict + remediation loop
7–8. Engagement/email digest + admin/trace support roles

Flow: sequential where dependent, **parallel where not** (StudyPlan ∥ LearningPathCurator via `ThreadPoolExecutor`, ~50% wall-clock cut), **two human-in-the-loop gates** (confirm progress data; confirm assessment readiness), conditional routing (score < 70% loops back to remediation), all persisted to SQLite with full reasoning traces.

## Why Microsoft Said It Won (verbatim from the spotlight)

> - ✅ **Clear separation of reasoning roles**, instead of prompt-heavy monoliths
> - ✅ **Deterministic fallbacks and guardrails**, critical for educational and decision-support systems
> - ✅ **Observable, debuggable workflows**, aligned with Foundry's production goals
> - ✅ **Explainable outputs**, surfaced directly in the UX

## The Engineering Practices — Code-Level Study

All verified directly in the cloned repo.

### 1. The 3-tier LLM fallback with a single shared contract (the killer feature)
`LearnerProfilingAgent` ([src/cert_prep/b0_intake_agent.py](https://github.com/athiq-ahmed/agentsleague/blob/main/src/cert_prep/b0_intake_agent.py), 471 lines):
- **Tier 1:** Azure AI Foundry Agent Service SDK (`azure-ai-projects`, managed agent + thread, cleanup in `finally`)
- **Tier 2:** direct Azure OpenAI GPT-4o, `response_format={"type": "json_object"}`, `temperature=0.2`
- **Tier 3:** deterministic rule-based mock engine — zero credentials

All three tiers validate through the **same Pydantic schema** (`LearnerProfile.model_validate`), defined once as `_PROFILE_JSON_SCHEMA` and rendered into both the prompt and the parser. Downstream agents cannot tell which tier ran. Result: **the full 8-agent pipeline runs in < 1 second with zero Azure credentials** (`FORCE_MOCK_MODE=true`) — judges could always run the demo, and the demo could never fail live.

### 2. A 17-rule GuardrailsPipeline at every agent boundary
[src/cert_prep/guardrails.py](https://github.com/athiq-ahmed/agentsleague/blob/main/src/cert_prep/guardrails.py) (852 lines): seven guard classes behind one façade, BLOCK / WARN / INFO severities; BLOCK calls `st.stop()` so nothing downstream ever sees invalid data. Three-layer PII detection: format regexes → keyword-context regexes ("my ssn is…") → Azure AI Language PII API (live mode, with `loggingOptOut: True`). Azure Content Safety via stdlib `urllib` with a 5s timeout and graceful regex fallback. Architectural rule documented in the module docstring: *"No agent imports or knows about this module — it is called exclusively by the orchestrator."*

This single module covers the **Reliability & Safety 20%** of the rubric almost by itself.

### 3. 342–352 automated tests, zero credentials required
277 named test functions (352 after parametrize expansion) across 15 modules. Standouts:
- `test_guardrails_full.py` — **one test class per guardrail rule** (TestG01…TestG17), 52 tests
- `test_agent_evals.py` — 920 lines of **rubric-based evals**: each agent output scored against 6–12 named checks (`_rubric_score`), mirroring `azure-ai-evaluation` patterns without credentials; plus an actual `eval_harness.py` integrating Coherence/Relevance/Fluency evaluators when Azure is available
- `test_serialization_helpers.py` — 25 tests for schema evolution, including a test that deliberately reproduces the crash to prove the guard is load-bearing
- `conftest.py` forces `FORCE_MOCK_MODE=true` before any import; `factories.py` builds exam-correct fixtures from the registry

### 4. Typed contracts + a data-driven registry (genuine extensibility)
Every agent boundary is a Pydantic v2 / dataclass contract in `models.py` (439 lines, imported by everything, imports nothing). `EXAM_DOMAIN_REGISTRY` + `get_exam_domains(exam_code)` makes the whole system exam-agnostic — supporting 9 certification families (AI-102, DP-100, AZ-204, AZ-305, AZ-400, SC-100, AI-900, DP-203, MS-102) where the challenge asked for one. The readiness formula pulls per-exam domain weights from the registry, never hardcoded.

### 5. Defensive persistence engineering
- `_dc_filter()` whitelist on every `*_from_dict` deserializer — old SQLite rows survive schema changes
- SQLite WAL mode; SHA-256-keyed LLM response cache (`{tier}::{model}::{message}`) where cache failures can never break the pipeline
- `peek_cache()` exists solely so the UI can show a different spinner message when a cache hit is coming — that's the level of polish

### 6. Documented decisions, not just code
`docs/` contains 10 living documents: a 20-section `technical_documentation.md` with Mermaid sequence/topology diagrams, a **judge-facing `qna_playbook.md`** (anticipating questions like "why ThreadPoolExecutor not asyncio?"), `unit_test_scenarios.md`, `changelog.md`, and — the standout — **`lessons.md`**: an incident log with *what went wrong / root cause / fix / prevention rule* for every non-trivial bug, with 7 extracted meta-rules (e.g., "Grep before doc — before describing a service as 'active', grep for its usage"). The README **maps each judging criterion to implementation evidence** and includes an "Honest Gaps" section admitting what wasn't done.

The ThreadPoolExecutor choice illustrates the pattern: `asyncio.gather()` fails inside Streamlit's event loop (`RuntimeError: event loop already running`); he documented the failure mode, the stdlib-only fix, and the measured ~50% wall-clock win — in the README, the tech docs, and the Q&A playbook.

### 7. Demo engineering as a first-class feature
- Mock mode = full pipeline, deterministic, < 1s, zero credentials
- Pre-seeded demo personas in SQLite; demo PDFs cached in `demo_pdfs/` so clicks are instant
- Live Streamlit Cloud deployment (auto-deploy on push, secrets via env vars)
- Admin Dashboard exposing reasoning traces and guardrail violations — judges could *inspect the reasoning*, not just watch outputs
- Professional demo video with voiceover (a judge commented: "I was not expecting such a complete and complex entry!")

### 8. Disciplined process under time pressure
50 commits in 5 days (Feb 25–28), conventional-commit style (`feat:`, `fix:`, `docs:`), with a classic arc: features days 1–2, dense bugfixing day 3 (26 commits), docs + demo stabilization days 4–5. GitHub Copilot used throughout for generation, refactoring, and test scaffolding. No secrets committed; placeholder-detection (`_is_placeholder()`) in config; frozen settings dataclass.

## Synthesis: The Win Formula

Mapped against the rubric:

| Rubric line | How CertPrep maxed it |
|---|---|
| Accuracy & Relevance 20% | Implemented Microsoft's reference architecture faithfully, then exceeded it (9 exams, not 1) |
| Reasoning & Multi-step 20% | 8 explicit reasoning roles, typed handoffs, conditional routing + remediation loop, visible reasoning traces |
| Reliability & Safety 20% | 17-rule guardrails, 3-tier fallback, 352 tests, Content Safety + PII layers, HITL gates |
| Creativity 15% | Largest Remainder allocation, exam-weighted readiness formula, GO/CONDITIONAL/NOT YET verdicts |
| UX & Presentation 15% | 7-tab UI, Gantt/radar/timeline visuals, explainable scores, instant zero-credential demo, polished video |
| Community vote 10% | Public live app anyone could try without setup |

The meta-lesson: **he treated a 2-week hackathon entry as a production system.** Every "extra" — tests, guardrails, fallbacks, traces, docs — wasn't gold-plating; each one mapped directly to a weighted rubric line. The deepest differentiators were (a) the demo *could not fail* (3-tier fallback + mock mode), (b) the reasoning was *inspectable* (traces, admin dashboard, explainable scores), and (c) the engineering decisions were *narrated* (lessons.md, Q&A playbook, criterion-to-evidence README mapping) so judges didn't have to dig to find the quality.

## Actionable Takeaways for an Agents League 2026 Entry

1. **Build the zero-credential mock path first.** Same typed contract for live and mock tiers; demo reliability is a feature, not a fallback.
2. **Put a validation/guardrail layer at every agent boundary**, owned by the orchestrator, unit-tested per rule.
3. **Make reasoning visible**: persist traces, expose them in an admin view, and surface *why* behind every score/verdict in the UX.
4. **Write the README as a judging-criteria-to-evidence map**, include an honest-gaps section, and keep a lessons.md.
5. **Generalize one axis beyond the brief** (CertPrep: 1 exam → 9 via a registry) — it converts "demo" into "product" in judges' eyes.
6. **Use real algorithms where LLMs aren't needed** (Largest Remainder, weighted formulas) — deterministic correctness scores better than another prompt.
7. **Parallelize independent agents and document the decision** (including why the obvious alternative fails).

## Sources

1. [Agents League Winner Spotlight – Reasoning Agents Track](https://techcommunity.microsoft.com/blog/azuredevcommunityblog/%F0%9F%8F%86-agents-league-winner-spotlight-%E2%80%93-reasoning-agents-track/4511211) — official Microsoft blog, Apr 2026
2. [microsoft-foundry discussion #377](https://github.com/orgs/microsoft-foundry/discussions/377) — winner spotlight AMA
3. [microsoft/agentsleague#76](https://github.com/microsoft/agentsleague/issues/76) — full winning submission (architecture, tech stack, challenges & learnings table)
4. [microsoft/agentsleague README](https://github.com/microsoft/agentsleague) — rules, judging rubric, prizes
5. [Reasoning Agents starter kit](https://github.com/microsoft/agentsleague/tree/main/starter-kits/2-reasoning-agents) — challenge brief + reference architecture
6. [athiq-ahmed/agentsleague](https://github.com/athiq-ahmed/agentsleague) — winning repo (cloned and analyzed at code level)
7. [Lee Stott's LinkedIn post](https://www.linkedin.com/posts/leestott_agents-league-winner-spotlight-reasoning-activity-7452027895704600577-_8w_) — Microsoft DevRel commentary
8. [Agents League: Meet the Winners](https://techcommunity.microsoft.com/blog/azuredevcommunityblog/agents-league-meet-the-winners/4507503) — winners announcement (100+ submissions)

## Methodology

Searched 6 query variations across the web (local SearXNG/Firecrawl). Deep-read 5 sources in full, including a code-level analysis of the cloned winning repository (file-by-file architecture review, test counts via grep, git history analysis). The Microsoft spotlight blog and submission issue were cross-referenced against the actual code; all engineering claims in this report were verified in source.
