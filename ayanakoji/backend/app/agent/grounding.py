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

from app.agent.contracts import CourseSuggestion, GroundingSource, TraceStep
from app.catalog.loader import default_catalog_path
from app.config import Settings, get_settings

# Honest provider labels — what *actually* retrieved the sources, surfaced in the trace.
# The offline lexical backend mirrors the Foundry IQ knowledge base's index; the live
# adapter (``grounding_azure``) flips these to the Azure agentic-retrieve labels.
LEXICAL_PROVIDER = "Foundry-IQ-pattern · offline lexical retrieval"

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
# Relevance floor (A1): a course only grounds an answer if the query terms its modules
# match carry enough of the query's *specificity*. Specificity is IDF-weighted, so
# matching a rare topical term (functions, pipelines) is strong, while matching only a
# generic term ("key") while the query's defining terms (quantum, cryptography, lattice)
# are absent from the whole catalog is weak — that single spurious hit is rejected, not
# asserted as coverage. A cert-code match (e.g. "DP-203") is exempt: it is strong
# grounding. The gate is a property of the *chosen candidate set* (the best course's
# matching modules), not an independent per-term filter — so it can neither invert the
# ranking (drop a top-scored course while admitting a near-zero one) nor be cleared by a
# single low-IDF word that brushes one off-topic module.
_MIN_IDF_COVERAGE = 0.33
# Absolute IDF mass a single matched term must carry — a generic high-frequency word
# (low IDF) cannot reach this on its own, so it can't ground a multi-term query alone.
_MIN_MATCHED_IDF = 3.0
# A query with ≥2 content terms whose chosen course matches only ONE of them grounds
# only when that term is genuinely topical: either it clears the coverage floor with a
# real overlap signal (term recurs / title hit ≥ this), or the overlap score is strong
# enough on its own (the course is unambiguously about that term, e.g. CI/CD pipelines).
_SINGLE_TERM_MIN_SCORE = 3
_SINGLE_TERM_STRONG_SCORE = 10
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
    "training": ("train",),  # inflection: "model training" reaches modules about training/trained
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


@dataclass(frozen=True)
class RetrievalActivity:
    """How a set of grounding sources was retrieved — the query plan, surfaced in the trace.

    The lexical backend reports its IDF-weighted keyword plan; the live Azure adapter
    reports the agentic-retrieve plan (LLM-decomposed subqueries + reranker scores). Both
    fill the same shape so the pipeline trace renders ``include_activity`` either way.
    """

    provider: str  # honest label of what retrieved the sources
    live: bool  # True only when a live Azure AI Search call produced this
    steps: tuple[TraceStep, ...] = ()


@dataclass(frozen=True)
class RetrievalResult:
    """Grounding sources plus the retrieval activity (query plan) that produced them."""

    sources: list[GroundingSource]
    activity: RetrievalActivity


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

    ``_KEEP_SHORT`` 2-letter topics ("ci", "cd", "ai", "ml", "db") match EXACTLY — the
    ``[a-z]{0,2}`` suffix would let "ci" hit "cite"/"city" and so ground "ci/cd" on an
    unrelated RAG module while the real CI/CD course is dropped. Real plurals for these
    are reached via the synonym map, not by accidental prefixing.
    """
    suffix = "" if term in _KEEP_SHORT else r"[a-z]{0,2}"
    return re.compile(r"\b" + re.escape(term) + suffix + r"\b")


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


def _course_relevance_ok(
    q_terms: tuple[str, ...],
    course_docs: tuple[GroundingDoc, ...],
    idf: dict[str, float],
    cert_blob: str,
) -> bool:
    """True if the *chosen course* clears the IDF-weighted relevance floor.

    The gate is a property of the candidate set (one course's matching modules), not an
    independent per-module filter — so it cannot drop a top-scored course while admitting
    a near-zero one (A1 wrong_course). It rejects three false-grounding shapes:

      * a single low-IDF generic word ("best", "table") brushing one off-topic module —
        below the absolute matched-IDF floor;
      * a multi-term query whose defining terms are catalog-absent and that matches only
        one term ("quantum…key") — below the coverage floor;
      * a single matched term that is not the course's actual subject (incidental "alert"
        in a security module) — passes only if it recurs / hits a title (real overlap
        score) or the score is strong on its own.

    A cert-code match (e.g. "DP-203") is authoritative and exempt.
    """
    if any((ck := _cert_key(d)) and ck in cert_blob for d in course_docs):
        return True
    total = sum(idf.values())
    if total <= 0:
        return False

    # Distinct query terms this course matches anywhere (topical breadth), and the
    # single best module's matched-IDF mass (topical depth on one module).
    matched_terms = {t for t in q_terms for d in course_docs if _term_in(t, d)}
    coverage = sum(idf[t] for t in matched_terms) / total
    best_doc_idf = max(
        (sum(idf[t] for t in q_terms if _term_in(t, d)) for d in course_docs),
        default=0.0,
    )
    if best_doc_idf < _MIN_MATCHED_IDF:
        return False

    n_content = len(q_terms)
    # Single content term ("data", "identity"): coverage is 1.0 by construction; the
    # absolute-IDF floor above already rejects a too-generic lone term.
    if n_content <= 1:
        return coverage >= _MIN_IDF_COVERAGE
    # ≥2 content terms, course matches ≥2 of them: ordinary coverage floor.
    if len(matched_terms) >= 2:
        return coverage >= _MIN_IDF_COVERAGE
    # ≥2 content terms but only ONE matched: require genuine topical signal so a lone
    # brush can't pose as coverage. Couple to the overlap score — measured on the RAW
    # query terms (no synonym expansion) so it reflects how strongly the course is about
    # *that* term (recurrence + course-title hits), not synonym recall.
    top_score = max((_score(q_terms, d, cert_blob) for d in course_docs), default=0)
    if top_score >= _SINGLE_TERM_STRONG_SCORE:
        return True
    return coverage >= _MIN_IDF_COVERAGE and top_score >= _SINGLE_TERM_MIN_SCORE


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
        scored = [(d, s) for d in pool if (s := _score(terms, d, cert_blob)) >= _MIN_SCORE]
        if not scored:
            return ()

        # Choose the grounding course by topical FIT, not raw keyword frequency: prefer a
        # cert match, then the course matching the most distinct *query terms* (breadth),
        # then the highest overlap score (depth). This couples course selection to the
        # relevance signal so a keyword-spam single-term course (e.g. "db" repeated) can't
        # outrank a course that actually matches partition+throughput, and a spurious
        # "ci"→"cite" hit can't displace the real CI/CD course (A1 wrong_course).
        def _course_terms(course_id: str) -> int:
            cds = [d for d, _ in scored if d.course_id == course_id]
            return len({t for t in q_terms for d in cds if _term_in(t, d)})

        def _course_top_score(course_id: str) -> int:
            return max(s for d, s in scored if d.course_id == course_id)

        def _course_has_cert(course_id: str) -> bool:
            return bool(cert_blob) and any(
                (ck := _cert_key(d)) and ck in cert_blob
                for d, _ in scored
                if d.course_id == course_id
            )

        course_ids = {d.course_id for d, _ in scored}
        top_course = max(
            course_ids,
            key=lambda c: (_course_has_cert(c), _course_terms(c), _course_top_score(c)),
        )
        course_docs = tuple(d for d, _ in scored if d.course_id == top_course)

        # Candidate-set relevance gate (A1): the chosen course's matching modules must
        # collectively clear the IDF coverage / matched-IDF / topical-score floors. A
        # single low-IDF generic word, or a multi-term query whose defining terms are
        # catalog-absent, is rejected rather than asserted as coverage.
        if not _course_relevance_ok(q_terms, course_docs, idf, cert_blob):
            return ()

        # Within the grounding course, keep only modules near its top score so weak,
        # generic hits don't pad the "sources" panel.
        ranked = sorted(
            ((d, _score(terms, d, cert_blob)) for d in course_docs),
            key=lambda ds: ds[1],
            reverse=True,
        )
        cutoff = max(_MIN_SCORE, ranked[0][1] * _RELATIVE_CUTOFF)
        return tuple(d for d, s in ranked if s >= cutoff)

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

    def retrieve(
        self, query: str, *, catalog_id: str | None = None, k: int = _TOP_K
    ) -> RetrievalResult:
        """Top-k sources for ``query`` plus the lexical query-plan activity (for the trace).

        Same retrieval as :meth:`search`, but it also reports *how* it retrieved — the
        content terms it planned on, any synonym expansion, and the IDF-weighted overlap
        scores of the chosen modules — so the pipeline trace surfaces the offline
        retrieval's reasoning, the way the live agentic-retrieve adapter surfaces its
        LLM-planned subqueries.
        """
        ranked = self._ranked(query, catalog_id)[:k]
        sources = [
            GroundingSource(
                ref=d.ref,
                title=f"{d.course_title}: {d.title}",
                snippet=d.snippet,
                kind="course",
            )
            for d in ranked
        ]
        return RetrievalResult(sources=sources, activity=self._lexical_activity(query, ranked))

    def _lexical_activity(self, query: str, ranked: tuple[GroundingDoc, ...]) -> RetrievalActivity:
        """Build the lexical query-plan trace for ``query`` over its retrieved ``ranked`` docs."""
        q_terms = tuple(dict.fromkeys(_tokenize(query)))
        terms = _expand(q_terms)
        cert_blob = re.sub(r"[^a-z0-9]", "", query.lower())
        synonyms = tuple(t for t in terms if t not in q_terms)
        plan = ", ".join(q_terms) or "(no content terms)"
        plan_detail = f"{len(q_terms)} content term(s): {plan}"
        if synonyms:
            plan_detail += f"  ·  +synonyms: {', '.join(synonyms)}"
        steps = [
            TraceStep(
                label="Query plan · lexical",
                passed=True,
                detail=plan_detail,
                model="lexical",
            )
        ]
        if ranked:
            top = ranked[0]
            scored = ", ".join(f"{d.ref}={_score(terms, d, cert_blob)}" for d in ranked)
            steps.append(
                TraceStep(
                    label="IDF-weighted keyword overlap",
                    passed=True,
                    detail=(
                        f"Top course '{top.course_title}' ({top.cert or 'no cert'}); "
                        f"module overlap scores: {scored}"
                    ),
                    model="lexical",
                )
            )
        else:
            steps.append(
                TraceStep(
                    label="IDF-weighted keyword overlap",
                    passed=False,
                    detail="No module cleared the relevance floor",
                    model="lexical",
                )
            )
        return RetrievalActivity(provider=LEXICAL_PROVIDER, live=False, steps=tuple(steps))

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
