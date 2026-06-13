"""Course grounding over the Athenaeum catalog (offline, deterministic, cited).

The Foundry-IQ route answers course questions *grounded* in approved content.
The deterministic backend here indexes the catalog's **module-level** objectives
and summaries — structured, citable by module id, and runnable with zero
credentials — so an answer can always cite a real source. When a live Foundry IQ
knowledge base is available it swaps in behind the same ``search``/``suggest``
surface; the cache (an in-process LRU keyed by the normalized query) is the
prod-grade equivalent of caching Foundry-IQ retrieval results.

Honest label: this is the *Foundry-IQ-pattern* grounding layer when run offline.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.agent.contracts import CourseSuggestion, GroundingSource
from app.catalog.loader import default_catalog_path
from app.config import Settings, get_settings

# Tokens that carry no retrieval signal (wrapped for readability).
_STOPWORD_TEXT = """
    a an the of to in on for with and or but is are be do does how what when where which who
    why this that these those i you we they it my your our their me us them can could should
    would will shall may might want need help about into over under as at by from get got tell
    explain show me learn learning study understand know course module azure microsoft
"""
_STOPWORDS = frozenset(_STOPWORD_TEXT.split())
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_TOP_K = 4
_MIN_SCORE = 1
# A source must score at least this fraction of the top match to count as grounding.
_RELATIVE_CUTOFF = 0.5


@dataclass(frozen=True)
class GroundingDoc:
    """One indexed module — the unit of retrieval and citation."""

    ref: str  # module id, e.g. "cb-c01-m02"
    course_id: str
    course_title: str
    course_summary: str
    cert: str
    vertical: str
    title: str  # module title
    snippet: str  # module summary + objectives (the material an answer grounds on)
    text: str  # lowercased index text for scoring


def _tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS and len(t) > 2]


@lru_cache(maxsize=8)
def _load_docs(catalog_path: str) -> tuple[GroundingDoc, ...]:
    """Flatten the catalog into module-level grounding docs (cached per path)."""
    data = json.loads(Path(catalog_path).read_text(encoding="utf-8"))
    docs: list[GroundingDoc] = []
    for vertical in data["verticals"]:
        cert = vertical.get("primary_cert", "")
        for course in vertical["courses"]:
            for module in course.get("modules", []):
                objectives = module.get("objectives", [])
                summary = module.get("summary", "")
                skills = " ".join(module.get("grounded_skills", []))
                index_text = " ".join(
                    (module["title"], summary, " ".join(objectives), skills)
                ).lower()
                # The material an answer actually grounds on: module summary + objectives.
                snippet = summary
                if objectives:
                    snippet = f"{summary} Objectives: {'; '.join(objectives)}."
                docs.append(
                    GroundingDoc(
                        ref=module["id"],
                        course_id=course["id"],
                        course_title=course["title"],
                        course_summary=course["summary"],
                        cert=cert,
                        vertical=vertical["id"],
                        title=module["title"],
                        snippet=snippet,
                        text=index_text,
                    )
                )
    return tuple(docs)


def _score(query_terms: tuple[str, ...], doc: GroundingDoc) -> int:
    """Keyword-overlap score; course title and cert matches weigh extra."""
    if not query_terms:
        return 0
    score = 0
    title_terms = set(_tokenize(doc.course_title))
    for term in query_terms:
        score += doc.text.count(term)
        if term in title_terms:
            score += 3
        if doc.cert and term == doc.cert.lower().replace("-", ""):
            score += 4
    return score


class CourseGrounding:
    """Search + course-suggestion over the catalog modules (offline backend)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._path = str(
            (settings or get_settings()).athenaeum_catalog_path or default_catalog_path()
        )

    def _docs(self) -> tuple[GroundingDoc, ...]:
        return _load_docs(self._path)

    @lru_cache(maxsize=256)  # noqa: B019 — bounded, instance-scoped query cache (the IQ cache)
    def _ranked(self, query: str, catalog_id: str | None) -> tuple[GroundingDoc, ...]:
        terms = tuple(dict.fromkeys(_tokenize(query)))  # de-dupe, keep order
        pool = self._docs()
        if catalog_id:
            scoped = tuple(d for d in pool if d.course_id == catalog_id)
            pool = scoped or pool
        scored = sorted(((d, _score(terms, d)) for d in pool), key=lambda ds: ds[1], reverse=True)
        kept = [(d, s) for d, s in scored if s >= _MIN_SCORE]
        if not kept:
            return ()
        # Keep only matches near the top score so weak, generic hits don't pose as
        # grounding — credibility of the "sources" panel depends on this.
        cutoff = max(_MIN_SCORE, kept[0][1] * _RELATIVE_CUTOFF)
        return tuple(d for d, s in kept if s >= cutoff)

    def search(
        self, query: str, *, catalog_id: str | None = None, k: int = _TOP_K
    ) -> list[GroundingSource]:
        """Top-k module sources backing an answer to ``query`` (cited by module id)."""
        ranked = self._ranked(query, catalog_id)[:k]
        return [
            GroundingSource(
                ref=d.ref,
                title=f"{d.course_title} — {d.title}",
                snippet=d.snippet,
                kind="course",
            )
            for d in ranked
        ]

    def suggest(self, query: str, *, catalog_id: str | None = None) -> CourseSuggestion | None:
        """Best-matching catalog course to offer as the 'pursue this?' tool, if any."""
        ranked = self._ranked(query, catalog_id)
        if not ranked:
            return None
        # The course owning the single best-matching module is the most relevant offer.
        best_course = ranked[0].course_id
        course_docs = [d for d in self._docs() if d.course_id == best_course]
        lead = course_docs[0]
        prep = [d.title for d in course_docs[:4]]
        return CourseSuggestion(
            catalog_id=best_course,
            title=lead.course_title,
            cert=lead.cert,
            pitch=lead.course_summary,
            prep_points=prep,
        )


@lru_cache(maxsize=1)
def get_grounding() -> CourseGrounding:
    """Default course-grounding provider bound to the configured catalog (cached)."""
    return CourseGrounding()
