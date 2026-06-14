"""Athenaeum agent red-team + smoke harness (clean-room, PyRIT-inspired).

Independent of the app's own ``evaluation/`` and ``tests/`` suites. Drives the
real agent pipeline over the live SSE API (``POST /api/courses/{id}/messages``),
attacking each node directly with adversarial inputs, then scoring the outcome.

Two lanes (configured in :mod:`agent_audit.config`):

- **online**  — real Azure/Groq providers (the production safety + answer layer).
- **offline** — degraded mode (regex-only gate, deterministic answers), the
  "all providers down" window the audit flagged as the weakest point.

Attack methodology mirrors Microsoft PyRIT: seed prompts (:mod:`agent_audit.seeds`)
× converters (:mod:`agent_audit.converters`) → orchestrated against a target
(:mod:`agent_audit.live_client`) → scored (:mod:`agent_audit.scorers`).
"""
