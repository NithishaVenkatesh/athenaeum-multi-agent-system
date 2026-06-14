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
import math
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
# Relevance floor (A1): a module only grounds an answer if the query terms it matches
# carry enough of the query's *specificity*. Specificity is IDF-weighted, so matching a
# rare topical term (functions, pipelines) is strong, while matching only a generic term
# ("key") while the query's defining terms (quantum, cryptography, lattice) are absent
# from the whole catalog is weak — that single spurious hit is rejected, not asserted as
# coverage. A cert-code match (e.g. "DP-203") is exempt: it is strong grounding.
_MIN_IDF_COVERAGE = 0.28
# Two-letter topics carry real signal in this domain; keep them despite the length floor.
_KEEP_SHORT = frozenset({"ai", "ml", "bi", "db", "iam", "vm", "k8s", "ci", "cd"})
# Synonyms so a learner's phrasing reaches the indexed wording (serverless ↔ functions).
_SYNONYMS: dict[str, tuple[str, ...]] = {
    "serverless": ("functions", "function"),
    "function": ("functions",),
    "container": ("containers", "kubernetes", "aks"),
    "auth": ("authentication", "identity"),
    "login": ("authentication", "identity"),
    "ml": ("machine", "learning"),
    "ai": ("cognitive", "openai", "intelligence"),
    "pipeline": ("pipelines",),
    "db": ("database", "cosmos", "sql"),
    "warehouse": ("synapse", "fabric"),
}


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
    return [
        t
        for t in _TOKEN_RE.findall(text.lower())
        if t not in _STOPWORDS and (len(t) > 2 or t in _KEEP_SHORT)
    ]


def _expand(terms: tuple[str, ...]) -> tuple[str, ...]:
    """Add domain synonyms so a learner's wording reaches the indexed terms."""
    out = list(terms)
    for term in terms:
        out.extend(_SYNONYMS.get(term, ()))
    return tuple(dict.fromkeys(out))


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


def _cert_key(doc: GroundingDoc) -> str:
    """The doc's cert as a comparable key, e.g. 'DP-203' → 'dp203'."""
    return doc.cert.lower().replace("-", "").replace(" ", "") if doc.cert else ""


@lru_cache(maxsize=1024)
def _term_re(term: str) -> re.Pattern[str]:
    """A word-boundary matcher allowing only a short suffix (plurals/inflections).

    ``\\bterm[a-z]{0,2}\\b`` matches 'cat'→'cat'/'cats' and 'function'→'functions',
    but NOT 'cat'→'catalog' or 'cat'→'application'; so a short off-topic token can't
    spuriously ground on an unrelated longer word (A1). Longer relations are handled
    deliberately by the synonym map, not by accidental prefixing.
    """
    return re.compile(r"\b" + re.escape(term) + r"[a-z]{0,2}\b")


def _term_hits(term: str, text: str) -> int:
    """Occurrences of the term at a word boundary (so 'cat' hits 'cats', not 'application')."""
    return len(_term_re(term).findall(text))


def _term_in(term: str, doc: GroundingDoc) -> bool:
    """True if the query term (or a domain synonym) appears at a word boundary in the doc.

    Word-boundary, not substring: 'cat' matches 'cats'/'catalog' but never 'application'
    or 'authentication', so a short off-topic token can't spuriously ground (A1).
    """
    return any(_term_re(variant).search(doc.text) for variant in (term, *_SYNONYMS.get(term, ())))


def _idf_weights(q_terms: tuple[str, ...], corpus: tuple[GroundingDoc, ...]) -> dict[str, float]:
    """Smoothed IDF per query term over the whole catalog.

    A term in few/no modules (quantum, cryptography) gets a high weight; a generic
    term in many modules (key, data, policy) gets a low one. df=0 → maximum weight,
    so a query whose defining terms are absent can't be "covered" by a generic hit.
    """
    n = len(corpus)
    weights: dict[str, float] = {}
    for term in q_terms:
        df = sum(1 for d in corpus if _term_in(term, d))
        weights[term] = math.log((n + 1) / (df + 1)) + 1.0
    return weights


def _relevance_ok(
    q_terms: tuple[str, ...], doc: GroundingDoc, idf: dict[str, float], cert_blob: str
) -> bool:
    """True if the doc clears the IDF-weighted relevance floor (or matches the cert)."""
    if (cert_key := _cert_key(doc)) and cert_key in cert_blob:
        return True
    total = sum(idf.values())
    if total <= 0:
        return False
    matched = sum(weight for term, weight in idf.items() if _term_in(term, doc))
    return matched / total >= _MIN_IDF_COVERAGE


def _score(query_terms: tuple[str, ...], doc: GroundingDoc, cert_blob: str) -> int:
    """Keyword-overlap score; course title and cert matches weigh extra.

    ``cert_blob`` is the query with non-alphanumerics stripped, so a cert typed
    with a hyphen ("DP-203") still matches the catalog cert ("dp203").
    """
    if not query_terms:
        return 0
    score = 0
    title_terms = set(_tokenize(doc.course_title))
    cert_key = doc.cert.lower().replace("-", "").replace(" ", "") if doc.cert else ""
    for term in query_terms:
        score += _term_hits(term, doc.text)
        if term in title_terms:
            score += 3
    if cert_key and cert_key in cert_blob:
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
        q_terms = tuple(dict.fromkeys(_tokenize(query)))  # distinct content terms
        terms = _expand(q_terms)  # + synonyms for scoring recall
        cert_blob = re.sub(r"[^a-z0-9]", "", query.lower())
        corpus = self._docs()
        # IDF is computed over the whole catalog so a query's defining terms count even
        # when scoped to one course (a spurious in-course keyword still can't ground).
        idf = _idf_weights(q_terms, corpus)
        pool = corpus
        if catalog_id:
            # Scoped to one course: stay scoped (never silently widen to the whole
            # catalog and cite another course's modules in this one's answer).
            pool = tuple(d for d in pool if d.course_id == catalog_id)
        scored = sorted(
            ((d, _score(terms, d, cert_blob)) for d in pool), key=lambda ds: ds[1], reverse=True
        )
        # Score floor + IDF relevance floor: a single spurious keyword hit on a multi-term
        # query (only "key" in "quantum cryptography lattice key exchange") is rejected
        # rather than asserted as coverage (A1).
        kept = [
            (d, s)
            for d, s in scored
            if s >= _MIN_SCORE and _relevance_ok(q_terms, d, idf, cert_blob)
        ]
        if not kept:
            return ()
        # Keep only matches near the top score so weak, generic hits don't pose as
        # grounding — credibility of the "sources" panel depends on this.
        cutoff = max(_MIN_SCORE, kept[0][1] * _RELATIVE_CUTOFF)
        near_top = [d for d, s in kept if s >= cutoff]
        # Course cap: ground in the single most-relevant course, not a sprawl across
        # unrelated courses presented as if they jointly answer the question (A5).
        top_course = near_top[0].course_id
        return tuple(d for d in near_top if d.course_id == top_course)

    def search(
        self, query: str, *, catalog_id: str | None = None, k: int = _TOP_K
    ) -> list[GroundingSource]:
        """Top-k module sources backing an answer to ``query`` (cited by module id)."""
        ranked = self._ranked(query, catalog_id)[:k]
        return [
            GroundingSource(
                ref=d.ref,
                title=f"{d.course_title}: {d.title}",
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
