"""Course-grounding tests (offline; over the committed catalog)."""

from __future__ import annotations

from app.agent.grounding import CourseGrounding, get_grounding


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
