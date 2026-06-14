"""Unit tests for the grounding relevance floor (findings A1 + A5).

- Off-catalog multi-term queries that share a single keyword with a module must
  NOT be returned as grounding (A1: no false coverage).
- Genuine catalog topics must still ground.
- A broad single keyword must not sprawl across multiple courses (A5).
"""

from __future__ import annotations

import pytest
from app.agent.grounding import CourseGrounding

GROUNDING = CourseGrounding()


# Off-catalog topics that previously matched a single spurious keyword.
@pytest.mark.parametrize(
    "query",
    [
        "quantum cryptography lattice key exchange",  # only "key" matched
        "explain the monetary policy of the european central bank",  # only "policy"
        "tell me about photosynthesis in plants",
        "how do I bake sourdough bread",
        "the history of the roman empire",
    ],
)
def test_off_catalog_not_grounded(query: str) -> None:
    assert GROUNDING.search(query) == [], f"false grounding for: {query!r}"
    assert GROUNDING.suggest(query) is None, f"false suggestion for: {query!r}"


# Genuine catalog topics must still return grounding sources.
@pytest.mark.parametrize(
    "query",
    [
        "explain how Azure Functions scaling works",
        "what is managed identity in Azure",
        "tell me about Cosmos DB storage",
        "real-time streaming analytics",
        "CI/CD pipelines",
    ],
)
def test_real_topics_still_grounded(query: str) -> None:
    assert GROUNDING.search(query), f"lost grounding for real topic: {query!r}"


def test_broad_keyword_does_not_sprawl_across_courses() -> None:
    """'data' must ground in one course, not span several (A5)."""
    sources = GROUNDING.search("data", k=8)
    courses = {"-".join(s.ref.split("-")[:2]) for s in sources}
    assert len(courses) <= 1, f"'data' sprawled across courses: {courses}"


def test_scoped_search_stays_in_course() -> None:
    """A locked chat never widens beyond its course."""
    sources = GROUNDING.search("identity", catalog_id="cb-c01")
    assert all(s.ref.startswith("cb-c01") for s in sources)
