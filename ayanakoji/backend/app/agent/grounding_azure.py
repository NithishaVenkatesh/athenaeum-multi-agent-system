"""Live Foundry IQ grounding over the Azure AI Search knowledge base.

This is the cloud adapter behind :class:`app.agent.grounding.GroundedRetriever`. It
grounds a course answer on the *real* knowledge base instead of the offline lexical
mirror: the agentic-retrieve pipeline plans the query into focused subqueries, runs
hybrid (vector + keyword) search per subquery, semantically reranks, and returns cited
references. The decomposed subqueries + planning + reranker scores are surfaced as the
retrieval *activity* (the ``include_activity`` query plan the brief asks for).

SDK imports are lazy (inside methods) so the module imports cleanly in the offline lane
where ``azure-search-documents`` is not installed — only a live ``retrieve`` touches it.
Every Azure call is best-effort: the agentic path falls back to plain hybrid search, and
a total failure raises so the caller (``FallbackRetriever``) degrades to lexical grounding.

Honest label: this is the live *Foundry IQ* grounding layer; the trace says which path
(agentic vs hybrid) actually answered, and the offline retriever takes over if neither does.
"""

from __future__ import annotations

import re

from app.agent.contracts import GroundingSource, TraceStep
from app.agent.grounding import (
    _TOP_K,
    AZURE_HYBRID_PROVIDER,
    AZURE_KB_PROVIDER,
    RetrievalActivity,
    RetrievalResult,
)
from app.config import Settings

# Trim indexed module content to a citation-sized snippet for the grounding prompt.
_SNIPPET_CHARS = 600
# A doc key is a module id (``cb-c01-m02``) or a course id (``cb-c01``); the course is
# the key with any trailing ``-mNN`` module segment removed.
_MODULE_SUFFIX = re.compile(r"-m\d+$", re.IGNORECASE)
# Catalog/course/module ids are slug-shaped. Anything else must NEVER reach an OData
# filter literal (defense-in-depth against filter injection): a non-conforming key is
# dropped from the snippet fetch, and a non-conforming course scope is simply not applied
# (the answer widens) rather than interpolated raw into the query.
_SAFE_KEY = re.compile(r"[A-Za-z0-9_-]+")


def _course_of(doc_key: str) -> str:
    """The course id owning a reference's doc key (``cb-c01-m02`` → ``cb-c01``)."""
    return _MODULE_SUFFIX.sub("", doc_key)


class AzureKnowledgeRetriever:
    """Retrieve grounding sources from the live Foundry IQ knowledge base.

    Primary path: agentic retrieve (LLM-planned subqueries → hybrid search → semantic
    rerank → cited references) with ``include_activity`` for the query plan. If that
    fails, plain hybrid (vector + semantic) search over the same index. If both fail,
    :meth:`retrieve` raises so the caller degrades to offline lexical grounding.
    """

    def __init__(self, settings: Settings) -> None:
        # Validate config eagerly (fail-loud at construction) but DO NOT import the SDK
        # here, so the offline lane can still build/select this provider in a test.
        self._cfg = settings.require_search()
        self._timeout = settings.foundry_iq_timeout_seconds

    # ── Public surface ──────────────────────────────────────────────────────────

    def retrieve(
        self, query: str, *, catalog_id: str | None = None, k: int = _TOP_K
    ) -> RetrievalResult:
        """Top-k cited sources for ``query`` plus the live agentic query-plan activity."""
        try:
            return self._agentic_retrieve(query, catalog_id, k)
        except Exception as agentic_error:  # noqa: BLE001 — degrade within the live tier
            # The agentic surface is preview; if its shape drifts or it throws, plain
            # hybrid search over the same index still grounds the answer.
            return self._hybrid_retrieve(query, catalog_id, k, agentic_error=agentic_error)

    # ── Agentic retrieve (primary) ──────────────────────────────────────────────

    def _agentic_retrieve(self, query: str, catalog_id: str | None, k: int) -> RetrievalResult:
        from azure.core.credentials import AzureKeyCredential
        from azure.search.documents.knowledgebases import KnowledgeBaseRetrievalClient
        from azure.search.documents.knowledgebases.models import (
            KnowledgeBaseMessage,
            KnowledgeBaseMessageTextContent,
            KnowledgeBaseRetrievalRequest,
        )

        client = KnowledgeBaseRetrievalClient(
            endpoint=self._cfg.endpoint,
            knowledge_base_name=self._cfg.knowledge_base_name,
            credential=AzureKeyCredential(self._cfg.admin_key),
        )
        request = KnowledgeBaseRetrievalRequest(
            messages=[
                KnowledgeBaseMessage(
                    role="user", content=[KnowledgeBaseMessageTextContent(text=query)]
                )
            ],
            include_activity=True,
            max_runtime_in_seconds=max(1, int(self._timeout)),
        )
        try:
            response = client.retrieve(request)
        finally:
            client.close()

        references = list(response.references or [])
        if catalog_id:
            references = [r for r in references if _course_of(_doc_key(r)) == catalog_id]
        references = references[:k]

        keys = [_doc_key(r) for r in references]
        snippets = self._fetch_snippets(keys) if keys else {}
        sources = [
            GroundingSource(
                ref=key,
                title=_reference_title(ref),
                snippet=snippets.get(key, ""),
                kind="course",
            )
            for ref, key in zip(references, keys, strict=True)
        ]
        activity = self._agentic_activity(response, references)
        return RetrievalResult(sources=sources, activity=activity)

    def _agentic_activity(self, response: object, references: list) -> RetrievalActivity:  # type: ignore[type-arg]
        """Render the agentic-retrieve plan (planning, subqueries, rerank) as trace steps."""
        steps: list[TraceStep] = []
        subqueries: list[str] = []
        for record in list(getattr(response, "activity", None) or []):
            kind = getattr(record, "type", "")
            if kind == "modelQueryPlanning":
                steps.append(
                    TraceStep(
                        label="Query plan · agentic",
                        passed=True,
                        detail=(
                            "LLM decomposed the question into focused subqueries "
                            f"({getattr(record, 'elapsed_ms', '?')}ms, "
                            f"{getattr(record, 'input_tokens', '?')}→"
                            f"{getattr(record, 'output_tokens', '?')} tok)"
                        ),
                        model="azure-openai",
                    )
                )
            elif kind == "searchIndex":
                sub = _activity_search_text(record)
                if sub:
                    subqueries.append(sub)
        if subqueries:
            steps.append(
                TraceStep(
                    label="Decomposed subqueries",
                    passed=True,
                    detail="; ".join(f'"{q}"' for q in subqueries),
                    model="azure-ai-search",
                )
            )
        if references:
            ranked = ", ".join(f"{_doc_key(r)}={round(_reranker(r), 2)}" for r in references)
            steps.append(
                TraceStep(
                    label="Semantic rerank (L2)",
                    passed=True,
                    detail=f"top cited references: {ranked}",
                    model="azure-ai-search",
                )
            )
        else:
            steps.append(
                TraceStep(
                    label="Knowledge base retrieve",
                    passed=False,
                    detail="No in-scope references returned by the knowledge base",
                    model="azure-ai-search",
                )
            )
        return RetrievalActivity(provider=AZURE_KB_PROVIDER, live=True, steps=tuple(steps))

    # ── Hybrid search (fallback within the live tier) ───────────────────────────

    def _hybrid_retrieve(
        self,
        query: str,
        catalog_id: str | None,
        k: int,
        *,
        agentic_error: Exception | None = None,
    ) -> RetrievalResult:
        from azure.core.credentials import AzureKeyCredential
        from azure.search.documents import SearchClient
        from azure.search.documents.models import QueryType, VectorizableTextQuery

        client = SearchClient(
            endpoint=self._cfg.endpoint,
            index_name=self._cfg.index_name,
            credential=AzureKeyCredential(self._cfg.admin_key),
        )
        vector_query = VectorizableTextQuery(
            text=query, k_nearest_neighbors=max(k * 3, 20), fields="content_vector"
        )
        # Only scope when the id is slug-shaped; never interpolate an untrusted literal.
        course_filter = (
            f"course_id eq '{catalog_id}'"
            if catalog_id and _SAFE_KEY.fullmatch(catalog_id)
            else None
        )
        try:
            results = client.search(
                search_text=query,
                vector_queries=[vector_query],
                query_type=QueryType.SEMANTIC,
                semantic_configuration_name=self._cfg.semantic_config,
                filter=course_filter,
                top=k,
                select=["id", "title", "course_id", "content"],
            )
            docs = list(results)
        finally:
            client.close()

        sources = [
            GroundingSource(
                ref=doc["id"],
                title=doc.get("title", ""),
                snippet=(doc.get("content") or "").strip()[:_SNIPPET_CHARS],
                kind="course",
            )
            for doc in docs
        ]
        steps: list[TraceStep] = []
        if agentic_error is not None:
            steps.append(
                TraceStep(
                    label="Agentic retrieve fallback",
                    passed=None,
                    detail=(
                        f"agentic retrieve failed ({type(agentic_error).__name__}); "
                        "used hybrid vector+semantic search"
                    ),
                    model="azure-ai-search",
                )
            )
        if docs:
            ranked = ", ".join(
                f"{doc['id']}={round(doc.get('@search.reranker_score', 0.0) or 0.0, 2)}"
                for doc in docs
            )
            steps.append(
                TraceStep(
                    label="Hybrid vector+semantic search",
                    passed=True,
                    detail=f"BM25+vector fused, L2 reranked: {ranked}",
                    model="azure-ai-search",
                )
            )
        else:
            steps.append(
                TraceStep(
                    label="Hybrid vector+semantic search",
                    passed=False,
                    detail="No matching documents in the index",
                    model="azure-ai-search",
                )
            )
        activity = RetrievalActivity(provider=AZURE_HYBRID_PROVIDER, live=True, steps=tuple(steps))
        return RetrievalResult(sources=sources, activity=activity)

    # ── Snippet hydration ───────────────────────────────────────────────────────

    def _fetch_snippets(self, doc_keys: list[str]) -> dict[str, str]:
        """Fetch trimmed module content for the cited doc keys (one filtered call)."""
        from azure.core.credentials import AzureKeyCredential
        from azure.search.documents import SearchClient

        client = SearchClient(
            endpoint=self._cfg.endpoint,
            index_name=self._cfg.index_name,
            credential=AzureKeyCredential(self._cfg.admin_key),
        )
        # Drop any non-slug key before it reaches the OData ``search.in`` literal.
        safe_keys = [k for k in doc_keys if _SAFE_KEY.fullmatch(k)]
        out: dict[str, str] = {}
        if not safe_keys:
            client.close()
            return out
        ids_csv = ",".join(safe_keys)
        try:
            results = client.search(
                search_text="*",
                filter=f"search.in(id, '{ids_csv}', ',')",
                select=["id", "content"],
                top=len(safe_keys),
            )
            for doc in results:
                out[doc["id"]] = (doc.get("content") or "").strip()[:_SNIPPET_CHARS]
        finally:
            client.close()
        return out


def _ref_field(reference: object, attr: str, key: str) -> object:
    """Read a reference field by typed attribute, else by mapping key (SDK-shape tolerant)."""
    value = getattr(reference, attr, None)
    if value is not None:
        return value
    getter = getattr(reference, "get", None)
    return getter(key) if callable(getter) else None


def _doc_key(reference: object) -> str:
    """The reference's source document key (a module or course id), or ''."""
    return str(_ref_field(reference, "doc_key", "docKey") or "")


def _reranker(reference: object) -> float:
    """The reference's L2 semantic reranker score (0.0 when absent/unparseable)."""
    try:
        return float(_ref_field(reference, "reranker_score", "rerankerScore") or 0.0)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _reference_title(reference: object) -> str:
    """Best title for a knowledge-base reference, across preview-SDK shapes.

    The 12.x model is a ``MutableMapping`` carrying ``title`` as a mapped key (no typed
    attribute); 11.7.x carried it in ``additional_properties``. Fall back to the doc key
    so a source is never untitled.
    """
    title = getattr(reference, "title", None)
    if title:
        return str(title)
    getter = getattr(reference, "get", None)
    if callable(getter):  # 12.x mapping model exposes 'title' only via .get(...)
        mapped = getter("title")
        if mapped:
            return str(mapped)
    extra = getattr(reference, "additional_properties", None) or {}
    if isinstance(extra, dict) and extra.get("title"):
        return str(extra["title"])
    return str(getattr(reference, "doc_key", "") or "source")


def _activity_search_text(record: object) -> str | None:
    """Pull the subquery text out of a searchIndex activity record (shape-tolerant)."""
    args = getattr(record, "search_index_arguments", None)
    if args is None:
        return None
    search = getattr(args, "search", None)
    if search is None and isinstance(args, dict):
        search = args.get("search")
    return str(search) if search else None
