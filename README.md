# msf-reasoning-agent

Multi-agent **Enterprise Learning System** for the Microsoft Agents League Hackathon 2026 — 🧠 Reasoning Agents track, Challenge A. Built on Microsoft Foundry with Foundry IQ grounding (+ Fabric IQ semantic model and Work IQ work-context patterns).

## Knowledge base (vectorless)

All research and planning lives in [kb/](kb/) as tagged markdown — retrieval is `grep`, not embeddings. Start at [kb/INDEX.md](kb/INDEX.md) for the tag taxonomy and document map:

- `kb/hackathon/` — rules, judging rubric, compliance checklists
- `kb/challenge/` — Challenge A brief, agent architecture, synthetic data pack
- `kb/iq/` — Foundry IQ / Work IQ / Fabric IQ deep dives incl. verified SDK recipes
- `kb/planning/` — build plan, decision log, progress log

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
