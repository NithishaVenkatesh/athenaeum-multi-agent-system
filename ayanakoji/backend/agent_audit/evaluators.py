"""#28 — Custom code evaluators.

An ``azure-ai-evaluation`` *custom code evaluator* is just a callable that returns a
0..1 score (plus a pass/fail and a reason). These formalize the deterministic oracles
the red-team batteries already use into reusable scorers that:

- run **standalone** today (no SDK, no network, no live model), and
- drop straight into ``azure.ai.evaluation.evaluate(...)`` or a cloud eval over traces
  once the ``foundry`` extra (``azure-ai-evaluation``) is installed — the protocol is
  "a callable returning a dict", which these satisfy.

The intrinsic scorers (citation / number groundedness) reuse the **production guards**
(``app.agent.guards``), so they score the real honesty logic, not a copy of it.

Batch usage when the SDK is present::

    from azure.ai.evaluation import evaluate
    from agent_audit.evaluators import CitationGroundednessEvaluator, ExactMatchEvaluator
    evaluate(
        data="datasets/answers.jsonl",
        evaluators={
            "citation": CitationGroundednessEvaluator(),
            "route": ExactMatchEvaluator(key="route"),
        },
    )

Each JSONL column is passed to ``__call__`` as a keyword argument. Run this module
directly (``python -m agent_audit.evaluators``) for a dependency-free self-test.
"""

from __future__ import annotations

from collections.abc import Iterable
from difflib import SequenceMatcher
from typing import Any

# Default pass threshold for continuous scorers; binary scorers pass at 1.0.
_PASS = 0.999


def _result(score: float, threshold: float = _PASS) -> str:
    return "pass" if score >= threshold else "fail"


class ExactMatchEvaluator:
    """1.0 iff the response equals the ground truth (case-insensitive, trimmed).

    Generic decision scorer — used for layer outputs that are a single label
    (router route, gate blocked-bool). Reads the ``response`` and ``ground_truth``
    columns, or a configured ``key`` column against ``ground_truth``.
    """

    def __init__(self, key: str = "response", *, case_sensitive: bool = False) -> None:
        self._key = key
        self._cs = case_sensitive

    def __call__(self, *, ground_truth: Any = None, **columns: Any) -> dict:
        observed = columns.get(self._key, columns.get("response"))
        a, b = str(observed), str(ground_truth)
        if not self._cs:
            a, b = a.lower().strip(), b.lower().strip()
        score = 1.0 if a == b else 0.0
        return {
            "exact_match": score,
            "exact_match_result": _result(score),
            "exact_match_reason": f"observed={observed!r} ground_truth={ground_truth!r}",
        }


class CitationGroundednessEvaluator:
    """1.0 iff the response cites no module id outside the allowed grounding sources.

    Reuses the production citation guard (``app.agent.guards.unknown_citations``), so a
    fabricated/phantom module id — bracketed, bare, or obfuscated — scores 0.0. Allowed
    ids come from ``allowed_refs`` (list of ids) or a ``context`` list of sources.
    """

    def __call__(
        self,
        *,
        response: str = "",
        allowed_refs: Iterable[str] | None = None,
        context: Any = None,
        **_: Any,
    ) -> dict:
        from app.agent.guards import unknown_citations

        allowed = list(allowed_refs or [])
        if not allowed and context:
            allowed = _refs_from_context(context)
        bad = unknown_citations(response, allowed)
        score = 0.0 if bad else 1.0
        reason = "no ungrounded citations" if not bad else f"phantom ids: {sorted(bad)}"
        return {
            "citation_groundedness": score,
            "citation_groundedness_result": _result(score),
            "citation_groundedness_reason": reason,
        }


class NumberGroundednessEvaluator:
    """1.0 iff every number in the response traces to an allowed value.

    Reuses ``app.agent.guards.ungrounded_numbers``. ``allowed_numbers`` is the set of
    figures the deterministic plan/source actually computed (strings or numbers).
    """

    def __call__(
        self,
        *,
        response: str = "",
        allowed_numbers: Iterable[Any] | None = None,
        **_: Any,
    ) -> dict:
        from app.agent.guards import numbers_in, ungrounded_numbers

        allowed: set[str] = set()
        for value in allowed_numbers or []:
            allowed |= numbers_in(str(value))
        bad = ungrounded_numbers(response, allowed)
        score = 0.0 if bad else 1.0
        reason = "all figures grounded" if not bad else f"ungrounded numbers: {sorted(bad)}"
        return {
            "number_groundedness": score,
            "number_groundedness_result": _result(score),
            "number_groundedness_reason": reason,
        }


class FuzzyMatchEvaluator:
    """Similarity of response to ground truth (rapidfuzz if available, else difflib).

    For domain string matching where exact match is too strict (paraphrase, casing,
    punctuation). Pass when similarity >= ``threshold``.
    """

    def __init__(self, threshold: float = 0.85) -> None:
        self._threshold = threshold

    def __call__(self, *, response: str = "", ground_truth: str = "", **_: Any) -> dict:
        score = _similarity(str(response), str(ground_truth))
        return {
            "fuzzy_match": round(score, 4),
            "fuzzy_match_result": _result(score, self._threshold),
            "fuzzy_match_reason": f"similarity={score:.3f} threshold={self._threshold}",
        }


def _similarity(a: str, b: str) -> float:
    try:
        from rapidfuzz import fuzz  # optional; faster + better

        return fuzz.ratio(a, b) / 100.0
    except ImportError:
        return SequenceMatcher(None, a, b).ratio()


def _refs_from_context(context: Any) -> list[str]:
    """Extract module ids from a context list of sources (dicts or objects with .ref)."""
    refs: list[str] = []
    for item in context or []:
        ref = item.get("ref") if isinstance(item, dict) else getattr(item, "ref", None)
        if ref:
            refs.append(str(ref))
    return refs


# ── Dependency-free self-test (no SDK, no network, no live model) ───────────────────


def run_self_test() -> bool:
    """Exercise each evaluator on known inputs; return True iff all behave correctly."""
    checks: list[tuple[str, bool]] = []

    em = ExactMatchEvaluator(key="route")
    checks.append(
        ("exact_match_hit", em(route="foundry_iq", ground_truth="foundry_iq")["exact_match"] == 1.0)
    )
    checks.append(
        ("exact_match_miss", em(route="general", ground_truth="foundry_iq")["exact_match"] == 0.0)
    )

    cg = CitationGroundednessEvaluator()
    checks.append(
        (
            "citation_clean",
            cg(response="As covered in [cb-c01-m01].", allowed_refs=["cb-c01-m01"])[
                "citation_groundedness"
            ]
            == 1.0,
        )
    )
    checks.append(
        (
            "citation_phantom",
            cg(response="As covered in cb-c99-m99.", allowed_refs=["cb-c01-m01"])[
                "citation_groundedness"
            ]
            == 0.0,
        )
    )

    ng = NumberGroundednessEvaluator()
    checks.append(
        (
            "number_clean",
            ng(response="Study 3 hours over 2 weeks.", allowed_numbers=[3, 2])[
                "number_groundedness"
            ]
            == 1.0,
        )
    )
    checks.append(
        (
            "number_ungrounded",
            ng(response="Study 5 hours.", allowed_numbers=[3])["number_groundedness"] == 0.0,
        )
    )

    fz = FuzzyMatchEvaluator(threshold=0.7)
    checks.append(
        ("fuzzy_hit", fz(response="AZ-204 study plan", ground_truth="az 204 study plan")[
            "fuzzy_match_result"
        ] == "pass")
    )
    checks.append(
        ("fuzzy_miss", fz(response="cosmos db", ground_truth="kubernetes networking")[
            "fuzzy_match_result"
        ] == "fail")
    )

    ok = all(passed for _, passed in checks)
    for label, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {label}")
    print(f"\n== evaluators self-test: {sum(p for _, p in checks)}/{len(checks)} ==")
    return ok


if __name__ == "__main__":
    import sys

    sys.exit(0 if run_self_test() else 1)
