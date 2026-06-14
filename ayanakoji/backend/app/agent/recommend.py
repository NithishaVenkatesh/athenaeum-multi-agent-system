"""Deterministic course recommendation, the natural next course for a learner.

Given the learner's profile (vertical + target cert from Work IQ) and the courses
they have already taken, rank the catalog's course ladder and return the courses
they should choose next: prereq-satisfied first, foundational → advanced. Pure
functions over the catalog graph (no LLM), the recommendation is auditable and
reproducible (master-plan A-104); an agent only narrates it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.agent.contracts import CourseSuggestion, TakenCourse
from app.catalog.loader import default_catalog_path
from app.config import Settings, get_settings

_DEFAULT_K = 3

# Topic keywords → catalog vertical, so "data science" recommends data courses
# (respecting what the learner ASKED for, not just their profile default).
_VERTICAL_KEYWORDS: dict[str, tuple[str, ...]] = {
    "data-engineering": (
        " data ",  # space-padded so it matches the standalone word, not "database"
        " analytics ",
        "data engineering",
        "data science",
        "data analytics",
        "data pipeline",
        "lakehouse",
        "etl",
        "spark",
        "fabric",
        "synapse",
        "dp-203",
        "dp-700",
        "warehouse",
    ),
    "ai-ml": (
        "ai-ml",
        "machine learning",
        "artificial intelligence",
        "deep learning",
        "ai-102",
        "cognitive",
        "openai",
        "ml model",
        " ai ",
        " ml ",
    ),
    "devops-platform": (
        "devops",
        "ci/cd",
        "cicd",
        "platform engineering",
        "pipelines",
        "az-400",
        "kubernetes",
        "gitops",
        "release",
    ),
    "architecture-security": (
        "architecture",
        "security",
        "az-305",
        "sc-100",
        "zero trust",
        "governance",
        "identity",
        "infrastructure design",
    ),
    "cloud-backend": (
        "cloud",
        "backend",
        "app service",
        "azure functions",
        "cosmos",
        "az-204",
        "serverless",
        "web api",
    ),
}


def verticals_from_text(text: str) -> list[str]:
    """Every catalog vertical a message is about, best match first (may be empty).

    A multi-topic ask ("data and AI") names more than one track; returning all of
    them lets the recommender span them instead of collapsing to a single guess.
    """
    lowered = f" {text.lower()} "
    scores = {
        vertical: sum(1 for kw in keywords if kw in lowered)
        for vertical, keywords in _VERTICAL_KEYWORDS.items()
    }
    hits = [(v, s) for v, s in scores.items() if s > 0]
    return [v for v, _ in sorted(hits, key=lambda vs: vs[1], reverse=True)]


@lru_cache(maxsize=8)
def _catalog_vertical_ids(catalog_path: str) -> frozenset[str]:
    """The authoritative set of real vertical ids in the catalog graph."""
    return frozenset(n.vertical for n in _load_graph(catalog_path))


def vertical_ids(settings: Settings | None = None) -> frozenset[str]:
    """The real catalog vertical id set, the allow-list any classifier is validated against."""
    settings = settings or get_settings()
    path = str(settings.athenaeum_catalog_path or default_catalog_path())
    return _catalog_vertical_ids(path)


# Grounded classify of a recommendation ask into the catalog's vertical vocabulary.
# This is the ROBUST replacement for keyword-negation regex: the model reads the
# sentence (including "anything EXCEPT X", "not anything to do with Y") and returns
# which tracks the learner WANTS vs. wants EXCLUDED, by id, from a fixed allow-list.
# Every id is validated against the real vertical set before use, so a hallucinated
# track can never leak in; an unparseable / empty reply degrades to no constraint.
_CLASSIFY_SYSTEM = (
    "You map a learner's course request onto a FIXED set of Azure learning tracks. "
    "Each track is given as `track-id: description`. You MUST copy the track-id EXACTLY "
    "as written (the slug before the colon, e.g. 'data-engineering'); never output a "
    "certification code, a description word, or any id not in the list.\n"
    "WANTED: a track the learner wants to learn (e.g. 'a data engineering course', "
    "'get into machine learning'). If they ask for 'the next X course', X is WANTED.\n"
    "EXCLUDED: a track the learner rejects as a WHOLE TOPIC (e.g. 'anything except "
    "security', 'not anything to do with data engineering', 'no devops', 'I'm not "
    "interested in architecture'). Put its track-id in `excluded`.\n"
    "CRITICAL: rejecting one SPECIFIC course, or a course they already finished "
    "('not the storage one I already did', 'not the foundations course'), is NOT a "
    "topic exclusion: do NOT exclude that course's track. Only exclude a track when the "
    "learner rejects the entire subject area. A track they did not clearly mention "
    "belongs in NEITHER list. Never list the same track as both wanted and excluded.\n"
    'Reply ONLY with JSON: {"wanted": [track-ids], "excluded": [track-ids]}.'
)


@dataclass(frozen=True)
class VerticalIntent:
    """Tracks a learner wants vs. explicitly excluded, both validated to real ids."""

    wanted: tuple[str, ...]
    excluded: tuple[str, ...]


def _track_catalogue(ids: frozenset[str]) -> str:
    """A stable id→human-label listing the classifier chooses from.

    Labels are plain topic words only, no certification codes: a cert code like
    'DP-203' in the label gets echoed back as a fake "id" by weaker FAST models,
    which then fails id-validation and silently drops the constraint.
    """
    label = {
        "cloud-backend": "cloud and backend development (app service, functions, serverless)",
        "devops-platform": "devops and platform engineering (ci/cd, pipelines, kubernetes)",
        "data-engineering": "data engineering and analytics (lakehouse, etl, data pipelines)",
        "ai-ml": "ai and machine learning",
        "architecture-security": "cloud solution architecture and security (governance, identity)",
    }
    return "\n".join(f"- {vid}: {label.get(vid, vid)}" for vid in sorted(ids))


def classify_vertical_intent(
    text: str,
    *,
    router: object | None = None,
    settings: Settings | None = None,
) -> VerticalIntent:
    """Grounded LLM classify of wanted/excluded tracks, validated to real vertical ids.

    Offline or with no router, returns an empty intent so the deterministic
    keyword path stays in charge. Any provider/parse failure also degrades to
    empty (fail-open to the normal recommendation, never a crash). The returned
    ids are intersected with the real vertical set, so nothing outside the
    catalog can ever be honored as wanted or excluded.
    """
    settings = settings or get_settings()
    real_ids = vertical_ids(settings)
    if settings.llm_offline or router is None or not text.strip():
        return VerticalIntent(wanted=(), excluded=())
    from app.agent.llm import Capability  # local import: offline CI lacks the SDK

    catalogue = _track_catalogue(real_ids)
    try:
        result = router.complete(  # type: ignore[attr-defined]
            Capability.FAST,
            [
                {"role": "system", "content": _CLASSIFY_SYSTEM},
                {
                    "role": "user",
                    "content": f"TRACKS:\n{catalogue}\n\nLEARNER REQUEST:\n{text}",
                },
            ],
            json_mode=True,
            max_tokens=160,
        )
        data = json.loads(result.text)
        wanted = tuple(v for v in data.get("wanted", []) if v in real_ids)
        excluded = tuple(v for v in data.get("excluded", []) if v in real_ids)
        # A track can't be both wanted and excluded; exclusion wins (the learner
        # said NO to it explicitly, which is the higher-signal constraint).
        wanted = tuple(v for v in wanted if v not in excluded)
        return VerticalIntent(wanted=wanted, excluded=excluded)
    except Exception:  # noqa: BLE001 — classify is best-effort; degrade to no constraint
        return VerticalIntent(wanted=(), excluded=())


def vertical_from_text(text: str) -> str | None:
    """The single best catalog vertical a message is about, or None if unspecific."""
    ranked = verticals_from_text(text)
    return ranked[0] if ranked else None


@dataclass(frozen=True)
class CatalogNode:
    """One course in the catalog ladder, with the ordering + prereq edges."""

    id: str
    title: str
    summary: str
    level: str
    order: int
    vertical: str
    vertical_title: str
    cert: str
    prereq_course_ids: tuple[str, ...]
    module_titles: tuple[str, ...]


@lru_cache(maxsize=8)
def _vertical_for_cert(catalog_path: str, cert: str) -> str | None:
    """Catalog vertical whose primary cert matches ``cert`` (AZ-305 → architecture-security)."""
    if not cert:
        return None
    needle = cert.lower()
    for node in _load_graph(catalog_path):
        # Vertical certs can be compound ("AZ-305 + SC-100"), match on containment.
        if node.cert and needle in node.cert.lower():
            return node.vertical
    return None


@lru_cache(maxsize=8)
def _load_graph(catalog_path: str) -> tuple[CatalogNode, ...]:
    data = json.loads(Path(catalog_path).read_text(encoding="utf-8"))
    nodes: list[CatalogNode] = []
    for vertical in data["verticals"]:
        for course in vertical["courses"]:
            nodes.append(
                CatalogNode(
                    id=course["id"],
                    title=course["title"],
                    summary=course["summary"],
                    level=course.get("level", ""),
                    order=course.get("order", 0),
                    vertical=vertical["id"],
                    vertical_title=vertical["title"],
                    cert=vertical.get("primary_cert", ""),
                    prereq_course_ids=tuple(course.get("prereq_course_ids", [])),
                    module_titles=tuple(m["title"] for m in course.get("modules", [])),
                )
            )
    return tuple(nodes)


def _to_suggestion(node: CatalogNode, reason: str) -> CourseSuggestion:
    return CourseSuggestion(
        catalog_id=node.id,
        title=node.title,
        cert=node.cert,
        level=node.level,
        pitch=node.summary,
        reason=reason,
        prep_points=list(node.module_titles[:4]),
    )


def recommend_overview(
    taken: list[TakenCourse] | None = None, settings: Settings | None = None
) -> list[CourseSuggestion]:
    """One choosable, *not-yet-registered* course per vertical (the platform breadth).

    Answers "what verticals / tracks / courses exist" with one course per track.
    Courses the learner has already registered (linked to another chat) are
    skipped, so the breadth list never re-offers something they're already on;
    a vertical whose courses are all registered drops out entirely.
    """
    settings = settings or get_settings()
    path = str(settings.athenaeum_catalog_path or default_catalog_path())
    graph = _load_graph(path)
    taken_ids = {t.catalog_id for t in (taken or [])}
    chosen: dict[str, CatalogNode] = {}
    for node in sorted(graph, key=lambda n: (n.vertical, n.order)):
        if node.id in taken_ids or node.vertical in chosen:
            continue
        chosen[node.vertical] = node
    return [
        _to_suggestion(
            node,
            f"Start of the {node.vertical_title} track."
            if node.level == "foundational"
            else f"The next course in the {node.vertical_title} track.",
        )
        for node in chosen.values()
    ]


# Generic words in course titles that don't identify a specific course on their own.
_COURSE_STOPWORDS = frozenset(
    {
        "and",
        "for",
        "the",
        "with",
        "your",
        "from",
        "into",
        "course",
        "courses",
        "class",
        "module",
        "track",
        "cert",
        "certification",
        "want",
        "take",
        "start",
        "open",
        "continue",
        "resume",
        "please",
        "azure",
    }
)


def _title_tokens(title: str) -> frozenset[str]:
    """Distinctive lowercase word tokens of a course title (stopwords removed)."""
    words = re.findall(r"[a-z0-9]+", title.lower())
    return frozenset(w for w in words if len(w) >= 3 and w not in _COURSE_STOPWORDS)


@lru_cache(maxsize=8)
def _course_token_index(
    catalog_path: str,
) -> tuple[tuple[tuple[str, frozenset[str]], ...], dict[str, int]]:
    """Per-course title tokens, plus how many courses each token appears in."""
    node_tokens = tuple((n.id, _title_tokens(n.title)) for n in _load_graph(catalog_path))
    freq: dict[str, int] = {}
    for _, toks in node_tokens:
        for t in toks:
            freq[t] = freq.get(t, 0) + 1
    return node_tokens, freq


def course_from_text(text: str, *, settings: Settings | None = None) -> str | None:
    """The specific catalog course a message explicitly names, or None.

    Matches a course id outright, otherwise scores each course by how many of its
    distinctive title tokens the message contains. A single token that is *unique*
    to one course (e.g. "lakehouse", "serverless") is enough; otherwise at least
    two tokens must match, so a vague topic word never resolves to one course.
    Precision-biased: a miss just falls through to normal recommendation.
    """
    settings = settings or get_settings()
    path = str(settings.athenaeum_catalog_path or default_catalog_path())
    lowered = f" {text.lower()} "
    for node in _load_graph(path):
        if node.id in lowered:
            return node.id
    node_tokens, freq = _course_token_index(path)
    best_id: str | None = None
    best_score = 0
    for cid, tokens in node_tokens:
        present = {t for t in tokens if re.search(rf"\b{re.escape(t)}\b", lowered)}
        if not present:
            continue
        unique_hit = any(freq[t] == 1 for t in present)
        if len(present) >= 2 or unique_hit:
            score = len(present) + (10 if unique_hit else 0)
            if score > best_score:
                best_id, best_score = cid, score
    return best_id


def recommend_courses(
    *,
    vertical: str | None,
    target_cert: str = "",
    taken: list[TakenCourse],
    role_title: str = "",
    k: int = _DEFAULT_K,
    exclude_verticals: frozenset[str] | None = None,
    settings: Settings | None = None,
) -> list[CourseSuggestion]:
    """The next courses a learner should choose, best first.

    The candidate pool spans the learner's *current* vertical and the vertical of
    their *target* certification (often different, e.g. on AZ-204, targeting
    AZ-305), so a learner mid-career sees real choices across both tracks. A course
    counts as *completed* when its status is negative (passed). The natural next is
    the lowest-order untaken course whose prereqs are all completed; if none
    qualify (mid-ladder gaps), fall back to the earliest untaken so there is always
    something to offer.

    ``exclude_verticals`` are tracks the learner explicitly does NOT want; every
    course in them is removed from the candidate pool *deterministically*, so an
    exclusion is honored even when it is the requested/target vertical. The
    subtraction is pure (covers the offline path too).
    """
    settings = settings or get_settings()
    path = str(settings.athenaeum_catalog_path or default_catalog_path())
    graph = _load_graph(path)
    excluded = exclude_verticals or frozenset()

    taken_ids = {t.catalog_id for t in taken}
    completed_ids = {t.catalog_id for t in taken if t.passed}
    # A prereq is "satisfied" once it's passed OR already enrolled in. A course is
    # only ``passed`` once every module's tests are cleared, so keying eligibility
    # only on "passed" would freeze the ladder; enrolled prereqs unlock the next.
    satisfied_ids = completed_ids | taken_ids

    # Pool spans the current vertical + the target-cert vertical (priority-ordered),
    # minus any explicitly-excluded track (the negation constraint, applied first).
    target_vertical = _vertical_for_cert(path, target_cert)
    verticals = [v for v in (vertical, target_vertical) if v and v not in excluded]
    priority = {v: i for i, v in enumerate(dict.fromkeys(verticals))}
    scoped = [n for n in graph if n.vertical in priority]
    # If the requested/target tracks were all excluded, widen to the whole catalog
    # (still minus the excluded tracks) so an honest alternative is offered.
    fallback = [n for n in graph if n.vertical not in excluded]
    pool = [n for n in (scoped or fallback) if n.id not in taken_ids and n.vertical not in excluded]
    if not pool:
        return []

    def rank_key(n: CatalogNode) -> tuple[int, int, str]:
        return (priority.get(n.vertical, 99), n.order, n.id)

    def next_step_reason(n: CatalogNode) -> str:
        suffix = f" for a {role_title}" if role_title else ""
        return f"Next step in the {n.vertical_title} track{suffix}."

    eligible = [n for n in pool if all(p in satisfied_ids for p in n.prereq_course_ids)]
    if eligible:
        ranked = sorted(eligible, key=rank_key)
        return [_to_suggestion(n, next_step_reason(n)) for n in ranked[:k]]

    # Mid-ladder gaps: offer the earliest untaken courses to get back on track.
    ranked = sorted(pool, key=rank_key)
    return [
        _to_suggestion(n, f"A solid next course in the {n.vertical_title} track.")
        for n in ranked[:k]
    ]
