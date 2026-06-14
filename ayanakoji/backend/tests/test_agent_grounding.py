"""Course-grounding tests (offline; over the committed catalog)."""

from __future__ import annotations

from app.agent.contracts import GroundingSource
from app.agent.grounding import (
    LEXICAL_PROVIDER,
    CourseGrounding,
    FallbackRetriever,
    RetrievalActivity,
    RetrievalResult,
    get_grounding,
    get_retriever,
)
from app.config import Settings


def _foundry_iq_settings() -> Settings:
    """Settings where foundry_iq_enabled is True (search creds + online)."""
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        search_endpoint="https://athenaeum-search.search.windows.net",
        search_admin_key="real-admin-key",
        groq_api_key="gsk_realkey",
        offline_llm=False,
    )


class _RaisingRetriever:
    """A primary retriever that always fails — to exercise the lexical fallback."""

    def retrieve(self, query: str, *, catalog_id: str | None = None, k: int = 4) -> RetrievalResult:
        raise RuntimeError("simulated live agentic-retrieve outage")


class _StubRetriever:
    """A primary retriever that returns a fixed live result."""

    def __init__(self, result: RetrievalResult) -> None:
        self._result = result

    def retrieve(self, query: str, *, catalog_id: str | None = None, k: int = 4) -> RetrievalResult:
        return self._result


def test_get_retriever_offline_is_lexical() -> None:
    settings = Settings(_env_file=None, offline_llm=True)  # type: ignore[call-arg]
    assert get_retriever(settings) is get_grounding()


def test_get_retriever_live_wraps_azure_in_a_fallback() -> None:
    retriever = get_retriever(_foundry_iq_settings())
    assert isinstance(retriever, FallbackRetriever)


def test_fallback_returns_primary_result_when_live_succeeds() -> None:
    live = RetrievalResult(
        sources=[GroundingSource(ref="cb-c01-m02", title="t", snippet="s", kind="course")],
        activity=RetrievalActivity(provider="live", live=True, steps=()),
    )
    retriever = FallbackRetriever(_StubRetriever(live), get_grounding())
    out = retriever.retrieve("azure functions")
    assert out is live
    assert out.activity.live is True


def test_fallback_degrades_to_lexical_when_live_fails() -> None:
    retriever = FallbackRetriever(_RaisingRetriever(), get_grounding())
    out = retriever.retrieve("how do azure functions triggers work")
    # The lexical fallback still grounds the answer (no 500), and the trace is honest.
    assert out.sources, "fallback should still return lexical sources"
    assert out.sources[0].ref == "cb-c01-m02"
    assert out.activity.live is False
    assert out.activity.steps[0].label == "Live retrieval fallback"
    assert "fell back to offline lexical" in out.activity.steps[0].detail


def test_retrieve_returns_sources_with_lexical_query_plan() -> None:
    g = CourseGrounding()
    result = g.retrieve("How do I use Azure Functions triggers and bindings?")
    assert isinstance(result, RetrievalResult)
    # Same sources as search() — retrieve() just adds the activity.
    assert [s.ref for s in result.sources] == [
        s.ref for s in g.search("How do I use Azure Functions triggers and bindings?")
    ]
    assert result.sources[0].ref == "cb-c01-m02"
    # The activity is the honestly-labelled offline query plan.
    assert result.activity.provider == LEXICAL_PROVIDER
    assert result.activity.live is False
    labels = [s.label for s in result.activity.steps]
    assert "Query plan · lexical" in labels
    plan = next(s for s in result.activity.steps if s.label == "Query plan · lexical")
    # The plan surfaces the actual content terms it retrieved on.
    assert "functions" in plan.detail.lower()
    assert "triggers" in plan.detail.lower()
    overlap = next(s for s in result.activity.steps if "overlap" in s.label.lower())
    assert overlap.passed is True
    assert "cb-c01-m02" in overlap.detail


def test_retrieve_off_topic_reports_empty_plan() -> None:
    g = CourseGrounding()
    result = g.retrieve("who won the cricket world cup final")
    assert result.sources == []
    assert result.activity.live is False
    overlap = next(s for s in result.activity.steps if "overlap" in s.label.lower())
    assert overlap.passed is False
    assert "cleared the relevance floor" in overlap.detail


def test_retrieve_respects_catalog_scope() -> None:
    g = CourseGrounding()
    result = g.retrieve("storage and data", catalog_id="cb-c02")
    assert result.sources
    assert all(s.ref.startswith("cb-c02") for s in result.sources)


def test_search_surfaces_relevant_module_first() -> None:
    g = CourseGrounding()
    sources = g.search("How do I use Azure Functions triggers and bindings?")
    assert sources, "expected at least one grounded source"
    # The Functions module should rank first for a Functions query.
    assert sources[0].ref == "cb-c01-m02"
    assert all(s.ref and s.title and s.kind == "course" for s in sources)


def test_search_off_topic_returns_no_sources() -> None:
    g = CourseGrounding()
    assert g.search("who won the cricket world cup final") == []


def test_search_respects_catalog_scope() -> None:
    g = CourseGrounding()
    sources = g.search("storage and data", catalog_id="cb-c02")
    assert sources
    # Scoped to the linked course — every source's module id is under cb-c02.
    assert all(s.ref.startswith("cb-c02") for s in sources)


def test_suggest_returns_course_of_top_match() -> None:
    g = CourseGrounding()
    suggestion = g.suggest("How do I use Azure Functions triggers and bindings?")
    assert suggestion is not None
    assert suggestion.catalog_id == "cb-c01"
    assert suggestion.cert == "AZ-204"
    assert suggestion.prep_points  # module titles to prepare


def test_suggest_off_topic_is_none() -> None:
    g = CourseGrounding()
    assert g.suggest("what's the weather tomorrow") is None


def test_k_limits_result_count() -> None:
    g = CourseGrounding()
    assert len(g.search("azure data storage security identity", k=2)) <= 2


def test_get_grounding_is_cached_singleton() -> None:
    assert get_grounding() is get_grounding()
