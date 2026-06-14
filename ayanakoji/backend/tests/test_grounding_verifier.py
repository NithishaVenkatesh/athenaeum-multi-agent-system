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
    assert good.grounded is True
    assert good.provider == "Azure AI evaluation"
    assert dict(good.metrics).get("groundedness", 0) >= settings.groundedness_min_score

    bad = azure_grounding(q, false_claim, _SRC, settings)
    # A real, existing module id on a false statement: the NLI groundedness judge catches
    # it where the id-existence guard and the lexical floor cannot.
    assert bad.grounded is False
