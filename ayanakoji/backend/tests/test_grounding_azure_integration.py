"""Live Foundry IQ retrieval tests (hit Azure AI Search; need creds + the foundry group).

Marked ``integration`` so the offline unit lane skips them. They verify the agentic
knowledge-base retrieve returns catalog-aligned, cited module sources plus the
``include_activity`` query plan, and that course scoping holds.
"""

from __future__ import annotations

import pytest
from app.config import Settings, get_settings

pytestmark = pytest.mark.integration


def _live_retriever():  # type: ignore[no-untyped-def]
    settings: Settings = get_settings()
    if not settings.search_configured:
        pytest.skip("Azure AI Search not configured (set SEARCH_ENDPOINT / SEARCH_ADMIN_KEY)")
    try:
        import azure.search.documents.knowledgebases  # noqa: F401
    except ImportError:
        pytest.skip("azure-search-documents not installed (foundry dependency group)")
    from app.agent.grounding_azure import AzureKnowledgeRetriever

    return AzureKnowledgeRetriever(settings)


def test_live_agentic_retrieve_returns_cited_module_with_query_plan() -> None:
    retriever = _live_retriever()
    result = retriever.retrieve("how do azure functions triggers and bindings work")

    # A live agentic-retrieve answer, grounded on real cited modules.
    assert result.activity.live is True
    refs = [s.ref for s in result.sources]
    assert "cb-c01-m02" in refs, f"expected the Functions module in {refs}"
    assert all(s.title and s.snippet for s in result.sources), "sources must be titled + hydrated"

    # The include_activity query plan is surfaced: the LLM-decomposed subqueries.
    labels = [step.label for step in result.activity.steps]
    assert any("subqueries" in label.lower() or "agentic" in label.lower() for label in labels)


def test_live_retrieve_respects_course_scope() -> None:
    retriever = _live_retriever()
    result = retriever.retrieve("event-driven functions", catalog_id="cb-c01")
    assert result.sources
    assert all(s.ref.startswith("cb-c01") for s in result.sources)


def test_live_retrieve_off_topic_returns_no_in_scope_sources() -> None:
    retriever = _live_retriever()
    # A topic the catalog doesn't cover, scoped to a course: no in-scope references.
    result = retriever.retrieve("how do I bake sourdough bread", catalog_id="cb-c01")
    assert result.sources == []
    assert result.activity.live is True
