"""Live course grounding: Cohere embeddings + Qdrant Cloud vector search.

Replaces the Azure AI Search / Foundry IQ adapter. Both services are called over
plain REST with the existing ``httpx`` stack (no extra SDKs):

- **Cohere** ``embed-v4.0`` embeds the learner's question (``input_type=search_query``).
  The trial key is capped at 1,000 calls/month, so query embeddings are cached
  in-process and the module corpus is embedded once, offline, by
  ``scripts/reindex_vectors.py`` (vectors committed to ``app/data/course_vectors.json``).
- **Qdrant Cloud** (free cluster) holds one point per catalog module, payload-tagged
  with its course so a scoped chat never cites another course.

The result is fused with the deterministic lexical retriever (reciprocal-rank fusion),
so a strong keyword/cert-code match still wins and the lexical relevance floor keeps
off-topic questions ungrounded. Any failure (quota, network, suspended cluster)
raises, and :class:`app.agent.grounding.FallbackRetriever` degrades to lexical-only
with an honest trace note.
"""

from __future__ import annotations

import uuid
from collections import OrderedDict
from threading import Lock
from typing import Any

import httpx

from app.agent.contracts import GroundingSource, TraceStep
from app.agent.grounding import (
    VECTOR_PROVIDER,
    CourseGrounding,
    RetrievalActivity,
    RetrievalResult,
    get_grounding,
)
from app.config import Settings, VectorSearchConfig

COHERE_EMBED_URL = "https://api.cohere.com/v2/embed"
_TOP_K = 4
# Cosine floor for a vector hit to count on its own (embed-v4.0 scores unrelated
# text around 0.1-0.3; on-topic module matches land well above 0.4).
VECTOR_MIN_SCORE = 0.40
# Reciprocal-rank-fusion constant (the standard k=60).
_RRF_K = 60
_QUERY_CACHE_SIZE = 512


def point_id(ref: str) -> str:
    """Stable Qdrant point id for a module ref (Qdrant ids must be uint or UUID)."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"athenaeum:{ref}"))


def cohere_embed(
    texts: list[str],
    *,
    cfg: VectorSearchConfig,
    input_type: str,
    timeout: float,
    client: httpx.Client | None = None,
) -> list[list[float]]:
    """Embed ``texts`` with Cohere (one API call; Cohere accepts up to 96 texts)."""
    http = client or httpx.Client(timeout=timeout)
    try:
        response = http.post(
            COHERE_EMBED_URL,
            headers={"Authorization": f"Bearer {cfg.cohere_api_key}"},
            json={
                "model": cfg.embed_model,
                "texts": texts,
                "input_type": input_type,
                "embedding_types": ["float"],
                "output_dimension": cfg.embed_dimensions,
            },
            timeout=timeout,
        )
        response.raise_for_status()
        vectors: list[list[float]] = response.json()["embeddings"]["float"]
        return vectors
    finally:
        if client is None:
            http.close()


class _QueryEmbedCache:
    """Process-wide LRU of query → embedding, so repeat questions cost no Cohere call."""

    def __init__(self, size: int = _QUERY_CACHE_SIZE) -> None:
        self._size = size
        self._data: OrderedDict[str, list[float]] = OrderedDict()
        self._lock = Lock()

    def get(self, key: str) -> list[float] | None:
        with self._lock:
            hit = self._data.get(key)
            if hit is not None:
                self._data.move_to_end(key)
            return hit

    def put(self, key: str, vector: list[float]) -> None:
        with self._lock:
            self._data[key] = vector
            self._data.move_to_end(key)
            while len(self._data) > self._size:
                self._data.popitem(last=False)


_query_cache = _QueryEmbedCache()


class VectorRetriever:
    """Hybrid retriever: Qdrant vector search fused with the lexical retriever."""

    def __init__(
        self,
        settings: Settings,
        *,
        lexical: CourseGrounding | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._cfg = settings.require_vector_search()  # fail loud on half-config
        self._timeout = settings.vector_search_timeout_seconds
        self._lexical = lexical or get_grounding()
        self._client = client

    # ── Live calls ──────────────────────────────────────────────────────────────

    def _http(self) -> httpx.Client:
        return self._client or httpx.Client(timeout=self._timeout)

    def _embed_query(self, query: str) -> tuple[list[float], bool]:
        key = " ".join(query.lower().split())
        cached = _query_cache.get(key)
        if cached is not None:
            return cached, True
        vector = cohere_embed(
            [query],
            cfg=self._cfg,
            input_type="search_query",
            timeout=self._timeout,
            client=self._client,
        )[0]
        _query_cache.put(key, vector)
        return vector, False

    def _search(self, vector: list[float], catalog_id: str | None, k: int) -> list[dict[str, Any]]:
        body: dict[str, Any] = {"vector": vector, "limit": k, "with_payload": True}
        if catalog_id:
            body["filter"] = {"must": [{"key": "course_id", "match": {"value": catalog_id}}]}
        http = self._http()
        try:
            response = http.post(
                f"{self._cfg.qdrant_url}/collections/{self._cfg.collection}/points/search",
                headers={"api-key": self._cfg.qdrant_api_key},
                json=body,
                timeout=self._timeout,
            )
            response.raise_for_status()
            hits: list[dict[str, Any]] = response.json()["result"]
            return hits
        finally:
            if self._client is None:
                http.close()

    # ── Public surface ──────────────────────────────────────────────────────────

    def retrieve(
        self, query: str, *, catalog_id: str | None = None, k: int = _TOP_K
    ) -> RetrievalResult:
        """Top-k cited module sources for ``query`` plus the hybrid retrieval trace."""
        vector, cache_hit = self._embed_query(query)
        hits = self._search(vector, catalog_id, k * 2)
        lexical = self._lexical.retrieve(query, catalog_id=catalog_id, k=k * 2)
        return fuse(query, hits, lexical, k=k, cache_hit=cache_hit, model=self._cfg.embed_model)


def fuse(
    query: str,
    hits: list[dict[str, Any]],
    lexical: RetrievalResult,
    *,
    k: int,
    cache_hit: bool,
    model: str,
) -> RetrievalResult:
    """Reciprocal-rank-fuse vector hits with lexical sources (pure; unit-tested).

    A vector hit below :data:`VECTOR_MIN_SCORE` only counts if lexical retrieval also
    found that module, so the lexical relevance floor still rejects off-topic queries.
    """
    del query
    lexical_refs = [s.ref for s in lexical.sources]
    by_ref: dict[str, GroundingSource] = {s.ref: s for s in lexical.sources}
    scores: dict[str, float] = {}
    vector_scores: dict[str, float] = {}

    for rank, hit in enumerate(hits):
        payload = hit.get("payload") or {}
        ref = str(payload.get("ref", ""))
        score = float(hit.get("score", 0.0))
        if not ref or (score < VECTOR_MIN_SCORE and ref not in lexical_refs):
            continue
        vector_scores[ref] = score
        scores[ref] = scores.get(ref, 0.0) + 1.0 / (_RRF_K + rank + 1)
        by_ref.setdefault(
            ref,
            GroundingSource(
                ref=ref,
                title=str(payload.get("title", ref)),
                snippet=str(payload.get("snippet", "")),
                kind="course",
            ),
        )
    for rank, ref in enumerate(lexical_refs):
        scores[ref] = scores.get(ref, 0.0) + 1.0 / (_RRF_K + rank + 1)

    ranked = sorted(scores, key=lambda r: scores[r], reverse=True)[:k]
    sources = [by_ref[r] for r in ranked]

    vector_detail = (
        ", ".join(f"{r} ({s:.2f})" for r, s in sorted(vector_scores.items(), key=lambda x: -x[1]))
        or f"no module cleared the {VECTOR_MIN_SCORE:.2f} cosine floor"
    )
    steps = (
        TraceStep(
            label="Query embedding",
            passed=True,
            detail=("cached (no API call)" if cache_hit else "embedded via Cohere") + f" · {model}",
            model=model,
        ),
        TraceStep(
            label="Vector search · Qdrant",
            passed=bool(vector_scores),
            detail=vector_detail,
            model="qdrant-cloud",
        ),
        *lexical.activity.steps,
        TraceStep(
            label="Reciprocal-rank fusion",
            passed=bool(sources),
            detail=", ".join(ranked) or "no grounded modules",
            model="rrf",
        ),
    )
    activity = RetrievalActivity(provider=VECTOR_PROVIDER, live=True, steps=steps)
    return RetrievalResult(sources=sources, activity=activity)
