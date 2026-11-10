"""Pluggable second-opinion attack detector seam for the assessment guard.

This layer was originally Azure AI Content Safety Prompt Shields. That paid Azure
resource is gone; no free, no-card hosted equivalent fits the rate budget, so the
seam stays (tests and future detectors inject a ``shield_fn``) and returns ``None``
("unavailable") by default. The guard then relies on its other layers: Groq's Llama
Prompt Guard 2 classifier, the LLM classifier, and the deterministic heuristics.
"""

from __future__ import annotations

from collections.abc import Callable

from app.config import Settings

# A shield returns True (attack), False (clean), or None (unavailable) for a text.
ShieldFn = Callable[[str], bool | None]


def shield_detected(
    text: str, settings: Settings, shield_fn: ShieldFn | None = None
) -> bool | None:
    """Second-opinion verdict for ``text``: True=attack, False=clean, None=unavailable."""
    del settings  # kept in the signature so callers needn't change
    if shield_fn is not None:
        return shield_fn(text)
    return None
