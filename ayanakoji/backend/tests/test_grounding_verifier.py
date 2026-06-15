"""Tests for the groundedness verifier selection + the Azure NLI evaluation adapter.

The deterministic selection (skip-when-uncited, Azure-when-available, lexical fallback)
is offline-unit-tested; the live Azure evaluators are exercised under ``integration``.
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
    """Settings where evaluation_available is True (AOAI judge configured + online)."""
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        foundry_project_endpoint="https://r.services.ai.azure.com/api/projects/p",
        azure_openai_endpoint="https://r.openai.azure.com/",
        azure_openai_api_key="real-key",
        offline_llm=False,
    )


def test_verify_grounding_skips_when_no_citation() -> None:
    # Nothing cites an approved source: the expensive judges are not spent, and the
    # no-citation case is left to the streaming guard's own disclaimer.
    verdict = verify_grounding("a general answer", _SRC, query="q", settings=_eval_settings())
    assert verdict.grounded is True
    assert verdict.metrics == ()
    assert "deterministic" in verdict.provider


def test_verify_grounding_falls_back_to_lexical_when_azure_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.agent.grounding_verifier as gv

    def _boom(*_a: object, **_k: object) -> object:
        raise RuntimeError("evaluator down")

    monkeypatch.setattr(gv, "azure_grounding", _boom)
    answer = "Cosmos DB partition keys shard throughput [cb-c01-m02]."  # cross-topic citation
    verdict = verify_grounding(answer, _SRC, query="q", settings=_eval_settings())
    # Degraded to the deterministic floor, which still flags the topic-disjoint citation.
    assert verdict.provider == "deterministic lexical overlap"
    assert verdict.grounded is False


def test_verify_grounding_uses_lexical_when_evaluation_unavailable() -> None:
    offline = Settings(_env_file=None, offline_llm=True)  # type: ignore[call-arg]
    answer = "Azure Functions use triggers and bindings [cb-c01-m02]."
    verdict = verify_grounding(answer, _SRC, query="q", settings=offline)
    assert verdict.provider == "deterministic lexical overlap"
    assert verdict.grounded is True


@pytest.mark.parametrize(
    ("groundedness_score", "expected_grounded"),
    [
        (3.0, False),  # "some claims unsupported" — a C-minus that must NOT pass now
        (3.9, False),  # still below the 4.0 mostly/fully-supported bar
        (4.0, True),  # "mostly/fully supported" — clears the gate
        (5.0, True),
    ],
)
def test_azure_grounding_gate_at_four(
    monkeypatch: pytest.MonkeyPatch, groundedness_score: float, expected_grounded: bool
) -> None:
    """The Azure groundedness gate passes at >=4 (default), not at 3.

    A score of 3 on Azure's 1..5 rubric means "some claims unsupported" — a partially
    grounded answer the gate must now reject; only 4+ ("mostly/fully supported") passes.
    """
    import app.agent.grounding_verifier as gv

    # Stub the evaluator surface so no live Azure call is made: each evaluator returns
    # the score we want under the {name} key; require_foundry needs no real creds here.
    class _StubEval:
        def __init__(self, _model_config: object) -> None: ...

        def __call__(self, **_kw: object) -> dict[str, object]:
            return {self._name: groundedness_score}

    class _Grounded(_StubEval):
        _name = "groundedness"

    class _Relevance(_StubEval):
        _name = "relevance"

    class _Retrieval(_StubEval):
        _name = "retrieval"

    import sys
    import types

    fake = types.ModuleType("azure.ai.evaluation")
    fake.AzureOpenAIModelConfiguration = lambda **_kw: object()  # type: ignore[attr-defined]
    fake.GroundednessEvaluator = _Grounded  # type: ignore[attr-defined]
    fake.RelevanceEvaluator = _Relevance  # type: ignore[attr-defined]
    fake.RetrievalEvaluator = _Retrieval  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "azure.ai.evaluation", fake)
    # Skip the Content-Safety-backed Pro evaluator (no project / no live call).
    monkeypatch.setattr(gv, "_groundedness_pro", lambda *_a, **_k: None)

    settings = _eval_settings()
    assert settings.groundedness_min_score == 4.0  # the raised default
    verdict = gv.azure_grounding("q", "an answer [cb-c01-m02]", _SRC, settings)
    assert verdict.grounded is expected_grounded


def _install_judge_stubs(
    monkeypatch: pytest.MonkeyPatch,
    *,
    groundedness: float | None,
    relevance: float | None,
    retrieval: float | None,
    pro: float | None = None,
) -> None:
    """Stub the azure.ai.evaluation surface with per-judge scores.

    A ``None`` score models a judge that errored: it returns ``{}`` so ``_extract_score``
    yields ``None`` and that judge does not gate. ``pro`` patches ``_groundedness_pro``.
    """
    import sys
    import types

    import app.agent.grounding_verifier as gv

    def _payload(name: str, score: float | None) -> dict[str, object]:
        return {} if score is None else {name: score}

    class _Grounded:
        def __init__(self, _model_config: object) -> None: ...

        def __call__(self, **_kw: object) -> dict[str, object]:
            return _payload("groundedness", groundedness)

    class _Relevance:
        def __init__(self, _model_config: object) -> None: ...

        def __call__(self, **_kw: object) -> dict[str, object]:
            return _payload("relevance", relevance)

    class _Retrieval:
        def __init__(self, _model_config: object) -> None: ...

        def __call__(self, **_kw: object) -> dict[str, object]:
            return _payload("retrieval", retrieval)

    fake = types.ModuleType("azure.ai.evaluation")
    fake.AzureOpenAIModelConfiguration = lambda **_kw: object()  # type: ignore[attr-defined]
    fake.GroundednessEvaluator = _Grounded  # type: ignore[attr-defined]
    fake.RelevanceEvaluator = _Relevance  # type: ignore[attr-defined]
    fake.RetrievalEvaluator = _Retrieval  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "azure.ai.evaluation", fake)
    monkeypatch.setattr(gv, "_groundedness_pro", lambda *_a, **_k: pro)


def test_azure_grounding_gates_on_relevance(monkeypatch: pytest.MonkeyPatch) -> None:
    # (a) groundedness clears its bar but relevance is below 3 → ungrounded. The verdict
    # must gate on every scoring judge, not groundedness alone, and the reason must name it.
    import app.agent.grounding_verifier as gv

    _install_judge_stubs(monkeypatch, groundedness=5.0, relevance=2.0, retrieval=5.0)
    verdict = gv.azure_grounding("q", "an answer [cb-c01-m02]", _SRC, _eval_settings())
    assert verdict.grounded is False
    assert "relevance 2 < 3" in verdict.reason


def test_azure_grounding_passes_when_every_judge_clears(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # (b) all three judges clear their thresholds → grounded.
    import app.agent.grounding_verifier as gv

    _install_judge_stubs(monkeypatch, groundedness=5.0, relevance=5.0, retrieval=5.0)
    verdict = gv.azure_grounding("q", "an answer [cb-c01-m02]", _SRC, _eval_settings())
    assert verdict.grounded is True


def test_azure_grounding_absent_judge_does_not_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # (c) relevance errored (no score) → it must NOT block. Groundedness + retrieval clear,
    # relevance is absent → grounded stays True (fail-open for an absent judge).
    import app.agent.grounding_verifier as gv

    _install_judge_stubs(monkeypatch, groundedness=5.0, relevance=None, retrieval=5.0)
    verdict = gv.azure_grounding("q", "an answer [cb-c01-m02]", _SRC, _eval_settings())
    assert verdict.grounded is True


def test_azure_grounding_gates_on_pro_when_scored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # groundedness/relevance/retrieval all clear, but the Content-Safety Pro judge returns
    # a real low score → pro tightens the gate to ungrounded and names itself in the reason.
    import app.agent.grounding_verifier as gv

    _install_judge_stubs(monkeypatch, groundedness=5.0, relevance=5.0, retrieval=5.0, pro=1.0)
    verdict = gv.azure_grounding("q", "an answer [cb-c01-m02]", _SRC, _eval_settings())
    assert verdict.grounded is False
    assert "groundedness_pro 1 < 3" in verdict.reason
    assert ("groundedness_pro", 1.0) in verdict.metrics


def test_extract_score_tolerates_nan_via_properties() -> None:
    from app.agent.grounding_verifier import _extract_score

    assert _extract_score({"retrieval": 4.0}, "retrieval") == 4.0
    # retrieval can return nan at top level; the real score sits in *_properties.score.
    assert (
        _extract_score({"retrieval": math.nan, "retrieval_properties": {"score": 5}}, "retrieval")
        == 5.0
    )
    assert _extract_score({"groundedness": True}, "groundedness") is None  # bool is not a score
    assert _extract_score({}, "relevance") is None


def test_judge_threshold_defaults() -> None:
    # The new per-judge thresholds default to 3.0 on the 1..5 rubric; groundedness stays 4.0.
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.groundedness_min_score == 4.0
    assert settings.relevance_min_score == 3.0
    assert settings.retrieval_min_score == 3.0
    assert settings.groundedness_pro_min_score == 3.0


# ── Live Azure evaluators ────────────────────────────────────────────────────────


@pytest.mark.integration
def test_live_azure_grounding_flags_false_claim_on_real_citation() -> None:
    settings = Settings()  # reads backend/.env
    if not settings.foundry_configured:
        pytest.skip("Azure OpenAI not configured")
    try:
        import azure.ai.evaluation  # noqa: F401
    except ImportError:
        pytest.skip("azure-ai-evaluation not installed")
    from app.agent.grounding_verifier import azure_grounding

    q = "How do Azure Functions triggers and bindings work?"
    grounded = "Triggers start a function and bindings connect it to services [cb-c01-m02]."
    false_claim = "Azure Functions are billed only by gigabytes of disk stored [cb-c01-m02]."

    good = azure_grounding(q, grounded, _SRC, settings)
    assert good.provider == "Azure AI evaluation"
    # Assert on the groundedness judge — the decision-driver — not the composite verdict.
    # The retrieval judge scores this single thin snippet at the 2/3 gate boundary, so the
    # composite verdict can flip on retrieval-judge noise that is orthogonal to whether the
    # *claim* is grounded. The all-judges-clear composite path is covered deterministically
    # by test_azure_grounding_passes_when_every_judge_clears.
    assert dict(good.metrics).get("groundedness", 0) >= settings.groundedness_min_score

    bad = azure_grounding(q, false_claim, _SRC, settings)
    # A real, existing module id on a false statement: the NLI groundedness judge catches
    # it where the id-existence guard and the lexical floor cannot — the groundedness score
    # itself drops below the bar, which sinks the composite verdict.
    assert dict(bad.metrics).get("groundedness", 0) < settings.groundedness_min_score
    assert bad.grounded is False
