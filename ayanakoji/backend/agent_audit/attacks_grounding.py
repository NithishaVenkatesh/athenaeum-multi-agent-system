"""Live red-team battery for the grounding layer (app.agent.grounding).

The grounding backend is a deterministic IDF-weighted keyword retrieval over the
Athenaeum catalog's module-level objectives. It has no LLM, but it runs LIVE: the
router and the answer agents cite whatever it returns, so a FALSE grounding here is
the seed of downstream fabrication — an answer that "grounds" an off-catalog
question on an unrelated module is a hallucination with a fake citation attached.

This battery attacks the *retrieval algorithm itself*, with a STRUCTURAL oracle
(no judge needed — the algorithm is deterministic):

  * FALSE grounding (crit): off-catalog / nonsense queries must return ``[]``.
    A returned ref means the layer asserted coverage it does not have.
  * Cross-course sprawl (high): every returned ref must belong to ONE course.
  * catalog_id scoping (crit): a scoped search must return ONLY that course.
  * False negative (high): genuine in-catalog topics must return non-empty.
  * Correct course (high): an in-catalog topic must ground in the RIGHT course,
    not a spuriously-matched unrelated one.
  * Robustness (med): pathological inputs (10k chars, emoji, empty, SQL/HTML
    junk) must not crash — and junk must not ground.

Oracle facts come straight from the real catalog id set, so the battery can never
drift from the source of truth. ``passed=True`` means NO undesired behavior.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache

from app.agent.grounding import get_grounding
from app.catalog.loader import default_catalog_path

from agent_audit.harness import CaseResult, live_settings

LAYER = "grounding"


# ── Catalog oracle (the source of truth for valid ids / course membership) ──────


@lru_cache(maxsize=1)
def _catalog() -> dict:
    return json.loads(default_catalog_path().read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _valid_module_ids() -> frozenset[str]:
    ids: set[str] = set()
    for vertical in _catalog()["verticals"]:
        for course in vertical["courses"]:
            for module in course.get("modules", []):
                ids.add(module["id"])
    return frozenset(ids)


@lru_cache(maxsize=1)
def _module_to_course() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for vertical in _catalog()["verticals"]:
        for course in vertical["courses"]:
            for module in course.get("modules", []):
                mapping[module["id"]] = course["id"]
    return mapping


def _course_of(ref: str) -> str:
    """The catalog course a returned ref belongs to (authoritative, not parsed)."""
    return _module_to_course().get(ref, f"<unknown:{ref}>")


def _courses(refs: list[str]) -> set[str]:
    return {_course_of(r) for r in refs}


def _invalid(refs: list[str]) -> list[str]:
    return [r for r in refs if r not in _valid_module_ids()]


# ── Case model ──────────────────────────────────────────────────────────────────

# What an oracle expects of the returned source set.
EMPTY = "empty"  # must return no sources (off-catalog / junk)
NONEMPTY = "nonempty"  # must return at least one source (real topic)
ONE_COURSE = "one_course"  # may return sources, but all from a single course
NOCRASH = "nocrash"  # must not raise (and, if anything, not be invalid)


@dataclass(frozen=True)
class GroundingCase:
    case_id: str
    category: str
    query: str
    expect: str
    severity: str = "high"
    catalog_id: str | None = None
    # For ONE_COURSE/NONEMPTY: if set, the single grounding course must be this one.
    must_be_course: str | None = None
    k: int = 4


# ── Attacks ──────────────────────────────────────────────────────────────────────

# FALSE grounding: clearly off-catalog. Any source returned is a fabricated citation.
# Several of these are multi-term queries whose *defining* terms (football, climate,
# running) are absent from the whole catalog and that only brush a single generic
# word ("best", "change") in one module — the retrieval must reject the brush.
_FALSE_GROUNDING: tuple[GroundingCase, ...] = (
    GroundingCase("bake_sourdough", "false_grounding", "how to bake sourdough bread", EMPTY, "crit"),
    GroundingCase(
        "quantum_keyex", "false_grounding", "quantum teleportation key exchange", EMPTY, "crit"
    ),
    GroundingCase(
        "football_transfers", "false_grounding", "best football transfers", EMPTY, "crit"
    ),
    GroundingCase("running_shoes", "false_grounding", "the best running shoes", EMPTY, "crit"),
    GroundingCase("climate_change", "false_grounding", "climate change effects", EMPTY, "crit"),
    GroundingCase("lorem_ipsum", "false_grounding", "lorem ipsum dolor sit amet", EMPTY, "crit"),
    GroundingCase(
        "roman_empire", "false_grounding", "the history of the roman empire", EMPTY, "crit"
    ),
    GroundingCase(
        "monetary_policy",
        "false_grounding",
        "explain the monetary policy of the european central bank",
        EMPTY,
        "crit",
    ),
)

# Cross-course sprawl: a broad generic word must not span unrelated courses. We allow
# it to ground (it is a real term) but ALL refs must come from one course.
_SPRAWL: tuple[GroundingCase, ...] = (
    GroundingCase("broad_data", "cross_course_sprawl", "data", ONE_COURSE, "high", k=8),
    GroundingCase("broad_security", "cross_course_sprawl", "security", ONE_COURSE, "high", k=8),
    GroundingCase("broad_design", "cross_course_sprawl", "design", ONE_COURSE, "high", k=8),
    GroundingCase("broad_identity", "cross_course_sprawl", "identity", ONE_COURSE, "high", k=8),
    GroundingCase(
        "broad_storage_pipelines",
        "cross_course_sprawl",
        "storage pipelines security model",
        ONE_COURSE,
        "high",
        k=8,
    ),
)

# catalog_id scoping: a locked chat must NEVER cite another course's modules.
_SCOPING: tuple[GroundingCase, ...] = (
    GroundingCase(
        "scope_identity_cb01",
        "scoping_leak",
        "identity",
        ONE_COURSE,
        "crit",
        catalog_id="cb-c01",
        must_be_course="cb-c01",
    ),
    GroundingCase(
        # A query whose best global match lives in another course must still not
        # leak into the scoped course (returns [] or only cb-c01 — never de-c03).
        "scope_streaming_cb01",
        "scoping_leak",
        "real-time streaming analytics",
        ONE_COURSE,
        "crit",
        catalog_id="cb-c01",
        must_be_course="cb-c01",
    ),
    GroundingCase(
        "scope_offcatalog_cb01",
        "scoping_leak",
        "best football transfers",
        EMPTY,
        "crit",
        catalog_id="cb-c01",
    ),
)

# False NEGATIVE: real in-catalog topics must still ground.
_FALSE_NEGATIVE: tuple[GroundingCase, ...] = (
    GroundingCase("fn_functions", "false_negative", "azure functions triggers", NONEMPTY, "high"),
    GroundingCase(
        "fn_cosmos", "false_negative", "cosmos db partition keys and throughput", NONEMPTY, "high"
    ),
    GroundingCase("fn_certcode", "false_negative", "AZ-204", NONEMPTY, "high"),
    GroundingCase("fn_zerotrust", "false_negative", "zero trust security architecture", NONEMPTY),
    GroundingCase("fn_vision", "false_negative", "computer vision image analysis", NONEMPTY),
)

# CORRECT course: an in-catalog topic must ground in the right course, not a
# spuriously-matched unrelated one (regression guard for the ci→"cite" defect).
_CORRECT_COURSE: tuple[GroundingCase, ...] = (
    GroundingCase(
        "right_cicd",
        "wrong_course",
        "ci/cd pipelines",
        NONEMPTY,
        "high",
        must_be_course="do-c02",  # CI/CD Pipelines & Release Engineering
    ),
    GroundingCase(
        "right_functions",
        "wrong_course",
        "azure functions triggers and bindings",
        NONEMPTY,
        "high",
        must_be_course="cb-c01",  # Azure Compute & Serverless Foundations
    ),
)

# Robustness: pathological inputs must not crash, and pure junk must not ground.
_ROBUSTNESS: tuple[GroundingCase, ...] = (
    GroundingCase("rb_empty", "robustness", "", EMPTY, "med"),
    GroundingCase("rb_spaces", "robustness", "       ", EMPTY, "med"),
    GroundingCase("rb_punct", "robustness", "!@#$%^&*()_+-=[]{};:,.<>?", EMPTY, "med"),
    GroundingCase("rb_emoji", "robustness", "🎉🔥💯😀🚀🧪", EMPTY, "med"),
    GroundingCase("rb_unicode", "robustness", "日本語のテスト بالعربية", EMPTY, "med"),
    GroundingCase("rb_sql", "false_grounding", "'; DROP TABLE modules; --", EMPTY, "high"),
    GroundingCase("rb_html", "false_grounding", "<script>alert(1)</script>", EMPTY, "high"),
    GroundingCase("rb_huge_junk", "robustness", "zzqxv " * 2000, NOCRASH, "med"),
    GroundingCase("rb_huge_real", "robustness", "azure functions " * 1500, NOCRASH, "med"),
)


_ALL: tuple[GroundingCase, ...] = (
    *_FALSE_GROUNDING,
    *_SPRAWL,
    *_SCOPING,
    *_FALSE_NEGATIVE,
    *_CORRECT_COURSE,
    *_ROBUSTNESS,
)


# ── Oracle ────────────────────────────────────────────────────────────────────────


def _evaluate(case: GroundingCase, refs: list[str]) -> tuple[bool, str]:
    """Apply the structural oracle. Returns (passed, detail)."""
    invalid = _invalid(refs)
    if invalid:
        return False, f"returned ids not in the catalog: {invalid}"
    courses = _courses(refs)

    if case.expect == EMPTY:
        if refs:
            return False, f"FALSE grounding: off-catalog query returned {refs} ({courses})"
        return True, "no sources (correct)"

    if case.expect == NONEMPTY:
        if not refs:
            return False, "FALSE NEGATIVE: real in-catalog topic returned no sources"
        if case.must_be_course and courses != {case.must_be_course}:
            return False, (
                f"WRONG/sprawled course: expected only {case.must_be_course!r}, got {courses}"
            )
        return True, f"grounded in {courses}"

    if case.expect == ONE_COURSE:
        if len(courses) > 1:
            return False, f"cross-course sprawl: refs span {courses}"
        if case.must_be_course and courses and courses != {case.must_be_course}:
            return False, f"scope leak: expected {case.must_be_course!r}, got {courses}"
        return True, f"single course {courses or '∅'}"

    if case.expect == NOCRASH:
        # Reaching here means search() did not raise. Any returned ids were already
        # validated above; that is sufficient for the robustness contract.
        return True, f"no crash ({len(refs)} refs from {courses or '∅'})"

    return False, f"unknown expectation {case.expect!r}"


def _run_case(case: GroundingCase) -> CaseResult:
    # Bind the live settings/catalog path the prod backend uses.
    live_settings()
    g = get_grounding()
    try:
        sources = g.search(case.query, catalog_id=case.catalog_id, k=case.k)
        # suggest() shares the same _ranked() core; assert it agrees so a false
        # grounding can't slip through the suggestion surface either.
        suggestion = g.suggest(case.query, catalog_id=case.catalog_id)
    except Exception as exc:  # noqa: BLE001 — a crash IS the finding for robustness cases
        return CaseResult(
            case_id=case.case_id,
            category=case.category,
            passed=False,
            detail=f"search()/suggest() raised: {type(exc).__name__}: {exc}",
            severity=case.severity,
            error=True,
            observed=repr(case.query[:80]),
        )

    refs = [s.ref for s in sources]
    passed, detail = _evaluate(case, refs)

    # Cross-check the suggestion surface for EMPTY cases: it must also abstain.
    if passed and case.expect == EMPTY and suggestion is not None:
        passed = False
        detail = (
            f"FALSE suggestion: suggest() offered course {suggestion.catalog_id!r} "
            f"for off-catalog/junk query"
        )

    observed = (
        f"refs={refs} courses={sorted(_courses(refs))} "
        f"suggest={getattr(suggestion, 'catalog_id', None)}"
    )
    return CaseResult(
        case_id=case.case_id,
        category=case.category,
        passed=passed,
        detail=detail,
        severity=case.severity,
        observed=observed,
    )


def run() -> list[CaseResult]:
    """Run the full grounding battery once against the live deterministic backend."""
    return [_run_case(c) for c in _ALL]
