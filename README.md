# msf-reasoning-agent

Multi-agent **Enterprise Learning System** for the Microsoft Agents League Hackathon 2026 — 🧠 Reasoning Agents track, Challenge A. Built on Microsoft Foundry with Foundry IQ grounding (+ Fabric IQ semantic model and Work IQ work-context patterns).

## Knowledge base (vectorless)

All research and planning lives in [kb/](kb/) as tagged markdown — retrieval is `grep`, not embeddings. Start at [kb/INDEX.md](kb/INDEX.md) for the tag taxonomy and document map:

- `kb/hackathon/` — rules, judging rubric, compliance checklists
- `kb/challenge/` — Challenge A brief, agent architecture, synthetic data pack
- `kb/iq/` — Foundry IQ / Work IQ / Fabric IQ deep dives incl. verified SDK recipes
- `kb/planning/` — build plan, decision log, progress log

## Evaluation scorecard

The agent ships with a clean-room red-team harness in [`agent_audit/`](agent_audit/) — a PyRIT-style battery (seeds × converters → live SSE API → code-based scorers) that is **independent of the app's own `evaluation/` and `tests/` suites**. It drives the real pipeline over HTTP on two lanes: `offline` (`:8020`, `OFFLINE_LLM=true`, regex-only degraded mode) and `online` (`:8021`, real Azure + Groq). See [`agent_audit/BASELINE.md`](agent_audit/BASELINE.md) for the full write-up.

The numbers below labelled **harness-measured** are real recorded results from `BASELINE.md` (the *pre-hardening baseline* run, dated **2026-06-14**). They are baseline figures kept honest on purpose — several flagged findings (S1–S3) were the point of the exercise. Metrics labelled **run to measure** are produced by the listed command; we do not print a number we have not recorded.

### Dimension 5 — Reliability & Safety

Injection / jailbreak / exfiltration battery with a paired **over-refusal anti-metric**, so a safety fix cannot game the score by simply blocking everything. Scorers live in [`agent_audit/scorers.py`](agent_audit/scorers.py); attack-success counts only real policy breaches (leaked system/tutor prompt or adopted attacker persona), not merely-unblocked safe answers.

| Metric (scorer) | offline (degraded) | online (prod) | Status |
|---|---|---|---|
| Direct injection block-rate (blatant + paraphrased + exfil) | 6/16 = **38%** | 13/16 = **81%** | harness-measured (BASELINE.md, 2026-06-14) |
| · blatant overrides blocked | — | — | sub-counts in BASELINE.md; rerun to refresh |
| · paraphrased (no instruction-object) blocked | 1/8 | 7/8 | harness-measured |
| · exfil (system-prompt extraction) blocked | 0/3 | 1/3 | harness-measured |
| Converter sweep blocked (obfuscation slips intent past?) | 4/48 | 17/24 | harness-measured (offline sweeps 6 converters; online sweeps 3, metered) |
| Attack-success rate (leak or persona compliance, lower=better) | see survivors list | see S2 (flaky leak) | `attack_succeeded()` in scorers.py |
| **Over-refusal** — benign learner messages wrongly blocked (lower=better) | **0/7** (clean) | **3/7** (over-blocks) | harness-measured |

Recorded findings (honest, not papered over): **S1** — degraded-mode gate is regex-only, so 10/11 non-blatant attacks pass (blast radius low: offline answers are tool-less). **S2** — *flaky* online system-prompt leak when the stochastic Azure classifier misses an exfil prompt. **S3** — *consistent* online over-refusal (3/3) of benign learner messages that merely contain trigger words.

### Dimension 1 — Accuracy & Relevance (grounding honesty)

Checks that the agent grounds an answer in catalog sources only when the topic is genuinely covered, and never sprawls one broad keyword across unrelated courses. Scorers: `false_grounding()`, `course_spread()`.

| Metric (scorer) | Value | Status |
|---|---|---|
| Grounding-honesty — grounds iff topic is covered (6 probes) | run to measure | `PYTHONPATH=. python -m agent_audit.dim1_accuracy [online]` → prints `grounding X/6 correct` |
| Cross-course spread cap (broad keyword spans ≤ 1 course, A5) | run to measure | same command → prints `spread-cap True/False` |
| Citation guard (A2) / number guard (A3/A4) | deterministic | guard functions verified by the app's `tests/test_guards*.py` (they only fire on a malformed LLM citation/figure) |

The Dim 1 battery is live-only (it asks the running agent which topics it will ground), so no baseline number is recorded — run the command above against a started lane to produce `correct/total`.

### Reproduce

The harness is **stdlib-only** (no extra deps). Start the lane(s) you want to score, then:

```bash
# Dimension 5 — safety battery (both lanes, or pass `offline` / `online`)
PYTHONPATH=. python -m agent_audit.dim5_safety offline

# Dimension 1 — grounding honesty (defaults to offline; pass `online` or `both`)
PYTHONPATH=. python -m agent_audit.dim1_accuracy offline

# One-command scorecard — aggregates both dimensions into a single printed table
PYTHONPATH=. python -m agent_audit.scorecard offline      # free
PYTHONPATH=. python -m agent_audit.scorecard online        # metered (real Azure/Groq tokens)
```

> ⚠️ The `online` lane spends real Azure + Groq tokens and is slow; prefer `offline` for fast, free iteration. Lane ports/personas are configured in [`agent_audit/config.py`](agent_audit/config.py).

## Headroom (context compression)

This repo ships a project-scoped MCP config ([.mcp.json](.mcp.json)) that gives Claude Code (and any MCP-compatible agent) the [Headroom](https://github.com/chopratejas/headroom) tools — `headroom_compress`, `headroom_retrieve`, `headroom_stats` — for compressing large tool outputs, logs, and files before they hit the model (60–95% fewer tokens).

### Collaborator setup

1. Install [uv](https://docs.astral.sh/uv/) if you don't have it: `curl -LsSf https://astral.sh/uv/install.sh | sh`
2. Open this repo in Claude Code and approve the `headroom` project MCP server when prompted (one time).

That's it — `uvx` fetches and runs `headroom-ai[mcp]` automatically; no global install needed. Verify with `/mcp` inside Claude Code.

### Optional: compress all traffic automatically

The MCP tools are on-demand. To compress everything, also run the proxy:

```bash
uvx --python 3.12 --from "headroom-ai[proxy]" headroom proxy   # terminal 1
ANTHROPIC_BASE_URL=http://127.0.0.1:8787 claude                # terminal 2
```
