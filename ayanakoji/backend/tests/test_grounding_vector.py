"""Offline tests for the Cohere + Qdrant hybrid retriever (HTTP mocked via httpx)."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from app.agent import grounding_vector as gv
from app.agent.contracts import GroundingSource
from app.agent.grounding import (
    VECTOR_PROVIDER,
    FallbackRetriever,
    RetrievalActivity,
    RetrievalResult,
    get_grounding,
)
from app.config import Settings


def _settings() -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        cohere_api_key="co_key",
        qdrant_url="https://cluster.cloud.qdrant.io",
        qdrant_api_key="qd_key",
        groq_api_key="gsk_x",
        offline_llm=False,
    )


def _hit(ref: str, score: float) -> dict[str, Any]:
    return {"score": score, "payload": {"ref": ref, "title": f"T {ref}", "snippet": "s"}}


class _Transport:
    """Records requests; answers Cohere embed + Qdrant search."""

    def __init__(self, hits: list[dict[str, Any]], *, fail_embed: bool = False) -> None:
        self.hits = hits
        self.fail_embed = fail_embed
        self.calls: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        if request.url.host == "api.cohere.com":
            if self.fail_embed:
                return httpx.Response(429, json={"message": "trial limit"})
            body = json.loads(request.content)
            assert body["input_type"] == "search_query"
            assert body["output_dimension"] == 1024
            assert request.headers["authorization"] == "Bearer co_key"
            return httpx.Response(200, json={"embeddings": {"float": [[0.1] * 1024]}})
        assert request.headers["api-key"] == "qd_key"
        return httpx.Response(200, json={"result": self.hits})


@pytest.fixture(autouse=True)
def _fresh_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gv, "_query_cache", gv._QueryEmbedCache())


def _retriever(transport: _Transport) -> gv.VectorRetriever:
    client = httpx.Client(transport=httpx.MockTransport(transport))
    return gv.VectorRetriever(_settings(), client=client)


def test_retrieve_fuses_vector_and_lexical() -> None:
    transport = _Transport([_hit("cb-c01-m02", 0.71), _hit("cb-c01-m03", 0.52)])
    result = _retriever(transport).retrieve("how do azure functions triggers work")
    refs = [s.ref for s in result.sources]
    assert refs[0] == "cb-c01-m02"  # agreed on by both rankings → fused to the top
    assert result.activity.live is True
    assert result.activity.provider == VECTOR_PROVIDER
    labels = [s.label for s in result.activity.steps]
    assert labels[0] == "Query embedding"
    assert "Vector search · Qdrant" in labels
    assert labels[-1] == "Reciprocal-rank fusion"


def test_query_embedding_is_cached() -> None:
    transport = _Transport([_hit("cb-c01-m02", 0.7)])
    retriever = _retriever(transport)
    retriever.retrieve("Azure Functions triggers")
    second = retriever.retrieve("  azure functions   TRIGGERS ")
    cohere_calls = [c for c in transport.calls if c.url.host == "api.cohere.com"]
    assert len(cohere_calls) == 1
    assert "cached" in second.activity.steps[0].detail


def test_catalog_scope_becomes_qdrant_filter() -> None:
    transport = _Transport([])
    _retriever(transport).retrieve("functions", catalog_id="cb-c01")
    search = next(c for c in transport.calls if "points/search" in str(c.url))
    body = json.loads(search.content)
    assert body["filter"]["must"][0] == {"key": "course_id", "match": {"value": "cb-c01"}}


def test_quota_error_degrades_to_lexical_via_fallback() -> None:
    transport = _Transport([], fail_embed=True)
    retriever = FallbackRetriever(_retriever(transport), get_grounding())
    out = retriever.retrieve("how do azure functions triggers work")
    assert out.sources and out.sources[0].ref == "cb-c01-m02"
    assert out.activity.live is False
    assert "HTTPStatusError" in out.activity.steps[0].detail


def _lexical(*refs: str) -> RetrievalResult:
    return RetrievalResult(
        sources=[GroundingSource(ref=r, title=r, snippet="", kind="course") for r in refs],
        activity=RetrievalActivity(provider="lexical", live=False, steps=()),
    )


def test_fuse_drops_weak_vector_hits_lexical_did_not_find() -> None:
    out = gv.fuse("q", [_hit("x-weak", 0.2)], _lexical(), k=4, cache_hit=False, model="m")
    assert out.sources == []  # off-topic: neither ranking clears its floor


def test_fuse_keeps_weak_vector_hit_lexical_agrees_with() -> None:
    out = gv.fuse("q", [_hit("a", 0.2)], _lexical("a"), k=4, cache_hit=False, model="m")
    assert [s.ref for s in out.sources] == ["a"]


def test_fuse_admits_strong_vector_hit_lexical_missed() -> None:
    out = gv.fuse("q", [_hit("sem", 0.8)], _lexical("lex"), k=4, cache_hit=True, model="m")
    assert {s.ref for s in out.sources} == {"sem", "lex"}


def test_point_id_is_stable_uuid() -> None:
    assert gv.point_id("cb-c01-m02") == gv.point_id("cb-c01-m02")
    assert gv.point_id("cb-c01-m02") != gv.point_id("cb-c01-m03")


def test_keepalive_search_hits_qdrant_once_per_window(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gv, "_keepalive_state", {"at": 0.0, "result": None})
    transport = _Transport([_hit("cb-c01-m02", 0.9)])
    client = httpx.Client(transport=httpx.MockTransport(transport))
    first = gv.keepalive_search(_settings(), client=client)
    second = gv.keepalive_search(_settings(), client=client)
    assert first["ok"] is True and first["cached"] is False
    assert second["cached"] is True
    assert len(transport.calls) == 1
    assert all(c.url.host != "api.cohere.com" for c in transport.calls)  # no embed spend


def test_keepalive_search_reports_failure_without_raising(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gv, "_keepalive_state", {"at": 0.0, "result": None})

    def down(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    client = httpx.Client(transport=httpx.MockTransport(down))
    out = gv.keepalive_search(_settings(), client=client)
    assert out["ok"] is False
    assert "HTTPStatusError" in out["detail"]


def test_keepalive_endpoint_unconfigured(client: object) -> None:
    gv._keepalive_state.update(at=0.0, result=None)
    response = client.get("/health/vector")  # type: ignore[attr-defined]
    assert response.status_code == 200
    assert response.json()["ok"] is False
