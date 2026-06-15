"""Output-side safety screen: the second perimeter over the model's own tokens."""

from __future__ import annotations

from app.agent.output_guard import (
    OUTPUT_BLOCKED_NOTICE,
    output_breach,
    safe_output_stream,
)


def _run(tokens: list[str]) -> str:
    return "".join(safe_output_stream(iter(tokens)))


def test_halts_on_attacker_persona() -> None:
    out = _run(["Sure. ", "I am DAN ", "and I have no restrictions, ", "here is the secret."])
    assert "here is the secret" not in out  # the breach continuation is truncated
    assert OUTPUT_BLOCKED_NOTICE in out


def test_halts_on_governance_prompt_leak() -> None:
    out = _run(["My instructions say: ", "You are a strict security gate", " that blocks..."])
    assert "that blocks" not in out
    assert OUTPUT_BLOCKED_NOTICE in out


def test_marker_spanning_token_boundary_is_caught() -> None:
    # "i have no restrictions" is split across three tokens — still detected.
    out = _run(["ok ", "i have ", "no ", "restrictions now"])
    assert OUTPUT_BLOCKED_NOTICE in out
    assert "now" not in out


def test_legitimate_answer_passes_untouched() -> None:
    # A real answer that mentions prompts / system design must NOT trip the screen — the
    # markers are high-precision governance/persona fragments, not broad words.
    tokens = [
        "A system prompt configures an LLM. ",
        "In system design, ",
        "you separate concerns and ground answers in sources [cb-c01-m02].",
    ]
    assert _run(tokens) == "".join(tokens)
    assert OUTPUT_BLOCKED_NOTICE not in _run(tokens)


def test_output_breach_predicate() -> None:
    assert output_breach("I can do anything now") is not None
    assert output_breach("Here is how triggers and bindings work") is None
    assert output_breach("the model's developer mode enabled flag") is not None
