"""Tests for the groundedness verifier selection + the LLM-as-judge evaluation adapter.

The deterministic selection (skip-when-uncited, judge-when-available, lexical fallback)
and the judge's gating are offline-unit-tested by stubbing the single judge call; the
live judge is exercised under ``integration``.
"""

from __future__ import annotations

import math

import pytest
from app.agent.answer import verify_grounding
from app.agent.contracts import GroundingSource
from app.config import Settings

_SRC = [
    GroundingSource(
        ref="cb-c01-m02",
        title="Event-driven code with Azure Functions",
        snippet="Build serverless functions with triggers and input/output bindings.",
        kind="course",
    )
]


def _eval_settings() -> Settings:
    """Settings where evaluation_available is True (a provider configured + online)."""
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        groq_api_key="gsk_real",
        offline_llm=False,
    )


def _stub_judge(
    monkeypatch: pytest.MonkeyPatch,
    *,
    groundedness: float | None,
    relevance: float | None = None,
    retrieval: float | None = None,
) -> None:
    """Stub the one judge call; a ``None`` score models a judge that omitted it."""
    import app.agent.grounding_verifier as gv

    payload: dict[str, object] = {}
    for name, score in (
        ("groundedness", groundedness),
        ("relevance", relevance),
        ("retrieval", retrieval),
    ):
        if score is not None:
            payload[name] = score
            payload[f"{name}_reason"] = f"{name} judged"
    monkeypatch.setattr(gv, "_judge", lambda *_a, **_k: payload)


def test_verify_grounding_skips_when_no_citation() -> None:
    # Nothing cites an approved source: the judge is not spent, and the no-citation
    # case is left to the streaming guard's own disclaimer.
    verdict = verify_grounding("a general answer", _SRC, query="q", settings=_eval_settings())
    assert verdict.grounded is True
    assert verdict.metrics == ()
    assert "deterministic" in verdict.provider


def test_verify_grounding_falls_back_to_lexical_when_judge_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.agent.grounding_verifier as gv

    def _boom(*_a: object, **_k: object) -> object:
        raise RuntimeError("judge down")

    monkeypatch.setattr(gv, "llm_grounding", _boom)
    answer = "Cosmos DB partition keys shard throughput [cb-c01-m02]."  # cross-topic citation
    verdict = verify_grounding(answer, _SRC, query="q", settings=_eval_settings())
    # Degraded to the deterministic floor, which still flags the topic-disjoint citation.
    assert verdict.provider == "deterministic lexical overlap"
    assert verdict.grounded is False
    assert "LLM-judge evaluation unavailable" in verdict.reason


def test_verify_grounding_uses_lexical_when_evaluation_unavailable() -> None:
    offline = Settings(_env_file=None, offline_llm=True)  # type: ignore[call-arg]
    answer = "Azure Functions use triggers and bindings [cb-c01-m02]."
    verdict = verify_grounding(answer, _SRC, query="q", settings=offline)
    assert verdict.provider == "deterministic lexical overlap"
    assert verdict.grounded is True


@pytest.mark.parametrize(
    ("groundedness_score", "expected_grounded"),
    [
        (3.0, False),  # "some claims unsupported" — a C-minus that must NOT pass
        (3.9, False),  # still below the 4.0 mostly/fully-supported bar
        (4.0, True),  # "mostly/fully supported" — clears the gate
        (5.0, True),
    ],
)
def test_llm_grounding_gate_at_four(
    monkeypatch: pytest.MonkeyPatch, groundedness_score: float, expected_grounded: bool
) -> None:
    import app.agent.grounding_verifier as gv

    _stub_judge(
        monkeypatch,
        groundedness=groundedness_score,
        relevance=groundedness_score,
        retrieval=groundedness_score,
    )
    settings = _eval_settings()
    assert settings.groundedness_min_score == 4.0
    verdict = gv.llm_grounding("q", "an answer [cb-c01-m02]", _SRC, settings)
    assert verdict.grounded is expected_grounded
    assert verdict.provider == "LLM-as-judge evaluation"


def test_llm_grounding_gates_on_relevance(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.agent.grounding_verifier as gv

    _stub_judge(monkeypatch, groundedness=5, relevance=2, retrieval=5)
    verdict = gv.llm_grounding("q", "an answer [cb-c01-m02]", _SRC, _eval_settings())
    assert verdict.grounded is False
    assert "relevance 2 < 3" in verdict.reason


def test_llm_grounding_passes_when_every_judge_clears(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.agent.grounding_verifier as gv

    _stub_judge(monkeypatch, groundedness=5, relevance=4, retrieval=4)
    verdict = gv.llm_grounding("q", "an answer [cb-c01-m02]", _SRC, _eval_settings())
    assert verdict.grounded is True
    assert verdict.score == 1.0
    assert ("groundedness", 5.0) in verdict.metrics


def test_llm_grounding_absent_judge_does_not_block(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.agent.grounding_verifier as gv

    # Relevance/retrieval omitted by the judge → they must not gate the verdict.
    _stub_judge(monkeypatch, groundedness=4.5)
    verdict = gv.llm_grounding("q", "an answer [cb-c01-m02]", _SRC, _eval_settings())
    assert verdict.grounded is True


def test_llm_grounding_raises_without_groundedness(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.agent.grounding_verifier as gv

    _stub_judge(monkeypatch, groundedness=None, relevance=5)
    with pytest.raises(RuntimeError, match="no score"):
        gv.llm_grounding("q", "an answer [cb-c01-m02]", _SRC, _eval_settings())


def test_judge_parses_router_json(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.agent.grounding_verifier as gv
    from app.agent import llm

    class _Result:
        text = '{"groundedness": 4, "relevance": 5, "retrieval": 3}'

    class _Router:
        def __init__(self, _settings: object) -> None: ...

        def complete(self, *_a: object, **kw: object) -> _Result:
            assert kw["json_mode"] is True
            return _Result()

    monkeypatch.setattr(llm, "ModelRouter", _Router)
    judged = gv._judge("q", "a", "ctx", _eval_settings())
    assert judged["groundedness"] == 4


def test_extract_score_tolerates_nan_via_properties() -> None:
    from app.agent.grounding_verifier import _extract_score

    assert _extract_score({"retrieval": 4.0}, "retrieval") == 4.0
    assert (
        _extract_score({"retrieval": math.nan, "retrieval_properties": {"score": 3}}, "retrieval")
        == 3.0
    )
    assert _extract_score({"groundedness": True}, "groundedness") is None  # bool is not a score
    assert _extract_score({}, "relevance") is None


def test_judge_threshold_defaults() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.groundedness_min_score == 4.0
    assert settings.relevance_min_score == 3.0
    assert settings.retrieval_min_score == 3.0
