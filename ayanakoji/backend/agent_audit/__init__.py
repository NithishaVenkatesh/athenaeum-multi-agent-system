"""Live red-team harness for the agentic pipeline.

This is a *production* adversarial regression suite, not a throwaway script. Every
layer of the chat pipeline (gate, router, grounding, guards, recommend, schedule,
the answer agents, the model router, the orchestrator) gets a battery of absurd /
hostile inputs run against the **live** model path (Azure + Groq, never the
deterministic offline mock). A layer "holds" only when its battery passes two
consecutive rounds with zero failures.

The offline/deterministic code paths are deliberately left untouched: the campaign
hardens *live* behavior by improving reasoning, tools, prompts, and algorithms —
never by adding per-case pattern matching.
"""
